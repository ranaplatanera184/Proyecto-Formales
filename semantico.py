# ============================================================================
# FASE SEMANTICA Y EVALUACION DEL COMPILADOR DE CIRCUITOS
# ----------------------------------------------------------------------------
# Comprueba las reglas de significado del circuito:
#   1. Aridad de cada compuerta (según reglas.json).
#   2. Una señal no puede definirse dos veces (ni colisionar con una entrada).
#   3. Toda señal usada debe estar definida (como entrada o como salida de
#      alguna compuerta). Se permite referenciar señales definidas después.
#   4. No debe haber ciclos en el grafo de dependencias (detección con DFS).
#
# Si el circuito es correcto, también calcula:
#   - Orden de evaluación (orden topológico).
#   - Tabla de verdad completa (2^n combinaciones) con señales intermedias.
#   - Expresión booleana equivalente de cada salida.
# ============================================================================

import os
import struct
from itertools import product


class AnalizadorSemantico:

    def __init__(self, entradas, compuertas, reglas_compuertas):
        # Fase semántica: trabaja sobre la estructura construida por el parser.
        self.entradas = entradas
        self.compuertas = compuertas

        # Aridad y operación de cada compuerta provienen de reglas.json.
        self.entradas_min = {}
        self.entradas_max = {}
        self.operacion = {}
        for regla in reglas_compuertas:
            self.entradas_min[regla["nombre"]] = regla["entradas_min"]
            self.entradas_max[regla["nombre"]] = regla["entradas_max"]
            self.operacion[regla["nombre"]] = regla["operacion"]

    # ------------------------------------------------------------------
    # Comprobaciones semánticas
    # ------------------------------------------------------------------
    def revisar(self):
        """Devuelve la lista de errores semánticos (vacía si todo es correcto)."""
        errores = []

        # 1. Aridad de las compuertas.
        for compuerta in self.compuertas:
            nombre = compuerta["compuerta"]
            n = len(compuerta["entradas"])
            minimo = self.entradas_min.get(nombre, 1)
            maximo = self.entradas_max.get(nombre, 0)

            if minimo == maximo and maximo > 0 and n != minimo:
                errores.append(
                    f"Error semántico línea {compuerta['linea']}: "
                    f"la compuerta {nombre} requiere exactamente {minimo} entrada(s)")
            elif n < minimo:
                errores.append(
                    f"Error semántico línea {compuerta['linea']}: "
                    f"la compuerta {nombre} requiere al menos {minimo} entradas")
            elif maximo > 0 and n > maximo:
                errores.append(
                    f"Error semántico línea {compuerta['linea']}: "
                    f"la compuerta {nombre} admite como máximo {maximo} entradas")

        # 2. Señales definidas: entradas más salidas de todas las compuertas.
        #    (Se recopilan primero para permitir referencias a señales que se
        #    definen más adelante en el circuito.)
        definidas = set(self.entradas)
        primera_definicion = {s: "ENTRADA" for s in self.entradas}

        for compuerta in self.compuertas:
            salida = compuerta["salida"]
            if salida in definidas:
                errores.append(
                    f"Error semántico línea {compuerta['linea']}: "
                    f"la señal {salida} ya está definida "
                    f"(primera definición: {primera_definicion.get(salida, '?')})")
            else:
                definidas.add(salida)
                primera_definicion[salida] = compuerta["compuerta"]

        # 3. Toda señal usada como entrada debe estar definida.
        for compuerta in self.compuertas:
            for senal in compuerta["entradas"]:
                if senal not in definidas:
                    errores.append(
                        f"Error semántico línea {compuerta['linea']}: "
                        f"la señal {senal} no está definida")

        # 4. Detección de ciclos en el grafo de dependencias (DFS).
        ciclo = self._detectar_ciclo()
        if ciclo is not None:
            errores.append(f"Error semántico línea {ciclo[1]}: ciclo detectado en la señal {ciclo[0]}")

        return errores

    def _detectar_ciclo(self):
        """Recorre el grafo de dependencias con DFS. Devuelve (senal, linea) si
        hay un ciclo o None si el grafo es acíclico."""
        n = len(self.compuertas)
        if n == 0:
            return None

        # mapa: salida de una compuerta -> indice de esa compuerta.
        mapa = {}
        for i, compuerta in enumerate(self.compuertas):
            mapa[compuerta["salida"]] = i

        # succ[u] = compuertas que dependen de la compuerta u.
        succ = [[] for _ in range(n)]
        for i, compuerta in enumerate(self.compuertas):
            for senal in compuerta["entradas"]:
                j = mapa.get(senal)
                if j is not None and j != i:
                    succ[i].append(j)

        color = [0] * n  # 0 = blanco (no visitado), 1 = gris (en pila), 2 = negro
        resultado = None

        def visitar(u, pila):
            nonlocal resultado
            color[u] = 1
            pila.append(u)
            for v in succ[u]:
                if color[v] == 1:
                    # Existe un ciclo: la señal implicada es la salida del nodo ancestro v.
                    resultado = (self.compuertas[v]["salida"], self.compuertas[v]["linea"])
                    return
                if color[v] == 0:
                    visitar(v, pila)
                    if resultado is not None:
                        return
            pila.pop()
            color[u] = 2

        for u in range(n):
            if color[u] == 0:
                visitar(u, [])
                if resultado is not None:
                    break

        return resultado

    # ------------------------------------------------------------------
    # Orden topológico
    # ------------------------------------------------------------------
    def orden_topologico(self):
        """Orden de evaluación de las compuertas (antes las que no dependen de ninguna otra)."""
        n = len(self.compuertas)
        mapa = {}
        for i, compuerta in enumerate(self.compuertas):
            mapa[compuerta["salida"]] = i

        # dependencias: succ[p] contiene las compuertas que usan la salida de p.
        succ = [[] for _ in range(n)]
        indeg = [0] * n
        for i, compuerta in enumerate(self.compuertas):
            for senal in compuerta["entradas"]:
                j = mapa.get(senal)
                if j is not None and j != i:
                    succ[j].append(i)
                    indeg[i] += 1

        # Kahn: primero las de grado de entrada 0 (orden estable por índice).
        cola = [i for i in range(n) if indeg[i] == 0]
        orden = []
        while cola:
            u = cola.pop(0)
            orden.append(self.compuertas[u])
            for v in succ[u]:
                indeg[v] -= 1
                if indeg[v] == 0:
                    cola.append(v)

        return orden

    # ------------------------------------------------------------------
    # Evaluación
    # ------------------------------------------------------------------
    def _aplicar_operacion(self, nombre, valores):
        operacion = self.operacion.get(nombre, "and")
        if operacion == "and":
            return all(valores)
        if operacion == "or":
            return any(valores)
        if operacion == "not":
            return not valores[0]
        if operacion == "xor":
            return sum(valores) % 2 == 1
        if operacion == "nand":
            return not all(valores)
        if operacion == "nor":
            return not any(valores)
        if operacion == "xnor":
            return sum(valores) % 2 == 0
        return False

    def _evaluar(self, valores_entrada):
        """Dado un diccionario de valores de entrada, devuelve los valores de
        todas las señales (entradas + salidas de compuertas)."""
        valores = dict(valores_entrada)
        for compuerta in self.orden_topologico():
            argumentos = [valores[senal] for senal in compuerta["entradas"]]
            valores[compuerta["salida"]] = self._aplicar_operacion(
                compuerta["compuerta"], argumentos)
        return valores

    def tabla_verdad(self):
        """Tabla de verdad completa (2^n combinaciones). Columnas: entradas
        primero y luego las salidas en el orden en que se definen."""
        senales = list(self.entradas) + [c["salida"] for c in self.compuertas]

        filas = []
        for combinacion in product([0, 1], repeat=len(self.entradas)):
            valores_entrada = dict(zip(self.entradas, [bool(x) for x in combinacion]))
            valores = self._evaluar(valores_entrada)
            filas.append([int(valores[senal]) for senal in senales])

        return {"señales": senales, "filas": filas}

    # ------------------------------------------------------------------
    # Expresiones booleanas
    # ------------------------------------------------------------------
    def expresiones_booleanas(self):
        """Expresión booleana equivalente de cada señal de salida que no es
        utilizada como entrada de otra compuerta."""
        mapa = {c["salida"]: c for c in self.compuertas}
        entradas_set = set(self.entradas)

        # Señales usadas como entrada por alguna compuerta.
        usadas = set()
        for c in self.compuertas:
            usadas.update(c["entradas"])

        # Salidas "finales" del circuito.
        salidas_finales = [c["salida"] for c in self.compuertas if c["salida"] not in usadas]

        def expresion_de(senal):
            if senal in entradas_set:
                return senal
            compuerta = mapa[senal]
            if compuerta["compuerta"] == "NOT":
                return f"NOT({expresion_de(compuerta['entradas'][0])})"

            # Cada operando que es compuerta se inserta entre paréntesis.
            operandos = []
            for entrada in compuerta["entradas"]:
                if entrada in entradas_set:
                    operandos.append(entrada)
                else:
                    operandos.append(f"({expresion_de(entrada)})")
            return f" {compuerta['compuerta']} ".join(operandos)

        return [(salida, expresion_de(salida)) for salida in salidas_finales]


# ---------------------------------------------------------------------------
# Diagrama del circuito con Graphviz (python-graphviz).
# ---------------------------------------------------------------------------
# Refactorizado en funciones pequeñas: cada una dibuja una parte del grafo.
# ---------------------------------------------------------------------------
import graphviz

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