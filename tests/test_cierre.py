"""Regresiones de los hallazgos de la verificación de cierre (fase 4)."""

import os
import subprocess
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from fastapi.testclient import TestClient

from AnalisisSintactico import MAXIMO_ANIDAMIENTO
from gestor_reglas import (GestorReglas, LIMITE_DIAGRAMA_COMPUERTAS,
                           MAXIMO_ERRORES_LEXICOS, MAXIMO_DIAGNOSTICOS_SEMANTICOS)
from sugerencias import distancia
from SERVIRCOR import app, MAXIMO_CELDAS_POR_PETICION


def analizar(codigo, **opciones):
    opciones.setdefault("imprimir", False)
    opciones.setdefault("registrar", False)
    opciones.setdefault("con_diagrama", False)
    return GestorReglas().analizar(codigo, **opciones)


def test_muchas_senales_no_definidas_validan_rapido():
    codigo = "ENTRADA[a]\n" + "\n".join(f"AND[a, z{i}] -> x{i}" for i in range(3000))
    inicio = time.perf_counter()
    resultado = analizar(codigo)
    assert time.perf_counter() - inicio < 5
    assert len(resultado["diagnosticos"]) == MAXIMO_DIAGNOSTICOS_SEMANTICOS + 1
    assert "más que no se muestran" in resultado["diagnosticos"][-1]["mensaje"]


def test_nombres_larguisimos_no_vuelven_lenta_la_sugerencia():
    inicio = time.perf_counter()
    analizar("ENTRADA[" + "a" * 3000 + "]\nAND[" + "a" * 3000 + ", " + "b" * 3000 + "] -> x")
    assert time.perf_counter() - inicio < 0.8


def test_distancia_con_tope():
    assert distancia("abcdef", "uvwxyz", tope=2) == 3
    assert distancia("ANDD", "AND", tope=2) == 1


def test_el_limite_de_anidamiento_es_exacto():
    def codigo(n):
        return "ENTRADA[a]\n" + "NOT[" * n + "a" + "]" * n + " -> y"
    assert analizar(codigo(MAXIMO_ANIDAMIENTO))["exito"] is True
    assert analizar(codigo(MAXIMO_ANIDAMIENTO + 1))["exito"] is False


def test_tope_de_errores_lexicos():
    resultado = analizar("ENTRADA[a]\n" + "\n".join("AND[a, $] -> x" for _ in range(500)))
    assert len(resultado["errores"]) == MAXIMO_ERRORES_LEXICOS + 1


def test_pin_repetido_avisa_una_vez_por_senal():
    resultado = analizar("ENTRADA[a, b]\nAND[" + ", ".join(["a", "b"] * 50) + "] -> x")
    avisos = [d for d in resultado["diagnosticos"] if d["severidad"] == "advertencia"]
    assert len(avisos) == 2


def test_ciclo_enorme_da_un_mensaje_legible():
    n = 3000
    lineas = ["ENTRADA[a]", f"AND[a, n{n - 1}] -> n0"] + [f"NOT[n{i - 1}] -> n{i}" for i in range(1, n)]
    (error,) = analizar("\n".join(lineas))["errores"]
    assert len(error) < 300
    assert "señales más" in error


def test_el_diagrama_se_omite_desde_el_limite_nuevo():
    lineas = ["ENTRADA[a, b]"] + [f"XOR[a, b] -> x{i}" for i in range(LIMITE_DIAGRAMA_COMPUERTAS + 1)]
    resultado = analizar("\n".join(lineas), con_diagrama=True)
    assert resultado["diagrama_svg"] == ""
    assert resultado["diagrama_omitido"]


def test_tabla_con_miles_de_columnas_limita_por_celdas():
    entradas = ", ".join(f"e{i}" for i in range(2000))
    codigo = f"ENTRADA[{entradas}]\nAND[{entradas}] -> y"
    datos = TestClient(app).post("/tabla", json={"codigo": codigo, "desde": 0,
                                                 "cantidad": 4096}).json()
    assert datos["cantidad"] * 2001 <= MAXIMO_CELDAS_POR_PETICION


def test_solo_comentarios_da_el_mismo_diagnostico_en_cli_y_api():
    api = TestClient(app).post("/analizar", json={"codigo": "# nada\n# otra"}).json()
    gestor = analizar("# nada\n# otra")
    assert api["diagnosticos"] == gestor["diagnosticos"]


def test_salida_antes_de_entrada_explica_el_orden():
    errores = analizar("SALIDA[x]\nENTRADA[a, b]\nAND[a, b] -> x")["diagnosticos"]
    assert "debe ser la primera" in errores[1]["mensaje"]


def test_corchete_sobrante_en_una_declaracion():
    (error,) = analizar("ENTRADA[a, b]]\nAND[a, b] -> x")["diagnosticos"]
    assert error["mensaje"] == "sobra ']' al final de la declaración"


def test_instrucciones_en_varias_lineas():
    for codigo in ("ENTRADA[a, b]\nAND[a,\nb] -> x", "ENTRADA[a, b]\nAND[a\n, b] -> x",
                   "ENTRADA[a, b]\nAND[a, b\n] -> x", "ENTRADA[a, b]\nAND[a, b]\n-> x"):
        assert analizar(codigo)["exito"] is True, codigo


def test_cli_con_salida_imposible_devuelve_2(tmp_path):
    proceso = subprocess.run(
        [sys.executable, os.path.join(RAIZ, "main.py"), "pruebas/01_circuito_valido.jace",
         "--verilog", "-o", str(tmp_path / "no" / "existe" / "x.v")],
        capture_output=True, cwd=RAIZ)
    assert proceso.returncode == 2
    assert b"Traceback" not in proceso.stderr
    assert b"no se pudo escribir" in proceso.stderr
