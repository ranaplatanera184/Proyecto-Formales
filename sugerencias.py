# ============================================================================
# SUGERENCIAS "¿QUISISTE DECIR...?"
# ----------------------------------------------------------------------------
# Distancia de edición de Levenshtein implementada a mano (programación
# dinámica con dos filas) y selección del candidato más parecido. La usan el
# parser (compuerta desconocida "ANDD" → AND) y el análisis semántico (señal
# no definida "zz" → z).
# ============================================================================


def distancia(a, b):
    """Mínimo de inserciones, borrados y sustituciones para convertir a en b."""
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)

    anterior = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        actual = [i]
        for j, cb in enumerate(b, start=1):
            actual.append(min(
                anterior[j] + 1,                    # borrar ca
                actual[j - 1] + 1,                  # insertar cb
                anterior[j - 1] + (ca != cb),       # sustituir (o igual)
            ))
        anterior = actual
    return anterior[-1]


def mas_parecido(palabra, candidatos, ignorar_mayusculas=False):
    """El candidato más cercano a `palabra`, o None si ninguno es razonable.

    Se sugiere solo cuando la distancia es como mucho 2 y menor que la
    longitud de la palabra (así "b" no sugiere "a": cambiar la única letra no
    es una errata, es otro nombre), o cuando el candidato es claramente el más
    cercano: el único a distancia mínima, a menos de la mitad de la longitud y
    con el siguiente al menos dos ediciones más lejos. Con empates gana el
    primero en orden de declaración.
    """
    normal = (lambda t: t.upper()) if ignorar_mayusculas else (lambda t: t)
    objetivo = normal(palabra)

    distancias = []
    for candidato in dict.fromkeys(candidatos):
        if candidato == palabra:
            continue
        distancias.append((distancia(objetivo, normal(candidato)), candidato))
    if not distancias:
        return None

    distancias.sort(key=lambda par: par[0])        # sort estable: respeta el orden
    mejor, candidato = distancias[0]
    if mejor == 0:
        return candidato                           # solo cambia en mayúsculas
    if mejor <= 2 and mejor < len(palabra):
        return candidato
    siguiente = distancias[1][0] if len(distancias) > 1 else None
    claramente = (mejor * 2 < len(palabra)
                  and (siguiente is None or siguiente >= mejor + 2))
    return candidato if claramente else None
