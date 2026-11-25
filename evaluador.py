# ============================================================================
# EVALUADOR DE CIRCUITOS POR BLOQUES DE FILAS (BIT-PARALELO)
# ----------------------------------------------------------------------------
# Evalúa un circuito ya ordenado topológicamente sobre un BLOQUE de filas de
# su tabla de verdad a la vez. Cada señal se representa con un entero de
# Python en el que el bit j es el valor de la señal en la fila (desde + j):
# una compuerta AND sobre 4096 filas es una sola operación `&` entre enteros.
#
# La fila r de la tabla corresponde a su índice binario: la primera entrada
# es el bit más significativo (el mismo orden que itertools.product). Así se
# puede calcular cualquier rango de filas sin construir la tabla completa.
# ============================================================================

# Operaciones que entiende el evaluador. Las cuatro últimas solo aparecen en
# el código intermedio optimizado (copias y constantes).
OPERACIONES = ("and", "or", "not", "xor", "nand", "nor", "xnor", "buf")

# Las constantes del lenguaje (argumentos 0 y 1) se tratan como señales
# predefinidas con valor fijo.
CONSTANTES = {"0": False, "1": True}


def vector_entrada(posicion, total_entradas, desde, cantidad):
    """Bits de una entrada en las filas [desde, desde + cantidad).

    `posicion` es el índice de la entrada (0 = la más significativa). Se arma
    por tramos: la entrada k vale 0 durante 2^k filas y 1 durante otras 2^k,
    así que basta con concatenar tramos en lugar de recorrer fila por fila.
    """
    peso = total_entradas - 1 - posicion
    tramo = 1 << peso
    partes = []
    fila = desde
    fin = desde + cantidad
    while fila < fin:
        siguiente = min(fin, (fila // tramo + 1) * tramo)
        partes.append(("1" if (fila >> peso) & 1 else "0") * (siguiente - fila))
        fila = siguiente
    texto = "".join(partes)
    # El bit 0 del entero es la primera fila del bloque.
    return int(texto[::-1], 2) if texto else 0


def aplicar(operacion, valores, mascara):
    """Aplica una operación a una lista de vectores de bits."""
    if operacion == "buf":
        return valores[0]
    if operacion == "not":
        return ~valores[0] & mascara
    if operacion in ("and", "nand"):
        resultado = mascara
        for valor in valores:
            resultado &= valor
    elif operacion in ("or", "nor"):
        resultado = 0
        for valor in valores:
            resultado |= valor
    elif operacion in ("xor", "xnor"):
        resultado = 0
        for valor in valores:
            resultado ^= valor
    else:
        raise ValueError(f"operación desconocida: {operacion!r}")

    if operacion in ("nand", "nor", "xnor"):
        resultado = ~resultado & mascara
    return resultado


class Programa:
    """Circuito listo para evaluarse por bloques.

    `entradas` es la lista de entradas (en el orden de las columnas de la
    tabla) e `instrucciones` una lista de (operacion, argumentos, destino) en
    orden topológico. Los argumentos pueden ser señales o las constantes
    "0" y "1".
    """

    def __init__(self, entradas, instrucciones):
        self.entradas = list(dict.fromkeys(entradas))
        self.instrucciones = [(op, list(args), destino)
                              for op, args, destino in instrucciones]
        for operacion, _, _ in self.instrucciones:
            if operacion not in OPERACIONES:
                raise ValueError(f"operación desconocida: {operacion!r}")

    @property
    def filas_totales(self):
        return 1 << len(self.entradas)

    def evaluar_bloque(self, desde, cantidad):
        """Vectores de bits de todas las señales en las filas pedidas."""
        if cantidad <= 0:
            return {}
        mascara = (1 << cantidad) - 1
        n = len(self.entradas)
        valores = {"0": 0, "1": mascara}
        for posicion, senal in enumerate(self.entradas):
            valores[senal] = vector_entrada(posicion, n, desde, cantidad)
        for operacion, argumentos, destino in self.instrucciones:
            valores[destino] = aplicar(
                operacion, [valores[a] for a in argumentos], mascara)
        return valores

    def filas(self, desde, cantidad, senales):
        """Filas [desde, desde + cantidad) con las columnas `senales` (0/1)."""
        desde = max(0, int(desde))
        cantidad = max(0, min(int(cantidad), self.filas_totales - desde))
        if cantidad == 0:
            return []
        vectores = self.evaluar_bloque(desde, cantidad)
        columnas = [format(vectores[s], f"0{cantidad}b")[::-1] for s in senales]
        return [[1 if columna[j] == "1" else 0 for columna in columnas]
                for j in range(cantidad)]

    def evaluar(self, valores_entrada):
        """Valores (bool) de todas las señales para una sola combinación."""
        valores = {"0": False, "1": True}
        for senal in self.entradas:
            valores[senal] = bool(valores_entrada.get(senal, False))
        for operacion, argumentos, destino in self.instrucciones:
            vector = aplicar(operacion, [int(valores[a]) for a in argumentos], 1)
            valores[destino] = bool(vector)
        return valores
