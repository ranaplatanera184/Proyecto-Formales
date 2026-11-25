# ============================================================================
# INTERFAZ DEL COMPILADOR DE CIRCUITOS LÓGICOS (JACE)
# ----------------------------------------------------------------------------
# Expone el compilador mediante FastAPI:
#   - Interfaz web (página servida en "/") con dos rutas de vista: el análisis
#     del circuito y la vista "background" (fondo visual de la página).
#   - Rutas del computador: /info, /analizar, /validar, /tabla, /historial y
#     /background (GET y POST).
# No depende de la consola (imprimir=False) y no escribe archivos en el disco.
# ============================================================================

import logging
import os
import sys
import traceback
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from gestor_reglas import GestorReglas, LIMITE_TABLA, mensaje_error_interno
from almacenamiento import Almacenamiento
from rutas import ruta_recurso
import diagnosticos as diag
import schematico

registro = logging.getLogger("jace.api")

# Máximo de filas que devuelve una sola petición a /tabla.
MAXIMO_FILAS_POR_PETICION = 4096

VERSION = "2.1"

app = FastAPI(
    title="JACE - Compilador de Circuitos Lógicos",
    description="Interfaz y API para analizar circuitos lógicos escritos en JACE",
    version=VERSION
)


# ---------------------------------------------------------------------------
# Recursos de la interfaz web (sirven dentro del ejecutable empaquetado).
# ---------------------------------------------------------------------------
def ruta_web():
    """Carpeta con la interfaz web (web/). Compatible con PyInstaller."""
    return ruta_recurso("web")


# Fondos predefinidos de la interfaz (además del color libre).
FONDOS = [
    {"nombre": "Blanco", "color": "#FFFFFF"},
    {"nombre": "Papel", "color": "#F5F3EE"},
    {"nombre": "Cielo", "color": "#E8F0FE"},
    {"nombre": "Menta", "color": "#E8F5F0"},
    {"nombre": "Arena", "color": "#FDF6E3"},
    {"nombre": "Grafito", "color": "#1F2937"},
    {"nombre": "Noche", "color": "#0B1220"},
    {"nombre": "Bosque", "color": "#0F2E23"},
]

# Fondo activo de la interfaz (lo fija la ruta POST /background).
FONDO_ACTIVO = {"valor": schematico.FONDO}

# Historial de la interfaz web: vive en la memoria de este servidor mientras
# la aplicación está abierta. La consola (main.py) es otro proceso con su
# propio historial, así que los dos NO se comparten.
ALMACENAMIENTO = Almacenamiento()


def respuesta_error_interno(error):
    """Convierte una excepción del compilador en un diagnóstico entendible.

    El detalle técnico se registra en el log (y el traceback completo se
    imprime si JACE_DEBUG=1); al usuario le llega un mensaje claro.
    """
    registro.error("Error interno en la API: %r", error)
    if os.environ.get("JACE_DEBUG") == "1":
        traceback.print_exc()
    fallo = diag.Diagnostico("interno", "error", None, None,
                             mensaje_error_interno(error))
    return {"exito": False, "errores": [fallo.texto()],
            "diagnosticos": [fallo.to_json()], "advertencias": []}


def respuesta_vacia():
    vacio = diag.error("léxico", 1, 1, "el circuito está vacío",
                       "escribe un circuito que empiece con ENTRADA[...]")
    return {"exito": False, "errores": [vacio.texto()],
            "diagnosticos": [vacio.to_json()], "advertencias": []}


def fondo_actual():
    """Devuelve el estado actual del fondo: color, si es oscuro y presets."""
    color = FONDO_ACTIVO["valor"]
    return {
        "fondo": color,
        "oscuro": schematico.es_fondo_oscuro(color),
        "fondos": FONDOS,
    }


def circuito_vacio(codigo):
    """True si el circuito no tiene nada que analizar (ignorando comentarios)."""
    return not codigo.strip() or all(linea.strip() == "" or
                                     linea.lstrip().startswith("#")
                                     for linea in codigo.split("\n"))


class CircuitoRequest(BaseModel):
    codigo: str
    fondo: Optional[str] = None


class FondoRequest(BaseModel):
    fondo: str


class TablaRequest(BaseModel):
    codigo: str
    desde: int = Field(0, ge=0)
    cantidad: int = Field(256, ge=1)


# ---------------------------------------------------------------------------
# Rutas del computador
# ---------------------------------------------------------------------------
@app.get("/info")
def inicio():
    return {
        "lenguaje": "JACE",
        "version": VERSION,
        "descripcion": "Compilador de circuitos lógicos digitales",
        "estado": "En desarrollo",
        "rutas": ["/info", "/analizar", "/validar", "/tabla", "/historial",
                  "/background"],
        "limite_tabla": LIMITE_TABLA,
    }


@app.post("/analizar")
def analizar_circuito(request: CircuitoRequest):
    """Analiza un circuito y devuelve el resultado del compilador en JSON.

    El campo opcional `fondo` es el color de fondo del diagrama; si no se
    envía se usa el fondo activo de la ruta /background. El análisis queda
    registrado en el historial (lo muestra la vista «Historial»).
    """
    try:
        if circuito_vacio(request.codigo):
            return respuesta_vacia()

        codigo = request.codigo
        fondo = schematico.normalizar_color(request.fondo) or fondo_actual()["fondo"]

        gestor = GestorReglas(almacenamiento=ALMACENAMIENTO)
        resultado = gestor.analizar(codigo, imprimir=False,
                                    fondo=fondo, escribir_archivos=False)
        resultado["fondo"] = fondo
        return resultado

    except Exception as error:
        return respuesta_error_interno(error)


@app.post("/validar")
def validar_circuito(request: CircuitoRequest):
    """Valida un circuito y devuelve solo si es válido y sus errores.

    No dibuja el diagrama, no calcula tabla de verdad/expresiones y no registra
    el análisis: la interfaz lo usa con cada tecla para mostrar los errores en
    la pestaña correspondiente. Calcular todo el resultado aquí congelaba la
    página en circuitos medianos.
    """
    try:
        if circuito_vacio(request.codigo):
            return respuesta_vacia()

        gestor = GestorReglas()
        resultado = gestor.analizar(request.codigo, imprimir=False,
                                    con_diagrama=False, registrar=False,
                                    escribir_archivos=False,
                                    con_resultados=False)
        return {
            "exito": resultado["exito"],
            "errores": resultado["errores"],
            "advertencias": resultado["advertencias"],
            "tokens": resultado["tokens"],
            "ast": resultado["ast"],
            "tabla_simbolos": resultado["tabla_simbolos"],
            "diagnosticos": resultado["diagnosticos"],
        }

    except Exception as error:
        return respuesta_error_interno(error)


@app.post("/tabla")
def tabla_por_bloques(request: TablaRequest):
    """Devuelve solo las filas [desde, desde + cantidad) de la tabla de verdad.

    Cada fila se calcula a partir de su índice binario, así que la tabla
    completa nunca se construye en memoria: sirve para circuitos con más
    entradas que LIMITE_TABLA (la web pide bloques al desplazarse y la
    exportación CSV los va concatenando).
    """
    try:
        if circuito_vacio(request.codigo):
            return respuesta_vacia()

        gestor = GestorReglas()
        semantico, resultado = gestor.preparar_evaluacion(request.codigo)
        if semantico is None:
            return {"exito": False, "errores": resultado["errores"],
                    "diagnosticos": resultado["diagnosticos"]}

        total = 2 ** len(semantico.entradas)
        desde = min(request.desde, total)
        cantidad = min(request.cantidad, MAXIMO_FILAS_POR_PETICION, total - desde)
        senales = semantico.senales_tabla()
        return {
            "exito": True,
            "señales": senales,
            "filas": semantico.filas_tabla(desde, cantidad, senales),
            "desde": desde,
            "cantidad": cantidad,
            "filas_totales": total,
        }

    except Exception as error:
        return respuesta_error_interno(error)


@app.get("/historial")
def obtener_historial():
    """Historial de análisis de la interfaz web (en memoria de este servidor)."""
    analisis = []
    for indice, registro in enumerate(ALMACENAMIENTO.obtener_historial()):
        entrada = registro.get("entrada", "")
        primera_linea = entrada.split("\n")[0].strip() if entrada else "(vacío)"
        analisis.append({
            "indice": indice,
            "entrada": entrada,
            "primera_linea": primera_linea,
            "resultado": registro.get("resultado", False),
            "errores": registro.get("errores", []),
            "fecha": registro.get("fecha", ""),
        })
    return {"analisis": analisis}


@app.delete("/historial/{indice}")
def borrar_historial(indice: int):
    """Borra un análisis del historial por su posición."""
    if not ALMACENAMIENTO.eliminar_analisis(indice):
        return JSONResponse(status_code=404,
                            content={"exito": False,
                                     "errores": [f"No existe el análisis {indice}"]})
    return {"exito": True, "borrado": indice}


@app.delete("/historial")
def limpiar_historial():
    """Borra todos los análisis del historial."""
    return {"exito": True, "borrados": ALMACENAMIENTO.limpiar_historial()}


@app.get("/background")
def obtener_background():
    """Devuelve el fondo visual actual de la interfaz y del diagrama."""
    return fondo_actual()


@app.post("/background")
def cambiar_background(request: FondoRequest):
    """Fija el fondo visual (color hex) de la interfaz y de los diagramas."""
    color = schematico.normalizar_color(request.fondo)
    if color is None:
        return JSONResponse(
            status_code=400,
            content={"exito": False,
                     "errores": ["Fondo no válido: use un color hex #RGB o #RRGGBB"]})

    FONDO_ACTIVO["valor"] = color
    return fondo_actual()


# ---------------------------------------------------------------------------
# Interfaz web: se monta al final para que las rutas de arriba sigan teniendo
# prioridad. El directorio se comprueba porque en un ejecutable antiguo (o sin
# la carpeta web/) la app debe seguir levantando la API.
# ---------------------------------------------------------------------------
if os.path.isdir(ruta_web()):
    app.mount("/", StaticFiles(directory=ruta_web(), html=True), name="web")
