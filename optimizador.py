# ============================================================================
# OPTIMIZADOR DEL CÓDIGO INTERMEDIO
# ----------------------------------------------------------------------------
# Gestor de pases que se aplican, en orden, hasta llegar a un punto fijo (una
# vuelta completa sin cambios):
#
#   1. constantes    Propagación y plegado de constantes:
#                    AND[x,0]=0, AND[x,1]=x, OR[x,1]=1, OR[x,0]=x, XOR[x,0]=x,
#                    XOR[x,1]=NOT x, y sus equivalentes en NAND/NOR/XNOR; una
#                    compuerta con todas sus entradas constantes se calcula.
#   2. algebraico    Simplificaciones seguras: NOT(NOT x)=x, AND[x,x]=x,
#                    OR[x,x]=x, XOR[x,x]=0 (las parejas se cancelan).
#   3. subexpresiones  Eliminación de subexpresiones comunes con una clave
#                    canónica (operación + argumentos ordenados, porque todas
#                    las compuertas de varias entradas son conmutativas).
#   4. código muerto Se quitan las instrucciones que no llegan a una salida.
#
# Cuando una instrucción queda como copia (BUF x) o constante (CONST 0/1) y
# su destino no es una salida, se elimina y las siguientes usan directamente
# el valor (propagación de copias). Las salidas conservan siempre su nombre.
#
# Cada cambio queda en una bitácora {pase, linea, antes, despues, motivo}.
# ============================================================================

from ir import COMPUERTAS, Instruccion

MAXIMO_VUELTAS = 100
CONSTANTES = ("0", "1")


def _entrada_bitacora(pase, instruccion, despues, motivo):
    return {"pase": pase, "linea": instruccion.linea,
            "antes": instruccion.texto(), "despues": despues, "motivo": motivo}


def _normalizar(instruccion, operacion, argumentos):
    """Compuerta sin argumentos o con uno solo → constante, copia o NOT."""
    if not argumentos:
        valor = {"AND": "1", "OR": "0", "XOR": "0",
                 "NAND": "0", "NOR": "1", "XNOR": "1"}[operacion]
        return instruccion.copia(operacion="CONST", argumentos=[valor])
    if len(argumentos) == 1 and operacion in ("AND", "OR", "XOR"):
        return instruccion.copia(operacion="BUF", argumentos=list(argumentos))
    if len(argumentos) == 1 and operacion in ("NAND", "NOR", "XNOR"):
        return instruccion.copia(operacion="NOT", argumentos=list(argumentos))
    return instruccion.copia(operacion=operacion, argumentos=list(argumentos))


# ---------------------------------------------------------------------------
# Reglas de reescritura (una instrucción → otra o None si no cambia)
# ---------------------------------------------------------------------------
def regla_constantes(instruccion, definiciones):
    operacion = instruccion.operacion
    argumentos = instruccion.argumentos
    if operacion == "CONST" or not any(a in CONSTANTES for a in argumentos):
        return None, None
    if operacion == "BUF":
        return instruccion.copia(operacion="CONST"), "copia de una constante"
    if operacion == "NOT":
        valor = "0" if argumentos[0] == "1" else "1"
        return instruccion.copia(operacion="CONST", argumentos=[valor]), \
            f"NOT {argumentos[0]} = {valor}"

    resto = [a for a in argumentos if a not in CONSTANTES]
    unos = argumentos.count("1")
    if operacion == "AND" and "0" in argumentos:
        return instruccion.copia(operacion="CONST", argumentos=["0"]), "AND con un 0 vale 0"
    if operacion == "OR" and "1" in argumentos:
        return instruccion.copia(operacion="CONST", argumentos=["1"]), "OR con un 1 vale 1"
    if operacion == "NAND" and "0" in argumentos:
        return instruccion.copia(operacion="CONST", argumentos=["1"]), "NAND con un 0 vale 1"
    if operacion == "NOR" and "1" in argumentos:
        return instruccion.copia(operacion="CONST", argumentos=["0"]), "NOR con un 1 vale 0"

    if operacion in ("AND", "NAND"):
        motivo = f"en {operacion} un 1 no cambia el resultado"
    elif operacion in ("OR", "NOR"):
        motivo = f"en {operacion} un 0 no cambia el resultado"
    else:
        # XOR/XNOR: los 0 no cambian nada y cada 1 invierte el resultado.
        if unos % 2:
            operacion = "XNOR" if operacion == "XOR" else "XOR"
            motivo = f"{instruccion.operacion} con un 1 invierte el resultado (x XOR 1 = NOT x)"
        else:
            motivo = f"en {operacion} un 0 no cambia el resultado"
    return _normalizar(instruccion, operacion, resto), motivo


def regla_algebraica(instruccion, definiciones):
    operacion = instruccion.operacion
    argumentos = instruccion.argumentos

    if operacion == "NOT":
        interna = definiciones.get(argumentos[0])
        if interna is not None and interna.operacion == "NOT":
            return instruccion.copia(operacion="BUF", argumentos=list(interna.argumentos)), \
                "NOT(NOT x) = x"
        return None, None

    if operacion in ("AND", "OR", "NAND", "NOR"):
        unicos = list(dict.fromkeys(argumentos))
        if len(unicos) == len(argumentos):
            return None, None
        repetido = next(a for a in argumentos if argumentos.count(a) > 1)
        base = operacion.replace("N", "", 1) if operacion in ("NAND", "NOR") else operacion
        return _normalizar(instruccion, operacion, unicos), \
            f"{repetido} {base} {repetido} = {repetido} (idempotencia)"

    if operacion in ("XOR", "XNOR"):
        cuentas = {}
        for a in argumentos:
            cuentas[a] = cuentas.get(a, 0) + 1
        if all(n == 1 for n in cuentas.values()):
            return None, None
        quedan = [a for a in dict.fromkeys(argumentos) if cuentas[a] % 2]
        repetido = next(a for a, n in cuentas.items() if n > 1)
        return _normalizar(instruccion, operacion, quedan), \
            f"{repetido} XOR {repetido} = 0 (las parejas se cancelan)"

    return None, None


# ---------------------------------------------------------------------------
# Pases
# ---------------------------------------------------------------------------
def _pase_de_reescritura(nombre, regla):
    """Pase que recorre el IR aplicando `regla` y propagando copias."""
    def pase(instrucciones, salidas):
        sustitucion = {}
        definiciones = {}
        nuevas = []
        bitacora = []
        for original in instrucciones:
            argumentos = [sustitucion.get(a, a) for a in original.argumentos]
            actual = original.copia(argumentos=argumentos)
            propagada = argumentos != original.argumentos
            reescrita, motivo = regla(actual, definiciones)
            final = reescrita or actual

            if final.operacion in ("BUF", "CONST") and final.destino not in salidas:
                valor = final.argumentos[0]
                sustitucion[final.destino] = valor
                bitacora.append(_entrada_bitacora(
                    nombre, original,
                    f"(se elimina: se usa {valor} en lugar de {final.destino})",
                    motivo or f"{final.destino} es una copia de {valor}"))
                continue

            if reescrita is not None:
                bitacora.append(_entrada_bitacora(nombre, original, final.texto(), motivo))
            elif propagada:
                cambios = ", ".join(f"{a} → {b}" for a, b in
                                    zip(original.argumentos, argumentos) if a != b)
                bitacora.append(_entrada_bitacora(
                    "propagación", original, final.texto(),
                    f"se usa el valor ya conocido ({cambios})"))
            nuevas.append(final)
            definiciones[final.destino] = final
        return nuevas, bitacora
    return pase


def pase_subexpresiones(instrucciones, salidas):
    """Eliminación de subexpresiones comunes con clave canónica."""
    vistas = {}
    sustitucion = {}
    nuevas = []
    bitacora = []
    for original in instrucciones:
        argumentos = [sustitucion.get(a, a) for a in original.argumentos]
        actual = original.copia(argumentos=argumentos)
        if actual.operacion not in COMPUERTAS:
            nuevas.append(actual)
            continue
        clave = (actual.operacion, tuple(sorted(argumentos)))
        previa = vistas.get(clave)
        if previa is None:
            vistas[clave] = actual.destino
            if argumentos != original.argumentos:
                bitacora.append(_entrada_bitacora(
                    "propagación", original, actual.texto(),
                    "se usa la subexpresión ya calculada"))
            nuevas.append(actual)
            continue
        motivo = f"misma operación que {previa} ({actual.operacion} con las mismas entradas)"
        if actual.destino in salidas:
            final = actual.copia(operacion="BUF", argumentos=[previa])
            bitacora.append(_entrada_bitacora("subexpresiones", original, final.texto(), motivo))
            nuevas.append(final)
        else:
            sustitucion[actual.destino] = previa
            bitacora.append(_entrada_bitacora(
                "subexpresiones", original,
                f"(se elimina: se usa {previa} en lugar de {actual.destino})", motivo))
    return nuevas, bitacora


def pase_codigo_muerto(instrucciones, salidas):
    """Quita las instrucciones cuyo resultado no llega a ninguna salida."""
    vivas = set(salidas)
    conservadas = []
    bitacora = []
    for instruccion in reversed(instrucciones):
        if instruccion.destino in vivas:
            vivas.update(instruccion.argumentos)
            conservadas.append(instruccion)
        else:
            bitacora.append(_entrada_bitacora(
                "código muerto", instruccion, "(se elimina)",
                f"{instruccion.destino} no llega a ninguna salida"))
    return conservadas[::-1], bitacora[::-1]


PASES = [
    ("constantes", _pase_de_reescritura("constantes", regla_constantes)),
    ("algebraico", _pase_de_reescritura("algebraico", regla_algebraica)),
    ("subexpresiones", pase_subexpresiones),
    ("código muerto", pase_codigo_muerto),
]


# ---------------------------------------------------------------------------
# Métricas y punto de entrada
# ---------------------------------------------------------------------------
def metricas(instrucciones, salidas, entradas):
    """Compuertas, profundidad máxima (en compuertas) y entradas usadas."""
    entradas = set(entradas)
    profundidad = {}
    for instruccion in instrucciones:
        base = max((profundidad.get(a, 0) for a in instruccion.argumentos), default=0)
        profundidad[instruccion.destino] = base + (instruccion.operacion in COMPUERTAS)

    definiciones = {i.destino: i for i in instrucciones}
    vivas = set()
    pendientes = list(salidas)
    usadas = set()
    while pendientes:
        senal = pendientes.pop()
        if senal in vivas:
            continue
        vivas.add(senal)
        if senal in entradas:
            usadas.add(senal)
        if senal in definiciones:
            pendientes.extend(definiciones[senal].argumentos)

    return {
        "compuertas": sum(1 for i in instrucciones if i.operacion in COMPUERTAS),
        "profundidad": max((profundidad.get(s, 0) for s in salidas), default=0),
        "entradas_usadas": len(usadas),
    }


def optimizar(instrucciones, salidas, entradas):
    """Aplica los pases hasta un punto fijo. Devuelve (ir, bitácora)."""
    salidas = set(salidas)
    actual = [i.copia() for i in instrucciones]
    bitacora = []
    for _ in range(MAXIMO_VUELTAS):
        hubo_cambios = False
        for _, pase in PASES:
            actual, registros = pase(actual, salidas)
            if registros:
                hubo_cambios = True
                bitacora.extend(registros)
        if not hubo_cambios:
            break
    return actual, bitacora


def informe(instrucciones, salidas, entradas):
    """Resultado completo para la API: IR optimizado, bitácora y métricas."""
    optimizado, bitacora = optimizar(instrucciones, salidas, entradas)
    return {
        "ir_optimizado": [i.a_json() for i in optimizado],
        "bitacora": bitacora,
        "metricas_antes": metricas(instrucciones, salidas, entradas),
        "metricas_despues": metricas(optimizado, salidas, entradas),
    }, optimizado
