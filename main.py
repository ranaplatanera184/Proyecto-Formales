# ============================================================================
# PUNTO DE ENTRADA DEL COMPILADOR DE CIRCUITOS LÓGICOS (.jace)
# ----------------------------------------------------------------------------
# Interfaz de consola:
#
#   python main.py                         modo interactivo (menú de comandos)
#   python main.py archivo.jace [opciones] compila un archivo
#
# Sin opciones imprime un RESUMEN: estado de cada fase (✔/✖), diagnósticos
# con línea, columna y sugerencia, las salidas con su expresión y las
# métricas de la optimización. Las opciones agregan secciones (ver --help).
#
# Códigos de salida: 0 si compila, 1 si hay errores de compilación,
# 2 si el uso es incorrecto (argumentos, archivo inexistente...).
# ============================================================================

import argparse
import os
import sys

from gestor_reglas import GestorReglas, LIMITE_TABLA
from almacenamiento import Almacenamiento
import consola

EXTENSION = ".jace"

COMPILA = 0
NO_COMPILA = 1
USO_INCORRECTO = 2


def preparar_salida_estandar():
    """Salida en UTF-8 cuando no es una terminal (tuberías, archivos).

    En una consola de Windows Python ya escribe Unicode; redirigida, usaría
    la página de códigos del sistema y fallaría con ✔, ✖ o →.
    """
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure") and not flujo.isatty():
            flujo.reconfigure(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Modo interactivo (se conserva el menú de comandos de reglas.json)
# ---------------------------------------------------------------------------
def ejecutar_linea(texto, gestor):
    """Procesa una línea del menú: identifica el comando y lo despacha."""
    texto = texto.strip()

    # Líneas vacías y comentarios se ignoran.
    if not texto or texto.startswith("#"):
        return None

    comando = texto.upper()

    if gestor.es_comando(comando):
        try:
            return gestor.ejecutar(comando)
        except SyntaxError as error:
            print(str(error))
            return None

    print(f"Comando no reconocido: '{texto}'. Escribe AYUDA para ver los comandos.")
    return None


def modo_interactivo():
    print("\n=== JACE · COMPILADOR DE CIRCUITOS LÓGICOS (.jace) ===")
    print("Escribe un comando y pulsa ENTER. Por ejemplo:")
    print("  ANALIZAR  → pega o escribe el circuito y termina con una línea vacía")
    print("  AYUDA     → lista todos los comandos · CERRAR → salir")
    print("Para compilar un archivo usa: python main.py archivo.jace (ver --help)\n")

    almacenamiento = Almacenamiento()
    gestor = GestorReglas(almacenamiento=almacenamiento)

    gestor._ejecutar_ayuda()
    print("=====================================================")

    while True:
        try:
            texto = input("\nJACE> ")
        except (KeyboardInterrupt, EOFError):
            print("\nPrograma terminado")
            break

        resultado = ejecutar_linea(texto, gestor)

        # CERRAR devuelve False y termina el programa.
        if resultado is False:
            break


# ---------------------------------------------------------------------------
# Compilación de un archivo
# ---------------------------------------------------------------------------
def crear_parser():
    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="JACE: compilador de circuitos lógicos. Sin argumentos abre el "
                    "modo interactivo.",
        epilog="Ejemplo: python main.py pruebas/01_circuito_valido.jace --arbol --tabla\n"
               "Códigos de salida: 0 compila, 1 errores de compilación, 2 uso incorrecto.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("archivo", help=f"circuito a compilar ({EXTENSION})")
    parser.add_argument("--tokens", action="store_true", help="muestra los tokens (también con errores)")
    parser.add_argument("--arbol", action="store_true", help="muestra el árbol sintáctico (ASCII)")
    parser.add_argument("--simbolos", action="store_true", help="muestra la tabla de símbolos")
    parser.add_argument("--intermedio", action="store_true", help="muestra el código de tres direcciones")
    parser.add_argument("--optimizar", action="store_true",
                        help="muestra el código optimizado y la bitácora del optimizador")
    parser.add_argument("--tabla", action="store_true",
                        help=f"muestra la tabla de verdad (hasta {LIMITE_TABLA} entradas)")
    parser.add_argument("--todas", action="store_true",
                        help=f"con --tabla, permite más de {LIMITE_TABLA} entradas")
    parser.add_argument("--temporales", action="store_true",
                        help="incluye las señales temporales (_t1...) en la tabla")
    parser.add_argument("--verilog", action="store_true", help="genera el módulo Verilog")
    parser.add_argument("--emit", choices=["verilog"], help="equivale a --verilog")
    parser.add_argument("--testbench", action="store_true",
                        help="con --verilog, agrega el testbench")
    parser.add_argument("--guardar", action="store_true",
                        help="guarda el diagrama (diagrama_circuito.svg y .png)")
    parser.add_argument("-o", "--salida", metavar="SALIDA",
                        help="con --verilog, archivo donde guardar el código")
    return parser


def leer_circuito(ruta):
    """Texto del archivo o un mensaje de error de uso."""
    if not os.path.exists(ruta):
        return None, f"el archivo '{ruta}' no existe"
    if not ruta.lower().endswith(EXTENSION):
        return None, f"el archivo debe tener la extensión {EXTENSION}"
    try:
        # utf-8-sig acepta también los archivos guardados con BOM.
        with open(ruta, "r", encoding="utf-8-sig") as archivo:
            return archivo.read(), None
    except UnicodeDecodeError:
        return None, f"el archivo '{ruta}' no está en UTF-8"
    except IsADirectoryError:
        return None, f"'{ruta}' es una carpeta, no un archivo"
    except OSError as error:
        if os.path.isdir(ruta):
            return None, f"'{ruta}' es una carpeta, no un archivo"
        return None, f"no se pudo leer '{ruta}': {error.strerror}"


def compilar_archivo(argumentos, parser):
    texto, problema = leer_circuito(argumentos.archivo)
    if problema:
        parser.print_usage(sys.stderr)
        print(f"error: {problema}", file=sys.stderr)
        return USO_INCORRECTO

    pintar = consola.Pintor(consola.usar_colores())
    gestor = GestorReglas()
    resultado = gestor.analizar(texto, imprimir=False, registrar=False,
                                con_diagrama=argumentos.guardar,
                                escribir_archivos=argumentos.guardar)
    print(consola.resumen(resultado, os.path.basename(argumentos.archivo), pintar))

    # Los tokens se muestran también cuando hay errores.
    if argumentos.tokens:
        print(consola.seccion("TOKENS", consola.texto_tokens(resultado), pintar))
    if argumentos.arbol and resultado["arbol_ascii"]:
        print(consola.seccion("ÁRBOL SINTÁCTICO", resultado["arbol_ascii"], pintar))
    if argumentos.simbolos and resultado["tabla_simbolos"]:
        print(consola.seccion("TABLA DE SÍMBOLOS", consola.texto_simbolos(resultado), pintar))

    if not resultado["exito"]:
        return NO_COMPILA

    if argumentos.intermedio:
        print(consola.seccion("CÓDIGO INTERMEDIO", consola.texto_ir(resultado["ir"]), pintar))
    if argumentos.optimizar:
        print(consola.seccion("OPTIMIZACIÓN", consola.texto_optimizacion(resultado), pintar))

    if argumentos.tabla:
        entradas = len(set(resultado["entradas"]))
        if entradas > LIMITE_TABLA and not argumentos.todas:
            print(consola.seccion("TABLA DE VERDAD",
                                  f"  El circuito tiene {entradas} entradas ({2 ** entradas} filas). "
                                  f"Usa --tabla --todas para imprimirla igualmente.", pintar))
        else:
            semantico, _ = gestor.preparar_evaluacion(texto)
            print(consola.seccion("TABLA DE VERDAD",
                                  consola.texto_tabla(semantico, argumentos.temporales), pintar))

    if argumentos.verilog:
        verilog = resultado["verilog"]
        codigo = verilog["modulo"]
        if argumentos.testbench:
            codigo += "\n" + (verilog["testbench"] or f"// {verilog['aviso_testbench']}\n")
        if argumentos.salida:
            try:
                with open(argumentos.salida, "w", encoding="utf-8") as archivo:
                    archivo.write(codigo)
            except OSError as error:
                print(f"error: no se pudo escribir '{argumentos.salida}': "
                      f"{error.strerror or error}", file=sys.stderr)
                return USO_INCORRECTO
            print(f"\nVerilog guardado en {argumentos.salida}")
        else:
            print(consola.seccion("VERILOG", codigo.rstrip(), pintar))

    if argumentos.guardar:
        estado = ("guardado en diagrama_circuito.svg y diagrama_circuito.png"
                  if resultado["diagrama_svg"] else "no se pudo generar")
        print(f"\nDiagrama {estado}")
    return COMPILA


def main(argv=None):
    preparar_salida_estandar()
    argv = sys.argv[1:] if argv is None else argv

    if not argv:
        modo_interactivo()
        return COMPILA

    parser = crear_parser()
    argumentos = parser.parse_args(argv)        # sale con código 2 si el uso es incorrecto
    if argumentos.emit == "verilog":
        argumentos.verilog = True
    if argumentos.salida and not argumentos.verilog:
        parser.error("-o/--salida solo se usa con --verilog")
    if argumentos.todas and not argumentos.tabla:
        parser.error("--todas solo se usa con --tabla")
    return compilar_archivo(argumentos, parser)


if __name__ == "__main__":
    sys.exit(main())
