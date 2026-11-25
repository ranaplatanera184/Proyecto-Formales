"""Fase 3: gramática nueva, AST tipado, desazucarado, SALIDA, constantes,
código intermedio, optimizador, backend Verilog y árbol ASCII."""

import glob
import os
import random
import shutil
import subprocess
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from fastapi.testclient import TestClient

from gestor_reglas import GestorReglas
from ImplementacionAnalisisLexico import tokenizar_circuito
from AnalisisSintactico import AnalisisSintactico, MAXIMO_ANIDAMIENTO
from ast_jace import arbol_ascii, Compuerta, Constante, Senal
from ir import Instruccion, generar_ir, programa_de, texto_ir
from optimizador import (metricas, optimizar, regla_algebraica, regla_constantes,
                         pase_codigo_muerto, pase_subexpresiones)
from backends.verilog import generar_modulo, generar_testbench, nombre_verilog
from SERVIRCOR import app


def analizar(codigo, **opciones):
    opciones.setdefault("imprimir", False)
    opciones.setdefault("con_diagrama", False)
    opciones.setdefault("registrar", False)
    return GestorReglas().analizar(codigo, **opciones)


def errores(codigo):
    return [d for d in analizar(codigo)["diagnosticos"] if d["severidad"] == "error"]


def tabla_por_columnas(resultado, columnas):
    senales = resultado["tabla_verdad"]["señales"]
    indices = [senales.index(c) for c in columnas]
    return [[fila[i] for i in indices] for fila in resultado["tabla_verdad"]["filas"]]


# ---------------------------------------------------------------------------
# 3.1 Gramática: SALIDA, constantes y anidamiento
# ---------------------------------------------------------------------------
def test_salida_es_palabra_reservada_en_reglas():
    assert "SALIDA" in GestorReglas().obtener_palabras_reservadas()


def test_constantes_0_y_1_son_tokens():
    tokens, errores_lexicos = tokenizar_circuito("AND[a, 0, 1] -> x")
    assert errores_lexicos == []
    assert [(t.token, t.valor) for t in tokens if t.token == "CONSTANTE"] == \
        [("CONSTANTE", "0"), ("CONSTANTE", "1")]


@pytest.mark.parametrize("numero", ["2", "10", "01", "00"])
def test_otros_numeros_siguen_siendo_error(numero):
    _, errores_lexicos = tokenizar_circuito(f"AND[a, {numero}] -> x")
    assert len(errores_lexicos) == 1


def test_circuito_con_salida_y_anidamiento_es_valido():
    resultado = analizar("ENTRADA[a, b, c]\nSALIDA[y]\nOR[AND[a, b], NOT[c]] -> y")
    assert resultado["exito"] is True
    assert resultado["salidas_declaradas"] == ["y"]
    assert resultado["salidas"] == ["y"]


@pytest.mark.parametrize("codigo,fragmento", [
    ("ENTRADA[a, 1]\nNOT[a] -> x", "no pueden declararse en ENTRADA"),
    ("ENTRADA[a]\nSALIDA[0]\nNOT[a] -> x", "no pueden declararse en SALIDA"),
    ("ENTRADA[a]\nNOT[a] -> 1", "la salida no puede ser la constante 1"),
    ("ENTRADA[a]\nSALIDA[]\nNOT[a] -> x", "SALIDA necesita al menos un nombre de salida"),
    ("ENTRADA[a]\nNOT[a] -> x\nSALIDA[x]", "SALIDA debe ir justo después de ENTRADA"),
    ("ENTRADA[a]\nOR[a, ANDD[a, a]] -> x", "'ANDD' no es una compuerta conocida"),
    ("ENTRADA[a]\nOR[a, AND] -> x", "para anidar una compuerta escribe AND[...]"),
    ("ENTRADA[a]\nOR[a AND[a, a]] -> x", "falta una coma entre 'a' y 'AND'"),
])
def test_errores_de_la_gramatica_nueva(codigo, fragmento):
    lista = errores(codigo)
    assert lista, codigo
    texto = lista[0]["mensaje"] + " " + (lista[0]["sugerencia"] or "")
    assert fragmento in texto


def test_anidamiento_demasiado_profundo_es_un_error_claro():
    profundidad = MAXIMO_ANIDAMIENTO + 5
    codigo = "ENTRADA[a]\n" + "NOT[" * profundidad + "a" + "]" * profundidad + " -> y"
    (error,) = errores(codigo)
    assert "anidadas" in error["mensaje"]


def test_anidamiento_profundo_permitido():
    profundidad = 60
    codigo = "ENTRADA[a]\n" + "NOT[" * profundidad + "a" + "]" * profundidad + " -> y"
    resultado = analizar(codigo)
    assert resultado["exito"] is True
    assert len(resultado["temporales"]) == profundidad - 1
    assert tabla_por_columnas(resultado, ["a", "y"]) == [[0, 0], [1, 1]]


def test_salida_en_minusculas_sigue_siendo_un_nombre():
    """Compatibilidad: muchos circuitos llaman 'salida' a su señal final."""
    resultado = analizar("ENTRADA[a]\nNOT[a] -> salida\nAND[a, salida] -> Salida2")
    assert resultado["exito"] is True


def test_salida_en_mayusculas_como_nombre_sin_corchete():
    resultado = analizar("ENTRADA[a, b]\nAND[a, b] -> SALIDA")
    assert resultado["exito"] is True
    assert resultado["salidas"] == ["SALIDA"]


# ---------------------------------------------------------------------------
# 3.2 AST tipado
# ---------------------------------------------------------------------------
def test_ast_tipado_con_posiciones():
    tokens, _ = tokenizar_circuito("ENTRADA[a, b]\nOR[AND[a, 1], b] -> y")
    estructura = AnalisisSintactico(tokens).construir_circuito()
    arbol = estructura["arbol"]
    (asignacion,) = arbol.instrucciones
    compuerta = asignacion.compuerta
    assert isinstance(compuerta, Compuerta) and compuerta.nombre == "OR"
    interna, b = compuerta.argumentos
    assert isinstance(interna, Compuerta) and (interna.linea, interna.columna) == (2, 4)
    assert isinstance(interna.argumentos[1], Constante)
    assert interna.argumentos[1].valor_logico == 1
    assert isinstance(b, Senal) and (b.linea, b.columna) == (2, 15)
    assert (asignacion.destino.nombre, asignacion.destino.columna) == ("y", 21)


def test_ast_json_tiene_forma_uniforme():
    resultado = analizar("ENTRADA[a]\nNOT[a] -> y")
    ast = resultado["ast"]
    assert ast["tipo"] == "circuito"
    pendientes = [ast]
    while pendientes:
        nodo = pendientes.pop()
        assert {"tipo", "linea", "columna", "hijos"} <= set(nodo)
        pendientes.extend(nodo["hijos"])


# ---------------------------------------------------------------------------
# 3.3 Desazucarado
# ---------------------------------------------------------------------------
def test_anidado_da_exactamente_la_misma_tabla_que_en_tres_lineas():
    anidado = analizar("ENTRADA[a, b, c]\nOR[AND[a, b], NOT[c]] -> y")
    plano = analizar("ENTRADA[a, b, c]\nAND[a, b] -> t1\nNOT[c] -> t2\nOR[t1, t2] -> y")
    columnas = ["a", "b", "c", "y"]
    assert tabla_por_columnas(anidado, columnas) == tabla_por_columnas(plano, columnas)
    # Con las temporales visibles, la tabla coincide columna a columna.
    assert anidado["tabla_verdad"]["filas"] == plano["tabla_verdad"]["filas"]
    assert anidado["temporales"] == ["_t1", "_t2"]


def test_temporales_en_la_tabla_de_simbolos_y_en_el_orden():
    resultado = analizar("ENTRADA[a, b, c]\nOR[AND[a, b], NOT[c]] -> y")
    tipos = {s["senal"]: s["tipo"] for s in resultado["tabla_simbolos"]}
    assert tipos == {"a": "entrada", "b": "entrada", "c": "entrada",
                     "_t1": "temporal", "_t2": "temporal", "y": "salida"}
    assert [c["salida"] for c in resultado["orden_topologico"]] == ["_t1", "_t2", "y"]


def test_las_temporales_no_chocan_con_nombres_del_usuario():
    _, errores_lexicos = tokenizar_circuito("ENTRADA[_t1]")
    assert errores_lexicos


def test_error_semantico_dentro_de_un_anidado_apunta_a_la_compuerta_interna():
    (error,) = errores("ENTRADA[a, b]\nOR[NOT[a, b], b] -> y")
    assert (error["linea"], error["columna"]) == (2, 4)
    assert "NOT requiere exactamente 1" in error["mensaje"]


# ---------------------------------------------------------------------------
# 3.4 Semántica de SALIDA
# ---------------------------------------------------------------------------
def test_salida_no_producida_es_error_con_sugerencia():
    (error,) = errores("ENTRADA[a, b]\nSALIDA[yy]\nAND[a, b] -> y")
    assert error["mensaje"] == "la salida yy declarada en SALIDA no la produce ninguna compuerta"
    assert error["sugerencia"] == "¿quisiste decir 'y'?"
    assert (error["linea"], error["columna"]) == (2, 8)


def test_entrada_declarada_como_salida_es_error():
    (error,) = errores("ENTRADA[a, b]\nSALIDA[a]\nAND[a, b] -> y")
    assert error["mensaje"] == "la entrada a no puede declararse como salida"


def test_salida_repetida_es_error():
    (error,) = errores("ENTRADA[a, b]\nSALIDA[y, y]\nAND[a, b] -> y")
    assert "declarada más de una vez" in error["mensaje"]


def test_las_salidas_declaradas_mandan_en_expresiones_y_diagrama():
    resultado = analizar("ENTRADA[a, b]\nSALIDA[x]\nAND[a, b] -> x\nNOT[x] -> y",
                         con_diagrama=True)
    assert resultado["salidas"] == ["x"]
    assert list(resultado["expresiones_booleanas"]) == ["x"]
    assert [e["salida"] for e in resultado["expresiones"]] == ["x"]
    assert resultado["diagrama_svg"]


def test_compuerta_muerta_con_salida_declarada():
    resultado = analizar("ENTRADA[a, b]\nSALIDA[x]\nAND[a, b] -> x\nOR[a, b] -> muerta")
    (aviso,) = [d for d in resultado["diagnosticos"] if d["severidad"] == "advertencia"]
    assert aviso["mensaje"] == "la compuerta OR -> muerta no llega a ninguna salida del circuito"
    assert (aviso["linea"], aviso["columna"]) == (4, 1)


# ---------------------------------------------------------------------------
# 3.5 Código intermedio
# ---------------------------------------------------------------------------
def test_ir_de_tres_direcciones_en_orden_topologico():
    resultado = analizar("ENTRADA[a, b, c]\nOR[AND[a, b], NOT[c]] -> y")
    assert [i["texto"] for i in resultado["ir"]] == [
        "_t1 = AND a, b", "_t2 = NOT c", "y = OR _t1, _t2"]
    assert [i["linea"] for i in resultado["ir"]] == [2, 2, 2]


def test_texto_ir_alinea_los_destinos():
    texto = texto_ir([Instruccion("y", "NOT", ["a"], 1), Instruccion("larga", "BUF", ["y"], 2)])
    assert texto == "y     = NOT a\nlarga = BUF y"


# ---------------------------------------------------------------------------
# 3.6 Optimizador: cada pase
# ---------------------------------------------------------------------------
def I(destino, operacion, *argumentos):
    return Instruccion(destino, operacion, list(argumentos), 1)


@pytest.mark.parametrize("instruccion,esperado", [
    (I("y", "AND", "x", "0"), ("CONST", ["0"])),
    (I("y", "AND", "x", "1"), ("BUF", ["x"])),
    (I("y", "OR", "x", "1"), ("CONST", ["1"])),
    (I("y", "OR", "x", "0"), ("BUF", ["x"])),
    (I("y", "XOR", "x", "0"), ("BUF", ["x"])),
    (I("y", "XOR", "x", "1"), ("NOT", ["x"])),
    (I("y", "XNOR", "x", "1"), ("BUF", ["x"])),
    (I("y", "XNOR", "x", "0"), ("NOT", ["x"])),
    (I("y", "NAND", "x", "0"), ("CONST", ["1"])),
    (I("y", "NAND", "x", "1"), ("NOT", ["x"])),
    (I("y", "NOR", "x", "1"), ("CONST", ["0"])),
    (I("y", "NOR", "x", "0"), ("NOT", ["x"])),
    (I("y", "NOT", "1"), ("CONST", ["0"])),
    (I("y", "AND", "1", "1"), ("CONST", ["1"])),
    (I("y", "XOR", "1", "1", "1"), ("CONST", ["1"])),
    (I("y", "AND", "a", "1", "b"), ("AND", ["a", "b"])),
])
def test_pase_de_constantes(instruccion, esperado):
    nueva, motivo = regla_constantes(instruccion, {})
    assert (nueva.operacion, nueva.argumentos) == esperado
    assert motivo


@pytest.mark.parametrize("instruccion,esperado", [
    (I("y", "AND", "x", "x"), ("BUF", ["x"])),
    (I("y", "OR", "x", "x", "z"), ("OR", ["x", "z"])),
    (I("y", "XOR", "x", "x"), ("CONST", ["0"])),
    (I("y", "XNOR", "x", "x"), ("CONST", ["1"])),
    (I("y", "XOR", "x", "x", "z"), ("BUF", ["z"])),
    (I("y", "NAND", "x", "x"), ("NOT", ["x"])),
])
def test_pase_algebraico(instruccion, esperado):
    nueva, _ = regla_algebraica(instruccion, {})
    assert (nueva.operacion, nueva.argumentos) == esperado


def test_doble_negacion():
    definiciones = {"n": I("n", "NOT", "x")}
    nueva, motivo = regla_algebraica(I("y", "NOT", "n"), definiciones)
    assert (nueva.operacion, nueva.argumentos) == ("BUF", ["x"])
    assert motivo == "NOT(NOT x) = x"


def test_pase_de_subexpresiones_comunes():
    ir = [I("p", "AND", "a", "b"), I("q", "AND", "b", "a"), I("y", "OR", "p", "q")]
    nuevas, bitacora = pase_subexpresiones(ir, {"y"})
    assert [i.texto() for i in nuevas] == ["p = AND a, b", "y = OR p, p"]
    assert bitacora[0]["pase"] == "subexpresiones"


def test_subexpresion_repetida_en_una_salida_conserva_el_nombre():
    ir = [I("y1", "AND", "a", "b"), I("y2", "AND", "a", "b")]
    nuevas, _ = pase_subexpresiones(ir, {"y1", "y2"})
    assert [i.texto() for i in nuevas] == ["y1 = AND a, b", "y2 = BUF y1"]


def test_pase_de_codigo_muerto():
    ir = [I("x", "AND", "a", "b"), I("muerta", "OR", "a", "b"), I("y", "NOT", "x")]
    nuevas, bitacora = pase_codigo_muerto(ir, {"y"})
    assert [i.destino for i in nuevas] == ["x", "y"]
    assert bitacora == [{"pase": "código muerto", "linea": 1, "antes": "muerta = OR a, b",
                         "despues": "(se elimina)",
                         "motivo": "muerta no llega a ninguna salida"}]


def test_las_salidas_conservan_su_nombre_aunque_sean_constantes():
    optimizado, _ = optimizar([I("y", "AND", "a", "0")], ["y"], ["a"])
    assert [i.texto() for i in optimizado] == ["y = CONST 0"]


def test_punto_fijo_y_bitacora_del_circuito_con_constantes():
    resultado = analizar("ENTRADA[a, b, c]\nSALIDA[y]\n"
                         "OR[AND[a, 1], NOT[NOT[c]], AND[1, a]] -> y")
    optimizacion = resultado["optimizacion"]
    assert [i["texto"] for i in optimizacion["ir_optimizado"]] == ["y = OR a, c"]
    assert {b["pase"] for b in optimizacion["bitacora"]} >= {"constantes", "algebraico",
                                                            "código muerto"}
    assert all(set(b) == {"pase", "linea", "antes", "despues", "motivo"}
               for b in optimizacion["bitacora"])
    assert optimizacion["metricas_antes"] == {"compuertas": 5, "profundidad": 3,
                                              "entradas_usadas": 2}
    assert optimizacion["metricas_despues"] == {"compuertas": 1, "profundidad": 1,
                                                "entradas_usadas": 2}


def test_metricas():
    ir = [I("x", "AND", "a", "b"), I("y", "NOT", "x"), I("z", "OR", "a", "a")]
    assert metricas(ir, ["y"], ["a", "b", "c"]) == {
        "compuertas": 3, "profundidad": 2, "entradas_usadas": 2}


# ---------------------------------------------------------------------------
# Corrección del optimizador: la tabla optimizada es idéntica a la original
# ---------------------------------------------------------------------------
def _tablas_equivalentes(resultado):
    entradas = list(dict.fromkeys(resultado["entradas"]))
    salidas = resultado["salidas"]
    original = programa_de(entradas, [Instruccion(**{k: v for k, v in i.items() if k != "texto"})
                                      for i in resultado["ir"]])
    optimizado = programa_de(entradas, [Instruccion(**{k: v for k, v in i.items()
                                                       if k != "texto"})
                                        for i in resultado["optimizacion"]["ir_optimizado"]])
    total = 2 ** len(entradas)
    columnas = entradas + salidas
    filas_original = original.filas(0, total, columnas)
    assert filas_original == optimizado.filas(0, total, columnas)
    # Y la tabla del IR original coincide con la del análisis.
    if resultado["tabla_verdad"]["filas"]:
        assert filas_original == tabla_por_columnas(resultado, columnas)


def test_optimizador_correcto_en_todos_los_circuitos_de_pruebas():
    validos = 0
    for ruta in sorted(glob.glob(os.path.join(RAIZ, "pruebas", "*.jace"))):
        with open(ruta, encoding="utf-8") as archivo:
            resultado = analizar(archivo.read())
        if resultado["exito"]:
            _tablas_equivalentes(resultado)
            validos += 1
    assert validos >= 6


def _circuito_aleatorio(azar):
    n = azar.randint(1, 10)
    entradas = [f"e{i}" for i in range(n)]
    senales = list(entradas)
    lineas = [f"ENTRADA[{', '.join(entradas)}]"]
    compuertas = ["AND", "OR", "XOR", "NAND", "NOR", "XNOR", "NOT"]

    def argumento(profundidad):
        r = azar.random()
        if r < 0.12:
            return azar.choice(["0", "1"])
        if r < 0.25 and profundidad < 3:
            return expresion(profundidad + 1)
        return azar.choice(senales)

    def expresion(profundidad):
        nombre = azar.choice(compuertas)
        aridad = 1 if nombre == "NOT" else azar.randint(2, 4)
        return f"{nombre}[{', '.join(argumento(profundidad) for _ in range(aridad))}]"

    definidas = []
    for k in range(azar.randint(1, 12)):
        destino = f"s{k}"
        lineas.append(f"{expresion(0)} -> {destino}")
        senales.append(destino)
        definidas.append(destino)
    if azar.random() < 0.5:
        declaradas = azar.sample(definidas, azar.randint(1, len(definidas)))
        lineas.insert(1, f"SALIDA[{', '.join(declaradas)}]")
    return "\n".join(lineas)


def test_optimizador_correcto_en_200_circuitos_aleatorios():
    azar = random.Random(31415)
    comprobados = 0
    while comprobados < 200:
        resultado = analizar(_circuito_aleatorio(azar))
        assert not any(e.startswith("Error interno") for e in resultado["errores"])
        if not resultado["exito"]:
            continue
        _tablas_equivalentes(resultado)
        comprobados += 1


# ---------------------------------------------------------------------------
# 3.7 Verilog
# ---------------------------------------------------------------------------
def test_modulo_verilog_estructural():
    ir = [I("_t1", "NAND", "a", "b", "c"), I("y", "XOR", "_t1", "a", "b"),
          I("z", "CONST", "1"), I("w", "NOT", "a"), I("v", "BUF", "a")]
    texto = generar_modulo(ir, ["a", "b", "c"], ["y", "z", "w", "v"])
    assert "module circuito (a, b, c, y, z, w, v);" in texto
    assert "  wire   _t1;" in texto
    assert "assign _t1 = ~(a & b & c);" in texto
    assert "assign y = _t1 ^ a ^ b;" in texto
    assert "assign z = 1'b1;" in texto
    assert "assign w = ~a;" in texto
    assert "assign v = a;" in texto
    assert texto.rstrip().endswith("endmodule")


def test_palabras_reservadas_de_verilog_se_escapan():
    assert nombre_verilog("module") == "\\module "
    assert nombre_verilog("wire") == "\\wire "
    assert nombre_verilog("x1") == "x1"
    assert nombre_verilog("0") == "1'b0"
    texto = generar_modulo([I("output", "AND", "input", "reg")], ["input", "reg"], ["output"])
    assert "assign \\output  = \\input  & \\reg ;" in texto


def test_verilog_en_el_resultado_y_testbench_solo_bajo_el_limite():
    resultado = analizar("ENTRADA[a, b]\nAND[a, b] -> y")
    assert "module circuito (a, b, y);" in resultado["verilog"]["modulo"]
    assert "for (jace_i = 0; jace_i < 4;" in resultado["verilog"]["testbench"]
    grande = analizar("ENTRADA[" + ", ".join(f"e{i}" for i in range(16)) + "]\n"
                      "AND[" + ", ".join(f"e{i}" for i in range(16)) + "] -> y")
    assert grande["verilog"]["testbench"] is None
    assert "2^16" in grande["verilog"]["aviso_testbench"]


@pytest.mark.skipif(shutil.which("iverilog") is None, reason="iverilog no está instalado")
def test_verilog_compila_y_simula_con_iverilog(tmp_path):
    resultado = analizar("ENTRADA[a, b, c]\nSALIDA[y, module]\n"
                         "OR[AND[a, b], NOT[c]] -> y\nXNOR[a, b, c] -> module")
    archivo = tmp_path / "circuito.v"
    archivo.write_text(resultado["verilog"]["modulo"] + resultado["verilog"]["testbench"],
                       encoding="utf-8")
    salida = tmp_path / "sim"
    subprocess.run(["iverilog", "-o", str(salida), str(archivo)], check=True)
    simulacion = subprocess.run(["vvp", str(salida)], capture_output=True, text=True,
                                check=True).stdout.splitlines()
    filas = [linea for linea in simulacion if "|" in linea][1:]
    esperado = tabla_por_columnas(resultado, ["a", "b", "c", "y", "module"])
    obtenido = [[int(x) for x in linea.replace("|", " ").split()] for linea in filas]
    assert obtenido == esperado


# ---------------------------------------------------------------------------
# 3.8 Árbol ASCII
# ---------------------------------------------------------------------------
def test_arbol_ascii():
    resultado = analizar("ENTRADA[a, b]\nSALIDA[y]\nOR[NOT[a], 1] -> y")
    assert resultado["arbol_ascii"] == "\n".join([
        "Circuito  (línea 1, col 1)",
        "├── Entradas  (línea 1, col 1)",
        "│   ├── Señal a  (línea 1, col 9)",
        "│   └── Señal b  (línea 1, col 12)",
        "├── Salidas  (línea 2, col 1)",
        "│   └── Señal y  (línea 2, col 8)",
        "└── Asignación → y  (línea 3, col 1)",
        "    ├── Compuerta OR  (línea 3, col 1)",
        "    │   ├── Compuerta NOT  (línea 3, col 4)",
        "    │   │   └── Señal a  (línea 3, col 8)",
        "    │   └── Constante 1  (línea 3, col 12)",
        "    └── Señal y  (línea 3, col 18)",
    ])


def test_arbol_ascii_de_un_circuito_enorme_no_usa_recursion():
    lineas = ["ENTRADA[a]"] + [f"NOT[{'a' if i == 0 else f'n{i - 1}'}] -> n{i}"
                               for i in range(3000)]
    resultado = analizar("\n".join(lineas))
    assert resultado["arbol_ascii"].count("Asignación") == 3000


# ---------------------------------------------------------------------------
# 3.9 Campos nuevos de la API
# ---------------------------------------------------------------------------
def test_campos_nuevos_de_analizar():
    datos = TestClient(app).post("/analizar", json={
        "codigo": "ENTRADA[a, b]\nSALIDA[y]\nAND[a, 1, b] -> y"}).json()
    assert datos["exito"] is True
    for campo in ("ast", "ir", "optimizacion", "verilog", "salidas_declaradas",
                  "salidas", "temporales", "arbol_ascii", "diagnosticos"):
        assert campo in datos, campo
    assert set(datos["optimizacion"]) == {"ir_optimizado", "bitacora",
                                          "metricas_antes", "metricas_despues"}
    assert datos["salidas_declaradas"] == ["y"]
    # Los campos de siempre siguen ahí.
    for campo in ("tokens", "tabla_simbolos", "orden_topologico", "tabla_verdad",
                  "expresiones", "expresiones_booleanas", "diagrama_svg", "errores",
                  "advertencias"):
        assert campo in datos, campo
