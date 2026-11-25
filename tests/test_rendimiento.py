"""Rendimiento y tabla de verdad bajo demanda (fallo P1).

Antes /analizar calculaba siempre la tabla completa, recalculaba el orden
topológico en cada fila y la enviaba entera: con 20 entradas tardaba 152 s y
respondía 84 MB. Los objetivos son /validar < 100 ms y /analizar < 2 s con
20 entradas y una respuesta < 1 MB; los umbrales de las pruebas tienen
tolerancia amplia para no fallar en equipos lentos.
"""

import os
import sys
import time
from itertools import product

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

import gestor_reglas
from gestor_reglas import GestorReglas, LIMITE_TABLA
from semantico import AnalizadorSemantico
from SERVIRCOR import app, MAXIMO_FILAS_POR_PETICION


def circuito_de(n):
    """Cadena de n entradas con compuertas variadas y una salida."""
    entradas = [f"e{i}" for i in range(n)]
    lineas = [f"ENTRADA[{', '.join(entradas)}]"]
    anterior = entradas[0]
    for i in range(1, n):
        operacion = ["AND", "OR", "XOR", "NAND", "NOR", "XNOR"][i % 6]
        lineas.append(f"{operacion}[{anterior}, {entradas[i]}] -> g{i}")
        anterior = f"g{i}"
    lineas.append(f"NOT[{anterior}] -> salida")
    return "\n".join(lineas)


@pytest.fixture(scope="module")
def http():
    return TestClient(app)


def test_limite_por_defecto_es_14():
    assert LIMITE_TABLA == 14


def test_validar_20_entradas_es_rapido(http):
    codigo = circuito_de(20)
    http.post("/validar", json={"codigo": codigo})          # calentamiento
    inicio = time.perf_counter()
    respuesta = http.post("/validar", json={"codigo": codigo})
    segundos = time.perf_counter() - inicio
    assert respuesta.json()["exito"] is True
    assert segundos < 0.5, f"/validar tardó {segundos:.3f} s (objetivo < 0.1 s)"


def test_analizar_20_entradas_es_rapido_y_liviano(http):
    codigo = circuito_de(20)
    inicio = time.perf_counter()
    respuesta = http.post("/analizar", json={"codigo": codigo})
    segundos = time.perf_counter() - inicio
    datos = respuesta.json()

    assert datos["exito"] is True
    assert segundos < 4, f"/analizar tardó {segundos:.2f} s (objetivo < 2 s)"
    assert len(respuesta.content) < 1_000_000
    assert datos["tabla_verdad"]["filas"] == []
    assert datos["tabla_omitida"]["filas_totales"] == 2 ** 20
    assert "20 entradas" in datos["tabla_omitida"]["motivo"]


def test_por_encima_del_limite_no_se_calcula_la_tabla(monkeypatch):
    def prohibida(self):
        raise AssertionError("no se debe calcular la tabla completa")

    monkeypatch.setattr(AnalizadorSemantico, "tabla_verdad", prohibida)
    resultado = GestorReglas().analizar(circuito_de(LIMITE_TABLA + 1),
                                        imprimir=False, con_diagrama=False,
                                        registrar=False)
    assert resultado["exito"] is True
    assert resultado["tabla_omitida"]["filas_totales"] == 2 ** (LIMITE_TABLA + 1)


def test_en_el_limite_la_tabla_viene_completa():
    # 14 entradas y una compuerta: 2^14 filas × 15 columnas, bajo LIMITE_CELDAS.
    entradas = ", ".join(f"e{i}" for i in range(LIMITE_TABLA))
    resultado = GestorReglas().analizar(f"ENTRADA[{entradas}]\nXOR[{entradas}] -> y",
                                        imprimir=False, con_diagrama=False,
                                        registrar=False)
    assert resultado["tabla_omitida"] is None
    assert len(resultado["tabla_verdad"]["filas"]) == 2 ** LIMITE_TABLA


def test_la_tabla_tambien_se_omite_por_celdas():
    """Hallazgo del verificador: 14 entradas y muchas compuertas daban 9 MB."""
    resultado = GestorReglas().analizar(circuito_de(LIMITE_TABLA), imprimir=False,
                                        con_diagrama=False, registrar=False)
    assert resultado["tabla_omitida"]["filas_totales"] == 2 ** LIMITE_TABLA
    assert "celdas" in resultado["tabla_omitida"]["motivo"]


def test_el_limite_es_configurable():
    resultado = GestorReglas().analizar(circuito_de(5), imprimir=False,
                                        con_diagrama=False, registrar=False,
                                        limite_tabla=4)
    assert resultado["tabla_omitida"]["filas_totales"] == 32
    assert resultado["tabla_omitida"]["limite_entradas"] == 4


def test_el_orden_topologico_se_calcula_una_sola_vez(monkeypatch):
    llamadas = []
    original = AnalizadorSemantico._calcular_orden

    def contar(self):
        llamadas.append(1)
        return original(self)

    monkeypatch.setattr(AnalizadorSemantico, "_calcular_orden", contar)
    GestorReglas().analizar(circuito_de(8), imprimir=False, con_diagrama=False,
                            registrar=False)
    assert len(llamadas) == 1


# ---------------------------------------------------------------------------
# Ruta /tabla: filas por bloques sin construir la tabla completa
# ---------------------------------------------------------------------------
OPERACIONES = {
    "AND": all,
    "OR": any,
    "NOT": lambda v: not v[0],
    "XOR": lambda v: sum(v) % 2 == 1,
    "NAND": lambda v: not all(v),
    "NOR": lambda v: not any(v),
    "XNOR": lambda v: sum(v) % 2 == 0,
}


def _tabla_a_mano(codigo):
    """Tabla de referencia: itertools.product y una evaluación independiente."""
    gestor = GestorReglas()
    semantico, _ = gestor.preparar_evaluacion(codigo)
    senales = semantico.senales_tabla()
    filas = []
    for combinacion in product([0, 1], repeat=len(semantico.entradas)):
        valores = dict(zip(semantico.entradas, combinacion))
        for compuerta in semantico.orden_topologico():
            argumentos = [valores[s] for s in compuerta["entradas"]]
            valores[compuerta["salida"]] = int(OPERACIONES[compuerta["compuerta"]](argumentos))
        filas.append([valores[s] for s in senales])
    return senales, filas


def test_tabla_por_bloques_coincide_con_la_tabla_completa(http):
    codigo = circuito_de(7)
    senales, completa = _tabla_a_mano(codigo)
    filas = []
    for desde in range(0, 128, 50):
        datos = http.post("/tabla", json={"codigo": codigo, "desde": desde,
                                          "cantidad": 50}).json()
        assert datos["exito"] is True
        assert datos["señales"] == senales
        assert datos["filas_totales"] == 128
        filas.extend(datos["filas"])
    assert filas == completa


def test_tabla_en_medio_de_un_circuito_enorme(http, monkeypatch):
    def prohibida(self):
        raise AssertionError("no se debe construir la tabla completa")

    monkeypatch.setattr(AnalizadorSemantico, "tabla_verdad", prohibida)
    codigo = circuito_de(20)
    datos = http.post("/tabla", json={"codigo": codigo, "desde": 700_000,
                                      "cantidad": 3}).json()
    assert datos["exito"] is True
    assert datos["desde"] == 700_000
    assert len(datos["filas"]) == 3
    # Las columnas de entrada son el índice binario de la fila.
    for desplazamiento, fila in enumerate(datos["filas"]):
        bits = format(700_000 + desplazamiento, "020b")
        assert "".join(map(str, fila[:20])) == bits


def test_tabla_limita_la_cantidad_y_el_final(http):
    codigo = circuito_de(16)
    datos = http.post("/tabla", json={"codigo": codigo, "desde": 0,
                                      "cantidad": 10 ** 9}).json()
    assert datos["cantidad"] == MAXIMO_FILAS_POR_PETICION
    assert len(datos["filas"]) == MAXIMO_FILAS_POR_PETICION

    final = http.post("/tabla", json={"codigo": codigo, "desde": 2 ** 16 - 2,
                                      "cantidad": 10}).json()
    assert len(final["filas"]) == 2

    fuera = http.post("/tabla", json={"codigo": codigo, "desde": 2 ** 17,
                                      "cantidad": 10}).json()
    assert fuera["filas"] == []


def test_tabla_de_un_circuito_con_errores_devuelve_los_diagnosticos(http):
    datos = http.post("/tabla", json={"codigo": "ENTRADA[a]\nAND[a, z] -> x",
                                      "desde": 0, "cantidad": 4}).json()
    assert datos["exito"] is False
    assert datos["errores"]
    assert datos["diagnosticos"][0]["severidad"] == "error"


def test_tabla_rechaza_parametros_negativos(http):
    respuesta = http.post("/tabla", json={"codigo": circuito_de(3), "desde": -1,
                                          "cantidad": 4})
    assert respuesta.status_code == 422
