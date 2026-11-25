"""Regresiones de los errores corregidos en la revisión del compilador.

Cada prueba corresponde a un fallo concreto que se podía reproducir antes:
líneas corridas, auto-conexiones, cadenas largas, comentarios al final de la
línea, alfabeto laxo y archivos que se sobrescribían sin permiso.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gestor_reglas import GestorReglas
from semantico import AnalizadorSemantico


def _analizar(codigo, **opciones):
    gestor = GestorReglas()
    opciones.setdefault("imprimir", False)
    opciones.setdefault("con_diagrama", False)
    opciones.setdefault("registrar", False)
    return gestor.analizar(codigo, **opciones)


# ---------------------------------------------------------------------------
# Números de línea
# ---------------------------------------------------------------------------
def test_los_comentarios_y_lineas_vacias_no_corren_los_errores():
    codigo = "# titulo\n\nENTRADA[a]\nAND[a, z] -> x"
    resultado = _analizar(codigo)
    assert resultado["exito"] is False
    assert resultado["errores"] == [
        "Error semántico línea 4: la señal z no está definida"]


def test_las_lineas_iniciales_en_blanco_no_corren_los_errores():
    codigo = "\n\nENTRADA[a]\nNOT[a] -> x\nAND[x, z] -> y"
    resultado = _analizar(codigo)
    assert resultado["errores"] == [
        "Error semántico línea 5: la señal z no está definida"]


# ---------------------------------------------------------------------------
# Ciclos, incluida la auto-conexión
# ---------------------------------------------------------------------------
def test_una_compuerta_conectada_a_si_misma_no_rompe_el_programa():
    codigo = "ENTRADA[a]\nAND[x, a] -> x"
    resultado = _analizar(codigo)

    assert resultado["exito"] is False
    assert any("ciclo detectado" in error for error in resultado["errores"])
    assert any("x → x" in error for error in resultado["errores"])


def test_el_mensaje_de_ciclo_muestra_el_camino_completo():
    codigo = "ENTRADA[a]\nNOT[x] -> y\nNOT[y] -> x\nAND[x, a] -> salida"
    resultado = _analizar(codigo)

    assert resultado["exito"] is False
    ciclo = [e for e in resultado["errores"] if "ciclo detectado" in e]
    assert len(ciclo) == 1
    # El camino exacto del bucle, con la señal repetida al final.
    camino = ciclo[0].split("ciclo detectado: ", 1)[1]
    assert camino in ("x → y → x", "y → x → y")


# ---------------------------------------------------------------------------
# Cadenas largas (sin límite oculto por recursión)
# ---------------------------------------------------------------------------
def test_una_cadena_de_mas_de_mil_compuertas_no_agota_la_pila():
    compuertas = 1500
    lineas = ["ENTRADA[a]", "NOT[a] -> n0"]
    for i in range(1, compuertas):
        lineas.append(f"NOT[n{i - 1}] -> n{i}")
    resultado = _analizar("\n".join(lineas))

    assert resultado["exito"] is True
    assert len(resultado["orden_topologico"]) == compuertas
    assert len(resultado["tabla_verdad"]["filas"]) == 2
    # La expresión expandida se omite por longitud, pero no revienta.
    datos = resultado["expresiones_booleanas"]["n1499"]
    assert datos["expandida"] is None
    assert "demasiado larga" in datos["aviso"]


# ---------------------------------------------------------------------------
# Comentarios y alfabeto
# ---------------------------------------------------------------------------
def test_comentario_al_final_de_una_instruccion():
    codigo = "ENTRADA[a, b]  # entradas\nAND[a, b] -> x # salida"
    resultado = _analizar(codigo)
    assert resultado["exito"] is True


def test_no_se_aceptan_caracteres_fuera_del_alfabeto():
    resultado = _analizar("ENTRADA[a]\nNOT[a] -> b²")
    assert resultado["exito"] is False
    assert any("carácter no reconocido '²'" in error
               for error in resultado["errores"])


# ---------------------------------------------------------------------------
# Validación rápida: no calcula la tabla de verdad
# ---------------------------------------------------------------------------
def test_la_validacion_rapida_no_calcula_la_tabla(monkeypatch):
    def tabla_prohibida(self):
        raise AssertionError("la validación no debe calcular la tabla de verdad")

    monkeypatch.setattr(AnalizadorSemantico, "tabla_verdad", tabla_prohibida)

    resultado = _analizar("ENTRADA[a]\nNOT[a] -> x", con_resultados=False)
    assert resultado["exito"] is True
    assert resultado["tabla_verdad"]["filas"] == []


# ---------------------------------------------------------------------------
# Archivos: nada se escribe salvo que se pida
# ---------------------------------------------------------------------------
def test_analizar_no_escribe_archivos_por_defecto(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    resultado = _analizar("ENTRADA[a]\nNOT[a] -> x", con_diagrama=True)
    assert resultado["exito"] is True
    assert os.listdir(tmp_path) == []


def test_analizar_escribe_el_diagrama_cuando_se_pide(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    resultado = _analizar("ENTRADA[a]\nNOT[a] -> x", con_diagrama=True,
                          escribir_archivos=True)
    assert resultado["exito"] is True
    assert sorted(os.listdir(tmp_path)) == ["diagrama_circuito.png",
                                             "diagrama_circuito.svg"]
