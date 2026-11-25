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
from collections import deque

import graphviz

from evaluador import Programa


class AnalizadorSemantico:

    def __init__(self, entradas, compuertas, reglas_compuertas,
                 linea_entrada=1):
        # Fase semántica: trabaja sobre la estructura construida por el parser.
        self.entradas = entradas
        self.compuertas = compuertas
        self.linea_entrada = linea_entrada

        # Aridad y operación de cada compuerta provienen de reglas.json.
        self.entradas_min = {}
        self.entradas_max = {}
        self.operacion = {}
        for regla in reglas_compuertas:
            self.entradas_min[regla["nombre"]] = regla["entradas_min"]
            self.entradas_max[regla["nombre"]] = regla["entradas_max"]
            self.operacion[regla["nombre"]] = regla["operacion"]

        # Cachés de un análisis: el orden topológico y el circuito compilado.
        self._orden = None
        self._programa = None

    # ------------------------------------------------------------------
    # Comprobaciones semánticas
    # ------------------------------------------------------------------
    def revisar(self):
        """Devuelve la lista de errores semánticos (vacía si todo es correcto)."""
        errores = []

        # Una entrada repetida crea una declaración ambigua antes incluso de
        # analizar las conexiones de las compuertas.
        vistas = set()
        for senal in self.entradas:
            if senal in vistas:
                errores.append(
                    f"Error semántico línea {self.linea_entrada}: "
                    f"la entrada {senal} está declarada más de una vez")
            vistas.add(senal)

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
        hay_redefinicion = len(vistas) != len(self.entradas)

        for compuerta in self.compuertas:
            salida = compuerta["salida"]
            if salida in definidas:
                hay_redefinicion = True
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
        #    Si una señal está definida dos veces el grafo ya es ambiguo y el
        #    error útil es la redefinición, no un ciclo derivado de ella.
        if not hay_redefinicion:
            ciclo = self._detectar_ciclo()
            if ciclo is not None:
                senales, linea = ciclo
                camino = " → ".join(senales)
                errores.append(
                    f"Error semántico línea {linea}: ciclo detectado: {camino}")

        return errores

    def tabla_simbolos(self):
        """Describe cada señal declarada y las líneas donde se utiliza."""
        usos = {}
        for compuerta in self.compuertas:
            for senal in compuerta["entradas"]:
                usos.setdefault(senal, []).append(compuerta["linea"])

        usadas = set(usos)
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
            filas.append({
                "senal": senal,
                "tipo": "cable interno" if senal in usadas else "salida",
                "linea_declaracion": compuerta["linea"],
                "lineas_uso": sorted(set(usos.get(senal, []))),
            })

        return filas

    def advertencias(self):
        """Devuelve advertencias que no invalidan el circuito."""
        usos = {
            senal
            for compuerta in self.compuertas
            for senal in compuerta["entradas"]
        }
        return [
            f"Advertencia línea {self.linea_entrada}: "
            f"la entrada {senal} no se utiliza"
            for senal in dict.fromkeys(self.entradas)
            if senal not in usos
        ]

    def _detectar_ciclo(self):
        """Recorre el grafo de dependencias con DFS iterativo.

        Devuelve ``(camino, linea)`` si hay un ciclo o ``None`` si el grafo es
        acíclico. ``camino`` incluye la señal repetida al final (por ejemplo
        ``["x", "y", "x"]``), así el mensaje muestra el bucle exacto.

        Se usa una pila explícita en lugar de recursión para que una cadena de
        miles de compuertas no agote la pila de llamadas de Python.
        """
        n = len(self.compuertas)
        if n == 0:
            return None

        # mapa: salida de una compuerta -> indice de esa compuerta.
        mapa = {}
        for i, compuerta in enumerate(self.compuertas):
            mapa[compuerta["salida"]] = i

        # succ[u] = compuertas de las que depende u. Una compuerta que se usa a
        # sí misma también cuenta (antes se ignoraba y el ciclo no se veía).
        succ = [[] for _ in range(n)]
        for i, compuerta in enumerate(self.compuertas):
            for senal in compuerta["entradas"]:
                j = mapa.get(senal)
                if j is not None:
                    succ[i].append(j)

        color = [0] * n  # 0 = blanco (no visitado), 1 = gris (en el camino), 2 = negro

        for inicio in range(n):
            if color[inicio] != 0:
                continue

            color[inicio] = 1
            camino = [inicio]
            # Cada elemento es [nodo, siguiente vecino por visitar].
            pila = [[inicio, 0]]

            while pila:
                u, indice = pila[-1]

                if indice < len(succ[u]):
                    v = succ[u][indice]
                    pila[-1][1] += 1

                    if color[v] == 1:
                        # v ya está en el camino: el ciclo va de v hasta u y
                        # vuelve a v.
                        desde = camino.index(v)
                        senales = [self.compuertas[k]["salida"]
                                   for k in camino[desde:]]
                        senales.append(self.compuertas[v]["salida"])
                        return senales, self.compuertas[v]["linea"]

                    if color[v] == 0:
                        color[v] = 1
                        camino.append(v)
                        pila.append([v, 0])
                    continue

                # Sin vecinos pendientes: el nodo queda terminado.
                color[u] = 2
                pila.pop()
                camino.pop()

        return None

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

    def senales_tabla(self):
        """Columnas de la tabla: entradas y luego salidas en orden de definición."""
        return list(self.entradas) + [c["salida"] for c in self.compuertas]

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
        entradas_set = set(self.entradas)

        # Señales usadas como entrada por alguna compuerta.
        usadas = set()
        for c in self.compuertas:
            usadas.update(c["entradas"])

        # Salidas "finales" del circuito.
        salidas_finales = [c["salida"] for c in self.compuertas if c["salida"] not in usadas]

        # Las expresiones se construyen en orden topológico (iterativo), no con
        # recursión: una cadena de miles de compuertas agotaría la pila.
        textos = {}
        for compuerta in self.orden_topologico():
            senal = compuerta["salida"]

            if compuerta["compuerta"] == "NOT":
                entrada = compuerta["entradas"][0]
                textos[senal] = f"NOT({entrada if entrada in entradas_set else textos[entrada]})"
            else:
                operandos = [
                    entrada if entrada in entradas_set else f"({textos[entrada]})"
                    for entrada in compuerta["entradas"]
                ]
                textos[senal] = f" {compuerta['compuerta']} ".join(operandos)

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