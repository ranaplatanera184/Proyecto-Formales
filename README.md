# JACE — Compilador de circuitos lógicos

Intérprete del lenguaje JACE para describir, validar y evaluar circuitos lógicos digitales.

## Estructura del Proyecto

```
Proyecto-Formales/
├── Token.py                        # Clase Token
├── ImplementacionAnalisisLexico.py  # Tokenizador
├── AnalisisSintactico.py            # Parser sintáctico
├── gestor_reglas.py                 # Gestor de reglas
├── reglas.json                      # Reglas gramaticales
├── almacenamiento.py                # Almacenamiento de datos
├── schematico.py                    # Diagrama del circuito (SVG/PNG)
├── semantico.py                     # Análisis semántico, tabla de verdad y DOT
├── expresiones.py                   # Expresiones booleanas (intermedia y expandida)
├── SERVIRCOR.py                     # Interfaz del computador (API + web)
├── jace_app.py                      # Aplicación (servidor local + navegador)
├── web/                             # Interfaz web (HTML, CSS, JS)
│                                     #   index.html, style.css, app.js, exportar.js
├── empaquetar.py                    # Empaquetado con PyInstaller (.exe)
├── jace_app.spec                    # Spec de PyInstaller
├── main.py                          # Punto de entrada
├── pruebas/diagrama_38.jace         # Circuito grande de prueba (512 filas)
├── docs/capturas/                   # Capturas de la interfaz
└── tests/                           # Tests unitarios
```

## Requisitos

- Python 3.10+

## Uso

```bash
# Modo interactivo
python main.py

# Ejecutar archivo .jace
python main.py archivo.jace

# Mostrar ayuda
python main.py --help
```

## Comandos Disponibles

| Comando | Descripción |
|---------|-------------|
| `ANALIZAR` | Pedir un circuito y analizarlo (léxico, sintáctico y semántico) |
| `HISTORIAL` | Mostrar los análisis realizados |
| `EXPORTAR` | Exportar el último análisis a un reporte `.txt` |
| `EXPRESIONES` | Mostrar las expresiones booleanas (intermedia y expandida) del último análisis correcto, en notación de símbolos y ASCII |
| `AYUDA` | Mostrar comandos disponibles |
| `CERRAR` | Salir del programa |

## Archivos .jace

Los archivos `.jace` contienen la descripción de un circuito: una línea
`ENTRADA[...]` y una instrucción por compuerta.

```
# Comentarios (se ignoran)
ENTRADA[a, b, c]
AND[a, b] -> x1
OR[x1, c] -> x2
NOT[x2] -> salida
```

### Formato

- Una declaración `ENTRADA[...]` con las señales de entrada
- Una instrucción `COMPUERTA[entradas] -> salida` por compuerta
- Líneas vacías se ignoran
- Líneas que empiecen con `#` son comentarios

### Ejemplo de ejecución

```bash
$ python main.py pruebas/01_circuito_valido.jace

=== Ejecutando pruebas/01_circuito_valido.jace ===

== ANÁLISIS DE CIRCUITO ==
...
== ORDEN DE EVALUACIÓN (TOPOLÓGICO) ==
  1. AND[a, b] -> x1
  2. OR[x1, c] -> x2
  3. NOT[x2] -> salida

== TABLA DE VERDAD ==
...
ANÁLISIS EXITOSO
```

## Arquitectura

```
[Entrada] → [Léxico] → [Sintáctico] → [Semántico] → [Evaluación]
            (Token)    (Parser)       (Validación)  (tabla/expresión/diagrama)
```

## Interfaz del computador (web + API)

`SERVIRCOR.py` expone el compilador con FastAPI y sirve la interfaz web de la
carpeta `web/`.

```bash
# Instalar dependencias de la interfaz
pip install -r requirements.txt

# Levantar la interfaz (abre http://127.0.0.1:8000)
python jace_app.py

# Sin abrir el navegador
python jace_app.py --sin-navegador --puerto 8080

# Solo la API
uvicorn SERVIRCOR:app --host 0.0.0.0 --port 8000
```

### Rutas de la API

| Ruta | Método | Descripción |
|------|--------|-------------|
| `/` | GET | Interfaz web (página del compilador) |
| `/info` | GET | Datos del lenguaje (JACE) |
| `/analizar` | POST | Analiza un circuito: `{codigo, fondo}`. Dibuja el diagrama y registra el análisis en el historial |
| `/validar` | POST | Solo comprueba el circuito: `{codigo}`. No dibuja ni registra nada (se usa mientras se escribe) |
| `/historial` | GET | Análisis registrados en memoria |
| `/historial/{indice}` | DELETE | Borra un análisis del historial |
| `/historial` | DELETE | Vacía el historial |
| `/background` | GET | Fondo visual actual, si es oscuro y los presets |
| `/background` | POST | Fija el fondo visual: `{"fondo": "#RRGGBB"}` |

El historial usa el mismo almacenamiento en memoria que el comando `HISTORIAL`
de la consola, así que web y consola muestran los mismos análisis mientras la
aplicación esté abierta. **No se guarda en disco**: al cerrar la aplicación se
pierde.

### Vistas de la interfaz

Navegación superior con tres vistas:

- `#/` — **Analizar**: layout de dos columnas. A la izquierda el editor del
  circuito; a la derecha el resultado en cinco pestañas (**Diagrama**,
  **Tabla de verdad**, **Expresión**, **Tokens**, **Errores**).
  - **Ctrl + Enter** analiza el circuito.
  - Mientras se escribe, la validación avisa en la pestaña **Errores** (con
    debounce de 600 ms) sin dibujar el diagrama ni ensuciar el historial. Al
    hacer clic en un error se selecciona la línea en el editor.
  - El diagrama tiene zoom (`+`, `−`, «Ajustar»), desplazamiento arrastrando y
    **Pantalla completa** (se cierra con `Esc`).
- La tabla de verdad se muestra por bloques de 32 filas con «Cargar más», y se
     puede filtrar por el valor de una señal (con sugerencias de los nombres
     reales del circuito).
  - La pestaña **Expresión** muestra, para cada salida final, la forma
    **intermedia** (una línea por compuerta, en orden topológico) y la
    **expandida** (una sola expresión con las entradas sustituidas). Se puede
    cambiar la notación entre símbolos (`¬ · ⊕ +`) y ASCII (`! & ^ |`) y copiar
    el resultado al portapapeles. Si la expandida supera los 2000 caracteres se
    omite y se indica el motivo; la intermedia no se recorta.
  - **Exportar** descarga el diagrama **SVG**, la tabla de verdad en **CSV** o
    todo el resultado en **JSON**. Se habilita tras un análisis correcto.
- `#/historial` — **Historial**: los análisis de la sesión actual, con fecha,
    número de compuertas y si terminaron con errores. Cada uno se puede cargar
    de nuevo en el editor (sin analizarlo) o borrar; también se vacía entero.
- `#/background` — **Background**: fondos predefinidos (Blanco, Papel, Cielo,
  Menta, Arena, Grafito, Noche, Bosque) o un color libre. El color se aplica a
  la página **y** al diagrama; el esquema se adapta solo a fondos claros u
  oscuros. Se recuerda el último color en el navegador.

### Circuitos de prueba

`pruebas/diagrama_38.jace` es un circuito de 9 entradas y 38 compuertas
(sumador ripple de 4 bits + multiplicador 2×2 + reducción de salidas). Genera
**512 filas** de tabla de verdad, así que sirve para medir el rendimiento de la
interfaz y para probar el filtro y el historial con datos de verdad.

```bash
python main.py pruebas/diagrama_38.jace
```

### Capturas

En `docs/capturas/` hay capturas de la interfaz: editor con errores, diagrama,
tabla de verdad, tokens, pantalla completa, circuito de 38 compuertas, menú de
exportar, historial, fondo oscuro y la versión móvil (390 px). Las tres últimas
muestran la pestaña **Expresión**: `14-expresion.png`, `15-expresion-aviso.png`
(circuito cuya expandida supera los 2000 caracteres) y
`16-expresion-circuito-grande.png`.

## Empaquetar como aplicación (.exe / binario)

Con PyInstaller se genera **un solo ejecutable** que levanta la interfaz local
y abre el navegador (doble clic):

```bash
pip install pyinstaller
python empaquetar.py             # un archivo: dist/jace-app[.exe]
python empaquetar.py --onedir    # carpeta dist/jace-app[.exe] (arranque rápido)
```

- `expresiones.py` viaja con los demás módulos: se importa desde
  `gestor_reglas.py`, así que PyInstaller lo incluye sin cambios en el `.spec`.
- **Linux / macOS**: produce `dist/jace-app` (ejecutable nativo).
- **Windows**: produce `dist/jace-app.exe`. Un `.exe` **solo** puede
  generarse en Windows: en esa máquina instala las dependencias
  (`pip install -r requirements.txt pyinstaller`) y ejecuta `python empaquetar.py`.
- La `web/` y `reglas.json` van incluidas dentro del ejecutable; no hay que
  copiar archivos aparte.
- Para probarlo sin empaquetar: `python jace_app.py`.

### Con Docker

```bash
docker compose up --build       # interfaz en http://localhost:8000
```

## Ejecutar Tests

```bash
python -m pytest tests/
```
