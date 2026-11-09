import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gestor_reglas import GestorReglas
from almacenamiento import Almacenamiento


def test_es_comando():
    gestor = GestorReglas()
    assert gestor.es_comando("ANALIZAR")
    assert gestor.es_comando("HISTORIAL")
    assert gestor.es_comando("EXPORTAR")
    assert gestor.es_comando("AYUDA")
    assert gestor.es_comando("CERRAR")
    assert not gestor.es_comando("COMPUERTA")
    assert not gestor.es_comando("INVENTADO")


def test_obtener_comando():
    gestor = GestorReglas()
    comando = gestor.obtener_comando("CERRAR")
    assert comando is not None
    assert comando["tipo"] == "salir"


def test_nombres_compuertas():
    gestor = GestorReglas()
    nombres = set(gestor.obtener_nombres_compuertas())
    assert {"AND", "OR", "NOT", "XOR", "NAND"} <= nombres


def test_palabras_reservadas():
    gestor = GestorReglas()
    reservadas = gestor.obtener_palabras_reservadas()
    assert "ENTRADA" in reservadas
    assert "AND" in reservadas


def test_analizar_circuito_valido():
    gestor = GestorReglas(almacenamiento=Almacenamiento())
    resultado = gestor.analizar(
        "ENTRADA[a, b]\n"
        "AND[a, b] -> x\n"
        "NOT[x] -> salida",
        imprimir=False,
    )
    assert resultado["exito"] is True
    assert resultado["errores"] == []
    assert len(resultado["tokens"]) > 0
    assert resultado["orden_topologico"][-1]["salida"] == "salida"
    assert resultado["tabla_verdad"]["señales"] == ["a", "b", "x", "salida"]
    assert len(resultado["tabla_verdad"]["filas"]) == 4
    assert resultado["expresiones"][0]["expresion"] == "NOT(a AND b)"
    assert "digraph circuito" in resultado["diagrama_dot"]


def test_analizar_circuito_invalido():
    gestor = GestorReglas(almacenamiento=Almacenamiento())
    resultado = gestor.analizar(
        "ENTRADA[a, b]\n"
        "NOT[a, b] -> salida",
        imprimir=False,
    )
    assert resultado["exito"] is False
    assert any("Error semántico" in e for e in resultado["errores"])


def test_analizar_vacio():
    gestor = GestorReglas(almacenamiento=Almacenamiento())
    resultado = gestor.analizar("", imprimir=False)
    assert resultado["exito"] is False
    assert any("vacío" in e for e in resultado["errores"])


def test_historial_se_llena():
    almacenamiento = Almacenamiento()
    gestor = GestorReglas(almacenamiento=almacenamiento)
    gestor.analizar("ENTRADA[a]\nNOT[a] -> salida", imprimir=False)
    gestor.analizar("ENTRADA[a]\nNOT[a, b] -> salida", imprimir=False)

    historial = almacenamiento.obtener_historial()
    assert len(historial) == 2
    assert historial[0]["resultado"] is True
    assert historial[1]["resultado"] is False
    assert len(historial[1]["errores"]) >= 1


def test_cerrar_detiene():
    gestor = GestorReglas(almacenamiento=Almacenamiento())
    assert gestor.ejecutar("CERRAR") is False


# ---------------------------------------------------------------------------
# Expresiones booleanas (forma intermedia y expandida)
# ---------------------------------------------------------------------------
CIRCUITO_EXPRESIONES = """ENTRADA[a, b, c]
AND[a, b] -> x1
OR[x1, c] -> x2
XOR[x2, a] -> x3
NAND[x3, b] -> salida"""


def _analizar_sin_dibujar(gestor, circuito):
    return gestor.analizar(circuito, imprimir=False, con_diagrama=False,
                           escribir_archivos=False, registrar=False)


def test_expresiones_booleanas_en_el_resultado():
    gestor = GestorReglas()
    resultado = _analizar_sin_dibujar(gestor, CIRCUITO_EXPRESIONES)

    datos = resultado["expresiones_booleanas"]["salida"]
    assert datos["intermedia"] == ["x1 = a · b", "x2 = x1 + c",
                                   "x3 = x2 ⊕ a", "salida = ¬(x3 · b)"]
    assert datos["expandida"] == "¬(((a · b + c) ⊕ a) · b)"
    assert datos["aviso"] is None
    assert datos["intermedia_ascii"][-1] == "salida = !(x3 & b)"
    assert datos["expandida_ascii"] == "!(((a & b | c) ^ a) & b)"


def test_expresiones_antiguas_no_cambian():
    """`expresiones` conserva su formato anterior: lista de {salida, expresion}."""
    gestor = GestorReglas()
    resultado = _analizar_sin_dibujar(gestor, CIRCUITO_EXPRESIONES)

    assert resultado["expresiones"] == [
        {"salida": "salida", "expresion": "(((a AND b) OR c) XOR a) NAND b"}
    ]


def test_expresiones_vacias_sin_errores():
    gestor = GestorReglas()
    resultado = _analizar_sin_dibujar(gestor, "ENTRADA[a, b]\nAND[a, z] -> x")

    assert resultado["exito"] is False
    assert resultado["expresiones_booleanas"] == {}


def test_expresiones_no_se_generan_si_no_hay_exito():
    gestor = GestorReglas()
    resultado = _analizar_sin_dibujar(gestor, "ENTRADA[a, b]\nAND[a, b]")

    assert resultado["exito"] is False
    assert resultado["expresiones"] == []
    assert resultado["expresiones_booleanas"] == {}


def test_expresiones_booleanas_tienen_una_entrada_por_salida_final():
    gestor = GestorReglas()
    resultado = _analizar_sin_dibujar(
        gestor, "ENTRADA[a, b]\nAND[a, b] -> x\nNOT[x] -> s1\nNAND[a, b] -> s2")

    assert set(resultado["expresiones_booleanas"]) == {"s1", "s2"}
    assert resultado["expresiones_booleanas"]["s1"]["expandida"] == "¬(a · b)"
    assert resultado["expresiones_booleanas"]["s2"]["expandida"] == "¬(a · b)"


def test_expresiones_se_generan_sin_dibujar_diagrama():
    """Con `con_diagrama=False` tampoco se necesita el SVG, pero sí las expresiones."""
    gestor = GestorReglas()
    resultado = _analizar_sin_dibujar(gestor, CIRCUITO_EXPRESIONES)

    assert resultado["diagrama_svg"] == ""
    assert resultado["expresiones_booleanas"]["salida"]["expandida"] is not None


# ---------------------------------------------------------------------------
# Comando EXPRESIONES
# ---------------------------------------------------------------------------
def test_expresiones_es_comando_del_menu():
    gestor = GestorReglas()
    assert gestor.es_comando("EXPRESIONES")
    comando = gestor.obtener_comando("EXPRESIONES")
    assert comando["tipo"] == "expresiones"


def test_comando_expresiones_sin_analisis_previo(capsys):
    gestor = GestorReglas()
    gestor.ejecutar("EXPRESIONES")
    assert "Use ANALIZAR primero" in capsys.readouterr().out


def test_comando_expresiones_muestra_ambas_notaciones(capsys):
    gestor = GestorReglas()
    _analizar_sin_dibujar(gestor, CIRCUITO_EXPRESIONES)
    gestor.ejecutar("EXPRESIONES")
    salida = capsys.readouterr().out

    assert "x1 = a · b" in salida
    assert "x1 = a & b" in salida
    assert "¬(((a · b + c) ⊕ a) · b)" in salida
    assert "!(((a & b | c) ^ a) & b)" in salida


def test_expresiones_no_se_recordan_si_el_analisis_falla(capsys):
    gestor = GestorReglas()
    _analizar_sin_dibujar(gestor, "ENTRADA[a, b]\nAND[a, z] -> x")
    gestor.ejecutar("EXPRESIONES")
    assert "Use ANALIZAR primero" in capsys.readouterr().out


def test_expresiones_usa_el_ultimo_analisis_exitoso(capsys):
    gestor = GestorReglas()
    _analizar_sin_dibujar(gestor, CIRCUITO_EXPRESIONES)
    _analizar_sin_dibujar(gestor, "ENTRADA[a]\nNOT[a] -> salida")
    gestor.ejecutar("EXPRESIONES")
    salida = capsys.readouterr().out

    assert "¬(a)" in salida
    assert "¬(((a · b + c) ⊕ a) · b)" not in salida


# ---------------------------------------------------------------------------
# El historial guarda las expresiones para el reporte
# ---------------------------------------------------------------------------
def test_historial_guarda_las_expresiones():
    almacenamiento = Almacenamiento()
    gestor = GestorReglas(almacenamiento=almacenamiento)
    gestor.analizar(CIRCUITO_EXPRESIONES, imprimir=False, con_diagrama=False,
                    escribir_archivos=False, registrar=True)

    registro = almacenamiento.obtener_historial()[0]
    assert registro["expresiones"]["salida"]["expandida"] == \
        "¬(((a · b + c) ⊕ a) · b)"


def test_historial_guarda_expresiones_vacias_si_falla():
    almacenamiento = Almacenamiento()
    gestor = GestorReglas(almacenamiento=almacenamiento)
    gestor.analizar("ENTRADA[a, b]\nAND[a, z] -> x", imprimir=False,
                    con_diagrama=False, escribir_archivos=False, registrar=True)

    assert almacenamiento.obtener_historial()[0]["expresiones"] == {}