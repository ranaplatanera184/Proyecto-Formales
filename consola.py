# ============================================================================
# PRESENTACIÓN EN CONSOLA
# ----------------------------------------------------------------------------
# Convierte el resultado de GestorReglas.analizar() en texto para la terminal:
# resumen por fases (✔/✖), diagnósticos con línea, columna y sugerencia,
# salidas con su expresión, métricas, y las secciones opcionales (tokens,
# árbol, símbolos, código intermedio, tabla y Verilog).
#
# Los diagnósticos salen en el MISMO orden y con los mismos textos que el
# campo "diagnosticos" de /analizar, que es lo que muestra la web.
# Colores ANSI solo si la salida es una terminal y NO_COLOR no está definido.
# ============================================================================

import os
import sys

FASES = [("léxico", "Léxico"), ("sintáctico", "Sintáctico"), ("semántico", "Semántico")]

COLORES = {"rojo": "31", "verde": "32", "amarillo": "33", "tenue": "2", "negrita": "1",
           "cian": "36"}


def activar_vt_windows():
    """Activa las secuencias ANSI en la consola de Windows (sin dependencias)."""
    if os.name != "nt":
        return True
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        manejador = kernel32.GetStdHandle(-11)            # STD_OUTPUT_HANDLE
        modo = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(manejador, ctypes.byref(modo)):
            return False
        return bool(kernel32.SetConsoleMode(manejador, modo.value | 0x0004))
    except (AttributeError, OSError):
        return False


def usar_colores(flujo=None):
    flujo = flujo or sys.stdout
    if "NO_COLOR" in os.environ or not hasattr(flujo, "isatty") or not flujo.isatty():
        return False
    return activar_vt_windows()


class Pintor:
    """Aplica colores solo si están activados."""

    def __init__(self, activo):
        self.activo = activo

    def __call__(self, texto, *estilos):
        if not self.activo or not estilos:
            return texto
        codigos = ";".join(COLORES[e] for e in estilos)
        return f"\033[{codigos}m{texto}\033[0m"


# ---------------------------------------------------------------------------
# Piezas del informe
# ---------------------------------------------------------------------------
def estado_de_fases(resultado):
    """[(nombre, estado, detalle)] con estado 'ok', 'error' o 'omitida'."""
    diagnosticos = resultado["diagnosticos"]
    errores = {fase: [d for d in diagnosticos
                      if d["fase"] == fase and d["severidad"] == "error"]
               for fase, _ in FASES}
    interno = [d for d in diagnosticos if d["fase"] == "interno"]
    filas = []

    lexico = "error" if errores["léxico"] or interno else "ok"
    filas.append(("Léxico", lexico, f"{len(resultado['tokens'])} tokens"
                  if lexico == "ok" else f"{len(errores['léxico'])} error(es)"))

    sintactico = "error" if errores["sintáctico"] else "ok"
    if interno:
        sintactico = "omitida"
    instrucciones = sum(1 for h in (resultado["ast"] or {}).get("hijos", [])
                        if h["tipo"] == "asignacion")
    detalle_ok = (f"{instrucciones} instrucción(es)" if resultado["ast"]
                  else "sin errores sintácticos")
    filas.append(("Sintáctico", sintactico,
                  detalle_ok if sintactico == "ok"
                  else f"{len(errores['sintáctico'])} error(es)"
                  if sintactico == "error" else "no se ejecutó"))

    if lexico != "ok" or sintactico != "ok":
        filas.append(("Semántico", "omitida", "no se ejecutó (hay errores previos)"))
    else:
        avisos = sum(1 for d in diagnosticos if d["severidad"] == "advertencia")
        semantico = "error" if errores["semántico"] else "ok"
        filas.append(("Semántico", semantico,
                      f"{len(errores['semántico'])} error(es), {avisos} advertencia(s)"))
    return filas


def linea_diagnostico(d, pintar):
    """'✖ línea 3, columna 8 · semántico: mensaje' (+ sugerencia aparte)."""
    if d["linea"] is None:
        posicion = "general"
    elif d["columna"] is None:
        posicion = f"línea {d['linea']}"
    else:
        posicion = f"línea {d['linea']}, columna {d['columna']}"
    es_error = d["severidad"] == "error"
    marca = pintar("✖", "rojo") if es_error else pintar("⚠", "amarillo")
    texto = f"  {marca} {pintar(posicion, 'negrita')} · {d['fase']}: {d['mensaje']}"
    if d.get("sugerencia"):
        texto += "\n      " + pintar(f"sugerencia: {d['sugerencia']}", "cian")
    return texto


def resumen(resultado, nombre, pintar):
    lineas = [pintar(f"JACE · {nombre}", "negrita"), ""]
    simbolos = {"ok": pintar("✔", "verde"), "error": pintar("✖", "rojo"),
                "omitida": pintar("–", "tenue")}
    for fase, estado, detalle in estado_de_fases(resultado):
        lineas.append(f"  {simbolos[estado]} {fase:<11} {pintar(detalle, 'tenue')}")

    if resultado["diagnosticos"]:
        lineas += ["", pintar("Diagnósticos", "negrita")]
        lineas += [linea_diagnostico(d, pintar) for d in resultado["diagnosticos"]]

    if resultado["exito"]:
        lineas += ["", pintar("Salidas", "negrita")]
        for salida in resultado["salidas"]:
            datos = resultado["expresiones_booleanas"].get(salida, {})
            expresion = datos.get("expandida") or datos.get("aviso") or "—"
            lineas.append(f"  {salida} = {expresion}")
        optimizacion = resultado.get("optimizacion")
        if optimizacion:
            antes, despues = optimizacion["metricas_antes"], optimizacion["metricas_despues"]
            lineas += ["", pintar("Métricas (antes → después de optimizar)", "negrita"),
                       f"  compuertas {antes['compuertas']} → {despues['compuertas']} · "
                       f"profundidad {antes['profundidad']} → {despues['profundidad']} · "
                       f"entradas usadas {antes['entradas_usadas']} → "
                       f"{despues['entradas_usadas']}"]
        lineas += ["", pintar("✔ El circuito compila.", "verde")]
    else:
        errores = sum(1 for d in resultado["diagnosticos"] if d["severidad"] == "error")
        lineas += ["", pintar(f"✖ El circuito no compila ({errores} error(es)).", "rojo")]
    return "\n".join(lineas)


def seccion(titulo, cuerpo, pintar):
    return f"\n{pintar('== ' + titulo + ' ==', 'negrita')}\n{cuerpo}"


def texto_tokens(resultado):
    return "\n".join(f"  {t['token']:18} {t['valor']!r:14} línea {t['linea']}, "
                     f"columna {t['columna']}" for t in resultado["tokens"]) or "  (ninguno)"


def texto_simbolos(resultado):
    filas = []
    for s in resultado["tabla_simbolos"]:
        usos = ", ".join(map(str, s["lineas_uso"])) or "—"
        filas.append(f"  {s['senal']:12} {s['tipo']:14} declarada en línea "
                     f"{s['linea_declaracion']}, usos: {usos}")
    return "\n".join(filas) or "  (vacía)"


def texto_ir(instrucciones):
    ancho = max((len(i["destino"]) for i in instrucciones), default=0)
    return "\n".join(f"  {i['destino'].ljust(ancho)} = {i['operacion']} "
                     f"{', '.join(i['argumentos'])}" for i in instrucciones) or "  (vacío)"


def texto_optimizacion(resultado):
    optimizacion = resultado["optimizacion"]
    partes = ["  Código optimizado:", texto_ir(optimizacion["ir_optimizado"]), "",
              "  Bitácora:"]
    if not optimizacion["bitacora"]:
        partes.append("    (sin cambios)")
    for b in optimizacion["bitacora"]:
        partes.append(f"    [{b['pase']}] línea {b['linea']}: {b['antes']}  ⇒  "
                      f"{b['despues']}   ({b['motivo']})")
    return "\n".join(partes)


def texto_tabla(semantico, temporales):
    """Tabla de verdad calculada por el evaluador por bloques."""
    senales = semantico.senales_tabla(incluir_temporales=temporales)
    anchos = [max(1, len(s)) for s in senales]
    lineas = ["  " + " | ".join(s.ljust(a) for s, a in zip(senales, anchos)),
              "  " + "-+-".join("-" * a for a in anchos)]
    total = 2 ** len(semantico.entradas)
    for desde in range(0, total, 4096):
        for fila in semantico.filas_tabla(desde, min(4096, total - desde), senales):
            lineas.append("  " + " | ".join(str(v).ljust(a) for v, a in zip(fila, anchos)))
    return "\n".join(lineas)
