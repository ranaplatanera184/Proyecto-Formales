# ============================================================================
# FASE LEXICA DEL COMPILADOR DE CIRCUITOS
# ----------------------------------------------------------------------------
# Convierte el texto del circuito en una lista de tokens, cada uno con su
# linea y columna de origen. Las palabras reservadas provienen de reglas.json
# para mantener las reglas del lenguaje en un unico lugar.
#
# Alfabeto: letras ASCII, dígitos, '_', los símbolos [ ] , -> y los espacios.
# Todo lo que sigue a '#' hasta el final de la línea es un comentario.
#
# Tokens: PALABRA RESERVADA, IDENTIFICADOR, CONSTANTE (0 y 1), CORCHETE
# ABRE, CORCHETE CIERRA, COMA y FLECHA.
#
# Recuperación de errores: el texto se corta en lexemas (secuencias sin
# espacios ni delimitadores) y cada lexema inválido produce UN solo error
# ("x$1" → "el nombre 'x$1' contiene el carácter no reconocido '$'"), no un
# error por carácter. Además se deja en su lugar un token ERROR interno que
# hace de comodín para que el parser pueda seguir analizando la sintaxis del
# resto de la línea sin inventar errores en cadena. Los tokens ERROR no se
# muestran al usuario.
# ============================================================================

from Token import Token
from rutas import cargar_reglas
import diagnosticos as diag

# Separadores que Python considera espacios (isspace) pero que el editor no
# muestra como espacio normal: se reportan como caracteres no válidos.
NO_ESPACIOS = set("\u2028\u2029\x85\x1c\x1d\x1e\x0b\x0c")


def _es_espacio(caracter):
    return caracter.isspace() and caracter not in NO_ESPACIOS


# Caracteres que separan lexemas (además de los espacios).
DELIMITADORES = set("[],#->")

TIPO_ERROR = "ERROR"

# Palabras reservadas que solo lo son en MAYÚSCULAS (añadidas después de que
# existieran circuitos que las usan como nombres en minúscula).
RESERVADAS_SENSIBLES = {"SALIDA"}

# Las constantes lógicas: 0 y 1 aislados (cualquier otro número es un error).
CONSTANTES_LOGICAS = ("0", "1")


def _cargar_palabras_reservadas(ruta=None):
    """Lee las palabras reservadas del lenguaje desde reglas.json.

    La ruta se resuelve en rutas.py (no depende del directorio actual). Si el
    archivo falta, se lanza rutas.ErrorReglas: no se inventan reglas.
    """
    return set(cargar_reglas(ruta).get("palabras_reservadas", []))


def _es_letra_ascii(caracter):
    """Letra del alfabeto del lenguaje (A-Z, a-z), sin unicode.

    `str.isalpha()` acepta caracteres como '²', 'Ω' o 'ñ'; el lenguaje JACE
    solo admite letras ASCII, así que el alfabeto se comprueba a mano.
    """
    return ("a" <= caracter <= "z") or ("A" <= caracter <= "Z")


def _es_digito(caracter):
    return "0" <= caracter <= "9"


def _es_inicio_identificador(caracter):
    """Un identificador empieza con una letra ASCII."""
    return _es_letra_ascii(caracter)


def _es_parte_identificador(caracter):
    """Un identificador continua con letras ASCII, digitos o guion bajo."""
    return _es_letra_ascii(caracter) or _es_digito(caracter) or caracter == "_"


def _visible(caracter):
    """El carácter tal cual, o su código si es invisible (U+200B, NUL...)."""
    if caracter.isprintable() and not caracter.isspace():
        return caracter
    return f"U+{ord(caracter):04X}"


def _token_error(sustituye, valor, linea, columna):
    """Comodín para el parser en el lugar de un lexema inválido."""
    token = Token(TIPO_ERROR, valor, linea, columna)
    token.sustituye = sustituye
    return token


def _clasificar_lexema(lexema, linea, columna, palabras_reservadas):
    """(token, diagnóstico) de un lexema; uno de los dos es None."""
    if _es_inicio_identificador(lexema[0]) and all(map(_es_parte_identificador, lexema)):
        palabra = lexema.upper()
        # SALIDA (fase 3) solo es palabra reservada escrita en mayúsculas:
        # "salida" era un nombre de señal muy usado y debe seguir siéndolo.
        es_reservada = (palabra in palabras_reservadas
                        and (palabra not in RESERVADAS_SENSIBLES or lexema == palabra))
        if es_reservada:
            return Token("PALABRA RESERVADA", palabra, linea, columna), None
        return Token("IDENTIFICADOR", lexema, linea, columna), None

    # Posición del primer carácter fuera del alfabeto de los nombres.
    invalidos = [i for i, c in enumerate(lexema) if not _es_parte_identificador(c)]
    if invalidos:
        primero = invalidos[0]
        caracter = _visible(lexema[primero])
        if len(invalidos) == len(lexema):
            # Solo símbolos extraños: "$", "@@", "😀".
            texto = "".join(_visible(c) for c in lexema)
            mensaje = (f"carácter no reconocido '{texto}'" if len(lexema) == 1
                       else f"caracteres no reconocidos '{texto}'")
        else:
            mensaje = (f"el nombre '{''.join(_visible(c) for c in lexema)}' contiene "
                       f"el carácter no reconocido '{caracter}'")
        if any(c.isalpha() for c in lexema if not _es_parte_identificador(c)):
            sugerencia = ("los nombres solo admiten letras sin tilde ni 'ñ' "
                          "(a-z, A-Z), dígitos y '_'")
        else:
            sugerencia = ("los nombres solo admiten letras ASCII, dígitos y '_'; "
                          "los símbolos válidos son [ ] , -> y # para comentarios")
        return None, diag.error("léxico", linea, columna + primero, mensaje, sugerencia)

    if lexema in CONSTANTES_LOGICAS:
        return Token("CONSTANTE", lexema, linea, columna), None

    if _es_digito(lexema[0]):
        if all(map(_es_digito, lexema)):
            return None, diag.error(
                "léxico", linea, columna,
                f"el número '{lexema}' no es válido: las únicas constantes son 0 y 1",
                "las señales se nombran con letras, por ejemplo 'x1'")
        return None, diag.error(
            "léxico", linea, columna,
            f"el nombre '{lexema}' no puede empezar con un dígito",
            f"empieza el nombre con una letra, por ejemplo 'x{lexema}'")

    # Empieza con '_': reservado para las señales temporales del compilador.
    return None, diag.error(
        "léxico", linea, columna,
        f"el nombre '{lexema}' no puede empezar con '_'",
        "los nombres que empiezan con '_' están reservados para las señales "
        "temporales del compilador")


def analizar_linea(linea, numero_linea, palabras_reservadas):
    """Tokeniza una línea: (tokens para el parser, diagnósticos).

    Los tokens para el parser incluyen los comodines ERROR.
    """
    tokens = []
    diagnosticos = []

    i = 0
    n = len(linea)
    while i < n:
        caracter = linea[i]

        # Se ignoran los espacios en blanco (incluido el '\r' de Windows).
        if _es_espacio(caracter):
            i += 1
            continue

        # Comentario: desde '#' hasta el final de la línea se ignora, tanto si
        # ocupa la línea completa como si va detrás de una instrucción.
        if caracter == "#":
            break

        columna = i + 1

        if caracter == "-":
            if i + 1 < n and linea[i + 1] == ">":
                tokens.append(Token("FLECHA", "->", numero_linea, columna))
                i += 2
                continue
            # "- >" con espacios: una sola falta, la flecha va junta.
            j = i + 1
            while j < n and linea[j] in " \t":
                j += 1
            if j < n and linea[j] == ">":
                diagnosticos.append(diag.error(
                    "léxico", numero_linea, columna,
                    "la flecha '->' no puede llevar espacios entre '-' y '>'",
                    "escribe '->' junto"))
                tokens.append(_token_error("FLECHA", linea[i:j + 1], numero_linea, columna))
                i = j + 1
                continue
            diagnosticos.append(diag.error(
                "léxico", numero_linea, columna,
                "carácter no reconocido '-': la flecha se escribe '->'",
                "agrega '>' después de '-'"))
            tokens.append(_token_error("FLECHA", "-", numero_linea, columna))
            i += 1
            continue

        if caracter == ">":
            diagnosticos.append(diag.error(
                "léxico", numero_linea, columna,
                "carácter no reconocido '>': la flecha se escribe '->'",
                "agrega '-' antes de '>'"))
            tokens.append(_token_error("FLECHA", ">", numero_linea, columna))
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

        # Lexema: secuencia de caracteres hasta un espacio o un delimitador.
        inicio = i
        while i < n and not _es_espacio(linea[i]) and linea[i] not in DELIMITADORES:
            i += 1
        lexema = linea[inicio:i]
        token, error = _clasificar_lexema(lexema, numero_linea, columna, palabras_reservadas)
        if error is not None:
            diagnosticos.append(error)
            tokens.append(_token_error("IDENTIFICADOR", lexema, numero_linea, columna))
        else:
            tokens.append(token)

    return tokens, diagnosticos


def analizar_lexico(texto, palabras_reservadas=None):
    """Fase léxica completa: (tokens, tokens_parser, diagnósticos).

    `tokens` son los tokens válidos (los que se muestran); `tokens_parser`
    además incluye los comodines ERROR para que la fase sintáctica pueda
    continuar después de un error léxico.
    """
    if palabras_reservadas is None:
        palabras_reservadas = _cargar_palabras_reservadas()

    tokens_parser = []
    diagnosticos = []
    for numero_linea, linea in enumerate(texto.split("\n"), start=1):
        tokens_linea, diagnosticos_linea = analizar_linea(
            linea, numero_linea, palabras_reservadas)
        tokens_parser.extend(tokens_linea)
        diagnosticos.extend(diagnosticos_linea)

    tokens = [t for t in tokens_parser if t.token != TIPO_ERROR]
    return tokens, tokens_parser, diagnosticos


def tokenizar_linea(linea, numero_linea, palabras_reservadas):
    """Tokeniza una sola linea devolviendo (tokens, errores)."""
    tokens, diagnosticos = analizar_linea(linea, numero_linea, palabras_reservadas)
    return ([t for t in tokens if t.token != TIPO_ERROR],
            [d.texto() for d in diagnosticos])


def tokenizar_circuito(texto, palabras_reservadas=None):
    """Tokeniza un circuito completo (varias lineas) devolviendo (tokens, errores).

    Cada token lleva su numero de linea y columna; los errores lexicos se
    reportan con el formato 'Error léxico línea L, columna C: mensaje'.
    """
    tokens, _, diagnosticos = analizar_lexico(texto, palabras_reservadas)
    return tokens, [d.texto() for d in diagnosticos]
