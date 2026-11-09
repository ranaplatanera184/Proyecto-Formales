# Autómatas Finitos Deterministas (AFD) del lenguaje de circuitos

Este documento especifica los AFD que reconoce cada tipo de token del
compilador de circuitos lógicos y verifica que el tokenizador
(`ImplementacionAnalisisLexico.py`) sea coherente con ellos.

## Alfabeto del lenguaje

El alfabeto efectivo de entrada es: letras (`A-Z`, `a-z`, con `ñ`/`Ñ`),
dígitos (`0-9`), guion bajo (`_`), corchetes (`[` y `]`), coma (`,`) y la
flecha formada por los caracteres `-` y `>`.

Se ignoran los espacios en blanco entre tokens.

## Estados de aceptación

Todo token se reconoce al llegar a un **estado de aceptación**. Los símbolos
que nunca forman parte de un token (p. ej. `$`, `#`, `"`) llevan el tokenizador
a un estado de error léxico.

## Tipos de token

| Token | Valor | Estado de aceptación | Definido en |
|---|---|---|---|
| `PALABRA RESERVADA` | `ENTRADA`, `AND`, `OR`, `NOT`, `XOR`, `NAND` | q3 (si la palabra está en el conjunto) | `reglas.json` → `palabras_reservadas` |
| `IDENTIFICADOR` | letra + letras/dígitos/`_` | q3 (si la palabra NO está en el conjunto) | `ImplementacionAnalisisLexico.tokenizar_linea` |
| `FLECHA` | `->` | q4 | ídem |
| `CORCHETE ABRE` | `[` | q1 | ídem |
| `CORCHETE CIERRA` | `]` | q1 | ídem |
| `COMA` | `,` | q1 | ídem |

## AFD de palabras e identificadores

El reconocimiento de palabras combina dos situaciones en un solo autómata:
la secuencia de letras/dígitos/`_` es idéntica, y la **clasificación final**
depende de si la palabra pertenece al conjunto de reservadas.

Convención: `L = {A-Z, a-z, ñ, Ñ}`, `D = {0-9}`.

| Estado actual | `L` | `D` | `_` | otros |
|---|---|---|---|---|
| q0 (inicio) | q1 | ERROR | ERROR | ERROR |
| q1 | q2 | q2 | q2 | → aceptar palabra |
| q2 | q2 | q2 | q2 | → aceptar palabra |

- **q1**: ya se leyó la primera letra; un solo carácter aislado es un
  identificador válido.
- **q2**: estado de aceptación con palabra en curso.
- Al llegar a un carácter distinto de `L`, `D` o `_`, se cierra la palabra:
  - si `palabra.upper()` ∈ `palabras_reservadas` → token `PALABRA RESERVADA`;
  - en caso contrario → token `IDENTIFICADOR`.

Estado de aceptación: **q2** (más el caso de palabra de una sola letra en q1).

## AFD de la flecha `->`

| Estado actual | `-` | `>` | otro |
|---|---|---|---|
| q0 | q3 | ERROR | ERROR |
| q3 | ERROR | q4 (acepta) | ERROR |

Estado de aceptación: **q4**.

Nota: si tras `-` no viene `>`, se genera `Error léxico línea N: carácter no
reconocido '-'`.

## AFD de los símbolos `[`, `]` y `,`

Cada símbolo es un AFD trivial de un solo paso:

| Estado actual | `[` | `]` | `,` |
|---|---|---|---|
| q0 | q1 (acepta `CORCHETE ABRE`) | q1 (acepta `CORCHETE CIERRA`) | q1 (acepta `COMA`) |

Estado de aceptación: **q1** en cada caso.

## Verificación de coherencia

El tokenizador `tokenizar_linea` implementa exactamente estos autómatas:

1. Empieza en un estado equivalente a q0 y salta los espacios en blanco.
2. Si ve `-`, inspecciona el siguiente carácter para formar la flecha
   (flujo del AFD de la flecha): si el siguiente es `>`, emite `FLECHA`;
   si no, error léxico; un `>` suelto también es error.
3. Si ve `[`, `]` o `,`, emite directamente el token correspondiente.
4. Si ve una letra, recorre letras, dígitos y `_` (estados q1/q2 del AFD de
   palabras) y clasifica el resultado: palabra reservada o identificador.
5. Cualquier otro carácter (dígito al inicio, `$`, `#`, `"`, etc.) produce
   `Error léxico línea N: carácter no reconocido '...'`, como exigen los
   estados ERROR de los autómatas anteriores.

### Coherencia verificada

- Las palabras reservadas no se hardcodean dos veces: `tokenizar_circuito`
  las carga de `reglas.json` (`palabras_reservadas`), la misma fuente que
  usa el gestor de reglas. Por tanto, si se agrega una compuerta nueva, el
  AFD de palabras la reconoce automáticamente.
- La clasificación es insensible a mayúsculas (como en el tokenizador
  original): la palabra se compara con `palabra.upper()`.
- La regla gramatical "los identificadores empiezan con letra" se refleja en
  el AFD: empezar con dígito o guion bajo lleva a ERROR.