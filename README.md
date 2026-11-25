# JACE — Compilador de circuitos lógicos

Compilador académico del lenguaje JACE: describe un circuito combinacional, lo
analiza (fases léxica, sintáctica y semántica), genera código intermedio, lo
optimiza y produce la tabla de verdad, las expresiones booleanas, el diagrama
esquemático y un módulo Verilog. Se usa desde la consola o desde una interfaz
web local que funciona sin conexión.

## El lenguaje

```
# Sumador completo de 1 bit
ENTRADA[a, b, cin]
SALIDA[suma, cout]
XOR[a, b] -> p
XOR[p, cin] -> suma
OR[AND[a, b], AND[p, cin]] -> cout     # compuertas anidadas
```

### Gramática

```
<circuito>     ::= <entrada> [<salidas>] <instruccion>+
<entrada>      ::= ENTRADA "[" <lista_id> "]"
<salidas>      ::= SALIDA  "[" <lista_id> "]"
<lista_id>     ::= ID ("," ID)*
<instruccion>  ::= <compuerta> "->" ID
<compuerta>    ::= NOMBRE_COMPUERTA "[" <argumento> ("," <argumento>)* "]"
<argumento>    ::= ID | CONSTANTE | <compuerta>
CONSTANTE      ::= "0" | "1"
NOMBRE_COMPUERTA ::= AND | OR | NOT | XOR | NAND | NOR | XNOR
ID             ::= letra (letra | dígito | "_")*        (solo ASCII)
```

- `#` inicia un comentario hasta el final de la línea; las líneas vacías se ignoran.
- Las palabras reservadas no distinguen mayúsculas (`and` = `AND`), salvo
  `SALIDA`, que solo es reservada en mayúsculas y seguida de `[`: los circuitos
  antiguos que llaman `salida` a una señal siguen siendo válidos.
- `NOT` recibe exactamente 1 entrada; las demás compuertas, 2 o más (definido en
  `reglas.json`). `XOR`/`XNOR` de N entradas son la paridad impar/par.
- `SALIDA` es opcional. Sin ella, las salidas son las señales que no alimentan a
  ninguna compuerta. Con ella, las salidas son las declaradas y las compuertas
  que no llegan a ninguna dan una advertencia de compuerta muerta.
- Cada compuerta anidada se convierte en una señal temporal `_t1`, `_t2`... Los
  nombres del usuario no pueden empezar con `_`, así que no hay choques.

### Diagnósticos

Todos los errores y advertencias llevan fase, línea, columna exacta y, cuando
hay una obvia, una sugerencia:

```
Error sintáctico línea 2, columna 7: falta una coma entre 'a' y 'b'
Error léxico línea 3, columna 15: el nombre 'x$1' contiene el carácter no reconocido '$'
Error semántico línea 4, columna 5: la señal sumaa no está definida   (¿quisiste decir 'suma'?)
Advertencia línea 5, columna 1: la compuerta OR -> muerta no llega a ninguna salida del circuito
```

- El parser se recupera de los errores (modo pánico) y los reporta todos de una
  pasada: uno por línea, hasta 50.
- Los errores léxicos y sintácticos se reportan juntos; la fase semántica solo
  se ejecuta si no los hay.
- Se comprueban: aridad, entradas y salidas repetidas, redefiniciones, señales
  no definidas, salidas declaradas que nadie produce, entradas declaradas como
  salida y ciclos (uno por componente fuertemente conexa). Las advertencias
  son: entradas sin usar, la misma señal dos veces en una compuerta y
  compuertas muertas.

## Fases del compilador

```
texto → léxico → sintáctico → AST → desazucarado → semántico → IR → optimizador → resultados
        tokens   (recuperación)      (_t1, _t2…)   (tabla de       (tres      (pases hasta   (tabla, expresiones,
                                                    símbolos)      direcciones) punto fijo)   diagrama, Verilog)
```

| Módulo | Qué hace |
|--------|----------|
| `ImplementacionAnalisisLexico.py` | Tokens con línea y columna; un error por lexema inválido |
| `AnalisisSintactico.py` | Parser descendente recursivo con recuperación de errores |
| `ast_jace.py` | AST tipado, desazucarado y árbol ASCII |
| `semantico.py` | Comprobaciones, tabla de símbolos, orden topológico y tabla de verdad |
| `evaluador.py` | Evaluación bit-paralela de cualquier bloque de filas de la tabla |
| `ir.py` | Código de tres direcciones (`t1 = AND a, b`) con la línea de origen |
| `optimizador.py` | Constantes, simplificaciones algebraicas, subexpresiones comunes y código muerto |
| `backends/verilog.py` | Módulo Verilog estructural y testbench |
| `expresiones.py` | Formas intermedia y expandida (símbolos `¬ · ⊕ +` o ASCII `! & ^ \|`) |
| `schematico.py` | Diagrama esquemático (SVG/PNG con schemdraw) |
| `diagnosticos.py`, `sugerencias.py` | Diagnósticos estructurados y distancia de Levenshtein |
| `gestor_reglas.py` | Orquesta las fases y los límites; nunca lanza excepciones |
| `consola.py`, `main.py` | Interfaz de consola |
| `SERVIRCOR.py`, `web/` | API FastAPI e interfaz web |
| `rutas.py` | Único punto que ubica `reglas.json` y `web/` (también dentro del `.exe`) |

### Optimizador

Aplica estos pases en orden hasta que una vuelta completa no cambia nada:

1. Constantes: `AND[x,0]=0`, `AND[x,1]=x`, `OR[x,1]=1`, `XOR[x,1]=NOT x`...
2. Algebraico: `NOT(NOT x)=x`, `AND[x,x]=x`, `XOR[x,x]=0`.
3. Subexpresiones comunes: la clave es la operación más los argumentos ordenados.
4. Código muerto: se quita lo que no llega a una salida.

Las salidas conservan su nombre (`y = BUF a`, `y = CONST 0`). Cada cambio queda
en una bitácora con la métrica antes y después: compuertas, profundidad y
entradas usadas. Un test comprueba que la tabla optimizada es idéntica a la
original en todos los `.jace` de `pruebas/` y en 200 circuitos aleatorios.

## Consola

```bash
python main.py                                   # modo interactivo (menú)
python main.py archivo.jace                      # resumen
python main.py archivo.jace --arbol --tabla      # con secciones extra
python main.py archivo.jace --verilog -o circuito.v
```

Sin opciones imprime un **resumen**: el estado de cada fase (✔/✖), los
diagnósticos con línea, columna y sugerencia, las salidas con su expresión y las
métricas de la optimización.

| Opción | Muestra |
|--------|---------|
| `--tokens` | Tokens (también cuando hay errores) |
| `--arbol` | Árbol sintáctico en ASCII (`├── └── │`) |
| `--simbolos` | Tabla de símbolos |
| `--intermedio` | Código de tres direcciones |
| `--optimizar` | Código optimizado y bitácora |
| `--tabla` | Tabla de verdad hasta 14 entradas; por encima exige `--tabla --todas` |
| `--temporales` | Incluye `_t1`, `_t2`... en la tabla |
| `--verilog` / `--emit verilog` | Módulo Verilog (`--testbench` añade el banco de pruebas, `-o` lo guarda) |
| `--guardar` | Escribe `diagrama_circuito.svg` y `.png` |

**Códigos de salida:** 0 si compila, 1 si hay errores de compilación y 2 si el
uso es incorrecto. Los colores ANSI solo se usan si la salida es una terminal y
`NO_COLOR` no está definido. La consola muestra los mismos diagnósticos, en el
mismo orden, que la web (hay un test que lo comprueba para cada `.jace`).

En el modo interactivo están los comandos `ANALIZAR`, `HISTORIAL`, `EXPORTAR`
(reporte `.txt`), `EXPRESIONES`, `AYUDA` y `CERRAR`.

## Interfaz web

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
python jace_app.py                # abre http://127.0.0.1:8000
python jace_app.py --sin-navegador --puerto 8765
```

- **Editor** con números de línea y marcas en las líneas con error o advertencia.
  Se valida mientras escribes; **Ctrl+Enter** analiza.
- **Ejemplos**: galería de circuitos válidos (sumador, multiplexor, comparador,
  anidados, constantes...) y con errores de cada fase.
- **Guía rápida** de sintaxis plegable bajo el editor.
- **Pestañas**:
  1. **Tokens**: tabla filtrable.
  2. **Árbol**: árbol plegable; un clic en un nodo lo señala en el editor.
  3. **Símbolos**: tipo (entrada, salida, cable interno o temporal), línea de declaración y líneas de uso.
  4. **Diagnósticos**: muestra la cuenta o ✔; clic para ir a la línea y columna.
  5. **Intermedio**: IR original, IR optimizado, métricas y bitácora.
  6. **Resultados**: Tabla, Expresión, Diagrama y Verilog.
  7. **Paso a paso**: eliges las entradas y recorres las compuertas en orden.
- **Exportar**: SVG, CSV, JSON y Verilog.
- **Fondo**: el botón de la paleta, arriba a la derecha, abre los fondos
  predefinidos y el color libre. Se aplica también al diagrama; el tema claro u
  oscuro se elige solo.

### Límites

- **Tabla de verdad**: se calcula completa hasta 14 entradas (`LIMITE_TABLA`,
  variable `JACE_LIMITE_TABLA`) y 2^18 celdas. Por encima, la web ofrece
  «Generar tabla» y pide las filas por bloques a `/tabla`, que calcula solo las
  filas pedidas a partir de su índice binario. El CSV también se exporta por
  bloques.
- **Diagrama**: se omite por encima de 300 compuertas o 1200 conexiones
  (`JACE_LIMITE_DIAGRAMA`).
- **Expresión expandida**: se omite si supera 2000 caracteres. Se calcula la
  longitud antes de construirla, así que no crece de forma exponencial.

Con 20 entradas, `/validar` tarda unos 10 ms y `/analizar` menos de 1 s, con una
respuesta de unos 250 KB.

### API

| Ruta | Método | Descripción |
|------|--------|-------------|
| `/info` | GET | Datos del lenguaje y límites |
| `/analizar` | POST | `{codigo, fondo?}` → resultado completo |
| `/validar` | POST | `{codigo}` → tokens, AST, símbolos y diagnósticos (sin tabla ni diagrama) |
| `/tabla` | POST | `{codigo, desde, cantidad}` → filas de la tabla (máximo 4096 por petición) |
| `/ejemplos` | GET | Galería de ejemplos |
| `/historial` | GET / DELETE | Historial de la web (en memoria; no se comparte con la consola) |
| `/historial/{i}` | DELETE | Borra un análisis |
| `/background` | GET / POST | Fondo actual / `{"fondo": "#RRGGBB"}` |

Campos de `/analizar`:

- **Ya existentes:** `exito`, `errores`, `advertencias`, `tokens`, `entradas`,
  `compuertas`, `tabla_simbolos`, `orden_topologico`, `tabla_verdad`,
  `expresiones`, `expresiones_booleanas`, `diagrama_dot`, `diagrama_svg`, `fondo`.
- **Nuevos:**
  - `diagnosticos`: lista de `{fase, severidad, linea, columna, mensaje, sugerencia}`.
  - `ast`: nodos `{tipo, valor, linea, columna, hijos}`.
  - `arbol_ascii`, `ir`, `optimizacion`, `verilog`.
  - `salidas`, `salidas_declaradas`, `temporales`.
  - `tabla_omitida` y `diagrama_omitido`.

Los errores internos nunca llegan como excepción. Se devuelven como
"Error interno del compilador: …, por favor repórtalo" y, con `JACE_DEBUG=1`,
el traceback se imprime en la consola del servidor.

## Archivos de ejemplo

- `pruebas/`: casos válidos e inválidos del enunciado (01–09) y circuitos de
  diagrama. `diagrama_38.jace` tiene 9 entradas y 38 compuertas.
- `ejemplos/`: la galería de la web. `catalogo.json` reutiliza los de `pruebas/`
  cuando sirven.

## Tests

```bash
python -m pytest tests/ -q
```

La prueba con `iverilog` se salta si no está instalado.

## Empaquetado

```bash
pip install pyinstaller
python empaquetar.py             # un archivo: dist/jace-app[.exe]
python empaquetar.py --onedir    # carpeta (arranque más rápido)
docker compose up --build        # interfaz en http://localhost:8000
```

`jace_app.spec` incluye `reglas.json`, `web/`, `ejemplos/` y `pruebas/` dentro
del ejecutable. Un `.exe` de Windows solo se puede generar en Windows.
