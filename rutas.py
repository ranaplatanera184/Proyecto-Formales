# ============================================================================
# RUTAS DE LOS RECURSOS DE JACE
# ----------------------------------------------------------------------------
# Único punto que sabe dónde están reglas.json y la carpeta web/. Funciona
# igual desde el código fuente, desde otra carpeta de trabajo y dentro del
# ejecutable de PyInstaller (que descomprime los datos en sys._MEIPASS).
# ============================================================================

import json
import os
import sys

NOMBRE_REGLAS = "reglas.json"


class ErrorReglas(Exception):
    """reglas.json no existe o no es un JSON válido."""


def carpeta_base():
    """Carpeta de los recursos: la del ejecutable empaquetado o la del código."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return base
    return os.path.dirname(os.path.abspath(__file__))


def ruta_recurso(*partes):
    """Ruta absoluta de un recurso empaquetado con JACE (reglas.json, web/...)."""
    return os.path.join(carpeta_base(), *partes)


def ubicar_reglas(ruta=None):
    """Ruta de reglas.json.

    Sin argumento (o con el nombre por defecto) se usa siempre el archivo que
    viaja con el programa, sin depender del directorio actual. Una ruta
    distinta se respeta tal cual (la usan las pruebas con reglas propias).
    """
    if ruta is None or ruta == NOMBRE_REGLAS:
        return ruta_recurso(NOMBRE_REGLAS)
    return ruta


_CACHE = {}


def cargar_reglas(ruta=None):
    """Lee reglas.json y devuelve el diccionario de reglas.

    El archivo de reglas por defecto se lee una sola vez (se guarda en caché).
    Si falta o está dañado se lanza ErrorReglas con un mensaje claro: nunca se
    sigue en silencio con reglas inventadas.
    """
    destino = ubicar_reglas(ruta)
    if destino in _CACHE:
        return _CACHE[destino]
    try:
        with open(destino, "r", encoding="utf-8") as archivo:
            reglas = json.load(archivo)
    except FileNotFoundError as error:
        raise ErrorReglas(f"No se encontró el archivo de reglas: {destino}") from error
    except json.JSONDecodeError as error:
        raise ErrorReglas(
            f"El archivo de reglas {destino} no es un JSON válido "
            f"(línea {error.lineno}, columna {error.colno})") from error
    _CACHE[destino] = reglas
    return reglas
