import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from semantico import AnalizadorSemantico, generar_dot


def _reglas():
    ruta = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reglas.json")
    with open(ruta, "r", encoding="utf-8") as archivo:
        return json.load(archivo)["compuertas"]


def _semantico(entradas, compuertas):
    return AnalizadorSemantico(entradas, compuertas, _reglas())


def test_circuito_valido_sin_errores():
    compuertas = [
        {"compuerta": "AND", "entradas": ["a", "b"], "salida": "x1", "linea": 2},
        {"compuerta": "OR", "entradas": ["x1", "c"], "salida": "x2", "linea": 3},
        {"compuerta": "NOT", "entradas": ["x2"], "salida": "salida", "linea": 4},
    ]
    semantico = _semantico(["a", "b", "c"], compuertas)
    assert semantico.revisar() == []


def test_señal_no_definida():
    compuertas = [
        {"compuerta": "AND", "entradas": ["a", "z"], "salida": "x", "linea": 2},
    ]
    semantico = _semantico(["a", "b"], compuertas)
    errores = semantico.revisar()
    assert len(errores) == 1
    assert "la señal z no está definida" in errores[0]
    assert "Error semántico línea 2" in errores[0]


def test_not_con_dos_entradas():
    compuertas = [
        {"compuerta": "NOT", "entradas": ["a", "b"], "salida": "x", "linea": 2},
    ]
    semantico = _semantico(["a", "b"], compuertas)
    errores = semantico.revisar()
    assert len(errores) == 1
    assert "exactamente 1 entrada" in errores[0]
    assert "Error semántico línea 2" in errores[0]


def test_and_con_una_entrada():
    compuertas = [
        {"compuerta": "AND", "entradas": ["a"], "salida": "x", "linea": 2},
    ]
    semantico = _semantico(["a", "b"], compuertas)
    errores = semantico.revisar()
    assert len(errores) == 1
    assert "al menos 2 entradas" in errores[0]


def test_redefinicion_de_señal():
    compuertas = [
        {"compuerta": "AND", "entradas": ["a", "b"], "salida": "x", "linea": 2},
        {"compuerta": "OR", "entradas": ["a", "b"], "salida": "x", "linea": 3},
    ]
    semantico = _semantico(["a", "b"], compuertas)
    errores = semantico.revisar()
    assert len(errores) == 1
    assert "la señal x ya está definida" in errores[0]
    assert "Error semántico línea 3" in errores[0]


def test_salida_igual_a_entrada():
    compuertas = [
        {"compuerta": "AND", "entradas": ["a", "b"], "salida": "a", "linea": 2},
    ]
    semantico = _semantico(["a", "b"], compuertas)
    errores = semantico.revisar()
    assert len(errores) == 1
    assert "la señal a ya está definida" in errores[0]


def test_ciclo_detectado():
    compuertas = [
        {"compuerta": "AND", "entradas": ["x", "a"], "salida": "y", "linea": 2},
        {"compuerta": "AND", "entradas": ["y", "a"], "salida": "x", "linea": 3},
    ]
    semantico = _semantico(["a"], compuertas)
    errores = semantico.revisar()
    assert len(errores) == 1
    assert "ciclo detectado" in errores[0]


def test_orden_topologico():
    compuertas = [
        {"compuerta": "AND", "entradas": ["a", "b"], "salida": "x1", "linea": 2},
        {"compuerta": "OR", "entradas": ["x1", "c"], "salida": "x2", "linea": 3},
        {"compuerta": "NOT", "entradas": ["x2"], "salida": "salida", "linea": 4},
    ]
    semantico = _semantico(["a", "b", "c"], compuertas)
    orden = semantico.orden_topologico()
    assert [c["salida"] for c in orden] == ["x1", "x2", "salida"]


def test_tabla_de_verdad():
    compuertas = [
        {"compuerta": "AND", "entradas": ["a", "b"], "salida": "x", "linea": 2},
    ]
    semantico = _semantico(["a", "b"], compuertas)
    tabla = semantico.tabla_verdad()
    assert tabla["señales"] == ["a", "b", "x"]
    assert len(tabla["filas"]) == 4
    assert [0, 0, 0] in tabla["filas"]
    assert [1, 1, 1] in tabla["filas"]


def test_expresion_booleana():
    compuertas = [
        {"compuerta": "AND", "entradas": ["a", "b"], "salida": "x1", "linea": 2},
        {"compuerta": "OR", "entradas": ["x1", "c"], "salida": "x2", "linea": 3},
        {"compuerta": "NOT", "entradas": ["x2"], "salida": "salida", "linea": 4},
    ]
    semantico = _semantico(["a", "b", "c"], compuertas)
    expresiones = semantico.expresiones_booleanas()
    assert len(expresiones) == 1
    salida, expresion = expresiones[0]
    assert salida == "salida"
    assert expresion == "NOT((a AND b) OR c)"


def test_generar_dot():
    dot = generar_dot(["a", "b"], [
        {"compuerta": "AND", "entradas": ["a", "b"], "salida": "x", "linea": 2},
    ])
    assert "digraph circuito" in dot
    assert "rankdir=LR" in dot
    assert "a [label=a" in dot
    assert "x [label=x" in dot