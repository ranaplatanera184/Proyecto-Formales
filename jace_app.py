# ============================================================================
# APLICACIÓN DE ESCRITORIO JACE (interfaz del computador)
# ----------------------------------------------------------------------------
# Este es el punto de entrada del ejecutable (jace-app.exe en Windows,
# jace-app en Linux):
#   1. Levanta el servidor local de la interfaz (SERVIRCOR) en 127.0.0.1.
#   2. Abre el navegador con la interfaz web.
#   3. Se queda esperando; al cerrar (Enter o Ctrl+C) apaga el servidor.
#
# Uso:  jace-app [--puerto N] [--sin-navegador]
# ============================================================================

import argparse
import socket
import sys
import threading
import time
import webbrowser

import uvicorn

from SERVIRCOR import app, ruta_web

ANCHO = 74


def puerto_libre(preferido=8000):
    """Devuelve el puerto indicado si está libre; si no, el siguiente libre."""
    for candidato in range(preferido, preferido + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", candidato))
                return candidato
            except OSError:
                continue
    return 0        # 0 = que el sistema elija uno libre


def linea(caracter="="):
    return caracter * ANCHO


def servir(app, puerto, abrir):
    """Levanta el servidor, abre el navegador y espera a que el usuario salga."""
    configuracion = uvicorn.Config(app, host="127.0.0.1", port=puerto,
                                   log_level="warning")
    servidor = uvicorn.Server(configuracion)

    hilo = threading.Thread(target=servidor.run, daemon=True)
    hilo.start()

    # Se espera a que el servidor acepte conexiones antes de abrir el navegador.
    while not servidor.started and hilo.is_alive():
        time.sleep(0.05)

    url = f"http://127.0.0.1:{servidor.config.port}/"
    print(linea())
    print(" JACE - Compilador de Circuitos Lógicos (interfaz web)")
    print(linea())
    print(f" Interfaz:  {url}")
    print(f" API:       {url}info   |   {url}analizar   |   {url}validar   |   {url}historial   |   {url}background")
    print(f" Recursos:  {ruta_web()}")
    print(linea("-"))
    print(" En la página: «Analizar» para el circuito (Ctrl+Enter),")
    print(" «Historial» para repetir o borrar análisis y «Background»")
    print(" para el fondo, que también se aplica al diagrama.")
    print(linea("-"))
    print(" Pulsa ENTER (o Ctrl+C) para cerrar la aplicación.")

    if abrir:
        webbrowser.open(url)

    try:
        input()
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        print("\n Cerrando JACE...")
        servidor.should_exit = True
        hilo.join(timeout=5)


def main():
    analizador = argparse.ArgumentParser(
        description="Interfaz web de JACE (compilador de circuitos lógicos)")
    analizador.add_argument("--puerto", type=int, default=8000,
                            help="puerto del servidor local (por defecto 8000)")
    analizador.add_argument("--sin-navegador", action="store_true",
                            help="no abrir el navegador al arrancar")
    argumentos = analizador.parse_args()

    puerto = puerto_libre(argumentos.puerto)
    if puerto == 0:
        print("No se encontró un puerto libre.")
        sys.exit(1)

    servir(app, puerto, abrir=not argumentos.sin_navegador)


if __name__ == "__main__":
    main()
