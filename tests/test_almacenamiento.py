import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from almacenamiento import Almacenamiento


def test_agregar_analisis_exitoso():
    almacenamiento = Almacenamiento()
    almacenamiento.agregar_analisis("ENTRADA[a]", True, [])
    historial = almacenamiento.obtener_historial()
    assert len(historial) == 1
    assert historial[0]["entrada"] == "ENTRADA[a]"
    assert historial[0]["resultado"] is True
    assert historial[0]["errores"] == []


def test_agregar_analisis_con_errores():
    almacenamiento = Almacenamiento()
    errores = ["Error semántico línea 2: la señal z no está definida"]
    almacenamiento.agregar_analisis("ENTRADA[a]\nAND[a, z] -> x", False, errores)
    historial = almacenamiento.obtener_historial()
    assert historial[0]["resultado"] is False
    assert historial[0]["errores"] == errores


def test_historial_vacio():
    almacenamiento = Almacenamiento()
    assert almacenamiento.obtener_historial() == []


def test_exportar_reporte(tmp_path):
    almacenamiento = Almacenamiento()
    almacenamiento.agregar_analisis("ENTRADA[a, b]\nAND[a, b] -> x", True, [])

    ruta = str(tmp_path / "reporte.txt")
    resultado = almacenamiento.exportar_reporte_txt(ruta)
    assert resultado == ruta
    assert os.path.exists(ruta)

    with open(ruta, "r", encoding="utf-8") as archivo:
        contenido = archivo.read()
    assert "REPORTE DE ANÁLISIS DE CIRCUITO" in contenido
    assert "ANÁLISIS EXITOSO" in contenido
    assert "ENTRADA[a, b]" in contenido


def test_exportar_sin_historial(tmp_path):
    almacenamiento = Almacenamiento()
    ruta = str(tmp_path / "reporte.txt")
    assert almacenamiento.exportar_reporte_txt(ruta) is None
    assert not os.path.exists(ruta)


# ---------------------------------------------------------------------------
# Expresiones en el reporte
# ---------------------------------------------------------------------------
EXPRESIONES = {
    "salida": {
        "intermedia": ["x1 = a · b", "salida = ¬(x1 + c)"],
        "expandida": "¬((a · b) + c)",
        "aviso": None,
        "intermedia_ascii": ["x1 = a & b", "salida = !(x1 | c)"],
        "expandida_ascii": "!((a & b) | c)",
    }
}


def test_agregar_analisis_guarda_las_expresiones():
    almacenamiento = Almacenamiento()
    almacenamiento.agregar_analisis("ENTRADA[a, b, c]", True, [], EXPRESIONES)
    assert almacenamiento.obtener_historial()[0]["expresiones"] == EXPRESIONES


def test_agregar_analisis_sin_expresiones():
    """El cuarto argumento es opcional: las llamadas de tres argumentos siguen valiendo."""
    almacenamiento = Almacenamiento()
    almacenamiento.agregar_analisis("ENTRADA[a]", True, [])
    assert almacenamiento.obtener_historial()[0]["expresiones"] == {}


def test_agregar_analisis_copia_las_expresiones():
    """Si el llamador modifica el diccionario después, el historial no cambia."""
    # Listas propias: si se compartieran con la constante de arriba, la mutación
    # de este test contaminaría los tests que la usan.
    expresiones = {"salida": {
        "intermedia": list(EXPRESIONES["salida"]["intermedia"]),
        "expandida": EXPRESIONES["salida"]["expandida"],
        "aviso": None,
        "intermedia_ascii": list(EXPRESIONES["salida"]["intermedia_ascii"]),
        "expandida_ascii": EXPRESIONES["salida"]["expandida_ascii"],
    }}
    almacenamiento = Almacenamiento()
    almacenamiento.agregar_analisis("c", True, [], expresiones)

    expresiones["salida"]["expandida"] = "MUTADA"
    expresiones["salida"]["intermedia"].append("inyectada")

    guardado = almacenamiento.obtener_historial()[0]["expresiones"]["salida"]
    assert guardado["expandida"] == "¬((a · b) + c)"
    assert guardado["intermedia"] == ["x1 = a · b", "salida = ¬(x1 + c)"]


def test_reporte_incluye_las_expresiones(tmp_path):
    almacenamiento = Almacenamiento()
    almacenamiento.agregar_analisis("ENTRADA[a, b, c]", True, [], EXPRESIONES)

    ruta = str(tmp_path / "reporte.txt")
    almacenamiento.exportar_reporte_txt(ruta)
    with open(ruta, "r", encoding="utf-8") as archivo:
        contenido = archivo.read()

    assert "EXPRESIONES BOOLEANAS:" in contenido
    assert "Salida: salida" in contenido
    assert "Forma intermedia (símbolos):" in contenido
    assert "x1 = a · b" in contenido
    assert "Forma intermedia (ASCII):" in contenido
    assert "x1 = a & b" in contenido
    assert "Forma expandida (símbolos):" in contenido
    assert "¬((a · b) + c)" in contenido
    assert "Forma expandida (ASCII):" in contenido
    assert "!((a & b) | c)" in contenido


def test_reporte_indica_cuando_la_expandida_no_esta_disponible(tmp_path):
    expresiones = {"salida": {
        "intermedia": ["x = a"],
        "expandida": None,
        "aviso": "Expresión expandida demasiado larga (4263 caracteres)",
        "intermedia_ascii": ["x = a"],
        "expandida_ascii": None,
    }}
    almacenamiento = Almacenamiento()
    almacenamiento.agregar_analisis("c", True, [], expresiones)

    ruta = str(tmp_path / "reporte.txt")
    almacenamiento.exportar_reporte_txt(ruta)
    with open(ruta, "r", encoding="utf-8") as archivo:
        contenido = archivo.read()

    assert "(no disponible) Expresión expandida demasiado larga" in contenido
    # La intermedia sí está: no se recorta aunque la expandida no quepa.
    assert "x = a" in contenido


def test_reporte_sin_expresiones_no_deja_encabezado(tmp_path):
    """Un análisis con errores no debe dejar una sección de expresiones vacía."""
    almacenamiento = Almacenamiento()
    almacenamiento.agregar_analisis("ENTRADA[a, b]\nAND[a, z] -> x", False,
                                   ["Error semántico línea 2: la señal z no está definida"])

    ruta = str(tmp_path / "reporte.txt")
    almacenamiento.exportar_reporte_txt(ruta)
    with open(ruta, "r", encoding="utf-8") as archivo:
        contenido = archivo.read()

    assert "EXPRESIONES BOLEANAS" not in contenido
    assert "Error semántico línea 2" in contenido