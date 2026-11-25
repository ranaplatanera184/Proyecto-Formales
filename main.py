# ============================================================================
# PUNTO DE ENTRADA DEL COMPILADOR DE CIRCUITOS LÓGICOS (.jace)
# ----------------------------------------------------------------------------
# Interfaz de consola: modo interactivo (menú) o ejecución de un archivo .jace
# que contiene un circuito completo.
# ============================================================================

import sys
import os

from gestor_reglas import GestorReglas
from almacenamiento import Almacenamiento

EXTENSION = ".jace"


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

    print(f"Error sintáctico línea 1: comando no reconocido '{texto}'")
    return None


def ejecutar_archivo(ruta, gestor, guardar=False):
    """Lee un archivo .jace con un circuito y lo analiza por completo.

    Los diagramas solo se escriben en el disco si `guardar` es True
    (opción --guardar); por defecto nunca se sobrescriben archivos ajenos.
    """
    if not os.path.exists(ruta):
        print(f"Error: el archivo '{ruta}' no existe")
        return False

    if not ruta.lower().endswith(EXTENSION):
        print(f"Error: el archivo debe tener la extensión {EXTENSION}")
        return False

    try:
        with open(ruta, "r", encoding="utf-8") as archivo:
            lineas = archivo.readlines()
    except Exception as error:
        print(f"Error leyendo el archivo: {error}")
        return False

    print(f"\n=== Ejecutando {ruta} ===\n")

    # Se muestran solo las líneas con instrucciones, pero se analiza el texto
    # completo: borrar comentarios o líneas vacías corría los números de línea
    # de los errores respecto al archivo original.
    hay_instrucciones = False
    for i, linea in enumerate(lineas, start=1):
        linea_limpia = linea.strip()

        if not linea_limpia or linea_limpia.startswith("#"):
            continue

        print(f"Línea {i}: {linea_limpia}")
        hay_instrucciones = True

    if not hay_instrucciones:
        print("El archivo está vacío (sin instrucciones)")
        return False

    texto = "".join(lineas)
    gestor.analizar(texto, imprimir=True, escribir_archivos=guardar)

    print("\n=== Análisis finalizado ===")
    return True


def modo_interactivo():
    print("\n=== COMPILADOR DE CIRCUITOS LÓGICOS (.jace) ===")

    almacenamiento = Almacenamiento()
    gestor = GestorReglas(almacenamiento=almacenamiento)

    gestor._ejecutar_ayuda()
    print("=====================================================")

    while True:
        try:
            texto = input("\nJACE> ")
        except KeyboardInterrupt:
            print("\nPrograma terminado")
            break
        except EOFError:
            print("\nPrograma terminado")
            break

        resultado = ejecutar_linea(texto, gestor)

        # CERRAR devuelve False y termina el programa.
        if resultado is False:
            break


def mostrar_ayuda():
    print("\nJACE Language - COMPILADOR DE CIRCUITOS LÓGICOS (FACULTAD SECCIONAL SOGAMOSO)")
    print("\nUso:")
    print("  python main.py                    - Modo interactivo")
    print(f"  python main.py archivo{EXTENSION}  - Ejecutar un archivo con un circuito")
    print(f"  python main.py --guardar archivo{EXTENSION}")
    print("                                      - Además guarda el diagrama SVG/PNG")
    print(f"  python main.py --help             - Mostrar esta ayuda")
    print(f"\nExtensión soportada: {EXTENSION}")

    print("\nEjemplo de archivo .jace:")
    print("  ENTRADA[a, b, c]")
    print("  AND[a, b] -> x1")
    print("  OR[x1, c] -> x2")
    print("  NOT[x2] -> salida")

    print("\nFormato del archivo:")
    print("  - Una instrucción por línea")
    print("  - Todo lo que sigue a # es un comentario (al inicio o al final de la línea)")
    print("  - Líneas vacías son ignoradas")
    print("  - Cada compuerta define una señal de salida con la flecha ->")
    print("\nEl diagrama no se guarda salvo que se pida con --guardar.")


def main():
    argumentos = sys.argv[1:]

    if not argumentos:
        modo_interactivo()
        return

    if any(argumento in ["--help", "-h"] for argumento in argumentos):
        mostrar_ayuda()
        return

    guardar = "--guardar" in argumentos
    argumentos = [argumento for argumento in argumentos if argumento != "--guardar"]

    if len(argumentos) == 1:
        ruta = argumentos[0]
        almacenamiento = Almacenamiento()
        gestor = GestorReglas(almacenamiento=almacenamiento)
        ejecutar_archivo(ruta, gestor, guardar=guardar)
        return

    print("Error: cantidad de argumentos inválida")
    mostrar_ayuda()


if __name__ == "__main__":
    main()