# ============================================================================
# FASE SEMANTICA Y EVALUACION DEL COMPILADOR DE CIRCUITOS
# ----------------------------------------------------------------------------
# Comprueba las reglas de significado del circuito:
#   1. Aridad de cada compuerta (según reglas.json).
#   2. Una señal no puede definirse dos veces (ni colisionar con una entrada).
#   3. Toda señal usada debe estar definida (como entrada o como salida de
#      alguna compuerta). Se permite referenciar señales definidas después.
#   4. No debe haber ciclos en el grafo de dependencias: se reporta uno por
#      cada componente fuertemente conexa (algoritmo de Tarjan iterativo).
#
# Cada error y advertencia lleva la línea y la columna exactas de la señal o
# la compuerta que lo provoca, y una sugerencia cuando hay una obvia (por
# ejemplo "¿quisiste decir 'z'?" con la distancia de Levenshtein).
#
# Advertencias: entradas sin usar, la misma señal conectada dos veces a una
# compuerta y compuertas muertas (que no llegan a ninguna salida declarada).
#
# Si el circuito es correcto, también calcula:
#   - Orden de evaluación (orden topológico).
#   - Tabla de verdad completa (2^n combinaciones) con señales intermedias.
#   - Expresión booleana equivalente de cada salida.
# ============================================================================

import os
import struct
from collections import deque

import graphviz

from evaluador import Programa, CONSTANTES
from sugerencias import mas_parecido
import diagnosticos as diag


def _orden_posicion(diagnostico):
    """Clave para ordenar diagnósticos por línea y columna."""
    return (diagnostico.linea or 0, diagnostico.columna or 0)


def _componentes_fuertes(nodos, sucesores):
    """Componentes fuertemente conexas (Tarjan, sin recursión)."""
    indice = {}
    bajo = {}
    en_pila = set()
    pila = []
    componentes = []
    contador = 0

    for raiz in nodos:
        if raiz in indice:
            continue
        indice[raiz] = bajo[raiz] = contador
        contador += 1
        pila.append(raiz)
        en_pila.add(raiz)
        trabajo = [(raiz, iter(sucesores[raiz]))]

        while trabajo:
            nodo, vecinos = trabajo[-1]
            avanzo = False
            for vecino in vecinos:
                if vecino not in indice:
                    indice[vecino] = bajo[vecino] = contador
                    contador += 1
                    pila.append(vecino)
                    en_pila.add(vecino)
                    trabajo.append((vecino, iter(sucesores[vecino])))
                    avanzo = True
                    break
                if vecino in en_pila:
                    bajo[nodo] = min(bajo[nodo], indice[vecino])
            if avanzo:
                continue

            trabajo.pop()
            if trabajo:
                padre = trabajo[-1][0]
                bajo[padre] = min(bajo[padre], bajo[nodo])
            if bajo[nodo] == indice[nodo]:
                componente = []
                while True:
                    miembro = pila.pop()
                    en_pila.discard(miembro)
                    componente.append(miembro)
                    if miembro == nodo:
                        break
                componentes.append(componente)

    return componentes


def _camino_de_ciclo(inicio, componente, sucesores):
    """Un ciclo concreto que sale de `inicio` y vuelve a él (búsqueda en anchura)."""
    padre = {inicio: None}
    cola = deque([inicio])
    while cola:
        nodo = cola.popleft()
        for vecino in sucesores[nodo]:
            if vecino == inicio:
                camino = [nodo]
                while padre[camino[-1]] is not None:
                    camino.append(padre[camino[-1]])
                return camino[::-1]
            if vecino in componente and vecino not in padre:
                padre[vecino] = nodo
                cola.append(vecino)
    return [inicio]


# Compuertas negadas que no son asociativas con N entradas.
NO_ASOCIATIVAS = {"NAND", "NOR", "XNOR"}


class AnalizadorSemantico:

    def __init__(self, entradas, compuertas, reglas_compuertas,
                 linea_entrada=1, pos_entradas=None, salidas_declaradas=None,
                 pos_salidas=None):
        # Fase semántica: trabaja sobre la estructura construida por el parser.
        self.entradas = entradas
        self.compuertas = compuertas
        self.linea_entrada = linea_entrada
        # Posición [línea, columna] de cada nombre de ENTRADA[...] (opcional:
        # sin posiciones los mensajes solo llevan la línea).
        self.pos_entradas = pos_entradas
        # Salidas declaradas con SALIDA[...] (None si el circuito no las declara).
        self.salidas_declaradas = salidas_declaradas
        self.pos_salidas = pos_salidas

        # Aridad y operación de cada compuerta provienen de reglas.json.
        self.entradas_min = {}
        self.entradas_max = {}
        self.operacion = {}
        for regla in reglas_compuertas:
            self.entradas_min[regla["nombre"]] = regla["entradas_min"]
            self.entradas_max[regla["nombre"]] = regla["entradas_max"]
            self.operacion[regla["nombre"]] = regla["operacion"]

        # Cachés de un análisis: el orden topológico, el circuito compilado y
        # los diagnósticos.
        self._orden = None
        self._programa = None
        self._errores = None
        self._advertencias = None

    # ------------------------------------------------------------------
    # Posiciones (línea y columna) de cada elemento del circuito
    # ------------------------------------------------------------------
    def _pos_entrada(self, indice):
        if self.pos_entradas and indice < len(self.pos_entradas):
            linea, columna = self.pos_entradas[indice]
            return linea, columna
        return self.linea_entrada, None

    @staticmethod
    def _pos_compuerta(compuerta):
        return compuerta["linea"], compuerta.get("columna")

    @staticmethod
    def _pos_referencia(compuerta, k):
        posiciones = compuerta.get("pos_entradas")
        if posiciones and k < len(posiciones):
            linea, columna = posiciones[k]
            return linea, columna
        return compuerta["linea"], None

    @staticmethod
    def _pos_salida(compuerta):
        posicion = compuerta.get("pos_salida")
        if posicion:
            return posicion[0], posicion[1]
        return compuerta["linea"], None

    # ------------------------------------------------------------------
    # Comprobaciones semánticas
    # ------------------------------------------------------------------
    def revisar(self):
        """Devuelve la lista de errores semánticos (vacía si todo es correcto)."""
        return [d.texto() for d in self.diagnosticos()]

    def advertencias(self):
        """Devuelve advertencias que no invalidan el circuito."""
        return [d.texto() for d in self.diagnosticos_advertencia()]

    def diagnosticos(self):
        """Errores semánticos como objetos Diagnostico, ordenados por posición."""
        if self._errores is None:
            self._errores = sorted(self._calcular_errores(), key=_orden_posicion)
        return self._errores

    def diagnosticos_advertencia(self):
        """Advertencias como objetos Diagnostico, ordenadas por posición."""
        if self._advertencias is None:
            self._advertencias = sorted(self._calcular_advertencias(), key=_orden_posicion)
        return self._advertencias

    def _calcular_errores(self):
        errores = []

        # Una entrada repetida crea una declaración ambigua antes incluso de
        # analizar las conexiones de las compuertas.
        vistas = set()
        for i, senal in enumerate(self.entradas):
            if senal in vistas:
                linea, columna = self._pos_entrada(i)
                errores.append(diag.error(
                    "semántico", linea, columna,
                    f"la entrada {senal} está declarada más de una vez",
                    "borra la repetición en ENTRADA[...]"))
            vistas.add(senal)

        # 1. Aridad de las compuertas.
        for compuerta in self.compuertas:
            nombre = compuerta["compuerta"]
            n = len(compuerta["entradas"])
            minimo = self.entradas_min.get(nombre, 1)
            maximo = self.entradas_max.get(nombre, 0)
            linea, columna = self._pos_compuerta(compuerta)

            if minimo == maximo and maximo > 0 and n != minimo:
                errores.append(diag.error(
                    "semántico", linea, columna,
                    f"la compuerta {nombre} requiere exactamente {minimo} entrada(s) "
                    f"y recibió {n}",
                    "NOT invierte una sola señal; para varias usa NAND o NOR"
                    if nombre == "NOT" else None))
            elif n < minimo:
                errores.append(diag.error(
                    "semántico", linea, columna,
                    f"la compuerta {nombre} requiere al menos {minimo} entradas "
                    f"y recibió {n}",
                    "agrega otra señal separada por coma"))
            elif maximo > 0 and n > maximo:
                errores.append(diag.error(
                    "semántico", linea, columna,
                    f"la compuerta {nombre} admite como máximo {maximo} entradas "
                    f"y recibió {n}"))

        # 2. Señales definidas: entradas más salidas de todas las compuertas.
        #    (Se recopilan primero para permitir referencias a señales que se
        #    definen más adelante en el circuito.)
        definidas = set(self.entradas) | set(CONSTANTES)
        primera_definicion = {s: "ENTRADA" for s in self.entradas}

        for compuerta in self.compuertas:
            salida = compuerta["salida"]
            if salida in definidas:
                linea, columna = self._pos_salida(compuerta)
                origen = primera_definicion.get(salida, "?")
                errores.append(diag.error(
                    "semántico", linea, columna,
                    f"la señal {salida} ya está definida (primera definición: {origen})",
                    "cada señal se define una sola vez: usa otro nombre para esta salida"))
            else:
                definidas.add(salida)
                primera_definicion[salida] = (f"{compuerta['compuerta']} en la línea "
                                              f"{compuerta['linea']}")

        # 3. Toda señal usada como entrada debe estar definida.
        candidatos = [s for s in list(self.entradas) + [c["salida"] for c in self.compuertas]
                      if not s.startswith("_")]
        for compuerta in self.compuertas:
            for k, senal in enumerate(compuerta["entradas"]):
                if senal not in definidas:
                    linea, columna = self._pos_referencia(compuerta, k)
                    parecida = mas_parecido(senal, candidatos)
                    errores.append(diag.error(
                        "semántico", linea, columna,
                        f"la señal {senal} no está definida",
                        f"¿quisiste decir '{parecida}'?" if parecida else
                        "declárala en ENTRADA[...] o como salida de una compuerta"))

        # 3b. Salidas declaradas con SALIDA[...].
        errores.extend(self._errores_de_salidas())

        # 4. Detección de ciclos. Siempre se ejecuta (aunque haya una señal
        #    redefinida) usando la primera definición de cada señal, y se
        #    reporta un ciclo por cada componente fuertemente conexa.
        errores.extend(self._errores_de_ciclos())

        return errores

    def _errores_de_salidas(self):
        """Cada salida declarada debe producirla una compuerta, sin repetirse."""
        if self.salidas_declaradas is None:
            return []
        errores = []
        entradas = set(self.entradas)
        producidas = [c["salida"] for c in self.compuertas if not c.get("temporal")]
        vistas = set()
        for i, senal in enumerate(self.salidas_declaradas):
            if self.pos_salidas and i < len(self.pos_salidas):
                linea, columna = self.pos_salidas[i]
            else:
                linea, columna = self.linea_entrada, None
            if senal in vistas:
                errores.append(diag.error(
                    "semántico", linea, columna,
                    f"la salida {senal} está declarada más de una vez",
                    "borra la repetición en SALIDA[...]"))
            elif senal in entradas:
                errores.append(diag.error(
                    "semántico", linea, columna,
                    f"la entrada {senal} no puede declararse como salida",
                    "una salida la produce una compuerta, por ejemplo "
                    f"OR[{senal}, 0] -> s y SALIDA[s]"))
            elif senal not in producidas:
                parecida = mas_parecido(senal, producidas)
                errores.append(diag.error(
                    "semántico", linea, columna,
                    f"la salida {senal} declarada en SALIDA no la produce ninguna compuerta",
                    f"¿quisiste decir '{parecida}'?" if parecida else
                    f"agrega una instrucción que termine en -> {senal}"))
            vistas.add(senal)
        return errores

    def temporales(self):
        """Señales temporales creadas al desazucarar compuertas anidadas."""
        return [c["salida"] for c in self.compuertas if c.get("temporal")]

    def _calcular_advertencias(self):
        advertencias = []

        usos = {senal for compuerta in self.compuertas for senal in compuerta["entradas"]}
        vistas = set()
        for i, senal in enumerate(self.entradas):
            if senal in vistas:
                continue
            vistas.add(senal)
            if senal not in usos:
                linea, columna = self._pos_entrada(i)
                advertencias.append(diag.advertencia(
                    "semántico", linea, columna, f"la entrada {senal} no se utiliza",
                    "quítala de ENTRADA[...] o conéctala a una compuerta"))

        # Una misma señal conectada dos veces a la misma compuerta.
        for compuerta in self.compuertas:
            vistas_pin = set()
            for k, senal in enumerate(compuerta["entradas"]):
                if senal in vistas_pin and senal not in CONSTANTES:
                    linea, columna = self._pos_referencia(compuerta, k)
                    advertencias.append(diag.advertencia(
                        "semántico", linea, columna,
                        f"la señal {senal} está conectada dos veces a la misma "
                        f"compuerta {compuerta['compuerta']}",
                        "revisa si querías conectar otra señal"))
                vistas_pin.add(senal)

        # Compuertas muertas: no alcanzan ninguna salida del circuito.
        for compuerta in self.compuertas_muertas():
            linea, columna = self._pos_compuerta(compuerta)
            advertencias.append(diag.advertencia(
                "semántico", linea, columna,
                f"la compuerta {compuerta['compuerta']} -> {compuerta['salida']} no "
                "llega a ninguna salida del circuito",
                "bórrala o conéctala a una salida declarada en SALIDA[...]"))

        return advertencias

    def salidas_finales(self):
        """Salidas del circuito: las declaradas o, sin SALIDA, las señales que
        no alimentan a ninguna compuerta (en orden de definición)."""
        if self.salidas_declaradas:
            return list(dict.fromkeys(self.salidas_declaradas))
        usadas = set()
        for compuerta in self.compuertas:
            usadas.update(compuerta["entradas"])
        return [c["salida"] for c in self.compuertas if c["salida"] not in usadas]

    def compuertas_muertas(self):
        """Compuertas cuya salida no llega a ninguna salida declarada.

        Sin SALIDA[...] las salidas son justamente las señales que no se usan,
        así que toda compuerta llega a alguna: solo hay compuertas muertas
        cuando el circuito declara sus salidas.
        """
        if not self.salidas_declaradas:
            return []
        productora = {}
        for compuerta in self.compuertas:
            productora.setdefault(compuerta["salida"], compuerta)
        vivas = set()
        pendientes = [s for s in self.salidas_declaradas if s in productora]
        while pendientes:
            senal = pendientes.pop()
            if senal in vivas:
                continue
            vivas.add(senal)
            for entrada in productora[senal]["entradas"]:
                if entrada in productora and entrada not in vivas:
                    pendientes.append(entrada)
        return [c for c in self.compuertas
                if productora.get(c["salida"]) is c and c["salida"] not in vivas]

    def tabla_simbolos(self):
        """Describe cada señal declarada y las líneas donde se utiliza."""
        usos = {}
        for compuerta in self.compuertas:
            for senal in compuerta["entradas"]:
                usos.setdefault(senal, []).append(compuerta["linea"])

        usadas = set(usos)
        declaradas = set(self.salidas_declaradas or [])
        filas = []
        vistas = set()
        for senal in self.entradas:
            if senal in vistas:
                continue
            vistas.add(senal)
            filas.append({
                "senal": senal,
                "tipo": "entrada",
                "linea_declaracion": self.linea_entrada,
                "lineas_uso": sorted(set(usos.get(senal, []))),
            })

        for compuerta in self.compuertas:
            senal = compuerta["salida"]
            if senal in vistas:
                continue
            vistas.add(senal)
            if compuerta.get("temporal"):
                tipo = "temporal"
            elif self.salidas_declaradas:
                tipo = "salida" if senal in declaradas else "cable interno"
            else:
                tipo = "cable interno" if senal in usadas else "salida"
            filas.append({
                "senal": senal,
                "tipo": tipo,
                "linea_declaracion": compuerta["linea"],
                "lineas_uso": sorted(set(usos.get(senal, []))),
            })

        return filas

    def _errores_de_ciclos(self):
        """Un error por cada componente fuertemente conexa con un ciclo.

        El grafo usa la primera definición de cada señal (las compuertas que
        redefinen una señal no producen nada y no pueden cerrar un ciclo). Las
        componentes se calculan con el algoritmo de Tarjan en versión
        iterativa, para que una cadena de miles de compuertas no agote la
        pila de llamadas de Python.
        """
        productora = {}
        entradas = set(self.entradas)
        for i, compuerta in enumerate(self.compuertas):
            salida = compuerta["salida"]
            if salida not in entradas and salida not in productora:
                productora[salida] = i
        nodos = sorted(set(productora.values()))

        # consumidores[u]: compuertas (nodo) que usan la salida de u.
        consumidores = {u: [] for u in nodos}
        for v in nodos:
            for senal in dict.fromkeys(self.compuertas[v]["entradas"]):
                u = productora.get(senal)
                if u is not None:
                    consumidores[u].append(v)

        errores = []
        for componente in _componentes_fuertes(nodos, consumidores):
            inicio = min(componente)
            if len(componente) == 1 and inicio not in consumidores[inicio]:
                continue
            camino = _camino_de_ciclo(inicio, set(componente), consumidores)
            senales = [self.compuertas[k]["salida"] for k in camino]
            senales.append(senales[0])
            linea, columna = self._pos_salida(self.compuertas[inicio])
            errores.append(diag.error(
                "semántico", linea, columna,
                f"ciclo detectado: {' → '.join(senales)}",
                "un circuito combinacional no puede realimentarse: rompe el ciclo "
                "usando otra señal"))
        return errores

    # ------------------------------------------------------------------
    # Orden topológico
    # ------------------------------------------------------------------
    def orden_topologico(self):
        """Orden de evaluación de las compuertas (antes las que no dependen de ninguna otra).

        Se calcula una sola vez por análisis (algoritmo de Kahn con una cola
        `deque`) y se reutiliza en la tabla de verdad, las expresiones y el
        paso a paso. Antes se recalculaba en cada fila de la tabla, con
        `list.pop(0)`, y un circuito de 20 entradas tardaba minutos.
        """
        if self._orden is None:
            self._orden = self._calcular_orden()
        return self._orden

    def _calcular_orden(self):
        n = len(self.compuertas)
        mapa = {}
        for i, compuerta in enumerate(self.compuertas):
            mapa.setdefault(compuerta["salida"], i)

        # dependencias: succ[p] contiene las compuertas que usan la salida de p.
        succ = [[] for _ in range(n)]
        indeg = [0] * n
        for i, compuerta in enumerate(self.compuertas):
            for senal in compuerta["entradas"]:
                j = mapa.get(senal)
                if j is not None:
                    succ[j].append(i)
                    indeg[i] += 1

        # Kahn: primero las de grado de entrada 0 (orden estable por índice).
        cola = deque(i for i in range(n) if indeg[i] == 0)
        orden = []
        while cola:
            u = cola.popleft()
            orden.append(self.compuertas[u])
            for v in succ[u]:
                indeg[v] -= 1
                if indeg[v] == 0:
                    cola.append(v)

        return orden

    # ------------------------------------------------------------------
    # Evaluación
    # ------------------------------------------------------------------
    def programa(self):
        """El circuito compilado para el evaluador por bloques (una vez)."""
        if self._programa is None:
            self._programa = Programa(self.entradas, [
                (self.operacion.get(c["compuerta"], "and"), c["entradas"], c["salida"])
                for c in self.orden_topologico()
            ])
        return self._programa

    def _evaluar(self, valores_entrada):
        """Dado un diccionario de valores de entrada, devuelve los valores de
        todas las señales (entradas + salidas de compuertas)."""
        valores = self.programa().evaluar(valores_entrada)
        valores.pop("0", None)
        valores.pop("1", None)
        return valores

    def senales_tabla(self, incluir_temporales=True):
        """Columnas de la tabla: entradas y luego salidas en orden de definición.

        Las señales temporales (_t1, _t2...) se pueden dejar fuera: la web y la
        consola las ocultan por defecto.
        """
        return list(self.entradas) + [
            c["salida"] for c in self.compuertas
            if incluir_temporales or not c.get("temporal")]

    def filas_tabla(self, desde=0, cantidad=None, senales=None):
        """Solo las filas [desde, desde + cantidad) de la tabla de verdad.

        Cada fila se calcula a partir de su índice binario, así que pedir las
        filas 500.000 a 500.100 de un circuito de 20 entradas no construye
        nada más que esas 100 filas.
        """
        programa = self.programa()
        if cantidad is None:
            cantidad = programa.filas_totales - desde
        return programa.filas(desde, cantidad, senales or self.senales_tabla())

    def tabla_verdad(self):
        """Tabla de verdad completa (2^n combinaciones). Columnas: entradas
        primero y luego las salidas en el orden en que se definen."""
        senales = self.senales_tabla()
        return {"señales": senales, "filas": self.filas_tabla(0, None, senales)}

    # ------------------------------------------------------------------
    # Expresiones booleanas
    # ------------------------------------------------------------------
    def expresiones_booleanas(self):
        """Expresión booleana equivalente de cada señal de salida que no es
        utilizada como entrada de otra compuerta."""
        # Hojas de la expresión: entradas y constantes.
        hojas = set(self.entradas) | set(CONSTANTES)

        # Salidas "finales" del circuito.
        salidas_finales = self.salidas_finales()

        # Las expresiones se construyen en orden topológico (iterativo), no con
        # recursión: una cadena de miles de compuertas agotaría la pila.
        textos = {}
        for compuerta in self.orden_topologico():
            senal = compuerta["salida"]

            nombre = compuerta["compuerta"]
            if nombre == "NOT":
                entrada = compuerta["entradas"][0]
                textos[senal] = f"NOT({entrada if entrada in hojas else textos[entrada]})"
            elif nombre in NO_ASOCIATIVAS and len(compuerta["entradas"]) > 2:
                # "a NAND b NAND c" es ambiguo: NAND no es asociativa y
                # (a NAND b) NAND c ≠ NAND[a, b, c]. Con 3 o más entradas se
                # usa notación de función: NAND(a, b, c).
                operandos = [entrada if entrada in hojas else textos[entrada]
                             for entrada in compuerta["entradas"]]
                textos[senal] = f"{nombre}({', '.join(operandos)})"
            else:
                operandos = [
                    entrada if entrada in hojas else f"({textos[entrada]})"
                    for entrada in compuerta["entradas"]
                ]
                textos[senal] = f" {nombre} ".join(operandos)

        return [(salida, textos[salida]) for salida in salidas_finales]


# ---------------------------------------------------------------------------
# Diagrama del circuito con Graphviz (python-graphviz).
# ---------------------------------------------------------------------------
# Refactorizado en funciones pequeñas: cada una dibuja una parte del grafo.
# ---------------------------------------------------------------------------

RUTA_ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

# Nombre del archivo (sin extensión) del símbolo de cada compuerta en assets/.
ASSETS_COMPUERTAS = {
    "AND": "and", "OR": "or", "NOT": "not", "XOR": "xor",
    "NAND": "nand", "NOR": "nor", "XNOR": "xnor",
}

# Estilo de cada clase de señal.
ESTILO_SENAL = {
    "entrada":    {"fillcolor": "#e8f0fe", "color": "#4285f4", "width": "0.60", "height": "0.40"},
    "salida":     {"fillcolor": "#e6f4ea", "color": "#34a853", "width": "0.60", "height": "0.40"},
    "intermedia": {"fillcolor": "#e8eaed", "color": "#80868b", "width": "0.45", "height": "0.30"},
}


def _dimensiones_png(ruta):
    """Lee ancho y alto de un PNG desde su cabecera (IHDR) con stdlib."""
    with open(ruta, "rb") as archivo:
        cabecera = archivo.read(24)
    if len(cabecera) < 24 or cabecera[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    ancho, alto = struct.unpack(">II", cabecera[16:24])
    return ancho, alto


def configurar_grafo():
    """Crea el grafo (Graphviz) con la configuración global del diagrama."""
    grafo = graphviz.Digraph("circuito")
    grafo.attr(rankdir="LR", splines="ortho", nodesep="0.5",
               ranksep="0.9", ordering="out")
    grafo.attr("node", fontname="Helvetica", fontsize="11", fontcolor="#1f2937")
    grafo.attr("edge", fontname="Helvetica", fontsize="11",
               color="#374151", arrowsize="0.7")
    return grafo


def dibujar_senal(grafo, senal, clase):
    """Dibuja el nodo de una señal (elipse), según su clase."""
    grafo.node(senal, shape="ellipse", style="filled", label=senal,
               **ESTILO_SENAL[clase])


def dibujar_compuerta(grafo, nodo, tipo):
    """Dibuja el símbolo real de la compuerta (imagen en assets/).
    Si el archivo no existe o no se puede usar, usa una caja redondeada."""
    nombre = ASSETS_COMPUERTAS.get(tipo, "")
    if nombre:
        ruta_png = os.path.join(RUTA_ASSETS, f"{nombre}.png")
        tamano = _dimensiones_png(ruta_png) if os.path.isfile(ruta_png) else None
        if tamano and tamano[0] > 0:
            ancho, alto = tamano
            w = 1.35
            grafo.node(nodo, shape="none", image=ruta_png, label="",
                       fixedsize="true", width=str(w),
                       height=str(round(w * alto / ancho, 3)), xlabel=tipo)
            return
    # Respaldo: caja redondeada y rellena.
    grafo.node(nodo, shape="box", style="rounded,filled", fillcolor="#fef7e0",
               color="#f9ab00", label=tipo)


def bifurcar(grafo, origen, senal, destinos):
    """Crea un punto de unión para una señal que alimenta varios destinos."""
    punto = f"u_{origen}"
    grafo.node(punto, shape="point", width="0.08", fixedsize="true",
               color="#374151")
    grafo.edge(origen, punto, arrowhead="none")
    for destino in destinos:
        grafo.edge(punto, destino, xlabel=senal,
                   fontsize="8", fontcolor="#80868b")


def generar_diagrama(entradas, compuertas):
    """Construye el grafo completo: entradas a la izquierda, salidas finales a
    la derecha y compuertas en columnas según su nivel de profundidad."""
    grafo = configurar_grafo()

    # Señales finales: las que no alimentan a ninguna otra compuerta.
    usadas = set()
    for compuerta in compuertas:
        usadas.update(compuerta["entradas"])
    salidas_finales = [c["salida"] for c in compuertas if c["salida"] not in usadas]

    # Columnas de nivel: todas las entradas en la misma columna (izquierda).
    with grafo.subgraph() as s:
        s.attr(rank="same")
        for senal in entradas:
            dibujar_senal(s, senal, "entrada")

    # Señales intermedias (las que sí se consumen).
    for compuerta in compuertas:
        if compuerta["salida"] not in salidas_finales:
            dibujar_senal(grafo, compuerta["salida"], "intermedia")

    # Salidas finales alineadas en la misma columna (derecha).
    with grafo.subgraph() as s:
        s.attr(rank="same")
        for senal in salidas_finales:
            dibujar_senal(s, senal, "salida")

    # Compuertas y bordes de salida, declarados en orden topológico.
    destino_senal = {}
    for i, compuerta in enumerate(compuertas):
        nodo = f"g{i}"
        tipo = compuerta["compuerta"]
        dibujar_compuerta(grafo, nodo, tipo)
        grafo.edge(nodo, compuerta["salida"])
        for senal in compuerta["entradas"]:
            destino_senal.setdefault(senal, []).append(nodo)

    # Conexiones de alimentación (con punto de unión si hay bifurcación).
    for senal, destinos in destino_senal.items():
        if len(destinos) == 1:
            grafo.edge(senal, destinos[0], xlabel=senal,
                       fontsize="8", fontcolor="#80868b")
        else:
            bifurcar(grafo, senal, senal, destinos)

    return grafo


def generar_dot(entradas, compuertas):
    """Genera el código DOT del circuito (interfaz pública del análisis)."""
    return generar_diagrama(entradas, compuertas).source