import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Token import Token


def test_token_creacion_con_posicion():
    token = Token("IDENTIFICADOR", "a", linea=2, columna=5)
    assert token.token == "IDENTIFICADOR"
    assert token.valor == "a"
    assert token.linea == 2
    assert token.columna == 5


def test_token_posicion_nula_por_defecto():
    token = Token("COMA", ",")
    assert token.linea is None
    assert token.columna is None


def test_token_to_json():
    token = Token("PALABRA RESERVADA", "AND", linea=1, columna=8)
    json_data = token.to_json()
    assert json_data["token"] == "PALABRA RESERVADA"
    assert json_data["valor"] == "AND"
    assert json_data["linea"] == 1
    assert json_data["columna"] == 8


def test_token_repr():
    token = Token("FLECHA", "->", linea=3, columna=1)
    repr_str = repr(token)
    assert "FLECHA" in repr_str
    assert "->" in repr_str
    assert "línea=3" in repr_str