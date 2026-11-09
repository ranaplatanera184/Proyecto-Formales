import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ImplementacionAnalisisLexico import tokenizar_circuito
from AnalisisSintactico import AnalisisSintactico


def _parsear(texto):
    tokens, errores = tokenizar_circuito(texto)
    assert errores == []
    parser = AnalisisSintactico(tokens)
    return parser.construir_circuito()


def test_circuito_valido():
    circuito = _parsear(
        "ENTRADA[a, b, c]\n"
        "AND[a, b] -> x1\n"
        "OR[x1, c] -> x2\n"
        "NOT[x2] -> salida"
    )
    assert circuito["entradas"] == ["a", "b", "c"]
    assert len(circuito["compuertas"]) == 3
    assert circuito["compuertas"][0]["compuerta"] == "AND"
    assert circuito["compuertas"][0]["entradas"] == ["a", "b"]
    assert circuito["compuertas"][0]["salida"] == "x1"


def test_falta_entrada():
    tokens, errores = tokenizar_circuito("AND[a, b] -> x")
    parser = AnalisisSintactico(tokens)
    try:
        parser.construir_circuito()
        assert False, "Debería fallar"
    except SyntaxError as e:
        assert "se esperaba ENTRADA" in str(e)
        assert "Error sintáctico" in str(e)


def test_entrada_vacia():
    tokens, errores = tokenizar_circuito("ENTRADA[]")
    parser = AnalisisSintactico(tokens)
    try:
        parser.construir_circuito()
        assert False, "Debería fallar"
    except SyntaxError as e:
        assert "se esperaba IDENTIFICADOR" in str(e)


def test_falta_flecha():
    tokens, errores = tokenizar_circuito("ENTRADA[a]\nAND[a] x")
    parser = AnalisisSintactico(tokens)
    try:
        parser.construir_circuito()
        assert False, "Debería fallar"
    except SyntaxError as e:
        assert "Error sintáctico" in str(e)


def test_circuito_sin_compuertas():
    tokens, errores = tokenizar_circuito("ENTRADA[a]")
    parser = AnalisisSintactico(tokens)
    try:
        parser.construir_circuito()
        assert False, "Debería fallar"
    except SyntaxError as e:
        assert "al menos una compuerta" in str(e)


def test_entrada_en_medio():
    tokens, errores = tokenizar_circuito("ENTRADA[a]\nENTRADA[b]")
    parser = AnalisisSintactico(tokens)
    try:
        parser.construir_circuito()
        assert False, "Debería fallar"
    except SyntaxError as e:
        assert "se esperaba una compuerta" in str(e)


def test_token_inesperado():
    tokens, errores = tokenizar_circuito("ENTRADA[a]\n5x -> y")
    parser = AnalisisSintactico(tokens)
    try:
        parser.construir_circuito()
        assert False, "Debería fallar"
    except SyntaxError as e:
        assert "Error sintáctico" in str(e)