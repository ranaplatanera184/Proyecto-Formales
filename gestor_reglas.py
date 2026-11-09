# ============================================================================
# GESTOR DE REGLAS - ORQUESTADOR DEL COMPILADOR DE CIRCUITOS
# ----------------------------------------------------------------------------
# Carga las reglas del lenguaje desde reglas.json (compuertas, palabras
# reservadas y comandos del menú) y coordina las fases del compilador:
# léxico -> sintáctico -> semántico. Además gestiona la salida del análisis
# (tokens, orden topológico, tabla de verdad, expresiones y diagrama).
# ============================================================================

import json
import os
import sys

from ImplementacionAnalisisLexico import tokenizar_circuito
from AnalisisSintactico import AnalisisSintactico
from semantico import AnalizadorSemantico, generar_dot
from expresiones import generar_expresiones
import schematico

from schematico import RUTA_DIAGRAMA_SVG, RUTA_DIAGRAMA_PNG
from schematico import FONDO, normalizar_color
RUTA_REPORTE = "reporte_circuito.txt"


class GestorReglas:

    def __init__(self, ruta="reglas.json", almacenamiento=None):
        with open(self._ubicar_reglas(ruta), "r", encoding="utf-8") as archivo:
            self.reglas = json.load(archivo)
        self.almacenamiento = almacenamiento
        # Último análisis exitoso, para que el comando EXPRESIONES pueda
        # reimprimirlo sin pedir el circuito otra vez.
        self.ultimo_resultado = None

    @staticmethod
    def _ubicar_reglas(ruta):
        """Ubica reglas.json aunque el programa se ejecute en otra carpeta.

        Al abrir el ejecutable (jace-app.exe) el archivo viaja dentro del
        propio binario, así que se busca primero en el directorio actual y,
        si no está, junto al programa (o dentro del ejecutable con PyInstaller).
        """
        if os.path.isabs(ruta) or os.path.isfile(ruta):
            return ruta

        base = getattr(sys, "_MEIPASS", None)
        if base is None:
            base = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base, ruta)

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
    def analizar(self, texto, imprimir=True, fondo=FONDO, escribir_archivos=True,
                  con_diagrama=True, registrar=True):
        """Ejecuta las fases léxica, sintáctica y semántica sobre un circuito.

        Devuelve un diccionario con el resultado (tokens, errores, orden
        topológico, tabla de verdad, expresiones y diagrama DOT).

        `fondo` es el color de fondo del diagrama esquemático (el esquema se
        adapta solo a fondos claros u oscuros). `escribir_archivos=False`
        devuelve el SVG sin dejar PNG/SVG en el disco (lo usa la interfaz web).
        `con_diagrama=False` se salta el dibujo del circuito y el DOT (para
        validar rápido) y `registrar=False` no añade el análisis al historial
        (para no llenarlo con validaciones automáticas).
        """
        texto = texto.strip()
        fondo = normalizar_color(fondo) or FONDO

        tokens = []
        errores = []
        estructura = None
        orden = []
        tabla = {"señales": [], "filas": []}
        expresiones = []
        expresiones_booleanas = {}
        dot = ""
        svg = ""
        circuito = None
        exito = False

        if not texto:
            errores.append("Error léxico línea 1: el circuito está vacío")
        else:
            # 1. FASE LEXICA.
            tokens, errores = tokenizar_circuito(
                texto, palabras_reservadas=self.obtener_palabras_reservadas())

            # 2. FASE SINTACTICA.
            if not errores:
                try:
                    parser = AnalisisSintactico(tokens, gestorReglas=self)
                    estructura = parser.construir_circuito()
                except SyntaxError as error:
                    errores.append(str(error))

            # 3. FASE SEMANTICA y EVALUACION.
            if not errores and estructura is not None:
                semantico = AnalizadorSemantico(
                    estructura["entradas"],
                    estructura["compuertas"],
                    self.reglas["compuertas"])
                errores_semanticos = semantico.revisar()
                errores.extend(errores_semanticos)

                if not errores_semanticos:
                    orden = semantico.orden_topologico()
                    tabla = semantico.tabla_verdad()
                    expresiones = [
                        {"salida": salida, "expresion": expresion}
                        for salida, expresion in semantico.expresiones_booleanas()
                    ]
                    # Expresiones en forma intermedia y expandida, en las dos
                    # notaciones. Es texto, así que no necesita el diagrama.
                    simbolos = generar_expresiones(semantico)
                    ascii_ = generar_expresiones(semantico, "ascii")
                    expresiones_booleanas = {
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
                    if con_diagrama:
                        circuito = schematico.generar_diagrama(
                            estructura["entradas"], estructura["compuertas"],
                            fondo=fondo)
                        dot = generar_dot(estructura["entradas"],
                                          estructura["compuertas"])
                        svg = schematico.exportar(
                            circuito, escribir_archivos=escribir_archivos)
                    exito = True

        # Registro en el historial (entrada, resultado, errores y expresiones).
        if self.almacenamiento is not None and registrar:
            self.almacenamiento.agregar_analisis(texto, exito, errores,
                                                 expresiones_booleanas)

        if imprimir:
            if exito:
                self._imprimir_resultado(texto, tokens, estructura, orden, tabla,
                                        expresiones, dot, escribir_archivos,
                                        con_diagrama)
            else:
                self._imprimir_errores(errores)

        resultado = {
            "exito": exito,
            "errores": errores,
            "tokens": [t.to_json() for t in tokens],
            "entradas": estructura["entradas"] if estructura else [],
            "compuertas": estructura["compuertas"] if estructura else [],
            "orden_topologico": orden,
            "tabla_verdad": tabla,
            "expresiones": expresiones,
            "expresiones_booleanas": expresiones_booleanas,
            "diagrama_dot": dot,
            "diagrama_svg": svg,
        }

        # Solo el último análisis exitoso se recuerda para el comando EXPRESIONES:
        # un circuito con errores no deja expresiones que mostrar.
        if exito:
            self.ultimo_resultado = resultado

        return resultado

    def _imprimir_resultado(self, texto, tokens, estructura, orden, tabla, expresiones, dot,
                            escribir_archivos=True, con_diagrama=True):
        print("\n=== ANÁLISIS DE CIRCUITO ===")

        print("\n== ENTRADA ==")
        for linea in texto.split("\n"):
            print(f"  {linea}")

        # Salida 1: lista de tokens reconocidos (con línea y columna).
        print("\n== TOKENS RECONOCIDOS ==")
        for token in tokens:
            print(f"  {token.token:26} {token.valor!r:20} (línea {token.linea}, columna {token.columna})")

        # Salida 2: orden de evaluación (orden topológico).
        print("\n== ORDEN DE EVALUACIÓN (TOPOLÓGICO) ==")
        for i, compuerta in enumerate(orden, start=1):
            entradas = ", ".join(compuerta["entradas"])
            print(f"  {i}. {compuerta['compuerta']}[{entradas}] -> {compuerta['salida']}")

        # Salida 3: tabla de verdad completa con señales intermedias.
        print("\n== TABLA DE VERDAD ==")
        cabecera = " | ".join(tabla["señales"])
        print(f"  {cabecera}")
        print("  " + "-" * max(len(cabecera), 1))
        for fila in tabla["filas"]:
            print("  " + " | ".join(str(valor) for valor in fila))

        # Salida 4: expresión booleana equivalente de cada salida.
        print("\n== EXPRESIÓN BOOLEANA ==")
        for item in expresiones:
            print(f"  {item['salida']} = {item['expresion']}")

        # Salida 5: diagrama (SVG y PNG con el símbolo real de cada compuerta).
        self._generar_diagrama(escribir_archivos, con_diagrama)

        print("\nANÁLISIS EXITOSO")

    def _imprimir_errores(self, errores):
        print("\nERRORES DEL ANÁLISIS:")
        for error in errores:
            print(f"  - {error}")
        print("\nEl circuito NO es válido.")

    def _generar_diagrama(self, escribir_archivos=True, con_diagrama=True):
        """Informa de los archivos del diagrama (exportados por schematico)."""
        print("\n== DIAGRAMA ==")
        if not con_diagrama:
            print("  No se generó el diagrama (validación sin dibujo).")
        elif not escribir_archivos:
            print("  SVG generado en memoria (no se escribieron archivos).")
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
            # Las líneas que empiezan con # son comentarios y se ignoran.
            if linea.strip().startswith("#"):
                continue
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