import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import schematico
from gestor_reglas import GestorReglas
from SERVIRCOR import app, fondo_actual, FONDO_ACTIVO, FONDOS

CIRCUITO = """ENTRADA[a, b]
AND[a, b] -> x
NOT[x] -> salida
"""


def cliente():
    from fastapi.testclient import TestClient
    return TestClient(app)


# ---------------------------------------------------------------------------
# Colores de fondo (los usa la ruta /background).
# ---------------------------------------------------------------------------
def test_es_color_valido():
    assert schematico.es_color_valido("#FFFFFF")
    assert schematico.es_color_valido("#fff")
    assert schematico.es_color_valido(" #1f2937 ")
    assert not schematico.es_color_valido("#12345")
    assert not schematico.es_color_valido("rojo")
    assert not schematico.es_color_valido(None)
    assert not schematico.es_color_valido("#GGGGGG")


def test_normalizar_color():
    assert schematico.normalizar_color("#fff") == "#FFFFFF"
    assert schematico.normalizar_color("#1f2937") == "#1F2937"
    assert schematico.normalizar_color("no es color") is None


def test_es_fondo_oscuro():
    assert schematico.es_fondo_oscuro("#000000")
    assert schematico.es_fondo_oscuro("#0b1220")
    assert not schematico.es_fondo_oscuro("#ffffff")
    assert not schematico.es_fondo_oscuro("#fdf6e3")


def test_fondo_por_defecto():
    estado = fondo_actual()
    assert estado["fondo"] == FONDO_ACTIVO["valor"]
    assert estado["oscuro"] is False
    assert len(estado["fondos"]) == len(FONDOS)


# ---------------------------------------------------------------------------
# Diagrama con fondo (el color llega hasta schematico).
# ---------------------------------------------------------------------------
def test_analizar_con_fondo_oscuro():
    gestor = GestorReglas()
    resultado = gestor.analizar(CIRCUITO, imprimir=False, fondo="#0B1220",
                                escribir_archivos=False)
    assert resultado["exito"] is True
    assert "#0b1220" in resultado["diagrama_svg"].lower()
    # Con fondo oscuro el esquema usa la paleta clara (líneas claras).
    assert "#e5e7eb" in resultado["diagrama_svg"].lower()


def test_analizar_fondo_invalido_usa_el_por_defecto():
    gestor = GestorReglas()
    resultado = gestor.analizar(CIRCUITO, imprimir=False, fondo="zzz",
                                escribir_archivos=False)
    assert resultado["exito"] is True
    assert schematico.FONDO.lower() in resultado["diagrama_svg"].lower()


def test_exportar_sin_escribir_archivos(tmp_path):
    circuito = schematico.generar_diagrama(
        ["a", "b"], [{"compuerta": "AND", "salida": "x", "entradas": ["a", "b"]}])
    svg = schematico.exportar(circuito, base=str(tmp_path / "salida"),
                              escribir_archivos=False)
    assert svg.startswith("<?xml") or "<svg" in svg
    assert os.listdir(tmp_path) == []       # no dejó archivos


# ---------------------------------------------------------------------------
# Rutas del computador: /background y /analizar.
# ---------------------------------------------------------------------------
def test_get_background():
    respuesta = cliente().get("/background")
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert "fondo" in datos and "fondos" in datos


def test_post_background_cambia_el_fondo():
    http = cliente()
    respuesta = http.post("/background", json={"fondo": "#1f2937"})
    assert respuesta.status_code == 200
    assert respuesta.json()["fondo"] == "#1F2937"
    assert respuesta.json()["oscuro"] is True

    # El análisis posterior usa ese fondo por defecto.
    resultado = http.post("/analizar", json={"codigo": CIRCUITO}).json()
    assert resultado["fondo"] == "#1F2937"
    assert "#1f2937" in resultado["diagrama_svg"].lower()

    http.post("/background", json={"fondo": "#FFFFFF"})


def test_post_background_rechaza_color_invalido():
    respuesta = cliente().post("/background", json={"fondo": "azul"})
    assert respuesta.status_code == 400
    assert respuesta.json()["exito"] is False


def test_analizar_acepta_fondo_propio():
    respuesta = cliente().post("/analizar",
                               json={"codigo": CIRCUITO, "fondo": "#fdf6e3"})
    datos = respuesta.json()
    assert datos["exito"] is True
    assert datos["fondo"] == "#FDF6E3"
    assert "#fdf6e3" in datos["diagrama_svg"].lower()


def test_analizar_circuito_invalido():
    datos = cliente().post("/analizar", json={"codigo": "AND[a] -> x"}).json()
    assert datos["exito"] is False
    assert datos["errores"]


def test_interfaz_web_se_sirve():
    http = cliente()
    pagina = http.get("/")
    assert pagina.status_code == 200
    assert "JACE" in pagina.text
    assert http.get("/app.js").status_code == 200
    assert http.get("/style.css").status_code == 200


def test_reglas_json_se_encuentra_desde_cualquier_carpeta(tmp_path):
    """La app abre el ejecutable desde cualquier carpeta: reglas.json debe aparecer."""
    anterior = os.getcwd()
    try:
        os.chdir(tmp_path)
        gestor = GestorReglas()
        assert gestor.es_comando("ANALIZAR")
        assert "XNOR" in gestor.obtener_nombres_compuertas()
    finally:
        os.chdir(anterior)


# ---------------------------------------------------------------------------
# Historial web: mismas funciones que el comando HISTORIAL de la consola.
# ---------------------------------------------------------------------------
def limpiar_historial_web():
    cliente().delete("/historial")


def test_historial_web_empieza_vacio():
    limpiar_historial_web()
    respuesta = cliente().get("/historial")
    assert respuesta.status_code == 200
    assert respuesta.json()["analisis"] == []


def test_analizar_registra_en_el_historial():
    limpiar_historial_web()
    http = cliente()
    http.post("/analizar", json={"codigo": CIRCUITO})

    analisis = http.get("/historial").json()["analisis"]
    assert len(analisis) == 1
    registro = analisis[0]
    assert registro["indice"] == 0
    assert registro["resultado"] is True
    assert registro["primera_linea"] == "ENTRADA[a, b]"
    assert registro["entrada"] == CIRCUITO.strip()
    assert registro["fecha"]


def test_historial_conserva_analisis_con_errores():
    limpiar_historial_web()
    http = cliente()
    http.post("/analizar", json={"codigo": "AND[a] -> x"})
    http.post("/analizar", json={"codigo": CIRCUITO})

    analisis = http.get("/historial").json()["analisis"]
    assert len(analisis) == 2
    assert analisis[0]["resultado"] is False
    assert analisis[0]["errores"]
    assert analisis[1]["resultado"] is True
    limpiar_historial_web()


def test_borrar_un_analisis_del_historial():
    limpiar_historial_web()
    http = cliente()
    http.post("/analizar", json={"codigo": CIRCUITO})
    http.post("/analizar", json={"codigo": "AND[a] -> x"})

    respuesta = http.delete("/historial/0")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"exito": True, "borrado": 0}

    analisis = http.get("/historial").json()["analisis"]
    assert len(analisis) == 1
    assert analisis[0]["resultado"] is False
    limpiar_historial_web()


def test_borrar_analisis_inexistente():
    limpiar_historial_web()
    respuesta = cliente().delete("/historial/7")
    assert respuesta.status_code == 404
    assert respuesta.json()["exito"] is False


def test_limpiar_historial():
    limpiar_historial_web()
    http = cliente()
    http.post("/analizar", json={"codigo": CIRCUITO})
    http.post("/analizar", json={"codigo": CIRCUITO})

    respuesta = http.delete("/historial")
    assert respuesta.json() == {"exito": True, "borrados": 2}
    assert http.get("/historial").json()["analisis"] == []


def test_almacenamiento_tiene_fecha_y_borrado():
    from almacenamiento import Almacenamiento

    almacenamiento = Almacenamiento()
    almacenamiento.agregar_analisis(CIRCUITO, True, [])
    assert "fecha" in almacenamiento.obtener_historial()[0]

    assert almacenamiento.eliminar_analisis(0) is True
    assert almacenamiento.eliminar_analisis(0) is False
    assert almacenamiento.eliminar_analisis(-1) is False
    assert almacenamiento.obtener_historial() == []

    almacenamiento.agregar_analisis(CIRCUITO, True, [])
    assert almacenamiento.limpiar_historial() == 1
    assert almacenamiento.obtener_historial() == []


# ---------------------------------------------------------------------------
# Validación rápida (POST /validar): errores sin diagrama ni historial.
# ---------------------------------------------------------------------------
def test_validar_devuelve_errores():
    datos = cliente().post("/validar", json={"codigo": "AND[a] -> x"}).json()
    assert datos["exito"] is False
    assert len(datos["errores"]) >= 1
    assert "diagrama_svg" not in datos


def test_validar_reporta_error_semantico_con_linea():
    """El frontend usa 'Error <tipo> línea N:' para el salto al editor."""
    datos = cliente().post("/validar",
                           json={"codigo": "ENTRADA[a]\nAND[a, z] -> x"}).json()
    assert datos["exito"] is False
    assert datos["errores"] == [
        "Error semántico línea 2: la señal z no está definida"]


def test_validar_circuito_valido():
    datos = cliente().post("/validar", json={"codigo": CIRCUITO}).json()
    assert datos["exito"] is True
    assert datos["errores"] == []
    assert len(datos["tokens"]) > 0


def test_validar_no_registra_en_el_historial():
    limpiar_historial_web()
    cliente().post("/validar", json={"codigo": CIRCUITO})
    cliente().post("/validar", json={"codigo": "AND[a] -> x"})
    assert cliente().get("/historial").json()["analisis"] == []


def test_validar_vacio():
    datos = cliente().post("/validar", json={"codigo": "   "}).json()
    assert datos["exito"] is False
    assert "vacío" in datos["errores"][0]


def test_validar_solo_comentarios_es_vacio():
    datos = cliente().post("/validar", json={"codigo": "# solo notas\n\n#otra"}).json()
    assert datos["exito"] is False
    assert "vacío" in datos["errores"][0]


def test_comentarios_se_omiten_por_la_web():
    """La consola ignora las líneas '#'; la web debe hacer lo mismo."""
    from SERVIRCOR import quitar_comentarios

    codigo = "# nota\nENTRADA[a, b]\n#otro\nAND[a, b] -> x"
    limpio = quitar_comentarios(codigo)
    assert limpio.split("\n") == ["", "ENTRADA[a, b]", "", "AND[a, b] -> x"]

    datos = cliente().post("/validar", json={"codigo": codigo}).json()
    assert datos["exito"] is True
    assert datos["errores"] == []


def test_comentarios_conservan_el_numero_de_linea():
    """Se sustituyen por líneas vacías, no se borran: los errores no se corren."""
    codigo = "# titulo\nENTRADA[a, b]\n# mitad\nXOR[a, z] -> x"
    datos = cliente().post("/validar", json={"codigo": codigo}).json()
    # El analizador descarta las líneas vacías iniciales, por eso la línea 4 del
    # editor se reporta como la 3; la web aplica ese desplazamiento al saltar.
    assert datos["errores"] == [
        "Error semántico línea 3: la señal z no está definida"]
    assert datos["tokens"][-1]["linea"] == 3


def test_web_omite_comentarios_que_romperian_el_analizador():
    """Sin el filtro, '#' produce errores léxicos en cada línea de comentario."""
    codigo = "# titulo\nENTRADA[a, b]\nXOR[a, z] -> x"
    crudo = GestorReglas().analizar(codigo, imprimir=False, con_diagrama=False,
                                    registrar=False)
    assert any("léxico" in e for e in crudo["errores"])

    datos = cliente().post("/validar", json={"codigo": codigo}).json()
    assert not any("léxico" in e for e in datos["errores"])


def test_analizar_con_comentarios_y_fondo():
    datos = cliente().post("/analizar", json={
        "codigo": "# circuito con nota\nENTRADA[a, b]\nXNOR[a, b] -> salida",
        "fondo": "#FFFFFF"}).json()
    assert datos["exito"] is True
    assert len(datos["tabla_verdad"]["filas"]) == 4
    assert datos["diagrama_svg"].startswith("<?xml") or "<svg" in datos["diagrama_svg"]


def test_historial_guarda_el_circuito_analizado():
    """El historial conserva el circuito como lo analiza el compilador."""
    limpiar_historial_web()
    cliente().post("/analizar", json={"codigo": "# con nota\nENTRADA[a, b]\nAND[a, b] -> x"})
    registro = cliente().get("/historial").json()["analisis"][0]
    assert registro["resultado"] is True
    assert registro["entrada"] == "ENTRADA[a, b]\nAND[a, b] -> x"
    limpiar_historial_web()


def test_historial_guarda_el_texto_literal_sin_comentarios():
    limpiar_historial_web()
    cliente().post("/analizar", json={"codigo": "ENTRADA[a, b]\nXNOR[a, b] -> x"})
    registro = cliente().get("/historial").json()["analisis"][0]
    assert registro["entrada"] == "ENTRADA[a, b]\nXNOR[a, b] -> x"
    limpiar_historial_web()


def test_validar_no_escribe_archivos(tmp_path):
    anterior = os.getcwd()
    try:
        os.chdir(tmp_path)
        cliente().post("/validar", json={"codigo": CIRCUITO})
        assert os.listdir(tmp_path) == []
    finally:
        os.chdir(anterior)


def test_analizar_sin_diagrama_no_lo_dibuja():
    gestor = GestorReglas()
    resultado = gestor.analizar(CIRCUITO, imprimir=False, con_diagrama=False,
                                registrar=False, escribir_archivos=False)
    assert resultado["exito"] is True
    assert resultado["diagrama_svg"] == ""
    assert resultado["diagrama_dot"] == ""
    assert len(resultado["tabla_verdad"]["filas"]) == 4


def test_analizar_sin_registrar_no_llena_el_historial():
    from almacenamiento import Almacenamiento

    almacenamiento = Almacenamiento()
    gestor = GestorReglas(almacenamiento=almacenamiento)
    gestor.analizar(CIRCUITO, imprimir=False, registrar=False)
    assert almacenamiento.obtener_historial() == []
    gestor.analizar(CIRCUITO, imprimir=False, registrar=True)
    assert len(almacenamiento.obtener_historial()) == 1


# ---------------------------------------------------------------------------
# Piezas de la interfaz web (navegación, pestañas, zoom, historial, exportar).
# ---------------------------------------------------------------------------
def test_interfaz_tiene_navegacion_y_pestanas():
    pagina = cliente().get("/").text

    for pieza in ['data-vista="analisis"', 'data-vista="historial"',
                  'data-vista="background"', 'id="botonExportar"',
                  'id="menuExportar"', 'data-exportar="svg"',
                  'data-exportar="csv"', 'data-exportar="json"',
                  'id="visor"', 'id="pestanas"', 'data-panel="tabla"',
                  'data-panel="expresion"', 'data-panel="tokens"',
                  'data-panel="errores"',
                  'id="panel-expresion"', 'id="notacionExpresion"',
                  'id="copiarExpresion"', 'id="listaExpresiones"',
                  'id="tablaVerdad"', 'id="tablaTokens"', 'id="listaErrores"',
                  'id="listaHistorial"', 'id="cargarMas"',
                  'id="pantallaCompleta"', 'id="modalDiagrama"',
                  'src="exportar.js"', 'src="app.js"']:
        assert pieza in pagina, f"falta en la página: {pieza}"


def test_interfaz_no_ofrece_cerrar_jace():
    """El cierre de la aplicación es de la consola, no de la web."""
    pagina = cliente().get("/").text.lower()
    assert "cerrar jade" not in pagina
    assert 'id="salir"' not in pagina
