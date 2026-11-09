import sys
import os
import json
import glob
import itertools

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from semantico import AnalizadorSemantico
from gestor_reglas import GestorReglas
from ImplementacionAnalisisLexico import tokenizar_circuito
from AnalisisSintactico import AnalisisSintactico
import expresiones
from expresiones import generar_expresiones, LIMITE_EXPANDIDA

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
class Bit(int):
    """0 o 1 con operadores lógicos, para poder evaluar con `eval`.

    `~` (el sustituto de `!`) devuelve 1 - valor, de modo que nunca produce el
    número negativo que daría el `~` de Python sobre enteros. Su precedencia es
    mayor que la de `&`, `^` y `|`, igual que la de `¬` en el enunciado.
    """

    def __and__(self, otro):
        return Bit(1 if int(self) & int(otro) else 0)

    def __or__(self, otro):
        return Bit(1 if int(self) | int(otro) else 0)

    def __xor__(self, otro):
        return Bit(1 if int(self) ^ int(otro) else 0)

    def __invert__(self):
        return Bit(1 - int(self))


def _reglas():
    with open(os.path.join(RAIZ, "reglas.json"), "r", encoding="utf-8") as archivo:
        return json.load(archivo)["compuertas"]


def _modelo(entradas, compuertas):
    """Semántico validado, listo para `generar_expresiones`."""
    semantico = AnalizadorSemantico(entradas, compuertas, _reglas())
    assert semantico.revisar() == []
    return semantico


def _compuertas(*filas):
    """(compuerta, entradas, salida) -> lista de compuertas con número de línea."""
    return [{"compuerta": nombre, "entradas": entradas, "salida": salida, "linea": i + 2}
            for i, (nombre, entradas, salida) in enumerate(filas)]


def _circuito(texto):
    """Compila un circuito en JACE y devuelve (modelo, resultado).

    Devuelve (None, resultado) si el circuito tiene errores, que es el caso de
    varios archivos de `pruebas/`: son justo los que no tienen expresiones.
    """
    gestor = GestorReglas()
    codigo = "\n".join(linea.strip() for linea in texto.strip().split("\n")
                       if linea.strip() and not linea.strip().startswith("#"))
    resultado = gestor.analizar(codigo, imprimir=False, con_diagrama=False,
                                escribir_archivos=False, registrar=False)
    if not resultado["exito"]:
        return None, resultado

    tokens, _ = tokenizar_circuito(
        codigo, palabras_reservadas=gestor.obtener_palabras_reservadas())
    estructura = AnalisisSintactico(tokens, gestorReglas=gestor).construir_circuito()
    modelo = AnalizadorSemantico(estructura["entradas"], estructura["compuertas"],
                                 gestor.reglas["compuertas"])
    assert modelo.revisar() == []
    return modelo, resultado


def _circuitos_de_pruebas():
    """(nombre, modelo, resultado) de los circuitos válidos de `pruebas/`."""
    for ruta in sorted(glob.glob(os.path.join(RAIZ, "pruebas", "*.jace"))):
        modelo, resultado = _circuito(open(ruta, encoding="utf-8").read())
        if modelo is not None:
            yield os.path.basename(ruta), modelo, resultado


def _evaluar(expandida_ascii, entradas):
    """Evalúa la forma ASCII con `Bit` y devuelve 0 o 1."""
    return int(bool(eval(expandida_ascii.replace("!", "~"),
                         {"__builtins__": {}},
                         {nombre: Bit(valor) for nombre, valor in entradas.items()})))


# ---------------------------------------------------------------------------
# La expresión expandida debe ser equivalente a la tabla de verdad
# ---------------------------------------------------------------------------
def test_expandida_del_ejemplo_es_exacta():
    semantico = _modelo(["a", "b", "c"], _compuertas(
        ("AND", ["a", "b"], "x1"),
        ("OR", ["x1", "c"], "x2"),
        ("XOR", ["x2", "a"], "x3"),
        ("NAND", ["x3", "b"], "salida"),
    ))
    assert generar_expresiones(semantico)["salida"]["expandida"] == \
        "¬(((a · b + c) ⊕ a) · b)"
    assert generar_expresiones(semantico, "ascii")["salida"]["expandida"] == \
        "!(((a & b | c) ^ a) & b)"


def test_expandida_de_not():
    semantico = _modelo(["a"], _compuertas(("NOT", ["a"], "salida")))
    assert generar_expresiones(semantico)["salida"]["expandida"] == "¬(a)"
    assert generar_expresiones(semantico, "ascii")["salida"]["expandida"] == "!(a)"


def test_expandida_de_not_anidado():
    semantico = _modelo(["a"], _compuertas(
        ("NOT", ["a"], "x"),
        ("NOT", ["x"], "salida"),
    ))
    assert generar_expresiones(semantico)["salida"]["expandida"] == "¬(¬(a))"


def test_expandida_de_xnor():
    semantico = _modelo(["a", "b"], _compuertas(("XNOR", ["a", "b"], "salida")))
    assert generar_expresiones(semantico)["salida"]["expandida"] == "¬(a ⊕ b)"


def test_expandida_de_nor():
    semantico = _modelo(["a", "b", "c"], _compuertas(("NOR", ["a", "b", "c"], "salida")))
    assert generar_expresiones(semantico)["salida"]["expandida"] == "¬(a + b + c)"


def test_expandida_de_nand():
    semantico = _modelo(["a", "b"], _compuertas(("NAND", ["a", "b"], "salida")))
    assert generar_expresiones(semantico)["salida"]["expandida"] == "¬(a · b)"


def test_los_parentesis_de_xor_y_or_no_sobran():
    """Un `+` dentro de un `·` sí necesita paréntesis; un `·` dentro de un `+` no.

    Con solo mirar la precedencia, `a · b + c` parece suficiente, pero el
    enunciado pide explícitos los paréntesis alrededor de `⊕` y `+`.
    """
    or_de_and = _modelo(["a", "b", "c"], _compuertas(
        ("OR", ["a", "b"], "x"), ("AND", ["x", "c"], "salida")))
    assert generar_expresiones(or_de_and)["salida"]["expandida"] == "(a + b) · c"

    or_de_or = _modelo(["a", "b", "c"], _compuertas(
        ("OR", ["a", "b"], "x"), ("OR", ["x", "c"], "salida")))
    assert generar_expresiones(or_de_or)["salida"]["expandida"] == "(a + b) + c"


# ---------------------------------------------------------------------------
# Precedencia y paréntesis
# ---------------------------------------------------------------------------
def test_parentesis_alrededor_de_xor_y_or():
    """`¬` > `·` > `⊕` > `+`: los operandos `⊕` y `+` siempre llevan paréntesis."""
    # Un `·` dentro de un `+` ya se agrupa solo por precedencia: sobra el paréntesis.
    and_de_or = _modelo(["a", "b", "c"], _compuertas(
        ("AND", ["a", "b"], "x"), ("OR", ["x", "c"], "salida")))
    assert generar_expresiones(and_de_or)["salida"]["expandida"] == "a · b + c"

    # En cambio un `+` o un `⊕` dentro de otro operador sí lo necesitan.
    or_de_xor = _modelo(["a", "b", "c"], _compuertas(
        ("OR", ["a", "b"], "x"), ("XOR", ["x", "c"], "salida")))
    assert generar_expresiones(or_de_xor)["salida"]["expandida"] == "(a + b) ⊕ c"

    and_de_xor = _modelo(["a", "b", "c"], _compuertas(
        ("AND", ["a", "b"], "x"), ("XOR", ["x", "c"], "salida")))
    assert generar_expresiones(and_de_xor)["salida"]["expandida"] == "a · b ⊕ c"

    or_de_and = _modelo(["a", "b", "c"], _compuertas(
        ("OR", ["a", "b"], "x"), ("AND", ["x", "c"], "salida")))
    assert generar_expresiones(or_de_and)["salida"]["expandida"] == "(a + b) · c"


def test_and_de_and_no_necesita_parentesis():
    """`·` y `·` se evalúan de izquierda a derecha, así que `a · b · c` basta."""
    semantico = _modelo(["a", "b", "c"], _compuertas(
        ("AND", ["a", "b"], "x"), ("AND", ["x", "c"], "salida")))
    assert generar_expresiones(semantico)["salida"]["expandida"] == "a · b · c"


def test_precedencia_de_la_negacion_sobre_el_and():
    """`¬a · b` es `(¬a) · b`, no `¬(a · b)`.

    Este es el caso que rompe si se traduce `!` a `not` en vez de `~`: en Python
    `not` liga menos que `&`, de modo que `not a & b` se leería como
    `not (a & b)` y daría un resultado distinto.
    """
    semantico = _modelo(["a", "b"], _compuertas(("NOT", ["a"], "salida")))
    expandida = generar_expresiones(semantico, "ascii")["salida"]["expandida"]

    assert expandida == "!(a)"
    for a, b in itertools.product([0, 1], repeat=2):
        assert _evaluar(expandida, {"a": a, "b": b}) == 1 - a

    # El orden de las operaciones se lee directamente del texto generado.
    negada_y_and = _modelo(["a", "b"], _compuertas(
        ("NOT", ["a"], "x"), ("AND", ["x", "b"], "salida")))
    assert generar_expresiones(negada_y_and)["salida"]["expandida"] == "¬(a) · b"


# ---------------------------------------------------------------------------
# Forma intermedia
# ---------------------------------------------------------------------------
def test_intermedia_va_en_orden_topologico():
    semantico = _modelo(["a", "b", "c"], _compuertas(
        ("AND", ["a", "b"], "x1"),
        ("OR", ["x1", "c"], "x2"),
        ("XOR", ["x2", "a"], "x3"),
        ("NAND", ["x3", "b"], "salida"),
    ))
    assert generar_expresiones(semantico)["salida"]["intermedia"] == [
        "x1 = a · b",
        "x2 = x1 + c",
        "x3 = x2 ⊕ a",
        "salida = ¬(x3 · b)",
    ]


def test_intermedia_usa_solo_las_compuertas_de_su_salida():
    """Con dos ramas independientes, cada salida muestra solo la suya."""
    semantico = _modelo(["a", "b", "c", "d"], _compuertas(
        ("AND", ["a", "b"], "x"),
        ("NOT", ["x"], "s1"),
        ("OR", ["c", "d"], "y"),
        ("NOT", ["y"], "s2"),
    ))
    resultado = generar_expresiones(semantico)
    assert resultado["s1"]["intermedia"] == ["x = a · b", "s1 = ¬(x)"]
    assert resultado["s2"]["intermedia"] == ["y = c + d", "s2 = ¬(y)"]


def test_intermedia_ascii_usa_los_simbolos_ascii():
    """El módulo solo devuelve `intermedia`; el `_ascii` lo arma el gestor."""
    semantico = _modelo(["a", "b"], _compuertas(("XNOR", ["a", "b"], "salida")))
    assert generar_expresiones(semantico, "ascii")["salida"]["intermedia"] == \
        ["salida = !(a ^ b)"]


def test_solo_las_salidas_finales_tienen_expresion():
    """Las señales intermedias no se listan: se ven dentro de la expandida."""
    semantico = _modelo(["a", "b"], _compuertas(
        ("AND", ["a", "b"], "x"), ("NOT", ["x"], "salida")))
    assert list(generar_expresiones(semantico)) == ["salida"]


# ---------------------------------------------------------------------------
# Límite de longitud
# ---------------------------------------------------------------------------
def _circuito_largo():
    """Cadena tipo Fibonacci: cada salida duplica el tamaño de la anterior."""
    n = 12
    filas = [("OR", ["e0", "e1"], "f2")]
    senales = ["e0", "e1", "f2"]
    for i in range(3, 15):
        filas.append(("OR", [senales[-2], senales[-1]], f"f{i}"))
        senales.append(f"f{i}")
    filas.append(("OR", [senales[-1], senales[-2]], "salida"))
    return _modelo([f"e{i}" for i in range(n)], _compuertas(*filas))


def test_expandida_demasiado_larga_se_omite_con_aviso():
    semantico = _circuito_largo()
    datos = generar_expresiones(semantico)["salida"]

    assert datos["expandida"] is None
    assert datos["aviso"].startswith("Expresión expandida demasiado larga (")
    assert datos["aviso"].endswith(" caracteres)")

    largo = int(datos["aviso"].split("(")[1].split(" ")[0])
    assert largo > LIMITE_EXPANDIDA


def test_la_intermedia_no_se_recorta_aunque_la_expandida_si():
    datos = generar_expresiones(_circuito_largo())["salida"]
    assert datos["expandida"] is None
    assert len(datos["intermedia"]) == 14
    assert datos["intermedia"][-1].startswith("salida = ")


def test_el_aviso_pertenece_solo_a_la_salida_larga():
    """Una salida corta no hereda el aviso de la larga del mismo circuito.

    La salida larga va declarada la primera a propósito: si el aviso se guardara
    en el contexto en vez de por señal, la corta (calculada después) lo heredaría.
    """
    filas = [("OR", ["e1", "e2"], "f3")]
    senales = ["e1", "e2", "f3"]
    for i in range(4, 15):
        filas.append(("OR", [senales[-2], senales[-1]], f"f{i}"))
        senales.append(f"f{i}")
    filas.append(("OR", [senales[-1], senales[-2]], "larga"))
    filas.append(("NOT", ["e0"], "corta"))

    resultado = generar_expresiones(_modelo([f"e{i}" for i in range(12)],
                                            _compuertas(*filas)))

    assert resultado["larga"]["expandida"] is None
    assert resultado["larga"]["aviso"] is not None

    assert resultado["corta"]["expandida"] == "¬(e0)"
    assert resultado["corta"]["aviso"] is None


def test_ambos_estilos_avisan_con_la_misma_longitud():
    """`¬`/`!`, `·`/`&`, `⊕`/`^` y `+`/`|` ocupan un carácter cada uno."""
    semantico = _circuito_largo()
    simbolos = generar_expresiones(semantico)["salida"]
    ascii_ = generar_expresiones(semantico, "ascii")["salida"]

    assert simbolos["aviso"] == ascii_["aviso"]
    assert simbolos["expandida"] is None and ascii_["expandida"] is None


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
def test_una_senal_reutilizada_se_expande_una_sola_vez():
    """La caché evita repetir el trabajo: 6 salidas que comparten `base` no
    expanden `base` seis veces."""
    filas = [("AND", ["a", "b"], "base")]
    for i in range(6):
        filas.append(("OR", ["base", f"e{i}"], f"u{i}"))
    for i in range(5):
        filas.append(("AND", [f"u{i}", f"u{i + 1}"], f"v{i}"))
    semantico = _modelo(["a", "b"] + [f"e{i}" for i in range(6)], _compuertas(*filas))

    contexto = expresiones._Contexto(semantico, expresiones.COMPERTAS)
    contexto._cuenta = 0
    for salida in contexto.salidas_finales:
        contexto.expandida_de(salida)

    # 12 compuertas en total, cada una expandida exactamente una vez. Sin caché
    # serían 18: las 6 salidas `u0..u5` pedirían `base` cada una.
    assert len(semantico.compuertas) == 12
    assert contexto._cuenta == 12


def test_la_cache_no_altera_el_texto_generado():
    """Que dos salidas compartan subexpresiones no debe cambiar el resultado."""
    semantico = _modelo(["a", "b", "c", "d"], _compuertas(
        ("AND", ["a", "b"], "x"),
        ("OR", ["x", "c"], "o1"),
        ("OR", ["x", "d"], "o2"),
    ))
    resultado = generar_expresiones(semantico)
    # `x` es un `·` dentro de un `+`: la precedencia ya agrupa bien, sin paréntesis.
    assert resultado["o1"]["expandida"] == "a · b + c"
    assert resultado["o2"]["expandida"] == "a · b + d"


def test_estilo_desconocido_da_error():
    semantico = _modelo(["a"], _compuertas(("NOT", ["a"], "salida")))
    try:
        generar_expresiones(semantico, "unicode")
    except ValueError as error:
        assert "unicode" in str(error)
    else:
        raise AssertionError("debía rechazar un estilo desconocido")


def test_cada_salida_expandida_es_una_sola_expresion():
    """La expandida no debe quedar partida en varios fragmentos."""
    semantico = _modelo(["a", "b", "c"], _compuertas(
        ("AND", ["a", "b"], "x1"),
        ("OR", ["x1", "c"], "x2"),
        ("XOR", ["x2", "a"], "x3"),
        ("NAND", ["x3", "b"], "salida"),
    ))
    expandida = generar_expresiones(semantico)["salida"]["expandida"]

    # Equilibra paréntesis y aparece una sola vez como asignable.
    assert expandida.count("(") == expandida.count(")")
    assert "\n" not in expandida
    assert expandida.count("¬") == 1


# ---------------------------------------------------------------------------
# Equivalencia con la tabla de verdad (eval)
# ---------------------------------------------------------------------------
def test_expandida_ascii_coincide_con_la_tabla_de_verdad():
    """Cada circuito de pruebas/, cada fila de su tabla, cada salida final."""
    comprobadas = 0

    for nombre, semantico, resultado in _circuitos_de_pruebas():
        senales = resultado["tabla_verdad"]["señales"]
        filas = resultado["tabla_verdad"]["filas"]

        for salida, datos in generar_expresiones(semantico, "ascii").items():
            if datos["expandida"] is None:
                continue
            columna = senales.index(salida)

            for fila in filas:
                entradas = {e: fila[senales.index(e)] for e in semantico.entradas}
                esperado = fila[columna]
                assert _evaluar(datos["expandida"], entradas) == esperado, \
                    f"{nombre} / {salida}"
                comprobadas += 1

    assert comprobadas == 1082, f"se esperaban 1082 filas, hubo {comprobadas}"


def test_expandida_ascii_coincide_en_todos_los_circuitos_de_pruebas():
    """Recorre todos los circuitos válidos sin fijar el número de filas."""
    validos = 0

    for _nombre, semantico, resultado in _circuitos_de_pruebas():
        validos += 1
        senales = resultado["tabla_verdad"]["señales"]

        for salida, datos in generar_expresiones(semantico, "ascii").items():
            if datos["expandida"] is None:
                continue
            columna = senales.index(salida)

            for fila in resultado["tabla_verdad"]["filas"]:
                entradas = {e: fila[senales.index(e)] for e in semantico.entradas}
                assert _evaluar(datos["expandida"], entradas) == fila[columna]

    assert validos >= 6, f"solo se analizaron {validos} circuitos válidos"


def test_los_circuitos_invalidos_de_pruebas_no_generan_expresiones():
    """Los archivos con errores se saltan, pero se comprueba que hay algunos."""
    total = len(glob.glob(os.path.join(RAIZ, "pruebas", "*.jace")))
    validos = sum(1 for _ in _circuitos_de_pruebas())

    assert validos < total, "ningún circuito de pruebas/ tiene errores"
    assert validos >= 6


def test_expandida_ascii_se_puede_evaluar_sin_builtins():
    """El texto generado no depende de nombres ni funciones del intérprete."""
    semantico, resultado = _circuito(
        "ENTRADA[a, b]\nNAND[a, b] -> salida\nXOR[a, b] -> otra")
    for datos in generar_expresiones(semantico, "ascii").values():
        if datos["expandida"] is None:
            continue
        # Con `__builtins__` vacío solo pueden aparecer las entradas del circuito.
        limpio = datos["expandida"].replace("(", " ").replace(")", " ")
        for operador in ("!", "&", "^", "|", "~"):
            limpio = limpio.replace(operador, " ")
        nombres = set(limpio.split())
        assert nombres <= set(semantico.entradas), nombres