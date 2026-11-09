# ============================================================================
# INTERFAZ DEL COMPILADOR DE CIRCUITOS LÓGICOS (JACE)
# ----------------------------------------------------------------------------
# Expone el compilador mediante FastAPI:
#   - Interfaz web (página servida en "/") con dos rutas de vista: el análisis
#     del circuito y la vista "background" (fondo visual de la página).
#   - Rutas del computador: /info, /analizar, /background (GET y POST).
# No depende de la consola (imprimir=False) y no escribe archivos en el disco.
# ============================================================================

import os
import sys
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from gestor_reglas import GestorReglas
from almacenamiento import Almacenamiento
import schematico

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
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "web")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


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

# Historial compartido: es el mismo almacenamiento que usa el comando
# HISTORIAL de la consola, así que la vista «Historial» de la web y la
# consola muestran los mismos análisis mientras la aplicación esté abierta.
ALMACENAMIENTO = Almacenamiento()


def fondo_actual():
    """Devuelve el estado actual del fondo: color, si es oscuro y presets."""
    color = FONDO_ACTIVO["valor"]
    return {
        "fondo": color,
        "oscuro": schematico.es_fondo_oscuro(color),
        "fondos": FONDOS,
    }


def quitar_comentarios(codigo):
    """Sustituye las líneas de comentario por líneas vacías.

    El analizador no reconoce el carácter `#`, pero el lenguaje JACE admite
    comentarios (los omite la consola). En la web el código llega tal como
    está en el editor, así que se neutralizan igual que en main.py. Se
    conservan las líneas vacías -en lugar de borrarlas- para que los números
    de línea de los errores sigan coincidiendo con el editor.
    """
    return "\n".join("" if linea.lstrip().startswith("#") else linea
                     for linea in codigo.split("\n"))


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
        "rutas": ["/info", "/analizar", "/validar", "/historial", "/background"],
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
            return {"exito": False, "errores": ["Error léxico línea 1: el circuito está vacío"]}

        codigo = quitar_comentarios(request.codigo)
        fondo = schematico.normalizar_color(request.fondo) or fondo_actual()["fondo"]

        gestor = GestorReglas(almacenamiento=ALMACENAMIENTO)
        resultado = gestor.analizar(codigo, imprimir=False,
                                    fondo=fondo, escribir_archivos=False)
        resultado["fondo"] = fondo
        return resultado

    except SyntaxError as error:
        return {"exito": False, "errores": [str(error)]}
    except Exception as error:
        return {"exito": False, "errores": [f"Error inesperado: {error}"]}


@app.post("/validar")
def validar_circuito(request: CircuitoRequest):
    """Valida un circuito y devuelve solo si es válido y sus errores.

    No dibuja el diagrama ni registra el análisis en el historial: la interfaz
    lo usa mientras se escribe para mostrar los errores en la pestaña
    correspondiente.
    """
    try:
        if circuito_vacio(request.codigo):
            return {"exito": False, "errores": ["Error léxico línea 1: el circuito está vacío"]}

        codigo = quitar_comentarios(request.codigo)
        gestor = GestorReglas()
        resultado = gestor.analizar(codigo, imprimir=False, con_diagrama=False,
                                    registrar=False, escribir_archivos=False)
        return {"exito": resultado["exito"], "errores": resultado["errores"],
                "tokens": resultado["tokens"]}

    except SyntaxError as error:
        return {"exito": False, "errores": [str(error)]}
    except Exception as error:
        return {"exito": False, "errores": [f"Error inesperado: {error}"]}


@app.get("/historial")
def obtener_historial():
    """Historial de análisis (el mismo que muestra HISTORIAL en la consola)."""
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
