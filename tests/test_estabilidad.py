"""Estabilidad del compilador (fallos C7 y C8) y campo `diagnosticos`.

- C7: reglas.json se ubica en un solo lugar, sin depender del directorio
  actual y sin tragarse los errores con `except Exception: pass`.
- C8: un fallo interno nunca llega como "Error inesperado: 'x'", sino como un
  diagnóstico entendible.
"""

import glob
import json
import os
import re
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from fastapi.testclient import TestClient

import rutas
from rutas import ErrorReglas, cargar_reglas, ubicar_reglas
from gestor_reglas import GestorReglas
from ImplementacionAnalisisLexico import tokenizar_circuito
from AnalisisSintactico import AnalisisSintactico
from SERVIRCOR import app
import diagnosticos as diag


def cliente():
    return TestClient(app)


# ---------------------------------------------------------------------------
# C7: rutas de reglas.json
# ---------------------------------------------------------------------------
def test_reglas_por_defecto_viajan_con_el_programa(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert ubicar_reglas() == os.path.join(RAIZ, "reglas.json")
    tokens, errores = tokenizar_circuito("ENTRADA[a]\nNOT[a] -> b")
    assert errores == []
    assert tokens[0].token == "PALABRA RESERVADA"
    assert "XNOR" in AnalisisSintactico(tokens).nombres_compuertas


def test_un_reglas_json_ajeno_en_la_carpeta_actual_no_cambia_el_lenguaje(tmp_path, monkeypatch):
    (tmp_path / "reglas.json").write_text(json.dumps({"compuertas": [],
                                                      "palabras_reservadas": []}),
                                          encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert GestorReglas().analizar("ENTRADA[a]\nNOT[a] -> b", imprimir=False,
                                   con_diagrama=False, registrar=False)["exito"]


def test_pyinstaller_usa_meipass(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert ubicar_reglas() == os.path.join(str(tmp_path), "reglas.json")
    assert rutas.ruta_recurso("web") == os.path.join(str(tmp_path), "web")


def test_reglas_inexistentes_dan_un_error_claro(tmp_path):
    with pytest.raises(ErrorReglas, match="No se encontró"):
        cargar_reglas(str(tmp_path / "no_existe.json"))


def test_reglas_danadas_dan_un_error_claro(tmp_path):
    ruta = tmp_path / "rotas.json"
    ruta.write_text("{ esto no es json", encoding="utf-8")
    with pytest.raises(ErrorReglas, match="no es un JSON válido"):
        cargar_reglas(str(ruta))


def test_no_quedan_excepciones_silenciosas():
    """Ningún módulo del compilador traga errores con `except ...: pass`."""
    patron = re.compile(r"except[^\n:]*:\s*\n\s*pass\b")
    for ruta in glob.glob(os.path.join(RAIZ, "*.py")):
        with open(ruta, encoding="utf-8") as archivo:
            assert not patron.search(archivo.read()), f"except/pass en {ruta}"


# ---------------------------------------------------------------------------
# C8: errores internos entendibles
# ---------------------------------------------------------------------------
def test_un_fallo_interno_del_gestor_es_un_diagnostico(monkeypatch):
    def explota(self, *args, **kwargs):
        raise KeyError("x")

    monkeypatch.setattr(GestorReglas, "_analizar", explota)
    resultado = GestorReglas().analizar("ENTRADA[a]\nNOT[a] -> b", imprimir=False,
                                        registrar=False)
    assert resultado["exito"] is False
    assert len(resultado["errores"]) == 1
    texto = resultado["errores"][0]
    assert texto.startswith("Error interno del compilador")
    assert "repórtalo" in texto
    assert "Error inesperado" not in texto
    assert resultado["diagnosticos"][0]["fase"] == "interno"


@pytest.mark.parametrize("ruta", ["/analizar", "/validar", "/tabla"])
def test_la_api_nunca_responde_error_inesperado(monkeypatch, ruta):
    def explota(self, *args, **kwargs):
        raise KeyError("x")

    monkeypatch.setattr(GestorReglas, "analizar", explota)
    datos = cliente().post(ruta, json={"codigo": "ENTRADA[a]\nNOT[a] -> b"}).json()
    assert datos["exito"] is False
    assert datos["errores"][0].startswith("Error interno del compilador")
    assert "Error inesperado" not in json.dumps(datos, ensure_ascii=False)
    assert datos["diagnosticos"][0]["severidad"] == "error"


def test_el_traceback_se_muestra_con_jace_debug(monkeypatch, capsys):
    def explota(self, *args, **kwargs):
        raise ValueError("fallo de prueba")

    monkeypatch.setenv("JACE_DEBUG", "1")
    monkeypatch.setattr(GestorReglas, "_analizar", explota)
    GestorReglas().analizar("ENTRADA[a]", imprimir=False, registrar=False)
    assert "Traceback" in capsys.readouterr().err


def test_el_comentario_del_historial_ya_no_dice_que_se_comparte():
    with open(os.path.join(RAIZ, "SERVIRCOR.py"), encoding="utf-8") as archivo:
        fuente = archivo.read()
    assert "Historial compartido" not in fuente
    assert "NO se comparten" in fuente


# ---------------------------------------------------------------------------
# Campo estructurado "diagnosticos"
# ---------------------------------------------------------------------------
def test_diagnosticos_y_errores_cuentan_lo_mismo():
    resultado = GestorReglas().analizar("ENTRADA[a, b]\nAND[a, z] -> x",
                                        imprimir=False, con_diagrama=False,
                                        registrar=False)
    errores = [d for d in resultado["diagnosticos"] if d["severidad"] == "error"]
    assert len(errores) == len(resultado["errores"])
    assert set(errores[0]) == {"fase", "severidad", "linea", "columna",
                               "mensaje", "sugerencia"}
    assert errores[0]["fase"] == "semántico"
    assert errores[0]["linea"] == 2


def test_validar_incluye_diagnosticos():
    datos = cliente().post("/validar", json={"codigo": "ENTRADA[a, b]\nNOT[a] -> s"}).json()
    assert datos["diagnosticos"] == [{
        "fase": "semántico", "severidad": "advertencia", "linea": 1,
        "columna": datos["diagnosticos"][0]["columna"],
        "mensaje": "la entrada b no se utiliza",
        "sugerencia": datos["diagnosticos"][0]["sugerencia"]}]


def test_formato_de_texto_de_un_diagnostico():
    d = diag.error("sintáctico", 4, 6, "falta una coma")
    assert d.texto() == "Error sintáctico línea 4, columna 6: falta una coma"
    a = diag.advertencia("semántico", 1, 12, "la entrada b no se utiliza")
    assert a.texto() == "Advertencia línea 1, columna 12: la entrada b no se utiliza"
    assert diag.error("semántico", 2, None, "x").texto() == "Error semántico línea 2: x"


def test_desde_texto_lee_el_formato_historico():
    d = diag.desde_texto("Error léxico línea 3, columna 15: carácter no reconocido '$'")
    assert (d.fase, d.severidad, d.linea, d.columna) == ("léxico", "error", 3, 15)
    a = diag.desde_texto("Advertencia línea 1: la entrada b no se utiliza")
    assert (a.severidad, a.linea, a.columna) == ("advertencia", 1, None)
