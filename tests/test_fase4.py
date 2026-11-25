"""Fase 4: CLI, galería de ejemplos, interfaz web y coherencia CLI/web."""

import glob
import json
import os
import re
import subprocess
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from fastapi.testclient import TestClient

from SERVIRCOR import app
from gestor_reglas import LIMITE_TABLA
import main as cli

PYTHON = sys.executable
PRUEBAS = sorted(glob.glob(os.path.join(RAIZ, "pruebas", "*.jace")))
EJEMPLOS = sorted(glob.glob(os.path.join(RAIZ, "ejemplos", "*.jace")))


def ejecutar(*argumentos, entorno=None):
    variables = dict(os.environ, NO_COLOR="1")
    variables.update(entorno or {})
    proceso = subprocess.run([PYTHON, os.path.join(RAIZ, "main.py"), *argumentos],
                             capture_output=True, cwd=RAIZ, env=variables)
    return (proceso.returncode, proceso.stdout.decode("utf-8").replace(chr(13) + chr(10), chr(10)),
            proceso.stderr.decode("utf-8", "replace"))


# ---------------------------------------------------------------------------
# 4.8 CLI
# ---------------------------------------------------------------------------
def test_resumen_de_un_circuito_valido():
    codigo, salida, _ = ejecutar("pruebas/02_xor_nand.jace")
    assert codigo == 0
    for fragmento in ("✔ Léxico", "✔ Sintáctico", "✔ Semántico", "Salidas",
                      "sal2 = a ⊕ b", "Métricas", "El circuito compila"):
        assert fragmento in salida
    assert "\033[" not in salida               # NO_COLOR: sin secuencias ANSI


def test_resumen_con_errores_y_sugerencia():
    codigo, salida, _ = ejecutar("ejemplos/error_senal_no_definida.jace")
    assert codigo == 1
    assert "✖ Semántico" in salida
    assert "✖ línea 4, columna 5 · semántico: la señal sumaa no está definida" in salida
    assert "sugerencia: ¿quisiste decir 'suma'?" in salida


def test_fases_no_ejecutadas_tras_un_error_lexico():
    codigo, salida, _ = ejecutar("pruebas/09_caracter_invalido.jace")
    assert codigo == 1
    assert "✖ Léxico" in salida
    assert "– Semántico" in salida


def test_tokens_tambien_con_errores():
    _, salida, _ = ejecutar("pruebas/09_caracter_invalido.jace", "--tokens")
    assert "== TOKENS ==" in salida
    assert "IDENTIFICADOR" in salida


def test_secciones_opcionales():
    _, salida, _ = ejecutar("ejemplos/constantes_optimizables.jace", "--arbol", "--simbolos",
                            "--intermedio", "--optimizar", "--tabla")
    for titulo in ("ÁRBOL SINTÁCTICO", "TABLA DE SÍMBOLOS", "CÓDIGO INTERMEDIO",
                   "OPTIMIZACIÓN", "TABLA DE VERDAD"):
        assert f"== {titulo} ==" in salida
    assert "└── " in salida
    assert re.search(r"y +=  ?OR a, c", salida)
    assert "_t1" not in salida.split("== TABLA DE VERDAD ==")[1]     # temporales ocultas


def test_tabla_por_encima_del_limite_exige_todas(tmp_path):
    entradas = ", ".join(f"e{i}" for i in range(LIMITE_TABLA + 1))
    ruta = tmp_path / "grande.jace"
    ruta.write_text(f"ENTRADA[{entradas}]\nAND[{entradas}] -> y\n", encoding="utf-8")
    codigo, salida, _ = ejecutar(str(ruta), "--tabla")
    assert codigo == 0
    assert "--tabla --todas" in salida
    assert "0 | 0 | 0" not in salida


def test_verilog_por_pantalla_y_a_archivo(tmp_path):
    _, salida, _ = ejecutar("pruebas/01_circuito_valido.jace", "--verilog", "--testbench")
    assert "module circuito (a, b, c, salida);" in salida
    assert "module circuito_tb;" in salida
    destino = tmp_path / "c.v"
    codigo, salida, _ = ejecutar("pruebas/01_circuito_valido.jace", "--emit", "verilog",
                                 "-o", str(destino))
    assert codigo == 0
    assert destino.read_text(encoding="utf-8").startswith("// Generado por JACE")


@pytest.mark.parametrize("argumentos", [
    ["no_existe.jace"],
    ["README.md"],
    ["pruebas/01_circuito_valido.jace", "-o", "x.v"],
    ["pruebas/01_circuito_valido.jace", "--todas"],
    ["pruebas/01_circuito_valido.jace", "--opcion-inventada"],
])
def test_uso_incorrecto_devuelve_2(argumentos):
    codigo, _, error = ejecutar(*argumentos)
    assert codigo == 2
    assert "error" in error.lower()


def test_ayuda():
    codigo, salida, _ = ejecutar("--help")
    assert codigo == 0
    assert "--verilog" in salida and "Códigos de salida" in salida


def test_colores_solo_en_terminal(monkeypatch):
    import consola

    class Falsa:
        def isatty(self):
            return True

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(consola, "activar_vt_windows", lambda: True)
    assert consola.usar_colores(Falsa()) is True
    monkeypatch.setenv("NO_COLOR", "1")
    assert consola.usar_colores(Falsa()) is False


def test_modo_interactivo_conserva_el_menu():
    proceso = subprocess.run([PYTHON, os.path.join(RAIZ, "main.py")],
                             input="AYUDA\nANALIZAR\nENTRADA[a]\nNOT[a] -> b\n\nCERRAR\n",
                             capture_output=True, cwd=RAIZ, text=True, encoding="utf-8",
                             env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    assert proceso.returncode == 0
    assert "COMANDOS DISPONIBLES" in proceso.stdout
    assert "ANÁLISIS EXITOSO" in proceso.stdout
    assert "└── " in proceso.stdout                        # árbol ASCII, no JSON


# ---------------------------------------------------------------------------
# 4.9 La consola y la web muestran la misma información
# ---------------------------------------------------------------------------
PATRON_DIAGNOSTICO = re.compile(
    r"^  (?P<marca>[✖⚠]) (?P<pos>general|línea (?P<l>\d+)(?:, columna (?P<c>\d+))?) · "
    r"(?P<fase>[^:]+): (?P<mensaje>.*)$")


def diagnosticos_de_la_cli(salida):
    resultado = []
    lineas = salida.splitlines()
    for i, linea in enumerate(lineas):
        m = PATRON_DIAGNOSTICO.match(linea)
        if not m:
            continue
        siguiente = lineas[i + 1] if i + 1 < len(lineas) else ""
        sugerencia = (siguiente.strip()[len("sugerencia: "):]
                      if siguiente.strip().startswith("sugerencia: ") else None)
        resultado.append({
            "fase": m["fase"], "severidad": "error" if m["marca"] == "✖" else "advertencia",
            "linea": int(m["l"]) if m["l"] else None,
            "columna": int(m["c"]) if m["c"] else None,
            "mensaje": m["mensaje"], "sugerencia": sugerencia})
    return resultado


@pytest.mark.parametrize("ruta", PRUEBAS + EJEMPLOS, ids=os.path.basename)
def test_cli_y_api_dan_los_mismos_diagnosticos(ruta):
    with open(ruta, encoding="utf-8") as archivo:
        codigo = archivo.read()
    api = TestClient(app).post("/analizar", json={"codigo": codigo}).json()
    estado, salida, _ = ejecutar(ruta)
    assert diagnosticos_de_la_cli(salida) == api["diagnosticos"]
    assert estado == (0 if api["exito"] else 1)


# ---------------------------------------------------------------------------
# 4.4 Galería de ejemplos
# ---------------------------------------------------------------------------
ESPERADO = {
    "Circuito del enunciado": (True, None),
    "Sumador completo": (True, None),
    "Multiplexor 2:1": (True, None),
    "Comparador de 2 bits": (True, None),
    "Compuertas anidadas": (True, None),
    "Constantes que se simplifican": (True, None),
    "Circuito grande (38 compuertas)": (True, None),
    "Léxico: carácter inválido": (False, "léxico"),
    "Sintáctico: tres errores": (False, "sintáctico"),
    "Semántico: señal no definida": (False, "semántico"),
    "Semántico: ciclo": (False, "semántico"),
    "Advertencia: compuerta muerta": (True, "advertencia"),
}


def test_la_galeria_tiene_los_ejemplos_pedidos():
    datos = TestClient(app).get("/ejemplos").json()["ejemplos"]
    assert [e["titulo"] for e in datos] == list(ESPERADO)
    assert {e["grupo"] for e in datos} == {"Válidos", "Con errores"}
    assert any(e["archivo"].startswith("pruebas/") for e in datos)


@pytest.mark.parametrize("titulo", list(ESPERADO))
def test_cada_ejemplo_hace_lo_que_promete(titulo):
    http = TestClient(app)
    ejemplo = next(e for e in http.get("/ejemplos").json()["ejemplos"] if e["titulo"] == titulo)
    datos = http.post("/validar", json={"codigo": ejemplo["codigo"]}).json()
    exito, fase = ESPERADO[titulo]
    assert datos["exito"] is exito
    if fase == "advertencia":
        assert any(d["severidad"] == "advertencia" for d in datos["diagnosticos"])
    elif fase:
        assert {d["fase"] for d in datos["diagnosticos"]} == {fase}


def test_tres_errores_sintacticos_en_la_galeria():
    with open(os.path.join(RAIZ, "ejemplos", "error_sintactico_multiple.jace"),
              encoding="utf-8") as archivo:
        datos = TestClient(app).post("/validar", json={"codigo": archivo.read()}).json()
    assert len(datos["errores"]) == 3


def test_el_ejemplo_de_constantes_se_reduce_a_una_compuerta():
    with open(os.path.join(RAIZ, "ejemplos", "constantes_optimizables.jace"),
              encoding="utf-8") as archivo:
        datos = TestClient(app).post("/analizar", json={"codigo": archivo.read()}).json()
    assert datos["optimizacion"]["metricas_despues"]["compuertas"] == 1


# ---------------------------------------------------------------------------
# 4.1–4.7 Interfaz web (estructura)
# ---------------------------------------------------------------------------
def pagina():
    return TestClient(app).get("/").text


def test_navegacion_solo_analizar_e_historial():
    enlaces = re.findall(r'data-vista="(\w+)"', pagina())
    assert enlaces == ["analisis", "historial"]
    assert 'id="colorRapido"' not in pagina()
    assert "Ambiente" not in pagina()
    assert 'id="vista-background"' not in pagina()


def test_un_solo_boton_exportar_con_cuatro_formatos():
    html = pagina()
    assert 'id="descargarSvg"' not in html
    assert re.findall(r'data-exportar="(\w+)"', html) == ["svg", "csv", "json", "verilog"]


def test_editor_con_margen_guia_y_galeria():
    html = pagina()
    for pieza in ('id="margen"', 'wrap="off"', 'id="guiaSintaxis"', 'id="botonEjemplos"',
                  'id="listaEjemplos"'):
        assert pieza in html
    assert 'id="ejemplo"' not in html
    assert "Cargar ejemplo" not in html


def test_la_ruta_background_abre_el_popover():
    codigo = TestClient(app).get("/app.js").text
    assert '#/background' in codigo and "abrirPopoverFondo" in codigo


def test_la_web_no_usa_recursos_externos():
    for archivo in ("index.html", "app.js", "style.css", "exportar.js"):
        texto = TestClient(app).get(f"/{archivo}").text
        assert not re.search(r"(src|href)=\"https?://", texto), archivo
        assert "@import url(http" not in texto
        assert "fetch(\"http" not in texto


def test_el_contador_de_diagnosticos_tiene_texto_accesible():
    html = pagina()
    assert 'id="textoBadge"' in html
    assert 'aria-haspopup="true" aria-expanded="false" aria-controls="listaExportar"' in html
