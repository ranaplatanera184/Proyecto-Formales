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
# Como resultado construye la estructura interna del circuito: una lista de
# compuertas (con sus entradas, salida y linea) y la lista de entradas.
# ============================================================================

import json


class AnalisisSintactico:

    def __init__(self, tokens, gestorReglas=None, rutaReglas="reglas.json"):
        # Fase sintactica: trabaja sobre la lista de tokens.
        self.tokens = tokens
        self.pos = 0

        # Nombres de compuerta validos definidos en reglas.json.
        self.nombres_compuertas = set()
        if gestorReglas is not None:
            self.nombres_compuertas = set(gestorReglas.obtener_nombres_compuertas())
        else:
            try:
                with open(rutaReglas, "r", encoding="utf-8") as archivo:
                    reglas = json.load(archivo)
                self.nombres_compuertas = {
                    c["nombre"] for c in reglas.get("compuertas", [])
                }
            except Exception:
                self.nombres_compuertas = {"AND", "OR", "NOT", "XOR", "NAND", "NOR", "XNOR"}

    def actual(self):
        """Devuelve el token actual o None si se acabó la entrada."""
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def _error_linea(self, token, mensaje):
        linea = getattr(token, "linea", None) or 1
        return f"Error sintáctico línea {linea}: {mensaje}"

    def _error_fin(self, mensaje):
        ultimo = self.tokens[-1] if self.tokens else None
        linea = getattr(ultimo, "linea", None) or 1
        return f"Error sintáctico línea {linea}: {mensaje}"

    def consumir(self, tipo):
        """Consume el token actual exigiendo que sea de un tipo concreto."""
        token = self.actual()
        if token is None:
            raise SyntaxError(self._error_fin(f"se esperaba {tipo} y llegó fin de entrada"))
        if token.token != tipo:
            raise SyntaxError(
                self._error_linea(token, f"se esperaba {tipo} y llegó {token.token} ({token.valor})"))
        self.pos += 1
        return token

    def _consumir_lista_identificadores(self):
        """Consume '[' <id> (',' <id>)* ']' y devuelve la lista de identificadores."""
        self.consumir("CORCHETE ABRE")

        ids = []
        primero = self.consumir("IDENTIFICADOR")
        ids.append(primero.valor)

        while True:
            token = self.actual()
            if token is None:
                raise SyntaxError(
                    self._error_fin("se esperaba ',' o ']' y llegó fin de entrada"))
            if token.token == "CORCHETE CIERRA":
                self.pos += 1
                break
            if token.token == "COMA":
                self.pos += 1
                self.consumir("IDENTIFICADOR")
                ids.append(self.tokens[self.pos - 1].valor)
            else:
                raise SyntaxError(
                    self._error_linea(token, f"se esperaba ',' o ']' y llegó {token.token} ({token.valor})"))

        return ids

    def construir_circuito(self):
        """Analiza la secuencia de tokens y devuelve la estructura del circuito."""
        if not self.tokens:
            raise SyntaxError("Error sintáctico línea 1: el circuito está vacío")

        # <circuito> ::= <entrada> <instruccion>+
        token_entrada = self.consumir("PALABRA RESERVADA")
        if token_entrada.valor != "ENTRADA":
            raise SyntaxError(
                self._error_linea(token_entrada, f"se esperaba ENTRADA y llegó {token_entrada.valor}"))

        linea_entrada = token_entrada.linea or 1
        entradas = self._consumir_lista_identificadores()

        # <instruccion>+ : una o mas compuertas.
        compuertas = []
        while self.pos < len(self.tokens):
            token_compuerta = self.actual()

            if token_compuerta.token != "PALABRA RESERVADA":
                raise SyntaxError(
                    self._error_linea(
                        token_compuerta,
                        f"token inesperado: {token_compuerta.token} ({token_compuerta.valor})"))

            if token_compuerta.valor == "ENTRADA":
                raise SyntaxError(
                    self._error_linea(token_compuerta, "se esperaba una compuerta y llegó ENTRADA"))

            if token_compuerta.valor not in self.nombres_compuertas:
                raise SyntaxError(
                    self._error_linea(token_compuerta, f"compuerta no reconocida '{token_compuerta.valor}'"))

            self.pos += 1
            nombre = token_compuerta.valor
            linea = token_compuerta.linea or 1

            entradas_gate = self._consumir_lista_identificadores()
            self.consumir("FLECHA")
            salida = self.consumir("IDENTIFICADOR")

            compuertas.append({
                "compuerta": nombre,
                "entradas": entradas_gate,
                "salida": salida.valor,
                "linea": linea,
            })

        if not compuertas:
            raise SyntaxError(
                f"Error sintáctico línea {linea_entrada}: el circuito debe contener al menos una compuerta")

        return {
            "entradas": entradas,
            "linea_entrada": linea_entrada,
            "compuertas": compuertas,
        }