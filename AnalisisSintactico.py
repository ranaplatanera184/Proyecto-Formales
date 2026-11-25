# ============================================================================
# FASE SINTACTICA DEL COMPILADOR DE CIRCUITOS
# ----------------------------------------------------------------------------
# Recibe la lista de tokens producida por la fase lexica y comprueba que se
# ajuste a la gramatica del lenguaje:
#
#   <circuito>     ::= <entrada> [<salidas>] <instruccion>+
#   <entrada>      ::= ENTRADA "[" <lista_id> "]"
#   <salidas>      ::= SALIDA  "[" <lista_id> "]"
#   <lista_id>     ::= ID ("," ID)*
#   <instruccion>  ::= <compuerta> "->" ID
#   <compuerta>    ::= NOMBRE_COMPUERTA "[" <argumento> ("," <argumento>)* "]"
#   <argumento>    ::= ID | CONSTANTE | <compuerta>
#   CONSTANTE      ::= "0" | "1"
#   NOMBRE_COMPUERTA ::= AND | OR | NOT | XOR | NAND | NOR | XNOR  (reglas.json)
#
# SALIDA es opcional: sin ella, las salidas del circuito son las señales que
# no alimentan a ninguna compuerta (como antes de la fase 3). Las compuertas
# pueden anidarse: OR[AND[a, b], NOT[c]] -> y.
#
# Parser descendente recursivo con RECUPERACIÓN EN MODO PÁNICO: al encontrar
# un error lo registra y se sincroniza en el primer token de una línea
# posterior, así reporta todos los errores de una pasada (como máximo uno por
# línea y unos 50 en total). Los mensajes no usan los nombres internos de los
# tokens: dicen qué falta y dónde ("falta una coma entre 'a' y 'b'").
#
# Como resultado construye el AST tipado (ast_jace.py) y, a partir de él, la
# estructura plana desazucarada {entradas, compuertas} que usan las fases
# siguientes: cada compuerta anidada pasa a ser una señal temporal _t1, _t2...
# ============================================================================

from ast_jace import (Asignacion, Circuito, Compuerta, Constante,
                      DeclaracionEntradas, DeclaracionSalidas, Senal,
                      ast_legado, desazucarar)
from rutas import cargar_reglas
from sugerencias import mas_parecido
import diagnosticos as diag

MAXIMO_ERRORES = 50

# Niveles de compuertas anidadas que se aceptan (el parser es recursivo).
MAXIMO_ANIDAMIENTO = 100

# Cómo se nombra cada tipo de token en los mensajes.
NOMBRES_AMIGABLES = {
    "CORCHETE ABRE": "'['",
    "CORCHETE CIERRA": "']'",
    "COMA": "','",
    "FLECHA": "'->'",
    "CONSTANTE": "una constante",
    "IDENTIFICADOR": "un nombre",
    "PALABRA RESERVADA": "una palabra reservada",
}


class _ErrorSintactico(Exception):
    """Error interno del parser: lleva el diagnóstico ya construido.

    `silencioso` marca los errores provocados por un comodín ERROR del léxico:
    ese error ya se reportó en la fase léxica, así que el parser solo se
    sincroniza sin repetirlo en cadena.
    """

    def __init__(self, diagnostico, silencioso=False):
        super().__init__(diagnostico.texto())
        self.diagnostico = diagnostico
        self.silencioso = silencioso


def describir(token):
    """Cómo se nombra un token concreto en un mensaje: 'b', ']', AND..."""
    if token is None:
        return "el final del archivo"
    if token.token == "IDENTIFICADOR":
        return f"el nombre '{token.valor}'"
    if token.token == "PALABRA RESERVADA":
        return f"la palabra reservada {token.valor}"
    if token.token == "CONSTANTE":
        return f"la constante {token.valor}"
    return f"'{token.valor}'"


def fin_de(token):
    """Columna justo después de un token (donde debería ir lo que falta)."""
    return token.columna + len(str(token.valor))


class AnalisisSintactico:

    def __init__(self, tokens, gestorReglas=None, rutaReglas=None):
        # Fase sintactica: trabaja sobre la lista de tokens.
        self.tokens = tokens
        self.pos = 0
        self.diagnosticos = []
        self._lineas_con_error = set()
        self._hubo_silenciosos = False

        # Nombres de compuerta validos definidos en reglas.json.
        self.nombres_compuertas = set()
        if gestorReglas is not None:
            self.nombres_compuertas = set(gestorReglas.obtener_nombres_compuertas())
        else:
            reglas = cargar_reglas(rutaReglas)
            self.nombres_compuertas = {
                c["nombre"] for c in reglas.get("compuertas", [])
            }

    # ------------------------------------------------------------------
    # Utilidades de lectura de tokens
    # ------------------------------------------------------------------
    def actual(self):
        """Devuelve el token actual o None si se acabó la entrada."""
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def siguiente(self, desplazamiento=1):
        indice = self.pos + desplazamiento
        return self.tokens[indice] if indice < len(self.tokens) else None

    def anterior(self):
        return self.tokens[self.pos - 1] if self.pos > 0 else None

    def es(self, token, tipo):
        """El token es del tipo pedido (un comodín ERROR vale por su tipo)."""
        if token is None:
            return False
        if token.token == tipo:
            return True
        return token.token == "ERROR" and getattr(token, "sustituye", None) == tipo

    def es_nombre(self, token):
        """Un nombre de señal. SALIDA es una palabra reservada contextual:
        solo abre una declaración si va seguida de '['; en cualquier otro
        lugar se acepta como nombre (había circuitos con señales «SALIDA»)."""
        if self.es(token, "IDENTIFICADOR"):
            return True
        if token is None or token.token != "PALABRA RESERVADA" or token.valor != "SALIDA":
            return False
        if token is not self.actual():
            return True
        return not self.es(self.siguiente(), "CORCHETE ABRE")

    def es_compuerta(self, token):
        return (token is not None and token.token == "PALABRA RESERVADA"
                and token.valor in self.nombres_compuertas)

    # ------------------------------------------------------------------
    # Errores y recuperación
    # ------------------------------------------------------------------
    def _fallo(self, linea, columna, mensaje, sugerencia=None):
        return _ErrorSintactico(diag.error("sintáctico", linea, columna, mensaje, sugerencia))

    def _fallo_en(self, token, mensaje, sugerencia=None):
        """Error señalando un token; si se acabó la entrada, tras el último."""
        if token is None:
            ultimo = self.tokens[-1] if self.tokens else None
            linea = ultimo.linea if ultimo else 1
            columna = fin_de(ultimo) if ultimo else 1
            return self._fallo(linea, columna, mensaje, sugerencia)
        error = self._fallo(token.linea, token.columna, mensaje, sugerencia)
        error.silencioso = token.token == "ERROR"
        return error

    def _fallo_tras(self, token, mensaje, sugerencia=None):
        """Error justo después de un token (para lo que falta al final)."""
        return self._fallo(token.linea, fin_de(token), mensaje, sugerencia)

    def _registrar(self, error):
        """Guarda un error (uno por línea y como máximo MAXIMO_ERRORES)."""
        d = error.diagnostico
        if error.silencioso:
            self._lineas_con_error.add(d.linea)
            self._hubo_silenciosos = True
            return
        if d.linea in self._lineas_con_error:
            return
        if len(self.diagnosticos) >= MAXIMO_ERRORES:
            return
        self._lineas_con_error.add(d.linea)
        self.diagnosticos.append(d)
        if len(self.diagnosticos) == MAXIMO_ERRORES:
            self.diagnosticos.append(diag.error(
                "sintáctico", d.linea, d.columna,
                f"hay demasiados errores; se muestran los primeros {MAXIMO_ERRORES}",
                "corrige estos y vuelve a analizar"))

    def _sincronizar(self, linea_error):
        """Modo pánico: salta hasta el primer token de una línea posterior."""
        while self.actual() is not None and self.actual().linea <= linea_error:
            self.pos += 1

    # ------------------------------------------------------------------
    # Reglas de la gramática
    # ------------------------------------------------------------------
    def _lista(self, duenio, token_duenio, que, leer_elemento):
        """'[' <elemento> (',' <elemento>)* ']' → lista de (texto, nodo, token_fin).

        `duenio` es ENTRADA, SALIDA o el nombre de la compuerta (para los
        mensajes) y `que` describe lo que va dentro ("entradas", ...).
        """
        apertura = self.actual()
        if not self.es(apertura, "CORCHETE ABRE"):
            if self.es_nombre(apertura) and apertura.linea == token_duenio.linea:
                raise self._fallo_en(apertura, f"falta '[' después de {duenio}",
                                     f"escribe {duenio}[{apertura.valor}, ...]")
            raise self._fallo_tras(token_duenio,
                                   f"falta '[' después de {duenio} para abrir la lista de {que}",
                                   f"escribe {duenio}[...]")
        self.pos += 1

        if self.es(self.actual(), "CORCHETE CIERRA"):
            if duenio in ("ENTRADA", "SALIDA"):
                ejemplo = "a, b" if duenio == "ENTRADA" else "y"
                raise self._fallo_en(self.actual(),
                                     f"{duenio} necesita al menos un nombre de "
                                     f"{'entrada' if duenio == 'ENTRADA' else 'salida'} "
                                     "entre los corchetes",
                                     f"por ejemplo {duenio}[{ejemplo}]")
            raise self._fallo_en(self.actual(),
                                 f"la compuerta {duenio} necesita al menos una entrada "
                                 "entre los corchetes",
                                 f"por ejemplo {duenio}[a, b] -> x")

        elementos = []
        while True:
            elementos.append(leer_elemento(apertura, elementos))

            separador = self.actual()
            if self.es(separador, "COMA"):
                self.pos += 1
                continue
            if self.es(separador, "CORCHETE CIERRA"):
                self.pos += 1
                return elementos
            raise self._separador_invalido(separador, duenio, apertura, elementos)

    def _leer_nombre_declarado(self, duenio):
        """Elemento de ENTRADA[...] o SALIDA[...]: solo nombres."""
        def leer(apertura, elementos):
            token = self.actual()
            if self.es_nombre(token):
                self.pos += 1
                return token.valor, Senal(token.linea, token.columna, token.valor), token
            if self.es(token, "CONSTANTE"):
                raise self._fallo_en(token,
                                     f"las constantes 0 y 1 no pueden declararse en {duenio}: "
                                     "solo se usan como argumentos de una compuerta",
                                     "por ejemplo AND[a, 1] -> x")
            raise self._argumento_invalido(token, duenio, apertura, elementos)
        return leer

    def _leer_argumento(self, duenio, profundidad):
        """Elemento de una compuerta: <id> | CONSTANTE | <compuerta>."""
        def leer(apertura, elementos):
            token = self.actual()
            if self.es_nombre(token) and token.token == "IDENTIFICADOR" \
                    and self.es(self.siguiente(), "CORCHETE ABRE"):
                raise self._compuerta_desconocida(token)
            if self.es_nombre(token):
                self.pos += 1
                return token.valor, Senal(token.linea, token.columna, token.valor), token
            if self.es(token, "CONSTANTE"):
                self.pos += 1
                return (token.valor, Constante(token.linea, token.columna, int(token.valor)),
                        token)
            if self.es_compuerta(token) and self.es(self.siguiente(), "CORCHETE ABRE"):
                compuerta = self._compuerta(profundidad + 1)
                return f"{compuerta.nombre}[...]", compuerta, self.anterior()
            if self.es_compuerta(token):
                raise self._fallo_en(token,
                                     f"la palabra reservada {token.valor} no puede usarse "
                                     "como nombre de señal",
                                     f"para anidar una compuerta escribe {token.valor}[...]")
            raise self._argumento_invalido(token, duenio, apertura, elementos)
        return leer

    def _argumento_invalido(self, token, duenio, apertura, elementos):
        """Mensaje cuando se esperaba un elemento dentro de los corchetes."""
        previo = self.anterior()
        if token is None or token.linea != previo.linea:
            return self._fallo_tras(previo, f"falta ']' para cerrar la lista de {duenio}",
                                    f"la lista se abrió en la columna {apertura.columna}")
        if self.es(token, "COMA"):
            if elementos:
                return self._fallo_en(token, "sobra una coma: hay dos comas seguidas",
                                      "borra una de las comas o escribe el nombre que falta")
            return self._fallo_en(token, "falta un nombre antes de ','",
                                  "la lista no puede empezar con una coma")
        if self.es(token, "CORCHETE CIERRA"):
            return self._fallo_en(token, "sobra la coma antes de ']'",
                                  "borra la última coma o agrega el nombre que falta")
        if token.token == "PALABRA RESERVADA":
            return self._fallo_en(token,
                                  f"la palabra reservada {token.valor} no puede usarse "
                                  "como nombre de señal",
                                  f"usa otro nombre, por ejemplo '{token.valor.lower()}1'")
        if self.es(token, "FLECHA"):
            return self._fallo_en(token, f"falta ']' para cerrar la lista de {duenio}",
                                  "cierra los corchetes antes de '->'")
        return self._fallo_en(token, f"se esperaba un nombre de señal y llegó {describir(token)}")

    def _separador_invalido(self, token, duenio, apertura, elementos):
        """Mensaje cuando tras un elemento no viene ',' ni ']'."""
        ultimo_texto, _, ultimo_token = elementos[-1]
        if token is None or token.linea != ultimo_token.linea:
            return self._fallo_tras(ultimo_token,
                                    f"falta ']' para cerrar la lista de {duenio}",
                                    f"la lista se abrió en la columna {apertura.columna}")
        if self.es_nombre(token) or token.token in ("PALABRA RESERVADA", "CONSTANTE"):
            nombre = token.valor
            return self._fallo_en(token,
                                  f"falta una coma entre '{ultimo_texto}' y '{nombre}'",
                                  f"escribe {ultimo_texto}, {nombre}")
        if self.es(token, "FLECHA"):
            return self._fallo_en(token, f"falta ']' para cerrar la lista de {duenio}",
                                  "cierra los corchetes antes de '->'")
        if self.es(token, "CORCHETE ABRE"):
            return self._fallo_en(token, "sobra '[': solo una compuerta puede abrir corchetes",
                                  "para anidar escribe el nombre de la compuerta antes del '['")
        return self._fallo_en(token, f"se esperaba ',' o ']' después de '{ultimo_texto}' "
                                     f"y llegó {describir(token)}")

    def _compuerta_desconocida(self, token):
        compuertas = ", ".join(sorted(self.nombres_compuertas))
        parecida = mas_parecido(token.valor, sorted(self.nombres_compuertas),
                                ignorar_mayusculas=True)
        sugerencia = (f"¿quisiste decir {parecida}?" if parecida
                      else f"las compuertas son {compuertas}")
        return self._fallo_en(token, f"'{token.valor}' no es una compuerta conocida",
                              sugerencia)

    def _declaracion(self, palabra):
        """<entrada> ::= ENTRADA '[' <lista_id> ']'  (igual para SALIDA)."""
        token = self.actual()
        self.pos += 1
        que = "entradas" if palabra == "ENTRADA" else "salidas"
        elementos = self._lista(palabra, token, que, self._leer_nombre_declarado(palabra))
        senales = [nodo for _, nodo, _ in elementos]
        clase = DeclaracionEntradas if palabra == "ENTRADA" else DeclaracionSalidas
        return clase(token.linea, token.columna, senales)

    def _compuerta(self, profundidad=0):
        """<compuerta> ::= NOMBRE '[' <argumento> (',' <argumento>)* ']'."""
        token = self.actual()
        if profundidad > MAXIMO_ANIDAMIENTO:
            raise self._fallo_en(token,
                                 f"hay más de {MAXIMO_ANIDAMIENTO} compuertas anidadas una "
                                 "dentro de otra",
                                 "separa la expresión en varias instrucciones con señales "
                                 "intermedias")
        self.pos += 1
        elementos = self._lista(token.valor, token, "entradas de la compuerta",
                                self._leer_argumento(token.valor, profundidad))
        return Compuerta(token.linea, token.columna, token.valor,
                         [nodo for _, nodo, _ in elementos])

    def _instruccion(self, fin_anterior):
        """<instruccion> ::= <compuerta> '->' <id>."""
        token = self.actual()
        if not self.es_compuerta(token):
            raise self._inicio_invalido(token, fin_anterior)
        nombre = token.valor

        compuerta = self._compuerta()
        cierre = self.anterior()

        flecha = self.actual()
        if not self.es(flecha, "FLECHA"):
            if self.es_nombre(flecha) and flecha.linea == cierre.linea:
                raise self._fallo_en(flecha,
                                     f"falta '->' antes del nombre de la salida '{flecha.valor}'",
                                     f"escribe {nombre}[...] -> {flecha.valor}")
            if flecha is None or flecha.linea != cierre.linea:
                raise self._fallo_tras(cierre,
                                       f"falta '->' y el nombre de la salida después de {nombre}[...]",
                                       "termina la instrucción con -> salida")
            raise self._fallo_en(flecha, f"se esperaba '->' después de ']' y llegó {describir(flecha)}")
        self.pos += 1

        salida = self.actual()
        if not self.es_nombre(salida):
            if salida is None or salida.linea != flecha.linea:
                raise self._fallo_tras(flecha, "falta el nombre de la salida después de '->'",
                                       f"por ejemplo {nombre}[...] -> x")
            if salida.token == "PALABRA RESERVADA":
                raise self._fallo_en(salida,
                                     f"la palabra reservada {salida.valor} no puede usarse "
                                     "como nombre de la salida",
                                     f"usa otro nombre, por ejemplo '{salida.valor.lower()}1'")
            if salida.token == "CONSTANTE":
                raise self._fallo_en(salida,
                                     f"la salida no puede ser la constante {salida.valor}: "
                                     "las constantes solo se usan como argumentos",
                                     "escribe un nombre de señal después de '->'")
            raise self._fallo_en(salida, "se esperaba el nombre de la salida después de '->' "
                                         f"y llegó {describir(salida)}")
        self.pos += 1
        return Asignacion(token.linea, token.columna, compuerta,
                          Senal(salida.linea, salida.columna, salida.valor))

    def _inicio_invalido(self, token, fin_anterior):
        """Mensaje cuando una instrucción no empieza con una compuerta."""
        compuertas = ", ".join(sorted(self.nombres_compuertas))
        if token.token == "PALABRA RESERVADA" and token.valor == "ENTRADA":
            return self._fallo_en(token,
                                  "se esperaba una compuerta y llegó ENTRADA: solo puede "
                                  "haber una declaración ENTRADA, al inicio del circuito",
                                  "junta todas las entradas en la primera ENTRADA[...]")
        if token.token == "PALABRA RESERVADA" and token.valor == "SALIDA":
            return self._fallo_en(token,
                                  "SALIDA debe ir justo después de ENTRADA[...] y solo "
                                  "una vez",
                                  "mueve SALIDA[...] a la segunda instrucción del circuito")
        if token.token == "IDENTIFICADOR" and self.es(self.siguiente(), "CORCHETE ABRE"):
            return self._compuerta_desconocida(token)
        if fin_anterior is not None and token.linea == fin_anterior.linea:
            return self._fallo_en(token,
                                  f"sobra {describir(token)} al final de la instrucción",
                                  "cada instrucción termina con '-> salida'")
        return self._fallo_en(token,
                              f"se esperaba una compuerta al inicio de la instrucción y "
                              f"llegó {describir(token)}",
                              f"las instrucciones tienen la forma AND[a, b] -> x "
                              f"(compuertas: {compuertas})")

    # ------------------------------------------------------------------
    # Punto de entrada
    # ------------------------------------------------------------------
    def analizar(self):
        """Analiza todos los tokens: (estructura o None, diagnósticos).

        La estructura es None si hubo algún error sintáctico.
        """
        self.pos = 0
        self.diagnosticos = []
        self._lineas_con_error = set()
        self._hubo_silenciosos = False

        if not self.tokens:
            self.diagnosticos.append(diag.error(
                "sintáctico", 1, 1, "el circuito está vacío",
                "empieza con ENTRADA[a, b] y una compuerta, por ejemplo AND[a, b] -> x"))
            return None, self.diagnosticos

        entradas = None
        salidas = None
        primero = self.actual()
        if primero.token == "PALABRA RESERVADA" and primero.valor == "ENTRADA":
            try:
                entradas = self._declaracion("ENTRADA")
            except _ErrorSintactico as error:
                self._registrar(error)
                self._sincronizar(error.diagnostico.linea)
        else:
            # Falta ENTRADA: se informa y se analizan igualmente las compuertas.
            self._registrar(self._fallo_en(
                primero,
                f"el circuito debe empezar declarando sus entradas: se esperaba "
                f"ENTRADA[...] y llegó {describir(primero)}",
                "agrega una primera línea como ENTRADA[a, b]"))
            if not self.es_compuerta(primero) and not \
                    (primero.token == "PALABRA RESERVADA" and primero.valor == "SALIDA"):
                self._sincronizar(primero.linea)

        # [<salidas>] opcional, justo después de ENTRADA.
        token = self.actual()
        if token is not None and token.token == "PALABRA RESERVADA" and token.valor == "SALIDA":
            try:
                salidas = self._declaracion("SALIDA")
            except _ErrorSintactico as error:
                self._registrar(error)
                self._sincronizar(error.diagnostico.linea)

        instrucciones = []
        fin_anterior = self.anterior()
        while self.actual() is not None:
            try:
                instrucciones.append(self._instruccion(fin_anterior))
                fin_anterior = self.anterior()
            except _ErrorSintactico as error:
                self._registrar(error)
                self._sincronizar(error.diagnostico.linea)
                fin_anterior = None

        if not instrucciones and not self.diagnosticos and not self._hubo_silenciosos:
            linea = entradas.linea if entradas else 1
            columna = entradas.columna if entradas else 1
            self.diagnosticos.append(diag.error(
                "sintáctico", linea, columna,
                "el circuito debe contener al menos una compuerta",
                "agrega una instrucción como AND[a, b] -> x"))

        # Con errores (o con comodines del léxico) no se construye nada.
        if self.diagnosticos or self._hubo_silenciosos or entradas is None:
            return None, self.diagnosticos

        circuito = Circuito(entradas.linea, entradas.columna, entradas, salidas,
                            instrucciones)
        return self._construir(circuito), []

    def construir_circuito(self):
        """Analiza la secuencia de tokens y devuelve la estructura del circuito.

        Interfaz histórica: lanza SyntaxError con el primer error. El atributo
        `diagnosticos` conserva todos los errores encontrados.
        """
        estructura, diagnosticos = self.analizar()
        if diagnosticos:
            error = SyntaxError(diagnosticos[0].texto())
            error.diagnosticos = diagnosticos
            raise error
        if estructura is None:
            raise SyntaxError("Error sintáctico línea 1: el circuito tiene errores léxicos")
        return estructura

    # ------------------------------------------------------------------
    # Construcción de la estructura y del AST
    # ------------------------------------------------------------------
    @staticmethod
    def _construir(circuito):
        """Estructura plana (desazucarada) + AST tipado + AST JSON histórico."""
        estructura = desazucarar(circuito)
        estructura["arbol"] = circuito
        estructura["ast"] = ast_legado(circuito)
        return estructura
