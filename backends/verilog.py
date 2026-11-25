# ============================================================================
# BACKEND VERILOG
# ----------------------------------------------------------------------------
# Traduce el código intermedio (optimizado) a un módulo Verilog estructural
# con sentencias `assign`:
#
#   AND  → a & b & c        NAND → ~(a & b & c)
#   OR   → a | b            NOR  → ~(a | b)
#   XOR  → a ^ b ^ c        XNOR → ~(a ^ b ^ c)     (XOR de N entradas = paridad)
#   NOT  → ~a               BUF  → a                CONST → 1'b0 / 1'b1
#
# Los nombres se sanean y las palabras reservadas de Verilog se escriben
# como identificadores escapados (\module ), que Verilog acepta tal cual.
# Opcionalmente genera un testbench que recorre todas las combinaciones.
# ============================================================================

import re

PALABRAS_VERILOG = {
    "always", "and", "assign", "automatic", "begin", "buf", "bufif0", "bufif1",
    "case", "casex", "casez", "cell", "cmos", "config", "deassign", "default",
    "defparam", "design", "disable", "edge", "else", "end", "endcase",
    "endconfig", "endfunction", "endgenerate", "endmodule", "endprimitive",
    "endspecify", "endtable", "endtask", "event", "for", "force", "forever",
    "fork", "function", "generate", "genvar", "highz0", "highz1", "if",
    "ifnone", "incdir", "include", "initial", "inout", "input", "instance",
    "integer", "join", "large", "liblist", "library", "localparam",
    "macromodule", "medium", "module", "nand", "negedge", "nmos", "nor",
    "noshowcancelled", "not", "notif0", "notif1", "or", "output", "parameter",
    "pmos", "posedge", "primitive", "pull0", "pull1", "pulldown", "pullup",
    "pulsestyle_onevent", "pulsestyle_ondetect", "rcmos", "real", "realtime",
    "reg", "release", "repeat", "rnmos", "rpmos", "rtran", "rtranif0",
    "rtranif1", "scalared", "showcancelled", "signed", "small", "specify",
    "specparam", "strong0", "strong1", "supply0", "supply1", "table", "task",
    "time", "tran", "tranif0", "tranif1", "tri", "tri0", "tri1", "triand",
    "trior", "trireg", "unsigned", "use", "uwire", "vectored", "wait", "wand",
    "weak0", "weak1", "while", "wire", "wor", "xnor", "xor",
}

OPERADORES = {"AND": "&", "OR": "|", "XOR": "^", "NAND": "&", "NOR": "|", "XNOR": "^"}
NEGADAS = {"NAND", "NOR", "XNOR"}
_VALIDO = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")


def nombre_verilog(nombre):
    """Identificador válido en Verilog para una señal de JACE."""
    if nombre in ("0", "1"):
        return f"1'b{nombre}"
    if nombre in PALABRAS_VERILOG or not _VALIDO.match(nombre):
        # Identificador escapado: barra invertida y un espacio al final.
        return f"\\{nombre} "
    return nombre


def _expresion(instruccion):
    args = [nombre_verilog(a) for a in instruccion.argumentos]
    operacion = instruccion.operacion
    if operacion == "CONST":
        return f"1'b{instruccion.argumentos[0]}"
    if operacion == "BUF":
        return args[0]
    if operacion == "NOT":
        return f"~{args[0]}"
    cuerpo = f" {OPERADORES[operacion]} ".join(args)
    return f"~({cuerpo})" if operacion in NEGADAS else cuerpo


def generar_modulo(instrucciones, entradas, salidas, nombre="circuito"):
    """Texto del módulo Verilog estructural."""
    salidas = list(dict.fromkeys(salidas))
    puertos = [nombre_verilog(e) for e in entradas] + [nombre_verilog(s) for s in salidas]
    internas = [i.destino for i in instrucciones if i.destino not in salidas]

    lineas = [
        "// Generado por JACE a partir del código intermedio optimizado.",
        f"module {nombre} ({', '.join(puertos)});",
    ]
    for entrada in entradas:
        lineas.append(f"  input  {nombre_verilog(entrada)};")
    for salida in salidas:
        lineas.append(f"  output {nombre_verilog(salida)};")
    for interna in internas:
        lineas.append(f"  wire   {nombre_verilog(interna)};")
    if instrucciones:
        lineas.append("")
    for instruccion in instrucciones:
        lineas.append(f"  assign {nombre_verilog(instruccion.destino)} = "
                      f"{_expresion(instruccion)};  // línea {instruccion.linea}")
    lineas.append("endmodule")
    return "\n".join(lineas) + "\n"


def generar_testbench(entradas, salidas, nombre="circuito"):
    """Testbench que recorre las 2^n combinaciones e imprime las salidas.

    Los nombres internos del testbench (jace_v, jace_i, jace_o0...) llevan
    prefijo para no chocar con las señales del circuito.
    """
    n = len(entradas)
    salidas = list(dict.fromkeys(salidas))
    cables = [f"jace_o{k}" for k in range(len(salidas))]
    lineas = [
        "`timescale 1ns/1ps",
        f"module {nombre}_tb;",
        f"  reg  [{max(n - 1, 0)}:0] jace_v;",
        "  integer jace_i;",
    ]
    for cable in cables:
        lineas.append(f"  wire {cable};")
    conexiones = [f".{nombre_verilog(e)}(jace_v[{n - 1 - i}])" for i, e in enumerate(entradas)]
    conexiones += [f".{nombre_verilog(s)}({c})" for s, c in zip(salidas, cables)]
    lineas.append(f"  {nombre} dut ({', '.join(conexiones)});")
    lineas.append("")
    lineas.append("  initial begin")
    encabezado = " ".join(entradas) + " | " + " ".join(salidas)
    lineas.append(f'    $display("{encabezado}");')
    formato = " ".join(["%b"] * n) + " | " + " ".join(["%b"] * len(salidas))
    valores = ", ".join([f"jace_v[{n - 1 - i}]" for i in range(n)] + cables)
    lineas.append(f"    for (jace_i = 0; jace_i < {2 ** n}; jace_i = jace_i + 1) begin")
    lineas.append("      jace_v = jace_i; #1;")
    lineas.append(f'      $display("{formato}", {valores});')
    lineas.append("    end")
    lineas.append("    $finish;")
    lineas.append("  end")
    lineas.append("endmodule")
    return "\n".join(lineas) + "\n"
