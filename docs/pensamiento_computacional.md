# JACE desde el pensamiento computacional

## Algoritmia, identificación de patrones, abstracción y descomposición

**Proyecto:** JACE — Compilador de circuitos lógicos digitales  
**Curso:** Lenguajes formales  
**Repositorio:** `Proyecto-Formales-`  
**Documento de apoyo:** análisis del sistema completo (léxico, sintáctico, semántico, evaluación, diagrama e interfaz web)

---

## Contenido

1. [Introducción](#1-introducción)
2. [JACE en una página](#2-jace-en-una-página)
3. [Pilar 1 — Algoritmia](#3-pilar-1--algoritmia)
4. [Pilar 2 — Identificación de patrones](#4-pilar-2--identificación-de-patrones)
5. [Pilar 3 — Abstracción](#5-pilar-3--abstracción)
6. [Pilar 4 — Descomposición en pequeños procesos](#6-pilar-4--descomposición-en-pequeños-procesos)
7. [Los cuatro pilares trabajando juntos: traza completa](#7-los-cuatro-pilares-trabajando-juntos-traza-completa)
8. [Matriz de trazabilidad](#8-matriz-de-trazabilidad)
9. [Conclusiones](#9-conclusiones)
10. [Anexos](#10-anexos)

---

## 1. Introducción

El pensamiento computacional es la forma de razonar que permite tomar un problema, representarlo de manera que pueda resolverse con pasos precisos y construir una solución verificable. No se reduce a programar: es una manera de organizar el razonamiento. En la literatura se suelen distinguir cuatro pilares que se aplican de forma articulada: la **algoritmia** (definir una secuencia ordenada y finita de pasos), la **identificación de patrones** (reconocer regularidades que se repiten), la **abstracción** (quedarse con lo esencial y ocultar el detalle que no aporta) y la **descomposición** (dividir un problema grande en problemas pequeños que se puedan resolver y probar por separado).

JACE es un caso de estudio especialmente claro para esos cuatro pilares porque no es un programa que resuelve una sola tarea: es un sistema que recibe un lenguaje, lo valida en varias fases, lo interpreta y produce varios artefactos de salida (tabla de verdad, expresión booleana, diagrama y reporte). Esa complejidad obliga a que el equipo haya tenido que aplicar los cuatro pilares de manera consciente: sin algoritmos claros las fases no terminarían, sin patrones el código se duplicaría, sin abstracción cada interfaz tendría que reimplementar el compilador y sin descomposición el proyecto sería un único archivo imposible de probar.

Este documento no se limita a enunciar los pilares. Para cada uno se presenta una definición breve, se explica cómo aparece de forma concreta en el código de JACE, se muestra la evidencia con referencias a archivo y línea, y se indica qué se puede demostrar con el sistema en funcionamiento. El objetivo es que cualquier lector pueda comprobar que las afirmaciones están sustentadas en el proyecto real y no en una descripción idealizada.

---

## 2. JACE en una página

JACE es un intérprete de un lenguaje propio para describir circuitos lógicos digitales. Un programa `.jace` declara las entradas y luego una instrucción por cada compuerta. Cada instrucción tiene la forma `COMPUERTA[lista de entradas] -> señal de salida`. Por ejemplo, el circuito de prueba `pruebas/01_circuito_valido.jace` es:

```
# Circuito de ejemplo del enunciado (válido)
ENTRADA[a, b, c]
AND[a, b] -> x1
OR[x1, c] -> x2
NOT[x2] -> salida
```

El sistema ejecuta tres fases clásicas de un compilador y, si el circuito es válido, continúa con la evaluación. La fase **léxica** convierte el texto en tokens (`ImplementacionAnalisisLexico.py`). La fase **sintáctica** comprueba que la secuencia de tokens respeta la gramática y construye el modelo del circuito (`AnalisisSintactico.py`). La fase **semántica** valida el significado: aridad de compuertas, señales definidas, redefiniciones y ciclos (`semantico.py`). Si todo es correcto, se calcula el orden topológico, la tabla de verdad y las expresiones booleanas, y se dibuja el diagrama esquemático (`expresiones.py` y `schematico.py`).

La coordinación de todo el proceso vive en un único punto: `GestorReglas.analizar()` (`gestor_reglas.py:75`). Esa función recibe el texto, llama a cada fase en orden, acumula los errores y arma un diccionario de resultado que después consumen tanto la consola (`main.py`) como la interfaz web (`SERVIRCOR.py`). Esa decisión —un solo orquestador y varias interfaces delgadas— es la que permite que el proyecto sea coherente y que las pruebas se puedan concentrar en el núcleo.

El flujo completo se puede resumir así:

```
                 ┌──────────────────────────────────────────────┐
 texto .jace ──▶ │  GestorReglas.analizar()  (orquestador)       │
                 │                                              │
                 │  1. tokenizar_circuito()      → tokens       │
                 │  2. AnalisisSintactico        → estructura   │
                 │  3. AnalizadorSemantico       → errores      │
                 │  4. orden_topologico()        → secuencia    │
                 │  5. tabla_verdad()            → 2^n filas    │
                 │  6. generar_expresiones()     → expresiones  │
                 │  7. schematico.generar_diagrama() → SVG/PNG  │
                 └──────────────────────────────────────────────┘
                        │                       │
                        ▼                       ▼
                 consola (main.py)       web (SERVIRCOR.py)
```

Las reglas del lenguaje no están repartidas por el código: viven en `reglas.json`. Ese archivo declara las compuertas con su aridad y su operación, las palabras reservadas y los comandos del menú. Esa centralización es la que hace posible que el lexer, el parser y el analizador semántico trabajen con la misma definición del lenguaje.

---

## 3. Pilar 1 — Algoritmia

### 3.1 Qué significa en este proyecto

La algoritmia es la capacidad de expresar una solución como una secuencia de pasos ordenados, finitos y sin ambigüedad. En JACE no hay un solo algoritmo: hay varios que se encadenan. El más importante es el **algoritmo de compilación**, que decide en qué orden se ejecutan las fases y qué se hace cuando una falla. Pero también hay algoritmos específicos dentro de cada fase: el autómata del lexer, el descenso recursivo del parser, la búsqueda en profundidad que detecta ciclos, el algoritmo de Kahn que produce el orden de evaluación, el producto cartesiano que genera la tabla de verdad y la expansión recursiva con memoización que construye las expresiones.

La clave algorítmica del sistema está en que cada fase tiene una precondición y una postcondición claras. La fase léxica solo avanza si produce tokens; la sintáctica solo se ejecuta si no hubo errores léxicos; la semántica solo se ejecuta si la estructura se construyó; la evaluación solo se ejecuta si no hubo errores semánticos. Esa cadena de dependencias es exactamente un algoritmo de control: evita trabajar sobre datos inválidos y garantiza que los errores que se reportan pertenecen a la primera fase que falló.

### 3.2 El algoritmo de control: las fases encadenadas

`GestorReglas.analizar()` (`gestor_reglas.py:75`) es el algoritmo principal. Primero limpia el texto y normaliza el color de fondo. Luego, si el texto no está vacío, ejecuta la fase léxica con `tokenizar_circuito()` (`gestor_reglas.py:108`). Si no hubo errores léxicos, construye la estructura con `AnalisisSintactico(tokens, gestorReglas=self).construir_circuito()` (`gestor_reglas.py:114`). Si la estructura existe, crea un `AnalizadorSemantico` y llama a `revisar()` (`gestor_reglas.py:125`). Solo si la lista de errores semánticos está vacía calcula el orden topológico, la tabla de verdad y las expresiones (`gestor_reglas.py:128-158`). Finalmente, si se pidió diagrama, llama a `schematico.generar_diagrama()` y a `exportar()`.

Ese orden no es casual. Si el lexer encontrara un carácter inválido, el parser recibiría una lista incompleta de tokens y produciría errores confusos; por eso el sistema corta en la primera fase que falla. La consecuencia práctica es que un programa con `$` en una señal reporta un error léxico y no intenta adivinar la estructura. El circuito `pruebas/09_caracter_invalido.jace` lo demuestra: la señal `x$1` produce `Error léxico línea 2: carácter no reconocido '$'` antes de que el parser tenga oportunidad de intervenir.

### 3.3 El autómata del análisis léxico

El lexer no recorre el texto con expresiones regulares monolíticas: implementa autómatas finitos deterministas (AFD) explícitos. La especificación está en `docs/automatas.md` y la implementación en `ImplementacionAnalisisLexico.tokenizar_linea()` (`ImplementacionAnalisisLexico.py:36`). Para las palabras e identificadores, el autómata tiene tres estados: `q0` (inicio), `q1` (se leyó la primera letra) y `q2` (se sigue leyendo una palabra). Un carácter que no sea letra, dígito o guion bajo cierra la palabra y obliga a clasificarla: si está en el conjunto de palabras reservadas se emite `PALABRA RESERVADA`; si no, `IDENTIFICADOR`. Para la flecha `->` hay un autómata de dos pasos: `q0` con `-` pasa a `q3`, y `q3` con `>` pasa a `q4` (aceptación); cualquier otra combinación es error léxico. Los símbolos `[`, `]` y `,` son autómatas triviales de un paso.

Lo importante desde la algoritmia es que el autómata es determinista y de memoria finita: en cada posición del texto hay un único estado siguiente posible, y el número de estados no depende de la longitud de la entrada. Eso hace que la fase léxica sea lineal en el tamaño del programa, que es la propiedad que se espera de un tokenizador.

### 3.4 El parser por descenso recursivo

La fase sintáctica implementa un parser por descenso recursivo en `AnalisisSintactico.construir_circuito()` (`AnalisisSintactico.py:92`). El algoritmo sigue la gramática de forma directa:

```
<circuito>    ::= <entrada> <instruccion>+
<entrada>     ::= "ENTRADA" "[" <id> ("," <id>)* "]"
<instruccion> ::= <compuerta> "[" <id> ("," <id>)* "]" "->" <id>
<compuerta>   ::= "AND" | "OR" | "NOT" | "XOR" | "NAND" | "NOR" | "XNOR"
```

El método `consumir(tipo)` (`AnalisisSintactico.py:55`) es la operación básica: verifica que el token actual sea del tipo esperado, avanza el cursor y devuelve el token; si no coincide, lanza un `SyntaxError` con la línea exacta. La función auxiliar `_consumir_lista_identificadores()` (`AnalisisSintactico.py:66`) reconoce el patrón `[ id , id , ... ]` y devuelve la lista. Con esas dos piezas, `construir_circuito()` exige primero una palabra reservada `ENTRADA`, luego su lista de identificadores, y después repite instrucciones hasta agotar los tokens.

El resultado del parser no es un árbol abstracto genérico: es un modelo útil para las fases siguientes, con la forma `{"entradas": [...], "linea_entrada": N, "compuertas": [{"compuerta", "entradas", "salida", "linea"}, ...]}`. Esa decisión algorítmica evita que el analizador semántico tenga que volver a interpretar tokens.

### 3.5 Detección de ciclos con búsqueda en profundidad

Un circuito lógico no puede tener dependencias circulares: si la señal `x` depende de `y` y `y` depende de `x`, no hay forma de evaluarlo. El analizador semántico detecta esa situación con una búsqueda en profundidad (DFS) sobre el grafo de dependencias en `AnalizadorSemantico._detectar_ciclo()` (`semantico.py:97`). El algoritmo colorea cada nodo con tres estados: blanco (no visitado), gris (en la pila de recursión) y negro (terminado). Si durante la visita se encuentra un vecino gris, se encontró un ciclo y se reporta la señal y la línea implicadas.

La implementación construye primero un mapa de `salida -> índice de compuerta` y una lista de sucesores. Luego recorre todos los nodos y, para cada uno no visitado, llama a `visitar()`. El uso de los tres colores es la forma estándar de distinguir un ciclo real de una simple convergencia de caminos: dos compuertas pueden depender de la misma señal sin que eso sea un ciclo. El circuito `pruebas/05_ciclo.jace` activa exactamente este algoritmo y produce `Error semántico línea 2: ciclo detectado en la señal y`.

### 3.6 Orden topológico con el algoritmo de Kahn

Para evaluar el circuito hay que respetar las dependencias: una compuerta solo puede evaluarse cuando sus entradas ya tienen valor. `AnalizadorSemantico.orden_topologico()` (`semantico.py:147`) resuelve ese problema con el algoritmo de Kahn. Construye el grafo de sucesores y el grado de entrada de cada compuerta; luego encola todas las compuertas con grado cero (las que solo dependen de entradas), las extrae en orden y, por cada una, decrementa el grado de sus consumidoras. Cuando una consumidora llega a cero, se encola. El resultado es una secuencia en la que ninguna compuerta aparece antes que sus dependencias.

La implementación usa una cola simple (`cola.pop(0)`) y recorre los nodos por índice, lo que produce un orden estable: ante varias compuertas listas al mismo tiempo, se elige la que aparece primero en el programa. Esa estabilidad es útil para que la salida de la consola y la de la web coincidan y para que las pruebas puedan comparar resultados sin ambigüedad. Si el grafo tuviera un ciclo, Kahn no podría procesar todos los nodos; por eso la detección de ciclos se hace antes, en `revisar()`.

### 3.7 Tabla de verdad: el producto cartesiano 2^n

La tabla de verdad se calcula en `AnalizadorSemantico.tabla_verdad()` (`semantico.py:208`). El algoritmo es directo: para `n` entradas, genera todas las combinaciones con `itertools.product([0, 1], repeat=n)`, y para cada combinación evalúa el circuito con `_evaluar()` (`semantico.py:198`). `_evaluar()` recorre el orden topológico y aplica la operación de cada compuerta con `_aplicar_operacion()` (`semantico.py:180`). Las columnas de la tabla son las entradas primero y luego las salidas de las compuertas en el orden en que se definieron, de modo que la tabla muestra también las señales intermedias.

El costo es inevitablemente exponencial: `2^n` filas para `n` entradas. Esa es una propiedad del problema, no un defecto de la implementación. El circuito grande de prueba `pruebas/diagrama_38.jace` tiene 9 entradas y produce 512 filas, lo que sirve para medir el rendimiento de la interfaz. Una observación de diseño: `_evaluar()` vuelve a llamar a `orden_topologico()` en cada fila, así que el orden se recalcula `2^n` veces; para circuitos pequeños es irrelevante, pero es un punto identificable si se quisiera optimizar.

### 3.8 Expansión de expresiones con memoización y precedencia

La generación de expresiones booleanas es el algoritmo más elaborado del proyecto. `expresiones.generar_expresiones()` (`expresiones.py:55`) produce, para cada salida final, dos formas: la **intermedia**, una línea por compuerta en orden topológico (`x1 = a · b`), y la **expandida**, una sola expresión con solo las entradas del circuito (`¬((a · b) + c)`). La forma intermedia se calcula en `_Contexto._calcular_lineas()` (`expresiones.py:127`) reutilizando `modelo.orden_topologico()` para no duplicar el algoritmo de Kahn. La forma expandida se calcula con `_expandir()` (`expresiones.py:179`), que es recursiva y memoiza el texto de cada señal en `self._expandida` para no expandir dos veces la misma rama.

El algoritmo de expansión también decide los paréntesis con una regla de precedencia: `NOT` (4) > `AND` (3) > `XOR` (2) > `OR` (1), definida en `COMPERTAS` (`expresiones.py:29`). En `_operandos()` (`expresiones.py:202`) se parentetiza un operando compuesto cuando su precedencia es menor o igual a 2, o cuando es menor que la del padre. Esa regla produce expresiones correctas con el mínimo de paréntesis necesario. Además, si la expresión expandida supera los 2000 caracteres (`LIMITE_EXPANDIDA`, `expresiones.py:20`), se omite y se devuelve un aviso; la forma intermedia nunca se recorta. Esa decisión algorítmica evita que un circuito grande genere una cadena inmanejable para la interfaz.

### 3.9 Evidencia del pilar de algoritmia

| Algoritmo | Dónde está | Qué resuelve |
|---|---|---|
| Control por fases | `gestor_reglas.py:75` | Orden de ejecución y corte en la primera fase que falla |
| AFD del lexer | `ImplementacionAnalisisLexico.py:36`; `docs/automatas.md` | Reconocimiento lineal de tokens |
| Descenso recursivo | `AnalisisSintactico.py:92` | Validación de la gramática y construcción del modelo |
| DFS con colores | `semantico.py:97` | Detección de ciclos |
| Kahn | `semantico.py:147` | Orden de evaluación sin violar dependencias |
| Producto cartesiano | `semantico.py:208` | Tabla de verdad completa |
| Expansión memoizada | `expresiones.py:179` | Expresión booleana con paréntesis mínimos |

En conjunto, este pilar se puede demostrar ejecutando un circuito válido y observando cómo el sistema produce, en orden, los tokens, el orden topológico, la tabla de verdad y la expresión. También se demuestra con los circuitos inválidos: cada uno activa un algoritmo distinto y reporta un error distinto.

---

## 4. Pilar 2 — Identificación de patrones

### 4.1 Qué significa en este proyecto

Identificar patrones es reconocer que varias situaciones distintas comparten una misma estructura y aprovechar esa regularidad. En un compilador los patrones son especialmente importantes porque el lenguaje mismo es un patrón: las instrucciones no son arbitrarias, siguen una forma repetida. JACE explota esa idea en dos niveles. En el nivel del lenguaje, reconoce el patrón de instrucción y el patrón de token. En el nivel del código, reconoce patrones de implementación que se repiten y los convierte en funciones, tablas o archivos de configuración reutilizables.

La consecuencia de no identificar patrones sería un sistema con decenas de casos especiales: una función distinta para cada compuerta, un `if` distinto para cada comando, un mensaje de error distinto en cada fase. JACE evita eso con cinco patrones claros que se describen a continuación.

### 4.2 Patrón de token

Todos los elementos del lenguaje se representan con la misma estructura: un `Token` con tipo, valor, línea y columna (`Token.py:3`). No importa si el token es una palabra reservada, un identificador, una flecha, un corchete o una coma: todos tienen la misma forma y el mismo método `to_json()` (`Token.py:11`). Ese patrón uniforme es lo que permite que el parser, los mensajes de error y la interfaz web trabajen con cualquier token sin conocer su origen.

La regularidad se ve también en la forma de construir los tokens: cada símbolo de un carácter se reconoce en un bloque casi idéntico (`ImplementacionAnalisisLexico.py:64-86`), y la flecha se reconoce con el mismo patrón de dos caracteres. La diferencia entre `PALABRA RESERVADA` e `IDENTIFICADOR` no es un caso especial del lexer: es la clasificación final de un mismo autómata de palabras.

### 4.3 Patrón de instrucción

Todas las compuertas comparten la misma forma sintáctica: `COMPUERTA[lista] -> señal`. El parser no tiene una función por compuerta; tiene una sola función `construir_circuito()` (`AnalisisSintactico.py:92`) que reconoce el patrón y consulta el conjunto de nombres válidos. Ese conjunto se carga de `reglas.json` (`AnalisisSintactico.py:27-38`), así que agregar una compuerta nueva no obliga a escribir un nuevo caso en el parser.

El patrón también se refleja en la estructura que produce el parser: todas las compuertas se guardan como diccionarios con las mismas cuatro claves (`compuerta`, `entradas`, `salida`, `linea`). Esa uniformidad es la que permite que el analizador semántico, el generador de expresiones y el dibujante recorran la lista de compuertas con el mismo bucle.

### 4.4 Patrón de error unificado

Los errores de las tres fases siguen el mismo formato: `Error {léxico|sintáctico|semántico} línea N: mensaje`. El lexer produce `Error léxico línea N: carácter no reconocido '...'` (`ImplementacionAnalisisLexico.py:60`); el parser produce `Error sintáctico línea N: ...` (`AnalisisSintactico.py:46`); el analizador semántico produce `Error semántico línea N: ...` (`semantico.py:54`). Esa regularidad no es cosmética: permite que la interfaz web muestre los errores en una sola lista, que la consola los imprima con el mismo formato y que las pruebas puedan verificar el mensaje sin depender de la fase.

El patrón incluye la línea porque el token guarda su posición desde la fase léxica. Esa decisión conecta los dos pilares: el patrón de token (posición) hace posible el patrón de error (ubicación).

### 4.5 Patrón de configuración externalizada

El patrón más importante del proyecto es el de **reglas en datos, no en código**. `reglas.json` declara cada compuerta con `nombre`, `entradas_min`, `entradas_max`, `operacion` y `descripcion`; además declara las palabras reservadas y los comandos del menú. Tres módulos consumen ese mismo archivo: el lexer lo usa para clasificar palabras (`ImplementacionAnalisisLexico.py:14`), el parser para validar nombres de compuerta (`AnalisisSintactico.py:27`) y el semántico para conocer aridad y operación (`semantico.py:29-36`).

Ese patrón tiene una consecuencia verificable: si se cambia la aridad de una compuerta en `reglas.json`, el cambio se refleja en las tres fases sin tocar el código. La descripción de cada compuerta también se reutiliza en la ayuda. El patrón evita la duplicación de la definición del lenguaje, que es la fuente más común de inconsistencias en un compilador.

### 4.6 Patrón de despacho por tabla

Los comandos del menú (`ANALIZAR`, `HISTORIAL`, `EXPORTAR`, `EXPRESIONES`, `AYUDA`, `CERRAR`) no se atienden con una cadena de `if/elif` gigante. `GestorReglas.ejecutar()` (`gestor_reglas.py:254`) busca el comando en `reglas.json`, lee su `tipo` y despacha a un método específico: `_ejecutar_analizar()`, `_ejecutar_mostrar()`, `_ejecutar_exportar()`, `_ejecutar_expresiones()`, `_ejecutar_ayuda()` o `_ejecutar_salir()`. Es el patrón de **tabla de despacho**: la asociación entre palabra y acción está en los datos, y el código solo interpreta el tipo.

La ventaja es que agregar un comando nuevo se reduce a añadirlo a `reglas.json` y a implementar su método. La desventaja controlada es que el tipo debe existir en el `if/elif` de `ejecutar()`; el proyecto lo resuelve lanzando un error claro si el tipo es desconocido (`gestor_reglas.py:275`).

### 4.7 Patrón estructural: el circuito como grafo dirigido acíclico

Un circuito lógico es, por naturaleza, un grafo dirigido acíclico (DAG): las entradas son nodos sin predecesores, cada compuerta es un nodo con aristas desde sus entradas y las salidas finales son nodos sin sucesores. JACE reconoce ese patrón en varios lugares y lo reutiliza. La detección de ciclos lo recorre con DFS (`semantico.py:97`); el orden topológico lo recorre con Kahn (`semantico.py:147`); el generador de expresiones identifica las salidas finales como las señales que no son usadas por ninguna compuerta (`expresiones.py:105-110`); el dibujante calcula niveles de profundidad con `_niveles()` (`schematico.py:246`) y ordena las compuertas por baricentro (`schematico.py:297`).

El patrón de "salida final" aparece en tres módulos con la misma definición: una señal es final si no aparece como entrada de otra compuerta. Esa regularidad es la que permite que la tabla de verdad, la expresión y el diagrama coincidan en qué señales son las salidas del circuito.

### 4.8 Patrón de reutilización núcleo-interfaz

La consola y la web no reimplementan el compilador. Ambas llaman a `GestorReglas.analizar()`. La consola lo hace desde `main.py`; la web desde `SERVIRCOR.analizar_circuito()` (`SERVIRCOR.py:119`). La diferencia está solo en los parámetros: la web usa `imprimir=False` y `escribir_archivos=False` para no llenar la consola ni el disco, y `con_diagrama=False` en la ruta de validación rápida. Ese patrón —un núcleo con opciones y varias interfaces delgadas— es el que garantiza que el resultado sea idéntico en ambos modos.

La web incluso reutiliza el mismo almacenamiento en memoria: `ALMACENAMIENTO = Almacenamiento()` (`SERVIRCOR.py:62`) es el mismo tipo que usa la consola, así que la vista de historial y el comando `HISTORIAL` muestran los mismos análisis mientras la aplicación está abierta.

### 4.9 Evidencia del pilar de identificación de patrones

| Patrón | Evidencia | Reutilización |
|---|---|---|
| Token uniforme | `Token.py:3`; `to_json()` en `Token.py:11` | Parser, errores, web |
| Instrucción `COMPUERTA[...] -> señal` | `AnalisisSintactico.py:92` | Todas las compuertas |
| Error `Error ... línea N: ...` | Lexer, parser y semántico | Consola y web |
| Reglas en `reglas.json` | `reglas.json`; tres consumidores | Lexer, parser, semántico |
| Tabla de despacho | `gestor_reglas.py:254` | Comandos del menú |
| DAG y salidas finales | `semantico.py:97`, `:147`; `expresiones.py:105` | Ciclos, orden, expresión, diagrama |
| Núcleo-interfaz | `main.py` y `SERVIRCOR.py:119` | Consola y web |

Este pilar se demuestra mostrando dos circuitos distintos que comparten la misma estructura y observando que el sistema los procesa con el mismo código. También se demuestra con `reglas.json`: la definición de una compuerta está en un solo lugar y las tres fases la consultan.

---

## 5. Pilar 3 — Abstracción

### 5.1 Qué significa en este proyecto

Abstraer es decidir qué detalles se ocultan y qué información se conserva para poder razonar sobre el problema. Un compilador es una cadena de abstracciones: el texto original es demasiado detallado para razonar sobre él, así que se convierte en tokens; los tokens son demasiado locales, así que se convierten en una estructura; la estructura es demasiado sintáctica, así que se convierte en un grafo de dependencias; el grafo se convierte en una tabla de verdad y en una expresión. Cada nivel conserva lo que el siguiente necesita y oculta el resto.

JACE aplica esa idea de forma explícita en cinco lugares: el token, el modelo del circuito, el archivo de reglas, el analizador semántico y la separación entre núcleo e interfaz. En cada caso, la abstracción tiene una frontera clara: una estructura de datos o una función pública que el resto del sistema puede usar sin conocer los detalles internos.

### 5.2 Del carácter al token

La primera abstracción es la más pequeña: un carácter aislado no significa nada, pero un `Token` sí. `Token` (`Token.py:3`) conserva cuatro datos —tipo, valor, línea y columna— y oculta todo lo demás. El parser no necesita saber si el token vino de una palabra o de un símbolo; solo necesita su tipo y su valor. Los mensajes de error no necesitan recalcular la posición; el token ya la trae.

Esa abstracción es la que permite que el lexer cambie su implementación sin afectar al parser. Mientras produzca objetos `Token` con los mismos campos, el resto del sistema sigue funcionando. Es una frontera de bajo nivel pero de alto impacto: toda la fase sintáctica depende de ella.

### 5.3 Del texto al modelo del circuito

La segunda abstracción es el modelo que produce el parser. El texto `AND[a, b] -> x1` se convierte en el diccionario `{"compuerta": "AND", "entradas": ["a", "b"], "salida": "x1", "linea": 2}`. Ese diccionario oculta los corchetes, las comas y la flecha, y conserva exactamente lo que el analizador semántico necesita: qué compuerta es, qué señales consume, qué señal produce y en qué línea está.

La estructura completa que devuelve `construir_circuito()` (`AnalisisSintactico.py:144`) tiene tres claves: `entradas`, `linea_entrada` y `compuertas`. Esa es la interfaz entre la fase sintáctica y la semántica. El analizador semántico nunca vuelve a mirar los tokens; trabaja sobre el modelo. Esa separación es la que permite que las pruebas del semántico construyan el modelo a mano, sin pasar por el lexer ni por el parser.

### 5.4 `reglas.json`: separar el qué del cómo

`reglas.json` es una abstracción de configuración. El código no sabe que `AND` requiere al menos dos entradas ni que su operación es `and`; lo lee del archivo. Esa separación entre el **qué** (la definición del lenguaje) y el **cómo** (la implementación del análisis) es una forma de abstracción muy potente: permite modificar el lenguaje sin modificar el motor.

El patrón se repite en las tres fases. El lexer abstrae el conjunto de palabras reservadas en `_cargar_palabras_reservadas()` (`ImplementacionAnalisisLexico.py:14`), con un conjunto por defecto si el archivo no está disponible. El parser abstrae los nombres de compuerta en `self.nombres_compuertas` (`AnalisisSintactico.py:27`). El semántico abstrae la aridad y la operación en tres diccionarios (`semantico.py:29-36`). En los tres casos, el código no contiene la definición del lenguaje: la consulta.

### 5.5 El analizador semántico como abstracción del circuito

El `AnalizadorSemantico` (`semantico.py:22`) abstrae el circuito como un grafo de dependencias. Para validar aridad no necesita el orden de las instrucciones; para detectar ciclos construye un mapa de sucesores; para el orden topológico construye grados de entrada; para la tabla de verdad aplica operaciones. Cada método trabaja con una representación distinta del mismo circuito, pero todas se derivan de las mismas dos listas: entradas y compuertas.

Esa abstracción es la que permite que el mismo objeto responda preguntas muy distintas —¿es válido?, ¿en qué orden se evalúa?, ¿qué tabla produce?, ¿qué expresión representa?— sin duplicar la lógica de recorrido. La clave es que el grafo se construye una vez a partir del modelo y luego se reutiliza.

### 5.6 Núcleo e interfaz: la misma lógica detrás de dos caras

La abstracción más visible para el usuario es la separación entre el núcleo y las interfaces. El núcleo es `GestorReglas` y sus módulos; las interfaces son `main.py` (consola) y `SERVIRCOR.py` (web). La consola no sabe cómo se tokeniza; la web no sabe cómo se detecta un ciclo. Ambas envían texto y reciben un diccionario de resultado.

Esa frontera se puede ver en la firma de `analizar()` (`gestor_reglas.py:75`): recibe el texto y opciones como `imprimir`, `fondo`, `escribir_archivos`, `con_diagrama` y `registrar`. Las opciones son la forma de adaptar el núcleo a cada interfaz sin duplicarlo. La web usa `imprimir=False` porque no tiene consola y `escribir_archivos=False` porque devuelve el SVG en memoria; la consola usa los valores por defecto. El resultado es el mismo diccionario con las mismas claves (`exito`, `errores`, `tokens`, `entradas`, `compuertas`, `orden_topologico`, `tabla_verdad`, `expresiones`, `expresiones_booleanas`, `diagrama_dot`, `diagrama_svg`).

La web añade una capa de abstracción más: `quitar_comentarios()` (`SERVIRCOR.py:75`) neutraliza las líneas que empiezan con `#` antes de analizar, porque el lexer no reconoce ese carácter y los comentarios son una convención de la consola. Esa función conserva las líneas vacías para que los números de línea de los errores sigan coincidiendo con el editor. Es un buen ejemplo de abstracción de entrada: la interfaz adapta el texto al contrato del núcleo.

### 5.7 Qué se oculta y qué se expone

Cada módulo decide qué hace público y qué deja privado. El lexer expone `tokenizar_circuito()` y `tokenizar_linea()`, pero oculta los detalles del autómata. El parser expone `construir_circuito()` y oculta `consumir()` y `_consumir_lista_identificadores()`, que son auxiliares. El semántico expone `revisar()`, `orden_topologico()`, `tabla_verdad()` y `expresiones_booleanas()`, y oculta `_detectar_ciclo()`, `_evaluar()` y `_aplicar_operacion()`. `expresiones.py` expone `generar_expresiones()` y oculta toda la clase `_Contexto`. La convención del guion bajo inicial es la señal de que algo es interno.

Esa disciplina de interfaces es una forma de abstracción: el lector de un módulo solo necesita conocer las funciones públicas. Las pruebas también se benefician, porque pueden probar la interfaz pública sin depender de los detalles internos.

### 5.8 Evidencia del pilar de abstracción

| Abstracción | Qué oculta | Qué conserva | Evidencia |
|---|---|---|---|
| `Token` | El origen y la forma del texto | Tipo, valor, línea, columna | `Token.py:3` |
| Modelo del circuito | Corchetes, comas y flecha | Compuerta, entradas, salida, línea | `AnalisisSintactico.py:144` |
| `reglas.json` | La implementación de cada compuerta | Aridad y operación | `reglas.json` |
| `AnalizadorSemantico` | El recorrido del grafo | Validez, orden, tabla, expresión | `semantico.py:22` |
| Núcleo-interfaz | La implementación del compilador | Un diccionario de resultado | `gestor_reglas.py:75` |

Este pilar se demuestra mostrando que el mismo circuito produce el mismo resultado en la consola y en la web, y que el modelo del circuito se puede construir y analizar sin pasar por el texto.

---

## 6. Pilar 4 — Descomposición en pequeños procesos

### 6.1 Qué significa en este proyecto

Descomponer es dividir un problema grande en partes más pequeñas que se puedan entender, implementar y probar por separado. JACE es un proyecto de casi 6000 líneas repartidas en módulos, pruebas, archivos de datos y una interfaz web. Sin descomposición sería imposible de mantener. La descomposición del proyecto se puede ver en cuatro dimensiones: por fases, por módulos, por funciones y por pruebas.

La descomposición no es solo organizativa: también es algorítmica. Cada fase recibe una entrada, produce una salida y puede probarse de forma aislada. Esa propiedad es la que hace que el proyecto tenga 128 funciones de prueba y que cada una pueda verificar una pieza concreta sin levantar todo el sistema.

### 6.2 Descomposición por fases

La primera división es la más natural para un compilador: léxico, sintáctico, semántico y evaluación. Cada fase tiene su propio módulo y su propia responsabilidad. El lexer no valida gramática; el parser no valida semántica; el semántico no genera diagramas. Esa separación se ve en el flujo de `analizar()`: cada fase se ejecuta en un bloque distinto y solo avanza si la anterior no produjo errores.

La ventaja de esta descomposición es que los errores se localizan con precisión. Si el problema es un carácter inválido, se reporta como léxico; si es una instrucción mal formada, como sintáctico; si es una señal no definida o un ciclo, como semántico. El usuario recibe un mensaje que le dice en qué nivel está el problema.

### 6.3 Descomposición por módulos

El proyecto separa cada responsabilidad en un archivo propio. La siguiente tabla resume esa división.

| Módulo | Responsabilidad | Interfaz principal |
|---|---|---|
| `Token.py` | Representar una unidad léxica | `Token` |
| `ImplementacionAnalisisLexico.py` | Convertir texto en tokens | `tokenizar_circuito()` |
| `AnalisisSintactico.py` | Validar gramática y construir el modelo | `construir_circuito()` |
| `semantico.py` | Validar significado, ordenar, evaluar y generar DOT | `AnalizadorSemantico` |
| `expresiones.py` | Generar expresiones intermedias y expandidas | `generar_expresiones()` |
| `schematico.py` | Dibujar el diagrama esquemático | `generar_diagrama()`, `exportar()` |
| `almacenamiento.py` | Guardar historial y exportar reporte | `Almacenamiento` |
| `gestor_reglas.py` | Cargar reglas y orquestar el análisis | `GestorReglas` |
| `main.py` | Interfaz de consola | `main()` |
| `SERVIRCOR.py` | API y servicio de la interfaz web | `app`, rutas FastAPI |
| `jace_app.py` | Aplicación de escritorio que levanta la web | `main()` |

Esta división no es arbitraria: sigue el principio de responsabilidad única. El módulo de expresiones no sabe dibujar; el de dibujo no sabe evaluar; el de almacenamiento no sabe analizar. Cada uno depende solo de lo que necesita.

Existe además `diagrama.py`, una variante antigua de dibujo en SVG que no forma parte del flujo actual: ningún módulo la importa y no está versionada en el repositorio. El dibujo vigente es `schematico.py`. Se menciona aquí para que la lectura del proyecto no confunda ese archivo heredado con un componente activo.

### 6.4 Descomposición por funciones pequeñas

Dentro de cada módulo, las funciones también están descompuestas. El lexer tiene funciones auxiliares para cargar palabras reservadas (`_cargar_palabras_reservadas`), para decidir si un carácter inicia un identificador (`_es_inicio_identificador`) y para decidir si lo continúa (`_es_parte_identificador`). El parser tiene `consumir()` y `_consumir_lista_identificadores()`. El semántico tiene `_detectar_ciclo()`, `orden_topologico()`, `_aplicar_operacion()`, `_evaluar()` y `tabla_verdad()`. El dibujante tiene `_niveles()`, `_producida_por()`, `_baricentro()`, `_carril()`, `_ordenar_y_colocar()` y `_cruza()`. La generación de expresiones tiene `_calcular_lineas()`, `_linea_de()`, `lineas_de()`, `_predecesoras()`, `expandida_de()`, `_expandir()` y `_operandos()`.

Esa granularidad tiene dos efectos. Primero, cada función se puede probar por separado. Segundo, el código se puede leer como una narración: `_expandir()` dice qué hace la expansión, `_operandos()` dice cómo se unen los operandos, `_predecesoras()` dice qué señales necesita una salida. Los nombres son específicos y no genéricos.

### 6.5 Descomposición de los datos

La descomposición también alcanza a las estructuras de datos. El resultado de un análisis es un diccionario con claves independientes: `exito`, `errores`, `tokens`, `entradas`, `compuertas`, `orden_topologico`, `tabla_verdad`, `expresiones`, `expresiones_booleanas`, `diagrama_dot` y `diagrama_svg`. Cada consumidor toma solo lo que necesita: la consola imprime varias secciones, la web devuelve el JSON completo, el historial guarda la entrada, el resultado y los errores, y el reporte `.txt` incluye las expresiones.

`reglas.json` también está descompuesto por tipo de información: `compuertas`, `palabras_reservadas` y `comandos`. Cada sección la consume un módulo distinto. Esa separación evita que un cambio en los comandos afecte la definición de las compuertas.

### 6.6 Las pruebas como verificación de la descomposición

La descomposición se comprueba con las pruebas. El proyecto tiene 128 funciones de prueba repartidas en ocho archivos: `test_token.py` (4), `test_lexico.py` (9), `test_sintactico.py` (7), `test_semantico.py` (11), `test_expresiones.py` (26), `test_gestor_reglas.py` (22), `test_almacenamiento.py` (11) y `test_interfaz.py` (38). Cada archivo prueba un módulo o una responsabilidad concreta.

Esa correspondencia entre módulo y archivo de pruebas es la mejor evidencia de que la descomposición funciona. Si el lexer estuviera mezclado con el parser, no se podría probar el reconocimiento de tokens sin construir un circuito completo. Si el semántico estuviera mezclado con el dibujo, no se podría probar la detección de ciclos sin generar un SVG. La separación permite probar cada pieza con la entrada mínima que necesita.

### 6.7 Evidencia del pilar de descomposición

| Nivel de descomposición | Evidencia | Beneficio |
|---|---|---|
| Por fases | `gestor_reglas.py:75` | Errores localizados por nivel |
| Por módulos | 11 módulos con responsabilidad única | Mantenibilidad y bajo acoplamiento |
| Por funciones | Funciones auxiliares con nombre específico | Legibilidad y pruebas unitarias |
| Por datos | Diccionario de resultado; `reglas.json` seccionado | Consumidores independientes |
| Por pruebas | 128 pruebas en 8 archivos | Verificación aislada de cada pieza |

Este pilar se demuestra ejecutando `python -m pytest tests/` y observando que cada módulo tiene sus propias pruebas. También se demuestra provocando un error: el mensaje indica la fase y la línea, lo que confirma que la responsabilidad está separada.

---

## 7. Los cuatro pilares trabajando juntos: traza completa

Los pilares no son compartimentos aislados. En JACE se aplican al mismo tiempo y se refuerzan entre sí. Para mostrarlo, se sigue el circuito de `pruebas/01_circuito_valido.jace` a través de todo el sistema.

### 7.1 Entrada

```
ENTRADA[a, b, c]
AND[a, b] -> x1
OR[x1, c] -> x2
NOT[x2] -> salida
```

### 7.2 Fase léxica: patrón de token y AFD

El lexer recorre el texto carácter a carácter. La palabra `ENTRADA` se reconoce con el autómata de palabras y se clasifica como `PALABRA RESERVADA`. Los corchetes y las comas se reconocen con sus autómatas de un paso. La flecha `->` se reconoce con el autómata de dos pasos. Los identificadores `a`, `b`, `c`, `x1`, `x2` y `salida` se reconocen como `IDENTIFICADOR`. Cada token conserva su línea y columna.

Aquí se ven dos pilares: la **algoritmia** del AFD y la **identificación de patrones** del token uniforme. También se ve la **abstracción**, porque el texto original se convierte en una lista de objetos con solo cuatro campos.

### 7.3 Fase sintáctica: patrón de instrucción y descenso recursivo

El parser consume el primer token `ENTRADA`, luego la lista `[a, b, c]` y después las tres instrucciones. Para cada instrucción verifica que la palabra sea una compuerta válida, que la lista de entradas esté bien formada y que después de la flecha venga un identificador. El resultado es el modelo:

```json
{
  "entradas": ["a", "b", "c"],
  "linea_entrada": 1,
  "compuertas": [
    {"compuerta": "AND", "entradas": ["a", "b"], "salida": "x1", "linea": 2},
    {"compuerta": "OR", "entradas": ["x1", "c"], "salida": "x2", "linea": 3},
    {"compuerta": "NOT", "entradas": ["x2"], "salida": "salida", "linea": 4}
  ]
}
```

Aquí se ven la **algoritmia** del descenso recursivo, la **identificación de patrones** de la instrucción y la **abstracción** del modelo del circuito.

### 7.4 Fase semántica: validación y orden

El analizador semántico revisa cuatro cosas. Primero, la aridad: `AND` tiene dos entradas, `OR` tiene dos, `NOT` tiene una; todo correcto. Segundo, las señales definidas: `a`, `b`, `c` son entradas; `x1`, `x2`, `salida` son salidas de compuertas; no hay redefiniciones. Tercero, las señales usadas: `a`, `b`, `c`, `x1` y `x2` están definidas. Cuarto, los ciclos: el grafo es acíclico. El orden topológico que produce Kahn es `x1`, `x2`, `salida`.

Aquí se ven la **algoritmia** del DFS y de Kahn, y la **identificación de patrones** del DAG y de las salidas finales.

### 7.5 Evaluación: tabla de verdad y expresión

La tabla de verdad tiene ocho filas porque hay tres entradas. Para cada combinación se evalúa en orden topológico: primero `x1 = a AND b`, luego `x2 = x1 OR c`, luego `salida = NOT x2`. El resultado es:

| a | b | c | x1 | x2 | salida |
|---|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0 | 1 |
| 0 | 0 | 1 | 0 | 1 | 0 |
| 0 | 1 | 0 | 0 | 0 | 1 |
| 0 | 1 | 1 | 0 | 1 | 0 |
| 1 | 0 | 0 | 0 | 0 | 1 |
| 1 | 0 | 1 | 0 | 1 | 0 |
| 1 | 1 | 0 | 1 | 1 | 0 |
| 1 | 1 | 1 | 1 | 1 | 0 |

La expresión intermedia es:

```
x1 = a · b
x2 = x1 + c
salida = ¬(x2)
```

La expresión expandida es:

```
salida = ¬((a · b) + c)
```

Aquí se ven la **algoritmia** del producto cartesiano y de la expansión memoizada, la **identificación de patrones** de las salidas finales y la **abstracción** de la expresión como texto independiente del circuito.

### 7.6 Diagrama: del grafo a la imagen

El dibujante calcula los niveles de profundidad: las entradas están en el nivel 0, `x1` en el nivel 1, `x2` en el nivel 2 y `salida` en el nivel 3. Ordena las compuertas por baricentro, reserva canales para los cables y dibuja los símbolos de cada compuerta con SchemDraw. El resultado se exporta como SVG y PNG, o se devuelve en memoria para la web.

Aquí se ven la **algoritmia** del layout por niveles, la **identificación de patrones** de la estructura del grafo y la **abstracción** del diagrama como una representación visual del modelo.

### 7.7 Síntesis de la traza

La misma entrada pasó por seis representaciones distintas: texto, tokens, modelo, grafo, tabla/expresión y diagrama. Cada representación fue construida por un algoritmo, reconoció un patrón, ocultó detalles y fue implementada en un proceso separado. Esa es la forma en que los cuatro pilares se articulan en JACE.

---

## 8. Matriz de trazabilidad

La siguiente matriz resume, para cada pilar, la evidencia principal, el artefacto que se puede mostrar y la prueba automatizada que lo respalda.

| Pilar | Evidencia en código | Artefacto demostrable | Prueba |
|---|---|---|---|
| Algoritmia | `gestor_reglas.py:75`; `ImplementacionAnalisisLexico.py:36`; `AnalisisSintactico.py:92`; `semantico.py:97`, `:147`, `:208`; `expresiones.py:179` | Tokens, orden topológico, tabla de verdad, expresión | `tests/test_lexico.py`, `tests/test_sintactico.py`, `tests/test_semantico.py`, `tests/test_expresiones.py` |
| Identificación de patrones | `Token.py:3`; `AnalisisSintactico.py:92`; `reglas.json`; `gestor_reglas.py:254` | Misma estructura en circuitos distintos; reglas en un solo archivo | `tests/test_gestor_reglas.py`, `tests/test_token.py` |
| Abstracción | `Token.py:3`; `AnalisisSintactico.py:144`; `semantico.py:22`; `gestor_reglas.py:75`; `SERVIRCOR.py:75` | Mismo resultado en consola y web; modelo independiente del texto | `tests/test_interfaz.py`, `tests/test_gestor_reglas.py` |
| Descomposición | 11 módulos; funciones auxiliares; 128 pruebas | `pytest`; error localizado por fase | `tests/test_almacenamiento.py`, `tests/test_interfaz.py`, `tests/test_expresiones.py` |

---

## 9. Conclusiones

JACE permite mostrar los cuatro pilares del pensamiento computacional con evidencia concreta y no con definiciones abstractas. La **algoritmia** aparece en el control por fases y en los algoritmos específicos que resuelven cada subproblema: autómatas, descenso recursivo, DFS, Kahn, producto cartesiano y expansión memoizada. La **identificación de patrones** aparece en la uniformidad del token, de la instrucción, del mensaje de error, de la configuración externalizada, del despacho por tabla y del grafo dirigido acíclico. La **abstracción** aparece en la cadena de representaciones que va del carácter al token, del token al modelo, del modelo al grafo y del grafo a la tabla, la expresión y el diagrama. La **descomposición** aparece en la separación por fases, por módulos, por funciones, por datos y por pruebas.

Lo más valioso del proyecto no es que use estructuras de datos o algoritmos conocidos, sino que esas decisiones están conectadas. El patrón de token hace posible el patrón de error; la abstracción del modelo hace posible la descomposición del análisis semántico; la descomposición por fases hace posible la identificación de patrones en los mensajes; la algoritmia del orden topológico hace posible la tabla de verdad y la expresión. Cada pilar refuerza a los demás, y esa articulación es la que convierte a JACE en un ejemplo defendible de pensamiento computacional aplicado.

---

## 10. Anexos

### 10.1 Glosario

- **Token:** unidad léxica con tipo, valor, línea y columna.
- **AFD:** autómata finito determinista; modelo del lexer.
- **Descenso recursivo:** técnica de análisis sintáctico que sigue la gramática con funciones recursivas.
- **DAG:** grafo dirigido acíclico; modelo de un circuito lógico.
- **Orden topológico:** secuencia de nodos en la que cada uno aparece después de sus dependencias.
- **DFS:** búsqueda en profundidad; se usa para detectar ciclos.
- **Kahn:** algoritmo de orden topológico basado en grados de entrada.
- **Memoización:** guardar resultados ya calculados para no repetir trabajo.
- **Salida final:** señal que no es usada como entrada por ninguna otra compuerta.

### 10.2 Circuitos de ejemplo

| Archivo | Qué demuestra |
|---|---|
| `pruebas/01_circuito_valido.jace` | Circuito válido básico con `AND`, `OR`, `NOT` |
| `pruebas/02_xor_nand.jace` | Dos salidas independientes y compuertas `XOR`, `NAND` |
| `pruebas/03_senal_no_definida.jace` | Error semántico por señal no definida |
| `pruebas/04_not_dos_entradas.jace` | Error semántico por aridad incorrecta |
| `pruebas/05_ciclo.jace` | Error semántico por ciclo |
| `pruebas/06_redefinicion.jace` | Error semántico por señal definida dos veces |
| `pruebas/07_compuerta_sin_entradas.jace` | Error sintáctico por lista vacía |
| `pruebas/08_entrada_vacia.jace` | Error sintáctico por `ENTRADA[]` |
| `pruebas/09_caracter_invalido.jace` | Error léxico por carácter fuera del alfabeto |
| `pruebas/diagrama_38.jace` | Circuito grande: 9 entradas, 38 compuertas, 512 filas |

### 10.3 Comandos útiles

```bash
# Modo interactivo
python main.py

# Ejecutar un archivo .jace
python main.py pruebas/01_circuito_valido.jace

# Ejecutar las pruebas
python -m pytest tests/

# Levantar la interfaz web
python jace_app.py
```

### 10.4 Estructura de archivos relevante

```
Proyecto-Formales-/
├── Token.py
├── ImplementacionAnalisisLexico.py
├── AnalisisSintactico.py
├── semantico.py
├── expresiones.py
├── schematico.py
├── almacenamiento.py
├── gestor_reglas.py
├── reglas.json
├── main.py
├── SERVIRCOR.py
├── jace_app.py
├── docs/
│   ├── automatas.md
│   └── pensamiento_computacional.md
├── pruebas/
└── tests/
```
