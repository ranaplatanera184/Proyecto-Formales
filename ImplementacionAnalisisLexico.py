# ============================================================================
# FASE LEXICA DEL COMPILADOR DE CIRCUITOS
# ----------------------------------------------------------------------------
# Convierte el texto del circuito en una lista de tokens, cada uno con su
# linea y columna de origen. Las palabras reservadas provienen de reglas.json
# para mantener las reglas del lenguaje en un unico lugar.
# ============================================================================

import json

from Token import Token


def _cargar_palabras_reservadas(ruta="reglas.json"):
    """Lee las palabras reservadas del lenguaje desde reglas.json."""
    reservadas = {"ENTRADA", "AND", "OR", "NOT", "XOR", "NAND", "NOR", "XNOR"}
    try:
        with open(ruta, "r", encoding="utf-8") as archivo:
            reglas = json.load(archivo)
        reservadas = set(reglas.get("palabras_reservadas", reservadas))
    except Exception:
        pass
    return reservadas


def _es_inicio_identificador(caracter):
    """Un identificador empieza con una letra."""
    return caracter.isalpha()


def _es_parte_identificador(caracter):
    """Un identificador continua con letras, digitos o guion bajo."""
    return caracter.isalpha() or caracter.isdigit() or caracter == "_"


def tokenizar_linea(linea, numero_linea, palabras_reservadas):
    """Tokeniza una sola linea devolviendo (tokens, errores)."""
    tokens = []
    errores = []

    i = 0
    n = len(linea)

    while i < n:
        caracter = linea[i]

        # Se ignoran los espacios en blanco.
        if caracter.isspace():
            i += 1
            continue

        columna = i + 1

        # Flecha "->" se reconoce como un unico token de dos caracteres.
        if caracter == "-" :
            if i + 1 < n and linea[i + 1] == ">":
                tokens.append(Token("FLECHA", "->", numero_linea, columna))
                i += 2
            else:
                errores.append(
                    f"Error léxico línea {numero_linea}: carácter no reconocido '{caracter}'")
                i += 1
            continue

        if caracter == ">":
            errores.append(
                f"Error léxico línea {numero_linea}: carácter no reconocido '{caracter}'")
            i += 1
            continue

        # Simbolos de apertura/cierre y coma.
        if caracter == "[":
            tokens.append(Token("CORCHETE ABRE", caracter, numero_linea, columna))
            i += 1
            continue

        if caracter == "]":
            tokens.append(Token("CORCHETE CIERRA", caracter, numero_linea, columna))
            i += 1
            continue

        if caracter == ",":
            tokens.append(Token("COMA", caracter, numero_linea, columna))
            i += 1
            continue

        # Palabras: palabras reservadas o identificadores.
        if _es_inicio_identificador(caracter):
            inicio = i
            while i < n and _es_parte_identificador(linea[i]):
                i += 1
            palabra = linea[inicio:i]

            if palabra.upper() in palabras_reservadas:
                tokens.append(Token("PALABRA RESERVADA", palabra.upper(), numero_linea, columna))
            else:
                tokens.append(Token("IDENTIFICADOR", palabra, numero_linea, columna))
            continue

        # Ni digitos ni guion bajo pueden iniciar un identificador.
        errores.append(
            f"Error léxico línea {numero_linea}: carácter no reconocido '{caracter}'")
        i += 1

    return tokens, errores


def tokenizar_circuito(texto, palabras_reservadas=None):
    """Tokeniza un circuito completo (varias lineas) devolviendo (tokens, errores).

    Cada token lleva su numero de linea y columna; los errores lexicos se
    reportan con el formato exigido: 'Error léxico línea N: mensaje'.
    """
    if palabras_reservadas is None:
        palabras_reservadas = _cargar_palabras_reservadas()

    tokens = []
    errores = []

    for numero_linea, linea in enumerate(texto.split("\n"), start=1):
        tokens_linea, errores_linea = tokenizar_linea(linea, numero_linea, palabras_reservadas)
        tokens.extend(tokens_linea)
        errores.extend(errores_linea)

    return tokens, errores