"""Prueba de robustez (fuzz) con semilla fija.

Genera más de 500 entradas: texto aleatorio, mutaciones de los .jace de
pruebas/, corchetes desbalanceados, Unicode y líneas enormes. El compilador
debe responder siempre con diagnósticos: nunca lanzar una excepción, nunca
devolver "Error inesperado" y nunca caer en un "Error interno".
"""

import glob
import os
import random
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from gestor_reglas import GestorReglas

SEMILLA = 20261125
PIEZAS = ["ENTRADA", "SALIDA", "AND", "OR", "NOT", "XOR", "NAND", "NOR", "XNOR",
          "[", "]", ",", "->", "-", ">", "a", "b", "c", "x1", "_t1", "0", "1", "2",
          "#", " ", "  ", "\n", "\t", "$", "ñ", "é", "²", "Ω", "😀", "​", "\r\n",
          "ANDD", "[[", "]]", "a,b", "->->", "x$1", "5x"]
EJEMPLOS = [open(ruta, encoding="utf-8").read()
            for ruta in sorted(glob.glob(os.path.join(RAIZ, "pruebas", "*.jace")))]


def _texto_aleatorio(azar):
    return "".join(azar.choice(PIEZAS) for _ in range(azar.randint(0, 60)))


def _mutar(azar, texto):
    caracteres = list(texto)
    for _ in range(azar.randint(1, 6)):
        operacion = azar.choice(["borrar", "insertar", "cambiar", "duplicar", "mezclar"])
        if operacion == "borrar" and caracteres:
            del caracteres[azar.randrange(len(caracteres))]
        elif operacion == "insertar":
            caracteres.insert(azar.randrange(len(caracteres) + 1), azar.choice(PIEZAS))
        elif operacion == "cambiar" and caracteres:
            caracteres[azar.randrange(len(caracteres))] = azar.choice(PIEZAS)
        elif operacion == "duplicar":
            lineas = "".join(caracteres).split("\n")
            linea = azar.choice(lineas)
            lineas.insert(azar.randrange(len(lineas) + 1), linea)
            caracteres = list("\n".join(lineas))
        elif operacion == "mezclar":
            lineas = "".join(caracteres).split("\n")
            azar.shuffle(lineas)
            caracteres = list("\n".join(lineas))
    return "".join(caracteres)


def _corchetes(azar):
    apertura = "[" * azar.randint(0, 4)
    cierre = "]" * azar.randint(0, 4)
    return f"ENTRADA{apertura}a, b{cierre}\nAND{apertura}a, b{cierre} -> x\nOR[x, a -> y"


def _linea_enorme(azar):
    nombres = [f"s{i}" for i in range(azar.randint(200, 2000))]
    if azar.random() < 0.5:
        return f"ENTRADA[{', '.join(nombres)}]\nAND[{', '.join(nombres)}] -> salida"
    return "ENTRADA[a]\n" + "NOT[" * 300 + "a" + "]" * 300 + " -> y"


def casos():
    azar = random.Random(SEMILLA)
    lista = []
    for _ in range(200):
        lista.append(_texto_aleatorio(azar))
    for _ in range(250):
        lista.append(_mutar(azar, azar.choice(EJEMPLOS)))
    for _ in range(30):
        lista.append(_corchetes(azar))
    for _ in range(10):
        lista.append(_linea_enorme(azar))
    for _ in range(30):
        texto = azar.choice(EJEMPLOS)
        lista.append("".join(chr(azar.randint(0x80, 0x2FFF)) if azar.random() < 0.05 else c
                             for c in texto))
    lista += ["", " ", "\n\n\n", "#", "ENTRADA", "ENTRADA[", "ENTRADA[]", "->", "[]",
              "ENTRADA[a]\nAND[a, a] -> a", "ENTRADA[a]\nNOT[a]->", "\x00\x01\x02",
              "ENTRADA[a]\r\nNOT[a] -> b\r\n"]
    return lista


def test_hay_mas_de_500_casos():
    assert len(casos()) >= 500


def test_el_compilador_nunca_falla():
    gestor = GestorReglas()
    for indice, texto in enumerate(casos()):
        resultado = gestor.analizar(texto, imprimir=False, con_diagrama=False,
                                    registrar=False)
        mensajes = resultado["errores"] + resultado["advertencias"]
        assert not any("Error inesperado" in m for m in mensajes), (indice, texto)
        assert not any(m.startswith("Error interno") for m in mensajes), (indice, texto, mensajes)
        assert isinstance(resultado["diagnosticos"], list)
        if not resultado["exito"]:
            assert resultado["errores"], (indice, texto)


def test_algunos_casos_tambien_dibujan_sin_fallar():
    gestor = GestorReglas()
    for texto in EJEMPLOS:
        resultado = gestor.analizar(texto, imprimir=False, registrar=False)
        assert not any(m.startswith("Error interno") for m in resultado["errores"])
