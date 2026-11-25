"""Fase 2: recuperación de errores, mensajes claros, sugerencias y columnas.

Cubre los fallos C1 (el parser se detenía en el primer error), C2 (mensajes
con nombres internos), C3 (errores léxicos en cadena), C4 (NAND ambiguo en el
formato legado), C5 (compuertas muertas), C6 (ciclos ocultos por una
redefinición) y V3 (columna real en los errores semánticos).
"""

import json
import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from gestor_reglas import GestorReglas
from semantico import AnalizadorSemantico
from AnalisisSintactico import AnalisisSintactico, MAXIMO_ERRORES
from ImplementacionAnalisisLexico import analizar_lexico, tokenizar_circuito
from sugerencias import distancia, mas_parecido


def analizar(codigo):
    return GestorReglas().analizar(codigo, imprimir=False, con_diagrama=False,
                                   registrar=False)


def diagnosticos(codigo, severidad="error"):
    return [d for d in analizar(codigo)["diagnosticos"] if d["severidad"] == severidad]


def posiciones(lista):
    return [(d["linea"], d["columna"]) for d in lista]


def _reglas():
    with open(os.path.join(RAIZ, "reglas.json"), encoding="utf-8") as archivo:
        return json.load(archivo)["compuertas"]


# ---------------------------------------------------------------------------
# C1: recuperación en modo pánico
# ---------------------------------------------------------------------------
def test_tres_errores_sintacticos_dan_tres_diagnosticos_con_columna():
    codigo = ("ENTRADA[a, b, c]\n"
              "AND[a b] -> x\n"          # falta coma: columna 7 ('b')
              "OR[x, c] y\n"             # falta '->': columna 10 ('y')
              "NOT[y -> z\n")            # falta ']': columna 7 ('->')
    errores = diagnosticos(codigo)
    assert len(errores) == 3
    assert posiciones(errores) == [(2, 7), (3, 10), (4, 7)]
    assert all(d["fase"] == "sintáctico" for d in errores)
    assert errores[0]["mensaje"] == "falta una coma entre 'a' y 'b'"
    assert errores[1]["mensaje"] == "falta '->' antes del nombre de la salida 'y'"
    assert errores[2]["mensaje"] == "falta ']' para cerrar la lista de NOT"


def test_como_maximo_un_error_por_linea():
    errores = diagnosticos("ENTRADA[a]\nAND[a b c d] -> -> x")
    assert len(errores) == 1


def test_tope_de_errores():
    codigo = "ENTRADA[a]\n" + "\n".join("AND[a a] -> x" for _ in range(80))
    errores = diagnosticos(codigo)
    assert len(errores) == MAXIMO_ERRORES + 1
    assert "demasiados errores" in errores[-1]["mensaje"]


def test_sin_entrada_se_siguen_revisando_las_compuertas():
    errores = diagnosticos("AND[a, b] -> x\nOR[x c] -> y")
    assert len(errores) == 2
    assert "se esperaba ENTRADA" in errores[0]["mensaje"]
    assert errores[1]["mensaje"] == "falta una coma entre 'x' y 'c'"


def test_lexicos_y_sintacticos_se_reportan_juntos():
    codigo = "ENTRADA[a, b]\nAND[a, b] -> x$1\nOR[a b] -> y"
    errores = diagnosticos(codigo)
    assert [(d["fase"], d["linea"]) for d in errores] == [("léxico", 2), ("sintáctico", 3)]


def test_un_caracter_invalido_no_impide_analizar_el_resto_de_la_linea():
    # El '$' se reporta, y aun así se detecta la flecha que falta en la línea.
    errores = diagnosticos("ENTRADA[a, b]\nAND[a, b$] y")
    assert [d["fase"] for d in errores] == ["léxico", "sintáctico"]
    assert "falta '->'" in errores[1]["mensaje"]


def test_sin_errores_en_cadena_tras_un_error_lexico():
    errores = diagnosticos("ENTRADA[a, b]\nANDñ[a, b] -> x")
    assert len(errores) == 1
    assert errores[0]["fase"] == "léxico"


def test_la_semantica_no_corre_si_hay_errores_sintacticos():
    errores = diagnosticos("ENTRADA[a]\nAND[a z] -> x\nOR[a, zz] -> y")
    assert all(d["fase"] == "sintáctico" for d in errores)


def test_construir_circuito_conserva_la_interfaz_historica():
    tokens, _ = tokenizar_circuito("ENTRADA[a]\nAND[a b] -> x\nOR[a c] -> y")
    with pytest.raises(SyntaxError) as informacion:
        AnalisisSintactico(tokens).construir_circuito()
    assert str(informacion.value).startswith("Error sintáctico línea 2, columna 7")
    assert len(informacion.value.diagnosticos) == 2


# ---------------------------------------------------------------------------
# C2: mensajes en español claro y específicos
# ---------------------------------------------------------------------------
CASOS_SINTACTICOS = {
    "ENTRADA[a, b]\nAND[a b] -> x": "falta una coma entre 'a' y 'b'",
    "ENTRADA[a, b]\nAND[a, b] x": "falta '->' antes del nombre de la salida 'x'",
    "ENTRADA[a, b]\nAND[a, b -> x": "falta ']' para cerrar la lista de AND",
    "ENTRADA[a, b]\nAND[a, b]": "falta '->' y el nombre de la salida después de AND[...]",
    "ENTRADA[a, b]\nAND[a, b] ->": "falta el nombre de la salida después de '->'",
    "ENTRADA[a, b]\nAND[a, OR] -> x": "la palabra reservada OR no puede usarse como nombre de señal",
    "ENTRADA[a, b]\nAND[a, b] -> NOT": "la palabra reservada NOT no puede usarse como nombre de la salida",
    "ENTRADA[a, b]\nANDD[a, b] -> x": "'ANDD' no es una compuerta conocida",
    "ENTRADA[a]\nAND[] -> x": "la compuerta AND necesita al menos una entrada entre los corchetes",
    "ENTRADA[]\nNOT[a] -> x": "ENTRADA necesita al menos un nombre de entrada entre los corchetes",
    "ENTRADA[a, b]\nAND[a,, b] -> x": "sobra una coma: hay dos comas seguidas",
    "ENTRADA[a, b]\nAND[a, b,] -> x": "sobra la coma antes de ']'",
    "ENTRADA[a, b]\nAND a, b] -> x": "falta '[' después de AND",
    "ENTRADA[a]\nENTRADA[b]\nNOT[a] -> x": "se esperaba una compuerta y llegó ENTRADA",
    "ENTRADA[a]\nNOT[a] -> x y": "sobra el nombre 'y' al final de la instrucción",
}


@pytest.mark.parametrize("codigo,esperado", CASOS_SINTACTICOS.items())
def test_mensajes_especificos(codigo, esperado):
    errores = diagnosticos(codigo)
    assert errores, codigo
    assert esperado in errores[0]["mensaje"]


@pytest.mark.parametrize("codigo", list(CASOS_SINTACTICOS) + [
    "ENTRADA[a]\nNOT[a]] -> x", "ENTRADA a\nNOT[a] -> x", "x -> y", "[a]",
    "ENTRADA[a]\n-> x", "ENTRADA[a]\nNOT[[a]] -> x"])
def test_ningun_mensaje_usa_nombres_internos_de_token(codigo):
    for d in analizar(codigo)["diagnosticos"]:
        for interno in ("IDENTIFICADOR", "CORCHETE ABRE", "CORCHETE CIERRA", "COMA",
                        "FLECHA", "PALABRA RESERVADA"):
            assert interno not in d["mensaje"], (codigo, d["mensaje"])


def test_la_columna_de_la_coma_faltante_es_la_del_segundo_nombre():
    (error,) = diagnosticos("ENTRADA[a, b]\nAND[a b] -> x")
    assert (error["linea"], error["columna"]) == (2, 7)
    assert error["sugerencia"] == "escribe a, b"


# ---------------------------------------------------------------------------
# C3: una secuencia inválida contigua produce un solo error
# ---------------------------------------------------------------------------
def test_x_dolar_1_es_un_solo_error_en_la_columna_del_dolar():
    with open(os.path.join(RAIZ, "pruebas", "09_caracter_invalido.jace"), encoding="utf-8") as f:
        errores = diagnosticos(f.read())
    assert len(errores) == 1
    assert (errores[0]["linea"], errores[0]["columna"]) == (3, 15)
    assert errores[0]["mensaje"] == "el nombre 'x$1' contiene el carácter no reconocido '$'"


@pytest.mark.parametrize("lexema", ["x$$1", "@@", "a.b.c", "señal", "x😀y"])
def test_secuencias_invalidas_contiguas(lexema):
    _, _, errores = analizar_lexico(f"ENTRADA[a]\nNOT[a] -> {lexema}")
    assert len(errores) == 1, errores


def test_numeros_y_guion_bajo_al_inicio():
    for texto, mensaje in [("5x", "no puede empezar con un dígito"),
                           ("25", "el número '25' no es válido"),
                           ("_t1", "no puede empezar con '_'")]:
        _, _, errores = analizar_lexico(f"ENTRADA[a]\nNOT[a] -> {texto}")
        assert len(errores) == 1
        assert mensaje in errores[0].mensaje


def test_flecha_con_espacio_es_un_solo_error():
    errores = diagnosticos("ENTRADA[a]\nNOT[a] - > x")
    assert len(errores) == 1
    assert "no puede llevar espacios" in errores[0]["mensaje"]


def test_caracter_invisible_se_muestra_con_su_codigo():
    _, _, errores = analizar_lexico("ENTRADA[a​]")
    assert "U+200B" in errores[0].mensaje


# ---------------------------------------------------------------------------
# 2.3: sugerencias con distancia de Levenshtein
# ---------------------------------------------------------------------------
def test_distancia_de_levenshtein():
    assert distancia("ANDD", "AND") == 1
    assert distancia("kitten", "sitting") == 3
    assert distancia("", "abc") == 3
    assert distancia("abc", "abc") == 0
    assert distancia("flaw", "lawn") == 2


def test_mas_parecido():
    assert mas_parecido("ANDD", ["AND", "OR", "NAND"], ignorar_mayusculas=True) == "AND"
    assert mas_parecido("zz", ["a", "z"]) == "z"
    assert mas_parecido("x2", ["a", "x1"]) == "x1"
    assert mas_parecido("b", ["a"]) is None              # cambiar la única letra no es errata
    assert mas_parecido("salidaaa", ["salida", "x"]) == "salida"
    assert mas_parecido("zzzzzz", ["a", "b"]) is None


def test_compuerta_desconocida_sugiere_la_correcta():
    (error,) = diagnosticos("ENTRADA[a, b]\nANDD[a, b] -> x")
    assert error["sugerencia"] == "¿quisiste decir AND?"
    (error,) = diagnosticos("ENTRADA[a, b]\nxorr[a, b] -> x")
    assert error["sugerencia"] == "¿quisiste decir XOR?"


def test_senal_no_definida_sugiere_la_mas_parecida():
    (error,) = diagnosticos("ENTRADA[a, b]\nAND[a, b] -> z\nOR[zz, a] -> y")
    assert error["mensaje"] == "la señal zz no está definida"
    assert error["sugerencia"] == "¿quisiste decir 'z'?"
    assert (error["linea"], error["columna"]) == (3, 4)


def test_sin_sugerencia_si_nada_se_parece():
    (error,) = diagnosticos("ENTRADA[a, b]\nAND[a, q] -> x")
    assert "quisiste decir" not in error["sugerencia"]


# ---------------------------------------------------------------------------
# 2.4: columna real en todos los errores semánticos y advertencias
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("codigo,posicion,fragmento", [
    ("ENTRADA[a, b]\nNOT[a, b] -> x", (2, 1), "exactamente 1 entrada"),
    ("ENTRADA[a, b]\n  AND[a] -> x", (2, 3), "al menos 2 entradas"),
    ("ENTRADA[a, b]\nAND[a, b] -> x\nOR[a, b] -> x", (3, 13), "ya está definida"),
    ("ENTRADA[a, b, a]\nAND[a, b] -> x", (1, 15), "declarada más de una vez"),
    ("ENTRADA[a]\nAND[a, x] -> y\nNOT[y] -> x", (2, 14), "ciclo detectado"),
    ("ENTRADA[a, b]\nAND[a, b] -> y\nOR[y,    zz] -> w", (3, 10), "no está definida"),
])
def test_errores_semanticos_con_columna_exacta(codigo, posicion, fragmento):
    errores = diagnosticos(codigo)
    assert len(errores) == 1, errores
    assert (errores[0]["linea"], errores[0]["columna"]) == posicion
    assert fragmento in errores[0]["mensaje"]


def test_advertencia_de_entrada_sin_usar_con_columna():
    (aviso,) = diagnosticos("ENTRADA[a, bb, c]\nAND[a, c] -> x", "advertencia")
    assert (aviso["linea"], aviso["columna"]) == (1, 12)


def test_todos_los_diagnosticos_semanticos_tienen_columna():
    codigo = ("ENTRADA[a, b, a]\nNOT[a, b] -> x\nAND[x, zz] -> y\nOR[y, a] -> x\n"
              "AND[p, a] -> q\nAND[q, a] -> p\nAND[a, a] -> w")
    resultado = analizar(codigo)
    assert len(resultado["diagnosticos"]) >= 5
    for d in resultado["diagnosticos"]:
        assert d["columna"] is not None, d


# ---------------------------------------------------------------------------
# C4: formato legado sin ambigüedad
# ---------------------------------------------------------------------------
def test_nand_de_tres_entradas_usa_notacion_de_funcion():
    resultado = analizar("ENTRADA[a, b, c]\nNAND[a, b, c] -> y")
    assert resultado["expresiones"] == [{"salida": "y", "expresion": "NAND(a, b, c)"}]


def test_nor_y_xnor_de_tres_entradas_y_anidados():
    resultado = analizar("ENTRADA[a, b, c]\nAND[a, b] -> x\nNOR[x, b, c] -> y\n"
                         "XNOR[y, a, b] -> z")
    assert resultado["expresiones"][0]["expresion"] == \
        "XNOR(NOR(a AND b, b, c), a, b)"


def test_nand_binario_sigue_en_infijo():
    resultado = analizar("ENTRADA[a, b]\nNAND[a, b] -> y")
    assert resultado["expresiones"][0]["expresion"] == "a NAND b"


# ---------------------------------------------------------------------------
# C5: compuertas muertas y pin repetido
# ---------------------------------------------------------------------------
def test_compuerta_muerta_respecto_a_las_salidas_declaradas():
    compuertas = [
        {"compuerta": "AND", "entradas": ["a", "b"], "salida": "x", "linea": 2, "columna": 1},
        {"compuerta": "OR", "entradas": ["a", "b"], "salida": "muerta", "linea": 3, "columna": 1},
        {"compuerta": "NOT", "entradas": ["muerta"], "salida": "tambien", "linea": 4, "columna": 1},
    ]
    semantico = AnalizadorSemantico(["a", "b"], compuertas, _reglas(),
                                    salidas_declaradas=["x"])
    assert [c["salida"] for c in semantico.compuertas_muertas()] == ["muerta", "tambien"]
    avisos = semantico.advertencias()
    assert "Advertencia línea 3, columna 1: la compuerta OR -> muerta no llega a ninguna " \
           "salida del circuito" in avisos


def test_sin_salida_declarada_no_hay_compuertas_muertas():
    semantico = AnalizadorSemantico(["a", "b"], [
        {"compuerta": "OR", "entradas": ["a", "b"], "salida": "muerta", "linea": 2},
    ], _reglas())
    assert semantico.compuertas_muertas() == []


def test_pin_repetido_es_advertencia_con_columna():
    resultado = analizar("ENTRADA[a, b]\nAND[a, b] -> x\nOR[x,  x] -> y")
    assert resultado["exito"] is True
    (aviso,) = [d for d in resultado["diagnosticos"] if d["severidad"] == "advertencia"]
    assert aviso["mensaje"] == "la señal x está conectada dos veces a la misma compuerta OR"
    assert (aviso["linea"], aviso["columna"]) == (3, 8)


# ---------------------------------------------------------------------------
# C6: los ciclos se detectan siempre, uno por componente fuerte
# ---------------------------------------------------------------------------
def test_un_ciclo_no_queda_oculto_por_una_redefinicion():
    codigo = ("ENTRADA[a, b]\n"
              "AND[a, b] -> x\n"
              "OR[a, b] -> x\n"          # redefinición
              "NOT[q] -> p\n"
              "NOT[p] -> q")             # ciclo en otra parte
    mensajes = [d["mensaje"] for d in diagnosticos(codigo)]
    assert any("ya está definida" in m for m in mensajes)
    assert any(m.startswith("ciclo detectado") for m in mensajes)


def test_se_reportan_todos_los_ciclos_distintos():
    codigo = ("ENTRADA[a]\n"
              "AND[a, y] -> x\nNOT[x] -> y\n"        # ciclo 1
              "AND[a, q] -> p\nNOT[p] -> q\n"        # ciclo 2
              "AND[r, a] -> r")                      # autolazo
    ciclos = [d for d in diagnosticos(codigo) if d["mensaje"].startswith("ciclo")]
    assert [d["mensaje"] for d in ciclos] == [
        "ciclo detectado: x → y → x",
        "ciclo detectado: p → q → p",
        "ciclo detectado: r → r",
    ]
    assert [d["linea"] for d in ciclos] == [2, 4, 6]


def test_un_ciclo_largo_se_detecta_sin_recursion():
    n = 3000
    lineas = ["ENTRADA[a]", f"AND[a, n{n - 1}] -> n0"]
    lineas += [f"NOT[n{i - 1}] -> n{i}" for i in range(1, n)]
    errores = diagnosticos("\n".join(lineas))
    assert len(errores) == 1
    assert errores[0]["mensaje"].startswith("ciclo detectado: n0 → n1 → n2")
    assert errores[0]["mensaje"].endswith(f"n{n - 1} → n0")
