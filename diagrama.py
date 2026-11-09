# ============================================================================
# DIAGRAMA DEL CIRCUITO EN SVG (formas dibujadas con código)
# ----------------------------------------------------------------------------
# Diseña y dibuja el circuito completo con control total de la geometría:
#   - Cada compuerta se construye desde código (trazos y arcos), sin imágenes.
#   - Los cables entran exactamente por los pines de entrada de cada compuerta
#     y salen por su punta de salida (forma coherente con un esquema lógico).
#   - El trazado es ortogonal (segmentos a 90 grados), como un circuito real.
#
# El SVG se rasteriza a PNG con rsvg-convert (sistema), sin dependencias.
# ============================================================================

import math

# ---------------------------------------------------------------------------
# Geometría de los iconos de compuerta (coordenadas relativas al icono).
# Cuerpo: entre y=12 y y=52 (centro y=32). Salida en x=118. Entradas en x=0.
# ---------------------------------------------------------------------------
ICONA_ANCHO = 118
ICONA_ALTO = 80
CUERPO_TOP = 12
CUERPO_BOTTOM = 52
CUERPO_MEDIO = 32
PUNTA_SALIDA = 118

# Punto (x) donde termina la pata de entrada según el tipo y la fila (y).
def _entrada_cuerpo(tipo, y):
    dy = y - CUERPO_MEDIO
    if tipo in ("AND", "NAND"):
        r = 26
        return 88 - math.sqrt(r * r - dy * dy)
    if tipo in ("OR", "NOR"):
        r = 20
        return 56 - math.sqrt(r * r - dy * dy)
    if tipo in ("XOR", "XNOR"):
        r = 13
        return 30 - math.sqrt(r * r - dy * dy)
    return 62  # NOT (base del triángulo)


# Salida del cuerpo (desde aquí se dibuja la pata hasta la punta).
def _salida_cuerpo(tipo):
    if tipo == "AND":
        return 88
    if tipo == "NOT":
        return 105
    if tipo == "NAND":
        return 101
    if tipo == "OR":
        return 104
    if tipo == "XOR":
        return 104
    if tipo == "NOR":
        return 117
    return 117  # XNOR


def _cuerpo_compuerta(tipo):
    """Camino SVG del cuerpo de la compuerta (abierto, sin relleno)."""
    if tipo == "AND":
        return "M88 12 A26 26 0 0 0 88 52 Z"
    if tipo == "NAND":
        return "M88 12 A26 26 0 0 0 88 52 Z"
    if tipo == "OR":
        b = "M76 12 A28 28 0 0 1 104 32 A28 28 0 0 1 76 52 Z "
        b += "M56 12 A20 20 0 0 0 56 52 Z "
        b += "M56 12 H76 M56 52 H76"
        return b
    if tipo == "NOR":
        b = "M76 12 A28 28 0 0 1 104 32 A28 28 0 0 1 76 52 Z "
        b += "M56 12 A20 20 0 0 0 56 52 Z "
        b += "M56 12 H76 M56 52 H76"
        return b
    if tipo == "XOR":
        b = "M76 12 A28 28 0 0 1 104 32 A28 28 0 0 1 76 52 Z "
        b += "M56 12 A20 20 0 0 0 56 52 Z "
        b += "M56 12 H76 M56 52 H76 "
        b += "M30 18 A13 13 0 0 0 30 46"
        return b
    if tipo == "XNOR":
        b = "M76 12 A28 28 0 0 1 104 32 A28 28 0 0 1 76 52 Z "
        b += "M56 12 A20 20 0 0 0 56 52 Z "
        b += "M56 12 H76 M56 52 H76 "
        b += "M30 18 A13 13 0 0 0 30 46"
        return b
    return "M62 12 L92 32 L62 52 Z"  # NOT


# Burbuja de negación (si el tipo la lleva).
def _burbuja(tipo):
    cx = {"NAND": 96, "NOR": 112, "XNOR": 112, "NOT": 100}.get(tipo)
    return cx


# ---------------------------------------------------------------------------
# Capa (columna) de cada señal: distancia máxima desde las entradas.
# ---------------------------------------------------------------------------
def _capas(entradas, compuertas):
    entradas_set = set(entradas)
    mapa = {c["salida"]: c for c in compuertas}
    memo = {}
    visitando = set()

    def dfs(senal):
        if senal in memo:
            return memo[senal]
        if senal in entradas_set:
            memo[senal] = 0
            return 0
        if senal in visitando or senal not in mapa:
            return 0  # ciclo o señal externa: no debe ocurrir tras el análisis
        visitando.add(senal)
        capa = 1 + max((dfs(e) for e in mapa[senal]["entradas"]), default=0)
        visitando.discard(senal)
        memo[senal] = capa
        return capa

    capa_compuerta = {}
    for c in compuertas:
        capa_compuerta[c["salida"]] = dfs(c["salida"])
    return capa_compuerta


# ---------------------------------------------------------------------------
# Generador principal del diagrama SVG.
# ---------------------------------------------------------------------------
def generar_svg(entradas, compuertas, titulo=""):
    """Devuelve el SVG completo del circuito (formas dibujadas con código)."""
    return _construir(entradas, compuertas, titulo)


def _construir(entradas, compuertas, titulo):
    Y0, FILA_SEP = 26, 32
    X_NODO_ENTRADA = 22
    X_ICONO_0 = 84
    CANAL = 46
    SEP_GATES = 84
    RAYOS = 7

    capa_compuerta = _capas(entradas, compuertas)

    # Columnas: compuertas agrupadas por capa (conservando orden de escritura).
    columnas = {}
    for c in compuertas:
        columnas.setdefault(capa_compuerta[c["salida"]], []).append(c)

    # Posiciones x de cada columna (la capa 1 es la primera cola de compuertas).
    x_columna = {capa: X_ICONO_0 + (capa - 1) * (ICONA_ANCHO + CANAL) for capa in columnas}

    # Filas verticales (y) de cada señal. Primero las entradas, luego las
    # compuertas por columnas (salida = centro del icono + desplazamiento).
    y_senal = {}
    for i, e in enumerate(entradas):
        y_senal[e] = Y0 + i * FILA_SEP

    ultimo_y_por_columna = {}
    for capa in sorted(columnas):
        previo = None
        for c in columnas[capa]:
            filas_entrada = [y_senal[e] for e in c["entradas"]]
            if not filas_entrada:
                deseado = Y0
            else:
                ordenado = sorted(filas_entrada)
                m = len(ordenado) // 2
                deseado = ordenado[m] if len(ordenado) % 2 else (ordenado[m - 1] + ordenado[m]) / 2
            if previo is not None:
                deseado = max(deseado, previo + SEP_GATES)
            y_senal[c["salida"]] = deseado
            ultimo_y_por_columna[capa] = deseado
            previo = deseado

    # Posición absoluta (y) de cada compuerta: su salida está en y=32 del icono.
    y_compuerta = {}
    for c in compuertas:
        y_compuerta[c["salida"]] = y_senal[c["salida"]] - CUERPO_MEDIO

    # Nodo visible de cada señal (punto de unión de los cables).
    def nodo_senal(senal):
        if senal in entradas or senal not in capa_compuerta:
            return X_NODO_ENTRADA, y_senal[senal], senal
        capa = capa_compuerta[senal]
        return x_columna[capa] + PUNTA_SALIDA + 26, y_senal[senal], senal

    # Escala del lienzo.
    x_max = max((x_columna[c] + ICONA_ANCHO + 70 for c in x_columna), default=0)
    y_max = 0
    for capa in columnas:
        for c in columnas[capa]:
            y_max = max(y_max, y_compuerta[c["salida"]] + ICONA_ALTO + 10)
    for senal in list(y_senal) + [e for e in entradas]:
        y_max = max(y_max, y_senal[senal] + 30)
    ancho = max(x_max, X_ICONO_0 + 118)
    alto = max(y_max, Y0 + len(entradas) * FILA_SEP + 30) + 16

    l = []
    l.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{ancho}" height="{alto}" '
             f'viewBox="0 0 {ancho} {alto}">')
    if titulo:
        l.append(f'  <text x="{ancho/2}" y="16" text-anchor="middle" font-family="DejaVu Sans, Arial" '
                 f'font-size="13" fill="#111">{titulo}</text>')

    # Obsesión: fondo transparente por defecto (sin rect).
    l.append('  <g stroke="#1a1a1a" stroke-width="2" fill="none" stroke-linecap="round">')

    # Cables: entradas de cada compuerta (rutas ortogonales hasta sus pines).
    # Cada cable recibe un carril propio en el canal de su columna de destino,
    # para que los verticales de señales distintas nunca se superpongan.
    cables = []
    for c in compuertas:
        gy = y_compuerta[c["salida"]]
        capa = capa_compuerta[c["salida"]]
        pin_x = x_columna[capa]
        k = len(c["entradas"])
        for j, senal in enumerate(c["entradas"]):
            y_pin = gy + CUERPO_TOP + 1 + (CUERPO_BOTTOM - CUERPO_TOP - 2) * (j + 1) / (k + 1)
            xn, yn, _ = nodo_senal(senal)
            cables.append({"xn": xn, "yn": yn, "pin_x": pin_x, "y_pin": y_pin})
            cables[-1]["carril"] = None

    # Asignación de carriles: el cable con el pin más bajo (mayor y) se coloca
    # más cerca de la compuerta; así sus verticales largos quedan a la derecha.
    por_columna = {}
    for c in cables:
        por_columna.setdefault(c["pin_x"], []).append(c)
    for pin_x, lista in por_columna.items():
        ordenada = sorted(lista, key=lambda d: d["y_pin"], reverse=True)
        for rango, d in enumerate(ordenada):
            carril = pin_x - 26 - 12 * rango
            d["carril"] = max(carril, d["xn"])

    l.append('  <g stroke="#1a1a1a" stroke-width="2" fill="none" stroke-linecap="round">')
    for d in cables:
        if abs(d["yn"] - d["y_pin"]) < 0.001:
            ruta = f'M{d["xn"]},{d["yn"]} H{d["pin_x"]}'
        else:
            ruta = f'M{d["xn"]},{d["yn"]} H{d["carril"]} V{d["y_pin"]} H{d["pin_x"]}'
        l.append(f'    <path d="{ruta}"/>')

    # Cables: salida de cada compuerta hasta su nodo de señal.
    for c in compuertas:
        xn, yn, _ = nodo_senal(c["salida"])
        gy = y_compuerta[c["salida"]]
        capa = capa_compuerta[c["salida"]]
        origen = x_columna[capa] + PUNTA_SALIDA
        if abs(origen - xn) > 0.001:
            l.append(f'    <path d="M{origen},{gy+CUERPO_MEDIO} H{xn}"/>')

    l.append('  </g>')

    # Compuertas: cuerpo + patas de entrada/salida + burbuja + etiqueta.
    for c in compuertas:
        gy = y_compuerta[c["salida"]]
        capa = capa_compuerta[c["salida"]]
        gx = x_columna[capa]
        tipo = c["compuerta"]
        k = len(c["entradas"])
        cuerpo = _cuerpo_compuerta(tipo)
        l.append(f'    <g transform="translate({gx},{gy})" stroke="#1a1a1a" '
                 f'stroke-width="2.4" fill="none" stroke-linejoin="round">')
        # Patas de entrada (desde el borde del icono hasta el cuerpo).
        for j in range(k):
            y_pin = CUERPO_TOP + 1 + (CUERPO_BOTTOM - CUERPO_TOP - 2) * (j + 1) / (k + 1)
            x_cuerpo = _entrada_cuerpo(tipo, y_pin)
            l.append(f'      <path d="M0,{y_pin:.1f} H{x_cuerpo:.1f}"/>')
        # Pata de salida (desde el cuerpo hasta la punta).
        l.append(f'      <path d="M{_salida_cuerpo(tipo)},{CUERPO_MEDIO} H{PUNTA_SALIDA}"/>')
        # Cuerpo de la compuerta.
        l.append(f'      <path d="{cuerpo}"/>')
        # Burbuja de negación.
        burbuja = _burbuja(tipo)
        if burbuja:
            l.append(f'      <circle cx="{burbuja}" cy="{CUERPO_MEDIO}" r="5"/>')
        # Etiqueta con el nombre de la compuerta.
        l.append(f'      <text x="{ICONA_ANCHO/2}" y="{CUERPO_BOTTOM+18}" text-anchor="middle" '
                 f'font-family="DejaVu Sans, Arial" font-size="12" fill="#1a1a1a">{tipo}</text>')
        l.append('    </g>')

    # Nodos de las señales (entradas con nombre; salidas con punto de unión).
    for e in entradas:
        x, y, nombre = nodo_senal(e)
        l.append(f'  <circle cx="{x}" cy="{y}" r="{RAYOS}" fill="#fff" stroke="#1a1a1a" stroke-width="1.8"/>')
        l.append(f'  <text x="{x}" y="{y+19}" text-anchor="middle" font-family="DejaVu Sans, Arial" '
                 f'font-size="11" fill="#111">{nombre}</text>')
    for c in compuertas:
        x, y, nombre = nodo_senal(c["salida"])
        l.append(f'  <circle cx="{x}" cy="{y}" r="4.5" fill="#fff" stroke="#1a1a1a" stroke-width="1.4"/>')
        l.append(f'  <text x="{x}" y="{y+17}" text-anchor="middle" font-family="DejaVu Sans, Arial" '
                 f'font-size="10" fill="#333">{nombre}</text>')

    l.append('</svg>')
    return "\n".join(l) + "\n"