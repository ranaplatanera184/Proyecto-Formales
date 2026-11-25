# ============================================================================
# GESTOR DE REGLAS - ORQUESTADOR DEL COMPILADOR DE CIRCUITOS
# ----------------------------------------------------------------------------
# Carga las reglas del lenguaje desde reglas.json (compuertas, palabras
# reservadas y comandos del menú) y coordina las fases del compilador:
# léxico -> sintáctico -> semántico. Además gestiona la salida del análisis
# (tokens, orden topológico, tabla de verdad, expresiones y diagrama).
# ============================================================================

import json
import logging
import os
import sys
import traceback

from rutas import cargar_reglas, ubicar_reglas

from ImplementacionAnalisisLexico import analizar_lexico
from AnalisisSintactico import AnalisisSintactico
from ast_jace import arbol_ascii
from ir import generar_ir
from optimizador import informe as informe_optimizador
from backends import verilog
from semantico import AnalizadorSemantico, generar_dot
from expresiones import generar_expresiones
import schematico

from schematico import RUTA_DIAGRAMA_SVG, RUTA_DIAGRAMA_PNG
from schematico import FONDO, normalizar_color
import diagnosticos as diag

RUTA_REPORTE = "reporte_circuito.txt"

# Máximo de entradas para calcular la tabla de verdad completa en /analizar
# (2^14 = 16.384 filas). Por encima se omite y se pide por bloques con la
# ruta /tabla. Se puede cambiar con la variable de entorno JACE_LIMITE_TABLA.
registro = logging.getLogger("jace")


def _entero_de_entorno(nombre, por_defecto):
    """Entero de una variable de entorno; un valor inválido no impide arrancar."""
    valor = os.environ.get(nombre)
    if valor is None:
        return por_defecto
    try:
        return int(valor)
    except ValueError:
        registro.warning("%s=%r no es un número: se usa %s", nombre, valor, por_defecto)
        return por_defecto


LIMITE_TABLA = _entero_de_entorno("JACE_LIMITE_TABLA", 14)

# Además del número de entradas, la tabla completa se omite si tendría más
# celdas (filas × columnas) que esto: con 14 entradas y 200 compuertas la
# respuesta pasaba de 9 MB.
LIMITE_CELDAS = 2 ** 18

# El diagrama esquemático se omite en circuitos muy grandes (schemdraw tarda
# decenas de segundos y produce SVG de varios MB). Se cuentan compuertas y
# conexiones (pines de entrada).
LIMITE_DIAGRAMA_COMPUERTAS = _entero_de_entorno("JACE_LIMITE_DIAGRAMA", 300)
LIMITE_DIAGRAMA_PINES = 4 * LIMITE_DIAGRAMA_COMPUERTAS


def normalizar_texto(texto):
    """Texto listo para analizar, sin cambiar los números de línea.

    - Se quita la marca BOM que el Bloc de notas pone al guardar en UTF-8.
    - Los finales de línea \r\n y \r (Mac antiguo) pasan a \n, como hace el
      editor de la web, para que las líneas coincidan en los dos lados.
    - Solo se recorta el final: quitar líneas del principio correría los
      números de línea que se muestran en los errores.
    """
    texto = (texto or "").lstrip("\ufeff")
    return texto.replace("\r\n", "\n").replace("\r", "\n").rstrip()


def mensaje_error_interno(error):
    """Texto entendible para un fallo del propio compilador (no del circuito)."""
    detalle = str(error) or type(error).__name__
    return (f"{type(error).__name__}: {detalle}. "
            "Es un fallo del compilador, no de tu circuito: por favor repórtalo")


class GestorReglas:

    def __init__(self, ruta=None, almacenamiento=None):
        self.reglas = cargar_reglas(ruta)
        self.almacenamiento = almacenamiento
        # Último análisis exitoso, para que el comando EXPRESIONES pueda
        # reimprimirlo sin pedir el circuito otra vez.
        self.ultimo_resultado = None
        # Analizador semántico del último circuito válido (para /tabla).
        self._semantico = None

    @staticmethod
    def _ubicar_reglas(ruta=None):
        """Ruta de reglas.json (se delega en rutas.py, el único punto que la
        resuelve, también dentro del ejecutable de PyInstaller)."""
        return ubicar_reglas(ruta)

    # ------------------------------------------------------------------
    # Reglas cargadas desde reglas.json
    # ------------------------------------------------------------------
    def obtener_nombres_compuertas(self):
        """Nombres de las compuertas permitidas (definidos en reglas.json)."""
        return [c["nombre"] for c in self.reglas.get("compuertas", [])]

    def obtener_palabras_reservadas(self):
        """Palabras reservadas del lenguaje (definidas en reglas.json)."""
        return set(self.reglas.get("palabras_reservadas", []))

    def obtener_comando(self, palabra):
        """Devuelve la definición del comando pedido o None si no existe."""
        for comando in self.reglas.get("comandos", []):
            if palabra in comando["palabras"]:
                return comando
        return None

    def es_comando(self, palabra):
        return self.obtener_comando(palabra) is not None

    # ------------------------------------------------------------------
    # Fases del compilador: análisis completo de un circuito
    # ------------------------------------------------------------------
    def analizar(self, texto, imprimir=True, fondo=FONDO, escribir_archivos=False,
                  con_diagrama=True, registrar=True, con_resultados=True,
                  limite_tabla=None):
        """Ejecuta las fases léxica, sintáctica y semántica sobre un circuito.

        Devuelve un diccionario con el resultado (tokens, errores, orden
        topológico, tabla de verdad, expresiones y diagrama DOT).

        El texto se analiza tal cual llega (sin borrar líneas vacías ni
        comentarios) para que los números de línea de los errores coincidan
        siempre con el archivo original.

        `fondo` es el color de fondo del diagrama esquemático (el esquema se
        adapta solo a fondos claros u oscuros). `escribir_archivos=False`
        (valor por defecto) devuelve el SVG en memoria sin escribir PNG/SVG en
        el disco; solo se escribe si el llamador lo pide expresamente.
        `con_diagrama=False` se salta el dibujo del circuito y el DOT (para
        validar rápido). `con_resultados=False` se detiene después de las
        comprobaciones semánticas, sin calcular tabla de verdad ni expresiones
        (lo usa la validación mientras se escribe en la web). `registrar=False`
        no añade el análisis al historial. `limite_tabla` es el máximo de
        entradas para calcular la tabla completa (por defecto LIMITE_TABLA).

        Nunca lanza excepciones: un fallo interno se devuelve como un
        diagnóstico de la fase "interno" y se registra en el log.
        """
        try:
            resultado = self._analizar(
                texto, fondo, escribir_archivos, con_diagrama, con_resultados,
                LIMITE_TABLA if limite_tabla is None else limite_tabla)
        except Exception as error:  # fallo del compilador, no del circuito
            registro.error("Error interno al analizar el circuito: %r", error)
            if os.environ.get("JACE_DEBUG") == "1":
                traceback.print_exc()
            resultado = self._resultado_vacio()
            resultado["texto"] = normalizar_texto(texto)
            fallo = diag.Diagnostico("interno", "error", None, None,
                                     mensaje_error_interno(error))
            resultado["errores"] = [fallo.texto()]
            resultado["diagnosticos"] = [fallo.to_json()]

        # Registro en el historial (entrada, resultado, errores y expresiones).
        if self.almacenamiento is not None and registrar:
            self.almacenamiento.agregar_analisis(
                resultado["texto"], resultado["exito"], resultado["errores"],
                resultado["expresiones_booleanas"])

        if imprimir:
            if resultado["exito"]:
                self._imprimir_resultado(resultado, escribir_archivos, con_diagrama)
            else:
                self._imprimir_errores(resultado["errores"], resultado["advertencias"],
                                       resultado["diagnosticos"])

        # Solo el último análisis exitoso se recuerda para el comando EXPRESIONES:
        # un circuito con errores no deja expresiones que mostrar.
        if resultado["exito"]:
            self.ultimo_resultado = resultado

        return resultado

    def preparar_evaluacion(self, texto):
        """Valida el circuito y devuelve (analizador semántico, resultado).

        El analizador es None si el circuito tiene errores. Lo usan las rutas
        que evalúan filas sueltas (/tabla) sin repetir todo el análisis.
        """
        resultado = self.analizar(texto, imprimir=False, con_diagrama=False,
                                  registrar=False, con_resultados=False)
        semantico = self._semantico if resultado["exito"] else None
        return semantico, resultado

    @staticmethod
    def _resultado_vacio():
        return {
            "exito": False,
            "errores": [],
            "diagnosticos": [],
            "tokens": [],
            "entradas": [],
            "compuertas": [],
            "ast": None,
            "tabla_simbolos": [],
            "advertencias": [],
            "orden_topologico": [],
            "tabla_verdad": {"señales": [], "filas": []},
            "tabla_omitida": None,
            "expresiones": [],
            "expresiones_booleanas": {},
            "diagrama_dot": "",
            "diagrama_svg": "",
            "texto": "",
            "arbol_ascii": "",
            "salidas": [],
            "salidas_declaradas": None,
            "temporales": [],
            "ir": [],
            "optimizacion": None,
            "verilog": None,
            "diagrama_omitido": None,
        }

    def _analizar(self, texto, fondo, escribir_archivos, con_diagrama,
                  con_resultados, limite_tabla):
        # Solo se recorta el final: quitar líneas del principio correría los
        # números de línea que se muestran en los errores.
        texto = normalizar_texto(texto)
        fondo = normalizar_color(fondo) or FONDO
        resultado = self._resultado_vacio()
        resultado["texto"] = texto

        diagnosticos = []
        tokens = []
        estructura = None

        if not texto:
            diagnosticos.append(diag.error(
                "léxico", 1, 1, "el circuito está vacío",
                "escribe un circuito que empiece con ENTRADA[...]"))
        else:
            # 1. FASE LEXICA. Los lexemas inválidos dejan un comodín para que
            #    la fase sintáctica pueda revisar el resto del archivo.
            tokens, tokens_parser, errores_lexicos = analizar_lexico(
                texto, palabras_reservadas=self.obtener_palabras_reservadas())

            # 2. FASE SINTACTICA (con recuperación de errores). Los errores
            #    léxicos y sintácticos se reportan juntos, por posición.
            parser = AnalisisSintactico(tokens_parser, gestorReglas=self)
            estructura, errores_sintacticos = parser.analizar()
            diagnosticos.extend(sorted(errores_lexicos + errores_sintacticos,
                                       key=lambda d: (d.linea or 0, d.columna or 0)))
            if errores_lexicos or errores_sintacticos:
                estructura = None
            else:
                # AST tipado ({tipo, valor, linea, columna, hijos}).
                resultado["ast"] = estructura["arbol"].a_json()
                resultado["arbol_ascii"] = arbol_ascii(estructura["arbol"])

        resultado["tokens"] = [t.to_json() for t in tokens]

        # 3. FASE SEMANTICA y EVALUACION.
        self._semantico = None
        if estructura is not None:
            resultado["entradas"] = estructura["entradas"]
            resultado["compuertas"] = estructura["compuertas"]
            semantico = AnalizadorSemantico(
                estructura["entradas"],
                estructura["compuertas"],
                self.reglas["compuertas"],
                linea_entrada=estructura["linea_entrada"],
                pos_entradas=estructura.get("pos_entradas"),
                salidas_declaradas=estructura.get("salidas_declaradas"),
                pos_salidas=estructura.get("pos_salidas"))
            resultado["salidas_declaradas"] = estructura.get("salidas_declaradas")
            resultado["salidas"] = semantico.salidas_finales()
            resultado["temporales"] = semantico.temporales()
            resultado["tabla_simbolos"] = semantico.tabla_simbolos()
            errores_semanticos = semantico.diagnosticos()
            diagnosticos.extend(errores_semanticos)
            diagnosticos.extend(semantico.diagnosticos_advertencia())

            if not errores_semanticos:
                # La validación rápida (con_resultados=False) termina aquí:
                # calcular la tabla de verdad de 2^n filas con cada tecla
                # congelaba la interfaz en circuitos medianos.
                if con_resultados:
                    self._calcular_resultados(resultado, semantico, estructura,
                                              fondo, escribir_archivos,
                                              con_diagrama, limite_tabla)
                resultado["exito"] = True
                self._semantico = semantico

        resultado["diagnosticos"] = [d.to_json() for d in diagnosticos]
        resultado["errores"] = [d.texto() for d in diagnosticos if d.es_error]
        resultado["advertencias"] = [d.texto() for d in diagnosticos if not d.es_error]
        return resultado

    def _calcular_resultados(self, resultado, semantico, estructura, fondo,
                             escribir_archivos, con_diagrama, limite_tabla):
        """Orden, tabla (si cabe), expresiones y diagrama de un circuito válido."""
        resultado["orden_topologico"] = semantico.orden_topologico()

        total_entradas = len(estructura["entradas"])
        celdas = 2 ** total_entradas * len(semantico.senales_tabla())
        if total_entradas <= limite_tabla and celdas <= LIMITE_CELDAS:
            resultado["tabla_verdad"] = semantico.tabla_verdad()
        else:
            # 2^n filas no caben en una respuesta: se omite y la web las pide
            # por bloques a la ruta /tabla.
            filas = 2 ** total_entradas
            resultado["tabla_verdad"] = {"señales": semantico.senales_tabla(),
                                         "filas": []}
            if total_entradas > limite_tabla:
                motivo = (f"El circuito tiene {total_entradas} entradas: la tabla "
                          f"completa tendría {filas:,} filas (el límite para "
                          f"calcularla de una vez es {limite_tabla} entradas)")
            else:
                motivo = (f"La tabla completa tendría {filas:,} filas × "
                          f"{len(semantico.senales_tabla())} columnas = {celdas:,} "
                          f"celdas (el límite es {LIMITE_CELDAS:,})")
            resultado["tabla_omitida"] = {
                "motivo": motivo.replace(",", "."),
                "filas_totales": filas,
                "limite_entradas": limite_tabla,
            }

        # Código intermedio, optimización y backend Verilog.
        codigo_intermedio = generar_ir(semantico)
        resultado["ir"] = [i.a_json() for i in codigo_intermedio]
        informe_optimizacion, optimizado = informe_optimizador(
            codigo_intermedio, resultado["salidas"], estructura["entradas"])
        resultado["optimizacion"] = informe_optimizacion
        entradas_unicas = list(dict.fromkeys(estructura["entradas"]))
        resultado["verilog"] = {
            "modulo": verilog.generar_modulo(optimizado, entradas_unicas,
                                             resultado["salidas"]),
            "testbench": (verilog.generar_testbench(entradas_unicas, resultado["salidas"])
                          if total_entradas <= limite_tabla else None),
            "aviso_testbench": (None if total_entradas <= limite_tabla else
                                f"Sin testbench: recorrería 2^{total_entradas} "
                                f"combinaciones (límite {limite_tabla} entradas)"),
        }

        resultado["expresiones"] = [
            {"salida": salida, "expresion": expresion}
            for salida, expresion in semantico.expresiones_booleanas()
        ]
        # Expresiones en forma intermedia y expandida, en las dos
        # notaciones. Es texto, así que no necesita el diagrama.
        simbolos = generar_expresiones(semantico)
        ascii_ = generar_expresiones(semantico, "ascii")
        resultado["expresiones_booleanas"] = {
            salida: {
                "intermedia": datos["intermedia"],
                "expandida": datos["expandida"],
                "aviso": datos["aviso"],
                "intermedia_ascii": ascii_[salida]["intermedia"],
                "expandida_ascii": ascii_[salida]["expandida"],
            }
            for salida, datos in simbolos.items()
        }
        # Diagrama esquemático (SchemDraw) y DOT de respaldo.
        # con_diagrama=False permite validar sin dibujar nada.
        compuertas_total = len(estructura["compuertas"])
        pines = sum(len(c["entradas"]) for c in estructura["compuertas"])
        if con_diagrama and (compuertas_total > LIMITE_DIAGRAMA_COMPUERTAS
                             or pines > LIMITE_DIAGRAMA_PINES):
            resultado["diagrama_omitido"] = {
                "motivo": (f"El circuito tiene {compuertas_total} compuertas y {pines} "
                           f"conexiones: el diagrama se dibuja hasta "
                           f"{LIMITE_DIAGRAMA_COMPUERTAS} compuertas y "
                           f"{LIMITE_DIAGRAMA_PINES} conexiones"),
            }
        elif con_diagrama:
            # Las constantes usadas se dibujan como terminales de entrada.
            constantes = [c for c in ("0", "1")
                          if any(c in g["entradas"] for g in estructura["compuertas"])]
            # Toda señal que no alimenta nada recibe un terminal de salida
            # (también las de compuertas muertas, para que se vean).
            usadas = {s for g in estructura["compuertas"] for s in g["entradas"]}
            salidas_dibujo = list(dict.fromkeys(
                resultado["salidas"] + [g["salida"] for g in estructura["compuertas"]
                                        if g["salida"] not in usadas]))
            circuito = schematico.generar_diagrama(
                estructura["entradas"] + constantes, estructura["compuertas"],
                fondo=fondo, salidas=salidas_dibujo)
            resultado["diagrama_dot"] = generar_dot(estructura["entradas"],
                                                    estructura["compuertas"])
            resultado["diagrama_svg"] = schematico.exportar(
                circuito, escribir_archivos=escribir_archivos)

    def _imprimir_resultado(self, resultado, escribir_archivos=False, con_diagrama=True):
        texto = resultado["texto"]
        tokens = resultado["tokens"]
        ast = resultado["ast"]
        tabla_simbolos = resultado["tabla_simbolos"]
        advertencias = resultado["advertencias"]
        expresiones_booleanas = resultado["expresiones_booleanas"]
        orden = resultado["orden_topologico"]
        tabla = resultado["tabla_verdad"]
        print("\n=== ANÁLISIS DE CIRCUITO ===")

        print("\n== ENTRADA ==")
        for linea in texto.split("\n"):
            print(f"  {linea}")

        # Salida 1: lista de tokens reconocidos (con línea y columna).
        print("\n== TOKENS RECONOCIDOS ==")
        for token in tokens:
            print(f"  {token['token']:26} {token['valor']!r:20} "
                  f"(línea {token['linea']}, columna {token['columna']})")

        # Fase 2: árbol sintáctico generado por el parser.
        # El JSON del árbol solo se exporta desde la web; aquí, árbol ASCII.
        print("\n== ÁRBOL SINTÁCTICO (AST) ==")
        print(resultado["arbol_ascii"])

        # Fase 3: tabla de símbolos y posiciones de uso.
        print("\n== TABLA DE SÍMBOLOS ==")
        for simbolo in tabla_simbolos or []:
            usos = ", ".join(str(linea) for linea in simbolo["lineas_uso"]) or "—"
            print(f"  {simbolo['senal']}: {simbolo['tipo']}, "
                  f"declarada en línea {simbolo['linea_declaracion']}, usos: {usos}")

        # Fase 4: advertencias semánticas que no invalidan el circuito.
        print("\n== ADVERTENCIAS ==")
        for d in resultado["diagnosticos"]:
            if d["severidad"] == "advertencia":
                print(f"  - {diag.Diagnostico(**d).texto_con_sugerencia()}")

        # Fase 5: representación intermedia, en orden topológico.
        print("\n== CÓDIGO INTERMEDIO ==")
        ancho = max((len(i["destino"]) for i in resultado["ir"]), default=0)
        for instruccion in resultado["ir"]:
            print(f"  {instruccion['destino'].ljust(ancho)} = {instruccion['operacion']} "
                  f"{', '.join(instruccion['argumentos'])}")
        print("\n== CÓDIGO OPTIMIZADO ==")
        for instruccion in resultado["optimizacion"]["ir_optimizado"]:
            print(f"  {instruccion['texto']}")

        print("\n== EXPRESIONES ==")
        for salida, datos in (expresiones_booleanas or {}).items():
            print(f"  {salida}:")
            for linea in datos["intermedia"]:
                print(f"    {linea}")
            print(f"    Expandida: {datos['expandida'] or datos['aviso']}")

        print("\n== ORDEN DE EVALUACIÓN (TOPOLÓGICO) ==")
        for i, compuerta in enumerate(orden, start=1):
            entradas = ", ".join(compuerta["entradas"])
            print(f"  {i}. {compuerta['compuerta']}[{entradas}] -> {compuerta['salida']}")

        # Fase 6: tabla de verdad y diagrama.
        print("\n== TABLA DE VERDAD ==")
        if resultado.get("tabla_omitida"):
            print(f"  {resultado['tabla_omitida']['motivo']}.")
        # Las temporales (_t1...) se ocultan, como en la web.
        visibles = [i for i, senal in enumerate(tabla["señales"])
                    if senal not in set(resultado["temporales"])]
        tabla = {"señales": [tabla["señales"][i] for i in visibles],
                 "filas": [[fila[i] for i in visibles] for fila in tabla["filas"]]}
        cabecera = " | ".join(tabla["señales"])
        print(f"  {cabecera}")
        print("  " + "-" * max(len(cabecera), 1))
        for fila in tabla["filas"]:
            print("  " + " | ".join(str(valor) for valor in fila))

        # El diagrama se deja al final junto con la tabla de resultados.
        self._generar_diagrama(escribir_archivos, con_diagrama)

        print("\nANÁLISIS EXITOSO")

    def _imprimir_errores(self, errores, advertencias=None, diagnosticos=None):
        """Errores y advertencias, con la sugerencia de cada uno si la hay."""
        if diagnosticos is not None:
            errores = [diag.Diagnostico(**d).texto_con_sugerencia()
                       for d in diagnosticos if d["severidad"] == "error"]
            advertencias = [diag.Diagnostico(**d).texto_con_sugerencia()
                            for d in diagnosticos if d["severidad"] == "advertencia"]
        print("\nERRORES DEL ANÁLISIS:")
        for error in errores:
            print(f"  - {error}")
        if advertencias:
            print("\nADVERTENCIAS:")
            for advertencia in advertencias:
                print(f"  - {advertencia}")
        print("\nEl circuito NO es válido.")

    def _generar_diagrama(self, escribir_archivos=True, con_diagrama=True):
        """Informa de los archivos del diagrama (exportados por schematico)."""
        print("\n== DIAGRAMA ==")
        if not con_diagrama:
            print("  No se generó el diagrama (validación sin dibujo).")
        elif not escribir_archivos:
            print("  SVG generado en memoria (no se escribieron archivos).")
            print("  Use --guardar para escribir el SVG y el PNG en el disco.")
        elif os.path.isfile(RUTA_DIAGRAMA_SVG) and os.path.isfile(RUTA_DIAGRAMA_PNG):
            print(f"  SVG generado: {RUTA_DIAGRAMA_SVG}")
            print(f"  PNG generado (dpi=200): {RUTA_DIAGRAMA_PNG}")
        else:
            print("  No se pudo generar el diagrama.")

    # ------------------------------------------------------------------
    # Comandos del menú (definidos en reglas.json)
    # ------------------------------------------------------------------
    def ejecutar(self, operacion):
        """Despacha la ejecución de un comando del menú."""
        comando = self.obtener_comando(operacion)
        if comando is None:
            raise SyntaxError(f"Error sintáctico línea 1: comando no reconocido '{operacion}'")

        tipo = comando["tipo"]

        if tipo == "analizar":
            return self._ejecutar_analizar()
        elif tipo == "mostrar":
            return self._ejecutar_mostrar(comando)
        elif tipo == "exportar":
            return self._ejecutar_exportar()
        elif tipo == "expresiones":
            return self._ejecutar_expresiones()
        elif tipo == "ayuda":
            return self._ejecutar_ayuda()
        elif tipo == "salir":
            return self._ejecutar_salir()
        else:
            raise SyntaxError(f"Error sintáctico línea 1: tipo de comando desconocido '{tipo}'")

    def _ejecutar_analizar(self):
        """ANALIZAR: solicita el circuito por consola (varias líneas) y lo analiza."""
        print("\n=== ANÁLISIS DE CIRCUITO ===")
        print("Ingrese el circuito (presione ENTER en una línea vacía para terminar):")

        lineas = []
        while True:
            try:
                linea = input()
            except EOFError:
                break
            if linea.strip() == "":
                break
            # Los comentarios se conservan: la fase léxica los ignora y así
            # los números de línea siguen coincidiendo con lo que se escribió.
            lineas.append(linea)

        texto = "\n".join(lineas)
        if not texto.strip():
            print("No se ingresó ningún circuito.")
            return None

        self.analizar(texto, imprimir=True)
        return None

    def _ejecutar_mostrar(self, comando):
        """HISTORIAL: muestra todos los análisis registrados."""
        if self.almacenamiento is None:
            print("No hay almacenamiento disponible")
            return None

        historial = self.almacenamiento.obtener_historial()
        if not historial:
            print("No hay análisis en el historial")
            return None

        print("HISTORIAL DE ANÁLISIS:")
        for i, analisis in enumerate(historial, start=1):
            estado = "EXITOSO" if analisis["resultado"] else "ERRORES"
            primera_linea = analisis["entrada"].split("\n")[0] if analisis["entrada"] else "(vacío)"
            print(f"  {i}. [{estado}] {primera_linea} ({len(analisis['errores'])} errores)")
        return None

    def _ejecutar_exportar(self):
        """EXPORTAR: genera un reporte .txt con el último análisis."""
        if self.almacenamiento is None:
            print("No hay almacenamiento disponible")
            return None

        ruta = self.almacenamiento.exportar_reporte_txt(RUTA_REPORTE)
        if ruta is None:
            print("No hay análisis para exportar (historial vacío)")
        else:
            print(f"Reporte exportado a: {ruta}")
        return None

    def _ejecutar_expresiones(self):
        """EXPRESIONES: reimprime las expresiones del último análisis exitoso."""
        resultado = self.ultimo_resultado
        if resultado is None:
            print("No hay análisis para mostrar. Use ANALIZAR primero.")
            return None

        for salida, datos in resultado["expresiones_booleanas"].items():
            print(f"\n== EXPRESIONES DE {salida} ==")

            print("\n  Forma intermedia (símbolos):")
            for linea in datos["intermedia"]:
                print(f"    {linea}")
            print("\n  Forma intermedia (ASCII):")
            for linea in datos["intermedia_ascii"]:
                print(f"    {linea}")

            print("\n  Forma expandida (símbolos):")
            print(f"    {datos['expandida']}" if datos["expandida"]
                  else f"    {datos['aviso']}")

            print("\n  Forma expandida (ASCII):")
            print(f"    {datos['expandida_ascii']}" if datos["expandida_ascii"]
                  else f"    {datos['aviso']}")

        return None

    def _ejecutar_ayuda(self):
        """AYUDA: lista los comandos disponibles."""
        print("COMANDOS DISPONIBLES:")
        for comando in self.reglas.get("comandos", []):
            palabras = ", ".join(comando["palabras"])
            descripcion = comando.get("descripcion", "")
            print(f"  {palabras:14} - {descripcion}")
        return None

    def _ejecutar_salir(self):
        """CERRAR: detiene la ejecución del programa."""
        print("Ejecución detenida")
        return False