import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ImplementacionAnalisisLexico import tokenizar_circuito


def test_palabra_reservada_entrada():
    tokens, errores = tokenizar_circuito("ENTRADA[a, b]")
    assert len(errores) == 0
    assert tokens[0].token == "PALABRA RESERVADA"
    assert tokens[0].valor == "ENTRADA"
    assert tokens[0].linea == 1
    assert tokens[0].columna == 1


def test_reservadas_resistentes_a_mayusculas():
    tokens, errores = tokenizar_circuito("and[x, y] -> z")
    assert len(errores) == 0
    assert tokens[0].token == "PALABRA RESERVADA"
    assert tokens[0].valor == "AND"


def test_identificador():
    tokens, errores = tokenizar_circuito("x_1")
    assert len(errores) == 0
    assert tokens[0].token == "IDENTIFICADOR"
    assert tokens[0].valor == "x_1"


def test_flecha():
    tokens, errores = tokenizar_circuito("->")
    assert len(errores) == 0
    assert tokens[0].token == "FLECHA"
    assert tokens[0].valor == "->"


def test_corchetes_y_coma():
    tokens, errores = tokenizar_circuito("[a, b]")
    assert len(errores) == 0
    assert [t.token for t in tokens] == ["CORCHETE ABRE", "IDENTIFICADOR", "COMA", "IDENTIFICADOR", "CORCHETE CIERRA"]


def test_lineas_y_columnas():
    tokens, errores = tokenizar_circuito("ENTRADA[a]\nNOT[a] -> b")
    assert len(errores) == 0
    # ENTRADA en línea 1
    assert tokens[0].linea == 1
    # NOT en línea 2
    assert tokens[4].token == "PALABRA RESERVADA"
    assert tokens[4].valor == "NOT"
    assert tokens[4].linea == 2


def test_caracter_invalido():
    tokens, errores = tokenizar_circuito("x$1")
    assert len(errores) > 0
    assert "Error léxico línea 1" in errores[0]
    assert "$" in errores[0]


def test_flecha_incompleta():
    tokens, errores = tokenizar_circuito("-")
    assert len(errores) > 0
    assert "Error léxico" in errores[0]


def test_comentario_no_es_token():
    # Los comentarios (# ...) se filtran antes de la fase léxica; si un '#'
    # llega al tokenizador, no pertenece al alfabeto del lenguaje.
    tokens, errores = tokenizar_circuito("ENTRADA[a] # comentario")
    assert len(errores) == 1
    assert "Error léxico línea 1" in errores[0]
    assert "#" in errores[0]