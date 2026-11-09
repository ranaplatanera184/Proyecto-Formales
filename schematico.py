# ============================================================================
# DIAGRAMA ESQUEMÁTICO DEL CIRCUITO CON SCHEMDRAW
# ----------------------------------------------------------------------------
# Dibuja el circuito como un esquema electrónico real (estilo clásico):
#   - Compuertas lógicas con pines exactos (schemdraw.logic): los cables se
#     conectan siempre al pin in1/in2/out (anchors) de cada compuerta.
#   - Layout por columnas de nivel (profundidad de cada compuerta).
#   - Orden por baricentro: dentro de cada columna las compuertas se ordenan
#     por la posición media de sus entradas (heurística del baricentro),
#     iterada de izquierda a derecha y de derecha a izquierda para reducir
#     cruces. Las entradas se reordenan según su primer uso.
#   - Espaciado dinámico: separación vertical mínima de 2.5 unidades entre
#     compuertas de una columna (crece con los cables que la atraviesan) y
#     separación horizontal de 3 + 0.4 * (cables que cruzan el canal).
#   - Ruteo por canales: entre columnas se reserva un canal y cada señal que
#     lo atraviesa usa una coordenada x propia (un "track" por señal y por
#     canal), con segmentos ortogonales. Los cables nunca entran en el cuerpo
#     de una compuerta ajena: los cruces de canal se ajustan a carriles libres.
#     El punto (logic.Dot) solo se dibuja en bifurcaciones reales, uno por
#     señal y por posición.
#   - Terminales elípticos para las entradas (izquierda, espaciado uniforme)
#     y las salidas (derecha).
#   - Etiquetas de las señales intermedias sobre el cable, en fuente pequeña
#     y con fondo de color (bgcolor) detrás para que la línea no las atraviese.
#
# Estilo centralizado (una sola paleta): el color de línea, el relleno de las
# compuertas y el fondo se aplican con d.config() a compuertas, cables y
# puntos a la vez. El fondo es un color sólido (param `fondo`) y las
# líneas/relleno/etiquetas se adaptan por luminosidad del fondo (claro/oscuro).
#
# El DOT de Graphviz se sigue generando en semantico.generar_dot() como
# respaldo textual; este módulo solo exporta SVG y PNG vectoriales.
# ============================================================================

import math
import os
import tempfile

import matplotlib
matplotlib.use("Agg")

import schemdraw
from schemdraw import logic
import schemdraw.elements as elm
from schemdraw.elements import Element
import schemdraw.segments as seg


RUTA_DIAGRAMA = "diagrama_circuito"
RUTA_DIAGRAMA_SVG = "diagrama_circuito.svg"
RUTA_DIAGRAMA_PNG = "diagrama_circuito.png"

# Fondo del diagrama y margen (espacio entre el circuito y el borde).
FONDO = "#FFFFFF"   # color de fondo por defecto
MARGEN = 1.0        # al menos 1 unidad de schemdraw de margen en los 4 lados

# ---------------------------------------------------------------------------
# Geometría del esquema (unidades de schemdraw).
# ---------------------------------------------------------------------------
X_ENTRADA = 0.0              # centro de las elipses de entrada
X_PRIMERA_COMPUERTA = 2.4    # columna (in1) mínima de las compuertas de nivel 0
BASE_GAP = 3.0               # separación horizontal base entre columnas
GAP_POR_CABLE = 0.4          # +0.4 unidades por cada cable que cruza el canal
Y_SEP_MIN = 2.5              # separación vertical mínima entre compuertas
Y_SEP_ENTRADAS = 2.5         # separación uniforme entre terminales de entrada
GAP_REFUERZO = 0.30          # holgura extra para los tracks del canal
PASO_TRACK = 0.42            # paso horizontal entre tracks de un mismo canal
RX_TERMINAL = 0.80           # radio x por defecto de los terminales (ancho 1.6)
RY_TERMINAL = 0.45           # radio y de los terminales (alto 0.9)
FS_TERMINAL = 12             # fuente (pt) de las etiquetas de los terminales
FS_SEÑAL = 8                 # fuente (pt) de las etiquetas sobre los cables
SEPARACION_SALIDA = 0.8      # hueco libro entre burbuja y borde de la elipse



# ---------------------------------------------------------------------------
# Paleta central (estilos). Una sola fuente de color/relleno/fondo.
# ---------------------------------------------------------------------------
ESTILO_CLARO = {
    "nombre": "claro",
    "linea": "#111827",      # color de compuertas, cables y puntos
    "relleno": "#f3f4f6",    # relleno del cuerpo de las compuertas
    "fondo": "blanco",       # "blanco" o "transparente"
    "grosor": 2.0,           # lw unificado para cables y compuertas
    "texto": "#374151",      # rótulos (nombres de compuerta y de señales)
}

ESTILO_OSCURO = {
    "nombre": "oscuro",
    "linea": "#e5e7eb",
    "relleno": "#334155",
    "fondo": "transparente",
    "grosor": 2.0,
    "texto": "#d1d5db",
}

ESTILO_ENTRADA = {"relleno": "#e8f0fe", "borde": "#4285f4", "texto": "#1967d2"}
ESTILO_SALIDA = {"relleno": "#e6f4ea", "borde": "#34a853", "texto": "#137333"}

TIPO_INVERTIDO = {"NOT", "NAND", "NOR", "XNOR"}


def _luminosidad(color):
    """Luminosidad percibida de un color hex: 0 = negro, 1 = blanco."""
    c = color.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255


def _esquema_para_fondo(fondo):
    """Paleta con contraste automático según la luminosidad del color de fondo."""
    if _luminosidad(fondo) < 0.5:
        return ESTILO_OSCURO
    return ESTILO_CLARO


# ---------------------------------------------------------------------------
# Colores de fondo: validación y normalización (los usa la interfaz web para
# la ruta /background, de modo que un color inválido nunca llegue al diagrama).
# ---------------------------------------------------------------------------
def es_color_valido(color):
    """True si `color` es un color hex válido (#RGB o #RRGGBB)."""
    if not isinstance(color, str):
        return False
    c = color.strip()
    if not c.startswith("#") or len(c) not in (4, 7):
        return False
    return all(ch in "0123456789abcdefABCDEF" for ch in c[1:])


def normalizar_color(color):
    """Devuelve el color en #RRGGBB (mayúsculas) o None si no es válido."""
    if not es_color_valido(color):
        return None
    c = color.strip().lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return "#" + c.upper()


def es_fondo_oscuro(color):
    """True si el color es oscuro (el esquema del diagrama se adapta a él)."""
    return _luminosidad(normalizar_color(color) or FONDO) < 0.5


# ---------------------------------------------------------------------------
# Compuerta: constructor y desplazamiento del pin in1 respecto a su origen.
# ---------------------------------------------------------------------------
def _constructor(tipo):
    """Devuelve una función que construye el elemento schemdraw del tipo."""
    if tipo == "NOT":
        return lambda **kw: logic.Not(**kw)
    if tipo == "NAND":
        return lambda **kw: logic.And(nand=True, **kw)
    if tipo == "NOR":
        return lambda **kw: logic.Or(nor=True, **kw)
    if tipo == "XOR":
        return lambda **kw: logic.Or(xor=True, **kw)
    if tipo == "XNOR":
        return lambda **kw: logic.Or(xor=True, nor=True, **kw)
    if tipo == "OR":
        return logic.Or
    return logic.And


def _desplazamiento_in1(tipo):
    """(dx, dy) del pin in1 respecto al origen del elemento (para alinear)."""
    elemento = _constructor(tipo)()
    pin = elemento.anchors.get("in1")
    if pin is None:
        raise ValueError(f"Elemento sin ancla in1 para {tipo}")
    return pin[0], pin[1]


def _metricas_gate(tipo, inputs):
    """(lead, trail) del símbolo respecto a su pin in1.

    lead  = cuánto se extiende el símbolo a la IZQUIERDA de in1 (cable de
            entrada visible de las inversoras); los tracks del canal deben
            quedar a la izquierda de esta extensión para no entrar al cuerpo.
    trail = cuánto se extiende a la DERECHA de in1 (cuerpo + burbuja); los
            tracks del canal a la derecha deben quedar más lejos que esto.
    """
    elemento = _constructor(tipo)(inputs=inputs)
    an = elemento.anchors
    x0 = min(v[0] for k, v in an.items()
             if k == "start" or k.startswith("in"))
    in1x = an["in1"][0]
    extra = 0.12 if tipo in TIPO_INVERTIDO else 0.05
    return in1x - x0, an["out"][0] + extra


# ---------------------------------------------------------------------------
# Terminal: elipse rellena con etiqueta centrada.
# ---------------------------------------------------------------------------
class Terminal(Element):
    """Elipse de señal (entrada o salida) con texto centrado."""

    def __init__(self, *d, rx=RX_TERMINAL, ry=RY_TERMINAL, relleno="#e8f0fe",
                 borde="#000000", texto="#1967d2", etiqueta="", grosor=2.0,
                 **kwargs):
        super().__init__(*d, **kwargs)
        self.etiqueta = etiqueta
        self.radio_x = rx
        puntos = [(rx * math.cos(2 * math.pi * k / 24),
                   ry * math.sin(2 * math.pi * k / 24)) for k in range(24)]
        self.segments.append(seg.SegmentPoly(puntos, closed=True,
                                             fill=relleno, color=borde,
                                             lw=grosor))
        if etiqueta:
            self.segments.append(seg.SegmentText((0, 0), etiqueta,
                                                 align=("center", "center"),
                                                 fontsize=FS_TERMINAL,
                                                 color=texto))


# ---------------------------------------------------------------------------
# Etiqueta sobre un cable con fondo de color (la línea no la atraviesa).
# ---------------------------------------------------------------------------
class EtiquetaSeñal(Element):
    """Texto con rectángulo de fondo (bgcolor) sobre un cable.

    El texto se define en coordenadas LOCALES (0,0) y el elemento se coloca
    con `.at(pos)`, igual que Terminal, para evitar el doble desplazamiento
    que sufriría si las coordenadas del SegmentText fueran absolutas.
    """

    def __init__(self, pos, texto, color, fondo, fontsize=FS_SEÑAL, **kwargs):
        super().__init__(**kwargs)
        self.segments.append(seg.SegmentText(
            (0, 0), texto, align=("center", "center"), color=color,
            bgcolor=fondo, fontsize=fontsize))
        self.pos = tuple(pos)


def _radio_x_etiqueta(etiqueta):
    """Radio x del terminal según la longitud de la etiqueta (fuente 12 pt)."""
    return max(RX_TERMINAL, 0.30 + 0.11 * len(etiqueta))


# ---------------------------------------------------------------------------
# Utilidades del esquema.
# ---------------------------------------------------------------------------
def _niveles(entradas, compuertas):
    """Profundidad (nivel/columna) de cada compuerta por orden topológico."""
    prof = {s: 0 for s in entradas}
    niveles = [None] * len(compuertas)
    cambio = True
    while cambio:
        cambio = False
        for i, c in enumerate(compuertas):
            profundidad = 1 + max((prof.get(s, 0) for s in c["entradas"]),
                                  default=0)
            if niveles[i] is None or niveles[i] != profundidad:
                niveles[i] = profundidad
                if prof.get(c["salida"], 0) < profundidad:
                    prof[c["salida"]] = profundidad
                cambio = True
    return niveles


def _producida_por(salida, compuertas):
    """Índice de la compuerta que produce la señal salida (o None)."""
    for i, c in enumerate(compuertas):
        if c["salida"] == salida:
            return i
    return None


def _muro_gate(absanchors, invertido):
    """Caja del cuerpo de una compuerta a partir de sus anclas absolutas."""
    xs = [v[0] for k, v in absanchors.items()
          if k == "start" or k.startswith("in")]
    ys = [v[1] for k, v in absanchors.items() if k.startswith("in")]
    x0 = min(xs) if xs else absanchors["out"][0]
    extra = 0.12 if invertido else 0.05
    return (x0, min(ys) - 0.62, absanchors["out"][0] + extra, max(ys) + 0.62)


def _cruza(a, b, muro):
    """True si el segmento a-b atraviesa el INTERIOR de la caja muro."""
    (x1, y1), (x2, y2) = a, b
    x0, y0, x1m, y1m = muro
    if abs(x1 - x2) < 1e-9:
        return x0 < x1 < x1m and min(y1, y2) < y1m and max(y1, y2) > y0
    if abs(y1 - y2) < 1e-9:
        return y0 < y1 < y1m and min(x1, x2) < x1m and max(x1, x2) > x0
    return False


# ---------------------------------------------------------------------------
# Construcción del esquema.
# ---------------------------------------------------------------------------

def _baricentro(i, compuertas, fila_señal):
    """Promedio de las filas de las entradas de la compuerta i."""
    ys = [fila_señal.get(s, 0.0) for s in compuertas[i]["entradas"]]
    return sum(ys) / len(ys) if ys else 0.0


def _carril(d, columna, muros_col, y):
    """Fila libre cerca de y en la columna: fuera de cuerpos y sin solaparse."""
    carriles = d.carriles.setdefault(columna, [])
    for salto in (0.0, 0.5, -0.5, 1.0, -1.0, 1.5, -1.5, 2.0, -2.0, 2.5, -2.5):
        cand = y + salto
        if any(y0 - 0.02 < cand < y1 + 0.02 for x0, y0, x1, y1 in muros_col):
            continue
        if any(abs(cand - u) < 0.14 for u in carriles):
            continue
        carriles.append(cand)
        return cand
    carriles.append(y)
    return y


def _ordenar_y_colocar(por_col, compuertas, entrada_y, sep_y, fila_señal):
    """Orden de las compuertas por baricentro y coordenadas y resultantes.

    - 1ª pasada izquierda->derecha siembra el orden inicial por el promedio de
      las filas de las entradas.
    - 4 iteraciones de baricentro: izquierda->derecha reordena y recoloca
      usando la fila de las señales ya colocadas; derecha->izquierda reordena
      usando la fila media de las compuertas consumidoras.
    - La colocación final separa filas con sep_y[columna] mínimo.
    """
    NC = max(por_col) + 1 if por_col else 0
    orden = {}
    centro = {}

    # 1ª siembra.
    for c in range(NC):
        col = por_col.get(c, [])
        col = sorted(col, key=lambda i: (_baricentro(i, compuertas, fila_señal), i))
        orden[c] = col
        prev = None
        for i in col:
            t = _baricentro(i, compuertas, fila_señal)
            if prev is not None and t < prev + sep_y[c]:
                t = prev + sep_y[c]
            centro[i] = t
            prev = t
            fila_señal[compuertas[i]["salida"]] = t

    # Iteraciones de baricentro.
    for _ in range(4):
        # Izquierda -> derecha: reordenar y recolocar.
        for c in range(NC):
            col = por_col.get(c, [])
            col = sorted(col, key=lambda i: (_baricentro(i, compuertas, fila_señal), i))
            orden[c] = col
            prev = None
            for i in col:
                t = _baricentro(i, compuertas, fila_señal)
                if prev is not None and t < prev + sep_y[c]:
                    t = prev + sep_y[c]
                centro[i] = t
                prev = t
                fila_señal[compuertas[i]["salida"]] = t

        # Derecha -> izquierda: solo reordenar por el baricentro de consumidores.
        for c in range(NC - 1, -1, -1):
            col = por_col.get(c, [])
            if not col:
                continue
            consumo = {}
            for i in col:
                fila_cons = [centro[j] for j in _consumidores(i, compuertas,
                                                              por_col)]
                consumo[i] = (sum(fila_cons) / len(fila_cons)) if fila_cons \
                    else centro.get(i, 0.0)
            col = sorted(col, key=lambda i: (consumo[i], i))
            orden[c] = col

    # Colocación final (estable) con las filas definitivas.
    for c in range(NC):
        col = orden.get(c, [])
        prev = None
        for i in col:
            t = _baricentro(i, compuertas, fila_señal)
            if prev is not None and t < prev + sep_y[c]:
                t = prev + sep_y[c]
            centro[i] = t
            prev = t
            fila_señal[compuertas[i]["salida"]] = t

    return orden, centro


def _consumidores(i, compuertas, por_col):
    """Índices de las compuertas que consumen la salida de la compuerta i."""
    salida = compuertas[i]["salida"]
    res = []
    for c, lista in por_col.items():
        for j in lista:
            if salida in compuertas[j]["entradas"]:
                res.append(j)
    return res


def generar_diagrama(entradas, compuertas, estilo=None, fondo=FONDO):
    """Devuelve un Drawing de schemdraw con el esquema completo del circuito.

    `estilo` es un dict de ESTILO_CLARO/ESTILO_OSCURO (paleta central de
    colores). Si no se pasa, se elige automáticamente por la luminosidad de
    `fondo`. `fondo` es el color de fondo del diagrama (no transparente) y
    `MARGEN` el espacio en blanco entre el circuito y el borde de la imagen.
    """
    estilo = estilo if estilo is not None else _esquema_para_fondo(fondo)

    d = schemdraw.Drawing(
        transparent=False,
        color=estilo["linea"], lw=estilo["grosor"], fill=estilo["relleno"],
        bgcolor=fondo)
    d.config(bgcolor=fondo, margin=MARGEN)
    d.wires = []
    d.terminales = []
    d.puntos = set()
    d.carriles = {}
    d.gate_muros = []
    d.pin_punto = {}
    d.out_punto = {}
    d.track = {}
    d.colx = {}

    niveles = _niveles(entradas, compuertas)
    NC = max(niveles) if niveles else 0   # número de columnas de compuertas
    por_col = {}
    for i, lv in enumerate(niveles):
        por_col.setdefault(lv - 1, []).append(i)

    # Consumidores y productores de cada señal.
    consum = {}
    for i, c in enumerate(compuertas):
        col = niveles[i] - 1
        for k, s in enumerate(c["entradas"]):
            consum.setdefault(s, []).append((col, k, i))

    prod_col = {s: -1 for s in entradas}
    for i, c in enumerate(compuertas):
        prod_col[c["salida"]] = niveles[i] - 1

    usadas = set()
    for c in compuertas:
        usadas.update(c["entradas"])
    salidas_finales = [c["salida"] for c in compuertas
                       if c["salida"] not in usadas]

    for s in salidas_finales:
        i = _producida_por(s, compuertas)
        consum.setdefault(s, []).append((NC, 0, i))
        prod_col[s] = niveles[i] - 1

    max_cons = {s: max(col for col, _, _ in consum[s]) for s in consum}
    señales = sorted(consum.keys(), key=lambda s: (prod_col[s], s))

    def _cruza_canal(g):
        return [s for s in señales
                if prod_col[s] <= g and max_cons[s] >= g + 1]

    n_cruce = {g: len(_cruza_canal(g)) for g in range(-1, NC + 1)}

    # Reordena las entradas según su primer uso por las compuertas del nivel 1.
    ent_orden = []
    vistos = set()
    for i in por_col.get(0, []):
        for s in compuertas[i]["entradas"]:
            if s in entradas and s not in vistos:
                ent_orden.append(s)
                vistos.add(s)
    ent_orden += [s for s in entradas if s not in vistos]
    n = len(entradas)
    entrada_y = {s: ((n - 1) / 2 - k) * Y_SEP_ENTRADAS
                 for k, s in enumerate(ent_orden)}

    # Columnas x de compuertas (anchura del canal: 3 + 0.4 * cables que cruzan).
    # Cada canal debe además dejar sitio para los tracks: a la derecha de los
    # cuerpos de la columna izquierda y a la izquierda del cable de entrada
    # visible de la columna derecha (lead).
    col_lead = {}
    col_trail = {}
    for c in range(NC):
        if not por_col.get(c):
            col_lead[c] = 0.0
            col_trail[c] = 2.1
            continue
        leads = []
        trails = []
        for i in por_col[c]:
            lead, trail = _metricas_gate(compuertas[i]["compuerta"],
                                         len(compuertas[i]["entradas"]))
            leads.append(lead)
            trails.append(trail)
        col_lead[c] = max(leads)
        col_trail[c] = max(trails)

    rx_in = {s: _radio_x_etiqueta(s) for s in entradas}
    rx_max_in = max(rx_in.values()) if entradas else RX_TERMINAL
    colx = {0: max(
        X_PRIMERA_COMPUERTA,
        X_ENTRADA + rx_max_in + 0.55 +
        PASO_TRACK * max(0, n_cruce[-1] - 1) + col_lead[0])}
    for g in range(0, NC - 1):
        n = n_cruce[g]
        ancho = max(
            BASE_GAP + GAP_POR_CABLE * n + GAP_REFUERZO,
            PASO_TRACK * (n - 1) + col_lead[g + 1] + col_trail[g] + 0.70)
        colx[g + 1] = colx[g] + ancho

    # Separación vertical por columna: crece con los cables que la atraviesan.
    pasantes = {}
    for c in range(NC):
        pasantes[c] = len([s for s in señales
                           if prod_col[s] <= c - 1 and max_cons[s] >= c + 1])
    sep_y = {c: Y_SEP_MIN + 0.08 * pasantes.get(c, 0) for c in range(NC)}

    # Orden de baricentro + filas finales.
    fila_señal = dict(entrada_y)
    orden, centro = _ordenar_y_colocar(por_col, compuertas, entrada_y, sep_y,
                                       fila_señal)

    # Coloca los elementos de las compuertas y registra pines y muros.
    elementos = {}
    pin_punto = d.pin_punto       # (i, k) -> (x, y) absoluto del pin in{k+1}
    muros_col = {c: [] for c in range(NC)}
    lead_x = {}
    out_punto = d.out_punto
    for c in range(NC):
        for i in orden.get(c, []):
            tipo = compuertas[i]["compuerta"]
            y = centro[i]
            dx, dy = _desplazamiento_in1(tipo)
            elem = d.add(_constructor(tipo)(inputs=len(compuertas[i]["entradas"]))
                         .at((colx[c] - dx, y - dy)))
            elem.label(tipo, loc="top", ofst=0.07, fontsize=9,
                       color=estilo["texto"])
            elementos[i] = elem
            anc = elem.absanchors
            muro = _muro_gate(anc, tipo in TIPO_INVERTIDO)
            muros_col[c].append(muro)
            d.gate_muros.append((muro, tipo, i))
            xs = [v[0] for k, v in anc.items()
                  if k == "start" or k.startswith("in")]
            lead_x[i] = min(xs) if xs else anc["out"][0]
            out_punto[i] = tuple(anc["out"])
            for k in range(len(compuertas[i]["entradas"])):
                py = anc[f"in{k + 1}"][1]
                pin_punto[(i, k)] = (lead_x[i], py)

    # Puntos de conexión absolutos de cada consumidor.
    consum_pts = {}
    for s, lista in consum.items():
        consum_pts[s] = sorted(consum.get(s, []), key=lambda t: (t[0], t[2], t[1]))

    # Columna de salida (borde izquierdo de la elipse a 0.8 de la burbuja).
    rx_out = {s: _radio_x_etiqueta(s) for s in salidas_finales}
    rx_max_out = max(rx_out.values()) if salidas_finales else RX_TERMINAL
    if salidas_finales:
        xs_out = [out_punto[prod][0] + 0.12 for prod in
                  [_producida_por(s, compuertas) for s in salidas_finales]]
        max_out = max(xs_out)
        x_sal = max_out + SEPARACION_SALIDA + rx_max_out + \
            0.42 * (len(salidas_finales) - 1) + 0.25
    else:
        x_sal = colx[NC - 1] + 2.0 if NC else 2.0

    # Borde izquierdo del espacio libre de cada canal (base de los tracks):
    # justo a la izquierda del cable de entrada visible de la columna derecha.
    der = {}
    for g in range(-1, NC - 1):
        der[g] = colx[g + 1] - col_lead[g + 1] - 0.25
    der[NC - 1] = x_sal - rx_max_out - 0.25

    # Asignación de track: un x distinto por señal y por canal.
    idx_track = {g: 0 for g in range(-1, NC)}
    track = {s: {} for s in señales}
    for s in señales:
        for g in range(prod_col[s], max_cons[s]):
            track[s][g] = der[g] - idx_track[g] * PASO_TRACK
            idx_track[g] += 1

    # Ruteo de cada señal por canales.
    etiquetas = []
    for s in señales:
        # Punto de origen (borde de línea de entrada o pin out).
        if s in entrada_y:
            origen = (X_ENTRADA + rx_in[s], entrada_y[s])
        else:
            origen = out_punto[_producida_por(s, compuertas)]

        # Consumidores agrupados por columna; los terminales finales usan la
        # columna fantasma NC (pin en el borde izquierdo de la elipse).
        por_col_cons = {}
        for (col, k, i) in consum_pts[s]:
            if col == NC:
                px_term = x_sal - rx_out.get(s, RX_TERMINAL)
                por_col_cons.setdefault(col, []).append((px_term, centro[i]))
            else:
                por_col_cons.setdefault(col, []).append(pin_punto[(i, k)])

        pasos = {col: sorted(pts, key=lambda p: p[1])
                 for col, pts in por_col_cons.items()}

        ox, oy = origen
        x, y = ox, oy
        segs_h = []
        segs_v = []
        act = {}
        ganchos = {}

        for g in range(prod_col[s], max_cons[s]):
            tx = track[s][g]
            if g == prod_col[s]:
                segs_h.append(((ox, y), (tx, y)))
                x = tx
            else:
                lane = _carril(d, g, muros_col.get(g, []), y)
                segs_h.append(((x, lane), (tx, lane)))
                act.setdefault(g - 1, set()).add(lane)
                x = tx
                y = lane

            destinos = pasos.get(g + 1, [])
            if destinos:
                filas = {y}
                for (px, py) in destinos:
                    filas.add(py)
                    segs_h.append(((tx, py), (px, py)))
                    ganchos.setdefault(g, []).append((tx, py))
                act.setdefault(g, set()).update(filas)
                y = destinos[-1][1]
            else:
                act.setdefault(g, set()).add(y)

        # Dibuja los verticales del canal (una sola señal cada uno).
        for g, filas in act.items():
            lo, hi = min(filas), max(filas)
            if hi - lo > 1e-9:
                segs_v.append((track[s][g], lo, hi))
        for a, b in segs_h:
            _cable(d, a, b)
        for (xg, lo, hi) in segs_v:
            _cable(d, (xg, lo), (xg, hi))

        # Puntos solo en bifurcaciones reales: el carril vertical atraviesa el
        # punto (porque sigue a otro pin/curso) o dos pines caen en la misma
        # fila. Los codos finales (L) no llevan punto.
        for g, gs in ganchos.items():
            lo, hi = min(act[g]), max(act[g])
            for (xr, yr) in gs:
                fanout = [p[1] for p in gs].count(yr) >= 2
                sigue = lo < yr < hi          # el vertical continúa -> T real
                if (sigue or fanout) and len(act[g]) >= 2:
                    _punto(d, xr, yr)

        # Etiqueta de la señal intermedia sobre su primer tramo horizontal.
        if segs_h and s not in entrada_y and s not in salidas_finales:
            (x1, y1), (x2, y2) = segs_h[0]
            if abs(y1 - y2) < 1e-9:
                etiquetas.append(((x1 + x2) / 2, y1, s))

    # Terminales de entrada.
    for s in entradas:
        _agregar_terminal(d, s, X_ENTRADA, entrada_y[s], ESTILO_ENTRADA, estilo)

    # Terminales de salida alineados con su compuerta productora.
    for s in salidas_finales:
        i = _producida_por(s, compuertas)
        y_term = centro[i]
        _agregar_terminal(d, s, x_sal, y_term, ESTILO_SALIDA, estilo)

    # Etiquetas sobre cables (al final, por encima de todo el trazo).
    for (mx, my, label) in etiquetas:
        d.add(EtiquetaSeñal((mx, my), label, color=estilo["texto"],
                            fondo=fondo).at((mx, my)))

    d.track = track
    d.colx = colx
    return d


def _cable(d, a, b):
    """Cable recto (-) y lo registra para poder auditar la conexión."""
    d.wires.append((tuple(a), tuple(b)))
    return d.add(elm.Wire("-", xy=a, to=b))


def _punto(d, x, y):
    """Un único Dot por coordenada (evita puntos duplicados en bifurcaciones)."""
    clave = (round(x, 5), round(y, 5))
    if clave in d.puntos:
        return None
    d.puntos.add(clave)
    return d.add(elm.Dot().at((x, y)))


def _agregar_terminal(d, s, x, y, estilo_terminal, estilo):
    rx = _radio_x_etiqueta(s)
    d.add(Terminal(rx=rx, ry=RY_TERMINAL, relleno=estilo_terminal["relleno"],
                   borde=estilo_terminal["borde"], texto=estilo_terminal["texto"],
                   etiqueta=s, grosor=estilo["grosor"]).at((x, y)))
    d.terminales.append((s, x, y, rx, estilo_terminal))


# ---------------------------------------------------------------------------
# Exportación.
# ---------------------------------------------------------------------------
def exportar(circuito, base=RUTA_DIAGRAMA, escala=1, escribir_archivos=True):
    """Guarda el PNG (300 dpi * escala) y el SVG. Devuelve el contenido SVG.

    El tamaño de la figura es proporcional al layout (schemdraw calcula el
    lienzo a partir del bounding box de los elementos y del margen). El fondo
    nunca sale transparente: el Drawing lleva `bgcolor` configurado y se
    exporta con transparent=False de modo que PNG y SVG muestran el color de
    fondo en toda la imagen (incluido el margen). El SVG es 100% vectorial.

    Con `escribir_archivos=False` no se deja ningún archivo en el disco: la
    exportación se hace en una carpeta temporal y solo se devuelve el SVG
    (lo usa la interfaz web, que no debe ensuciar el directorio del usuario).
    """
    if not escribir_archivos:
        with tempfile.TemporaryDirectory() as temporal:
            return exportar(circuito, base=os.path.join(temporal, RUTA_DIAGRAMA),
                            escala=escala)

    ruta_png = base + ".png"
    ruta_svg = base + ".svg"
    try:
        circuito.save(ruta_png, transparent=False, dpi=300 * escala)
        circuito.save(ruta_svg, transparent=False)
        with open(ruta_svg, encoding="utf-8") as archivo:
            return archivo.read()
    except Exception:
        # Con la variable JACE_DEBUG=1 se muestra el error real (por ejemplo
        # dentro del ejecutable, donde fallan los recursos de matplotlib).
        if os.environ.get("JACE_DEBUG"):
            import traceback
            traceback.print_exc()
        return ""
