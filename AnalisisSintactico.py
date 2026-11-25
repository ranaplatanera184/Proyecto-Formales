# ============================================================================
# FASE SINTACTICA DEL COMPILADOR DE CIRCUITOS
# ----------------------------------------------------------------------------
# Recibe la lista de tokens producida por la fase lexica y comprueba que se
# ajuste a la gramatica del lenguaje:
#
#   <circuito>    ::= <entrada> <instruccion>+
#   <entrada>     ::= "ENTRADA" "[" <id> ("," <id>)* "]"
#   <instruccion> ::= <compuerta> "[" <id> ("," <id>)* "]" "->" <id>
#   <compuerta>   ::= "AND" | "OR" | "NOT" | "XOR" | "NAND" | "NOR" | "XNOR"
#
# Parser descendente recursivo con RECUPERACIÓN EN MODO PÁNICO: al encontrar
# un error lo registra y se sincroniza en el primer token de una línea
# posterior, así reporta todos los errores de una pasada (como máximo uno por
# línea y unos 50 en total). Los mensajes no usan los nombres internos de los
# tokens: dicen qué falta y dónde ("falta una coma entre 'a' y 'b'").
#
# Como resultado construye la estructura interna del circuito (entradas y
# compuertas con la posición de cada referencia) y un AST JSON.
# ============================================================================

from rutas import cargar_reglas
from sugerencias import mas_parecido
import diagnosticos as diag

MAXIMO_ERRORES = 50

# Cómo se nombra cada tipo de token en los mensajes.
NOMBRES_AMIGABLES = {
    "CORCHETE ABRE": "'['",
    "CORCHETE CIERRA": "']'",
    "COMA": "','",
    "FLECHA": "'->'",
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
        return self.es(token, "IDENTIFICADOR")

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
    def _lista_de_nombres(self, duenio, token_duenio, es_entrada):
        """'[' <id> (',' <id>)* ']' → lista de (nombre, token).

        `duenio` es "ENTRADA" o el nombre de la compuerta, para los mensajes.
        """
        apertura = self.actual()
        if not self.es(apertura, "CORCHETE ABRE"):
            if self.es_nombre(apertura) and apertura.linea == token_duenio.linea:
                raise self._fallo_en(apertura, f"falta '[' después de {duenio}",
                                     f"escribe {duenio}[{apertura.valor}, ...]")
            raise self._fallo_tras(
                token_duenio,
                f"falta '[' después de {duenio} para abrir la lista de "
                + ("entradas" if es_entrada else "entradas de la compuerta"),
                f"escribe {duenio}[...]")
        self.pos += 1

        que = "un nombre de entrada" if es_entrada else "al menos una entrada"
        if self.es(self.actual(), "CORCHETE CIERRA"):
            if es_entrada:
                raise self._fallo_en(self.actual(),
                                     "ENTRADA necesita al menos un nombre de entrada "
                                     "entre los corchetes",
                                     "por ejemplo ENTRADA[a, b]")
            raise self._fallo_en(self.actual(),
                                 f"la compuerta {duenio} necesita {que} entre los corchetes",
                                 f"por ejemplo {duenio}[a, b] -> x")

        nombres = []
        while True:
            token = self.actual()
            if self.es_nombre(token):
                nombres.append((token.valor, token))
                self.pos += 1
            else:
                raise self._argumento_invalido(token, duenio, apertura, nombres)

            separador = self.actual()
            if self.es(separador, "COMA"):
                self.pos += 1
                continue
            if self.es(separador, "CORCHETE CIERRA"):
                self.pos += 1
                return nombres
            raise self._separador_invalido(separador, duenio, apertura, nombres)

    def _argumento_invalido(self, token, duenio, apertura, nombres):
        """Mensaje cuando se esperaba un nombre dentro de los corchetes."""
        previo = self.anterior()
        if token is None or token.linea != previo.linea:
            return self._fallo_tras(previo, f"falta ']' para cerrar la lista de {duenio}",
                                    f"la lista se abrió en la columna {apertura.columna}")
        if self.es(token, "COMA"):
            if nombres:
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

    def _separador_invalido(self, token, duenio, apertura, nombres):
        """Mensaje cuando tras un nombre no viene ',' ni ']'."""
        ultimo_nombre, ultimo_token = nombres[-1]
        if token is None or token.linea != ultimo_token.linea:
            return self._fallo_tras(ultimo_token,
                                    f"falta ']' para cerrar la lista de {duenio}",
                                    f"la lista se abrió en la columna {apertura.columna}")
        if self.es_nombre(token) or token.token == "PALABRA RESERVADA":
            nombre = token.valor
            return self._fallo_en(token,
                                  f"falta una coma entre '{ultimo_nombre}' y '{nombre}'",
                                  f"escribe {ultimo_nombre}, {nombre}")
        if self.es(token, "FLECHA"):
            return self._fallo_en(token, f"falta ']' para cerrar la lista de {duenio}",
                                  "cierra los corchetes antes de '->'")
        if self.es(token, "CORCHETE ABRE"):
            return self._fallo_en(token, "sobra '[': los corchetes no se pueden anidar aquí")
        return self._fallo_en(token, f"se esperaba ',' o ']' después de '{ultimo_nombre}' "
                                     f"y llegó {describir(token)}")

    def _declaracion_entradas(self):
        """<entrada> ::= ENTRADA '[' <id> (',' <id>)* ']'."""
        token = self.actual()
        self.pos += 1
        nombres = self._lista_de_nombres("ENTRADA", token, es_entrada=True)
        return token, nombres

    def _instruccion(self, fin_anterior):
        """<instruccion> ::= <compuerta> '[' ids ']' '->' <id>."""
        token = self.actual()
        if not self.es_compuerta(token):
            raise self._inicio_invalido(token, fin_anterior)
        self.pos += 1
        nombre = token.valor

        argumentos = self._lista_de_nombres(nombre, token, es_entrada=False)
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
                                       f"termina la instrucción con -> salida")
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
            raise self._fallo_en(salida, "se esperaba el nombre de la salida después de '->' "
                                         f"y llegó {describir(salida)}")
        self.pos += 1
        return token, argumentos, salida

    def _inicio_invalido(self, token, fin_anterior):
        """Mensaje cuando una instrucción no empieza con una compuerta."""
        compuertas = ", ".join(sorted(self.nombres_compuertas))
        if token.token == "PALABRA RESERVADA" and token.valor == "ENTRADA":
            return self._fallo_en(token,
                                  "se esperaba una compuerta y llegó ENTRADA: solo puede "
                                  "haber una declaración ENTRADA, al inicio del circuito",
                                  "junta todas las entradas en la primera ENTRADA[...]")
        siguiente = self.siguiente()
        if self.es_nombre(token) and token.token == "IDENTIFICADOR" and self.es(siguiente, "CORCHETE ABRE"):
            parecida = mas_parecido(token.valor, sorted(self.nombres_compuertas),
                                    ignorar_mayusculas=True)
            sugerencia = (f"¿quisiste decir {parecida}?" if parecida
                          else f"las compuertas son {compuertas}")
            return self._fallo_en(token, f"'{token.valor}' no es una compuerta conocida",
                                  sugerencia)
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

        entradas = []
        token_entrada = None
        primero = self.actual()
        if primero.token == "PALABRA RESERVADA" and primero.valor == "ENTRADA":
            try:
                token_entrada, entradas = self._declaracion_entradas()
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
            if not self.es_compuerta(primero):
                self._sincronizar(primero.linea)

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
            linea = token_entrada.linea if token_entrada else 1
            columna = token_entrada.columna if token_entrada else 1
            self.diagnosticos.append(diag.error(
                "sintáctico", linea, columna,
                "el circuito debe contener al menos una compuerta",
                "agrega una instrucción como AND[a, b] -> x"))

        # Con errores (o con comodines del léxico) no se construye nada.
        if self.diagnosticos or self._hubo_silenciosos:
            return None, self.diagnosticos
        return self._construir(token_entrada, entradas, instrucciones), []

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
    def _construir(token_entrada, entradas, instrucciones):
        linea_entrada = token_entrada.linea or 1
        compuertas = []
        instrucciones_ast = []
        for token, argumentos, salida in instrucciones:
            compuertas.append({
                "compuerta": token.valor,
                "entradas": [nombre for nombre, _ in argumentos],
                "salida": salida.valor,
                "linea": token.linea or 1,
                "columna": token.columna,
                "pos_entradas": [[t.linea, t.columna] for _, t in argumentos],
                "pos_salida": [salida.linea, salida.columna],
            })
            instrucciones_ast.append({
                "tipo": "asignacion",
                "salida": salida.valor,
                "linea": token.linea or 1,
                "expresion": {
                    "tipo": "compuerta",
                    "nombre": token.valor,
                    "entradas": [{"tipo": "senal", "nombre": nombre}
                                 for nombre, _ in argumentos],
                },
            })

        return {
            "entradas": [nombre for nombre, _ in entradas],
            "linea_entrada": linea_entrada,
            "columna_entrada": token_entrada.columna,
            "pos_entradas": [[t.linea, t.columna] for _, t in entradas],
            "compuertas": compuertas,
            "ast": {
                "tipo": "circuito",
                "declaracion_entradas": {
                    "tipo": "declaracion_entradas",
                    "linea": linea_entrada,
                    "entradas": [{"tipo": "senal", "nombre": nombre}
                                 for nombre, _ in entradas],
                },
                "instrucciones": instrucciones_ast,
            },
        }
