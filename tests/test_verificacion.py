"""Regresiones de los hallazgos del subagente verificador (cierre de la fase 1).

Cada prueba reproduce un fallo que encontró intentando romper el compilador.
"""

import os
import subprocess
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import matplotlib.pyplot as plt
from fastapi.testclient import TestClient

from gestor_reglas import GestorReglas, LIMITE_DIAGRAMA_COMPUERTAS
from SERVIRCOR import app

PYTHON = sys.executable


def analizar(codigo, **opciones):
    opciones.setdefault("imprimir", False)
    opciones.setdefault("registrar", False)
    return GestorReglas().analizar(codigo, **opciones)


def test_expresion_con_senal_reutilizada_no_crece_exponencialmente():
    """OR[x, x] en cada nivel duplicaba el texto: 22 líneas = 31 millones de
    caracteres y unas 30 tumbaban el servidor."""
    lineas = ["ENTRADA[a, b]", "AND[a, b] -> x0"]
    lineas += [f"OR[x{i - 1}, x{i - 1}] -> x{i}" for i in range(1, 60)]
    inicio = time.perf_counter()
    resultado = analizar("\n".join(lineas), con_diagrama=False)
    assert time.perf_counter() - inicio < 5
    assert resultado["exito"] is True
    (legado,) = resultado["expresiones"]
    assert legado["expresion"].startswith("(expresión demasiado larga:")
    assert len(legado["expresion"]) < 200
    datos = resultado["expresiones_booleanas"]["x59"]
    assert datos["expandida"] is None
    assert "demasiado larga" in datos["aviso"]


def test_el_diagrama_se_omite_en_circuitos_enormes():
    lineas = ["ENTRADA[a]", "NOT[a] -> n0"]
    lineas += [f"NOT[n{i - 1}] -> n{i}" for i in range(1, LIMITE_DIAGRAMA_COMPUERTAS + 50)]
    inicio = time.perf_counter()
    resultado = analizar("\n".join(lineas))
    assert time.perf_counter() - inicio < 5
    assert resultado["diagrama_svg"] == ""
    assert "compuertas" in resultado["diagrama_omitido"]["motivo"]


def test_las_figuras_de_matplotlib_se_cierran():
    http = TestClient(app)
    with open(os.path.join(RAIZ, "pruebas", "diagrama_38.jace"), encoding="utf-8") as f:
        codigo = f.read()
    http.post("/analizar", json={"codigo": codigo})
    antes = len(plt.get_fignums())
    for _ in range(5):
        http.post("/analizar", json={"codigo": codigo})
    assert len(plt.get_fignums()) == antes


def test_archivo_con_bom_se_acepta():
    assert analizar("﻿ENTRADA[a, b]\nAND[a, b] -> x", con_diagrama=False)["exito"]


def test_cli_acepta_archivos_con_bom(tmp_path):
    ruta = tmp_path / "bom.jace"
    ruta.write_bytes(b"\xef\xbb\xbfENTRADA[a, b]\nAND[a, b] -> x\n")
    proceso = subprocess.run([PYTHON, os.path.join(RAIZ, "main.py"), str(ruta)],
                             capture_output=True, cwd=RAIZ)
    assert proceso.returncode == 0, proceso.stdout.decode("utf-8", "replace")


def test_cli_redirigida_no_falla_con_unicode(tmp_path):
    """La salida redirigida usaba cp1252 y fallaba con ⊕ o →."""
    entorno = dict(os.environ, PYTHONIOENCODING="")
    entorno.pop("PYTHONIOENCODING")
    proceso = subprocess.run([PYTHON, os.path.join(RAIZ, "main.py"),
                              os.path.join(RAIZ, "pruebas", "02_xor_nand.jace")],
                             capture_output=True, cwd=RAIZ, env=entorno)
    assert proceso.returncode == 0
    assert "⊕" in proceso.stdout.decode("utf-8")


def test_cli_devuelve_1_si_el_circuito_no_compila():
    proceso = subprocess.run([PYTHON, os.path.join(RAIZ, "main.py"),
                              os.path.join(RAIZ, "pruebas", "03_senal_no_definida.jace")],
                             capture_output=True, cwd=RAIZ)
    assert proceso.returncode == 1


def test_retorno_de_carro_solo_separa_lineas():
    resultado = analizar("ENTRADA[a, b]\rAND[a, z] -> x", con_diagrama=False)
    (error,) = resultado["errores"]
    assert error.startswith("Error semántico línea 2")


def test_separador_de_linea_unicode_es_un_caracter_invalido():
    resultado = analizar("ENTRADA[a, b] AND[a, b] -> x", con_diagrama=False)
    assert resultado["exito"] is False
    assert any("U+2028" in e for e in resultado["errores"])


def test_tabla_con_parametros_invalidos_responde_en_espanol():
    respuesta = TestClient(app).post("/tabla", json={"codigo": "ENTRADA[a]\nNOT[a] -> x",
                                                     "desde": -1})
    assert respuesta.status_code == 422
    datos = respuesta.json()
    assert datos["exito"] is False
    assert datos["errores"][0].startswith("Petición inválida: el campo 'desde'")


def test_limite_de_tabla_invalido_en_el_entorno_no_impide_arrancar():
    entorno = dict(os.environ, JACE_LIMITE_TABLA="abc")
    proceso = subprocess.run([PYTHON, "-c", "import gestor_reglas; print(gestor_reglas.LIMITE_TABLA)"],
                             capture_output=True, cwd=RAIZ, env=entorno, text=True)
    assert proceso.returncode == 0
    assert proceso.stdout.strip() == "14"
