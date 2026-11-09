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


def ejecutar_archivo(ruta, gestor):
    """Lee un archivo .jace con un circuito y lo analiza por completo."""
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

    # Se muestran y se conservan solo las líneas con instrucciones.
    instrucciones = []
    for i, linea in enumerate(lineas, start=1):
        linea_limpia = linea.strip()

        if not linea_limpia or linea_limpia.startswith("#"):
            continue

        print(f"Línea {i}: {linea_limpia}")
        instrucciones.append(linea_limpia)

    if not instrucciones:
        print("El archivo está vacío (sin instrucciones)")
        return False

    texto = "\n".join(instrucciones)
    gestor.analizar(texto, imprimir=True)

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
    print(f"  python main.py --help             - Mostrar esta ayuda")
    print(f"\nExtensión soportada: {EXTENSION}")

    print("\nEjemplo de archivo .jace:")
    print("  ENTRADA[a, b, c]")
    print("  AND[a, b] -> x1")
    print("  OR[x1, c] -> x2")
    print("  NOT[x2] -> salida")

    print("\nFormato del archivo:")
    print("  - Una instrucción por línea")
    print("  - Líneas que empiecen con # son ignoradas (comentarios)")
    print("  - Líneas vacías son ignoradas")
    print("  - Cada compuerta define una señal de salida con la flecha ->")


def main():
    if len(sys.argv) == 1:
        modo_interactivo()
        return

    if sys.argv[1] in ["--help", "-h"]:
        mostrar_ayuda()
        return

    if len(sys.argv) == 2:
        ruta = sys.argv[1]
        almacenamiento = Almacenamiento()
        gestor = GestorReglas(almacenamiento=almacenamiento)
        ejecutar_archivo(ruta, gestor)
        return

    print("Error: cantidad de argumentos inválida")
    mostrar_ayuda()


if __name__ == "__main__":
    main()