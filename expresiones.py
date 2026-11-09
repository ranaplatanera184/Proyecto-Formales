# ============================================================================
# EXPRESIONES BOOLEANAS - FORMA INTERMEDIA Y EXPANDIDA
# ----------------------------------------------------------------------------
# Genera, para cada señal de salida final de un circuito ya validado, dos
# representaciones de su función booleana equivalente:
#
#   * intermedia: una línea por compuerta, en orden topológico, del tipo
#     `x1 = a · b`. Sirve para leer el circuito como una cadena de pasos.
#   * expandida: una sola expresión con las entradas del circuito
#     sustituidas en su lugar, del tipo `¬(((a · b + c) ⊕ a) · b)`.
#
# Precedencia de los operadores, de mayor a menor:
#     ¬  (NOT)  >  ·  (AND)  >  ⊕  (XOR)  >  +  (OR)
# Los paréntesis son mínimos: solo aparecen cuando son necesarios para no
# cambiar el orden de evaluación.
#
# Este módulo no evalúa ni compila expresiones: solo construye texto.
# ============================================================================

LIMITE_EXPANDIDA = 2000

AVISO_LARGA = "Expresión expandida demasiado larga ({n} caracteres)"

# Símbolo, precedencia y carácter de negación de cada compuerta. Para NOT el
# símbolo es su propia negación; para NAND/NOR/XNOR el símbolo es el de la
# compuerta positiva y el prefijo `¬`/`!` niega el resultado.
# La precedencia coincide con la de Python (not > & > ^ > |), por lo que la
# forma ASCII puede evaluarse con `eval` sustituyendo `!` por `~`.
COMPERTAS = {
    "AND":  ("·", 3, None),
    "OR":   ("+", 1, None),
    "XOR":  ("⊕", 2, None),
    "NOT":  ("¬", 4, "¬"),
    "NAND": ("·", 3, "¬"),
    "NOR":  ("+", 1, "¬"),
    "XNOR": ("⊕", 2, "¬"),
}

# Las mismas reglas escritas con caracteres ASCII, para clientes que no
# admiten los símbolos (la web las usa sin traducción en el navegador).
COMPERTAS_ASCII = {
    "AND":  ("&", 3, None),
    "OR":   ("|", 1, None),
    "XOR":  ("^", 2, None),
    "NOT":  ("!", 4, "!"),
    "NAND": ("&", 3, "!"),
    "NOR":  ("|", 1, "!"),
    "XNOR": ("^", 2, "!"),
}


ESTILOS = ("simbolos", "ascii")


def generar_expresiones(modelo, estilo="simbolos"):
    """Expresiones intermedia y expandida de cada salida final del circuito.

    `modelo` es un `AnalizadorSemantico` ya validado con `revisar()`. Se
    devuelve un diccionario indexado por señal de salida final:

        {
            "salida": {
                "intermedia": ["x1 = a · b", "salida = ¬(x1 + c)"],
                "expandida": "¬((a · b) + c)",
                "aviso": None,
            }
        }

    Si la expandida supera `LIMITE_EXPANDIDA` caracteres, se omite (queda en
    `None`) y se devuelve el motivo en `aviso`; la intermedia no se recorta.

    `estilo` es "simbolos" (¬ · ⊕ +) o "ascii" (! & ^ |).
    """
    if estilo not in ESTILOS:
        raise ValueError(f"estilo de expresión desconocido: {estilo!r}")

    contexto = _Contexto(modelo, COMPERTAS_ASCII if estilo == "ascii" else COMPERTAS)

    resultado = {}
    for salida in contexto.salidas_finales:
        expandida = contexto.expandida_de(salida)
        resultado[salida] = {
            "intermedia": contexto.lineas_de(salida),
            "expandida": expandida,
            "aviso": None if expandida is not None else contexto.avisos[salida],
        }
    return resultado


class _Contexto:
    """Estado compartido de una generación: reglas y textos ya calculados.

    Se construye una vez por llamada a `generar_expresiones` para que la caché
    de textos expandidos sirva a todas las salidas finales: una señal usada
    por varias se expande una sola vez.
    """

    def __init__(self, modelo, reglas):
        self.reglas = reglas
        self.entradas = set(modelo.entradas)
        self.compuertas = {c["salida"]: c for c in modelo.compuertas}

        # Señales que alimentan alguna compuerta: las que no aparecen aquí son
        # salidas finales, igual que en semantico.expresiones_booleanas().
        usadas = set()
        for compuerta in modelo.compuertas:
            usadas.update(compuerta["entradas"])
        self.salidas_finales = [
            c["salida"] for c in modelo.compuertas if c["salida"] not in usadas
        ]

        # `_expandida` guarda el texto ya expandido de cada señal; `_cuenta` lleva
        # el número de expansiones realmente calculadas.
        self._expandida = {}
        self._cuenta = 0

        # Motivo de haber omitido una expandida, indexado por señal: el aviso
        # pertenece a la salida larga, no a todas las salidas del circuito.
        self.avisos = {}

        # Orden topológico y líneas de la forma intermedia, calculados una vez.
        self._lineas = dict(self._calcular_lineas(modelo))

    # ------------------------------------------------------------------
    # Forma intermedia
    # ------------------------------------------------------------------
    def _calcular_lineas(self, modelo):
        """(señal, línea) por compuerta, en orden topológico.

        Se usa `orden_topologico()` del modelo para no duplicar aquí el
        algoritmo de Kahn.
        """
        for compuerta in modelo.orden_topologico():
            yield compuerta["salida"], self._linea_de(compuerta)

    def _linea_de(self, compuerta):
        """`x1 = a · b` para una compuerta, con su símbolo y su negación."""
        simbolo, _, negacion = self.reglas[compuerta["compuerta"]]
        cuerpo = f" {simbolo} ".join(compuerta["entradas"])
        if negacion:
            cuerpo = f"{negacion}({cuerpo})"
        return f"{compuerta['salida']} = {cuerpo}"

    def lineas_de(self, salida):
        """Líneas de la forma intermedia que llevan desde las entradas a `salida`.

        Solo las compuertas de las que depende esa salida, para no mezclar en
        un caso de 50 compuertas las que pertenecen a otra rama del circuito.
        """
        necesarias = self._predecesoras(salida)
        return [linea for senal, linea in self._lineas.items() if senal in necesarias]

    def _predecesoras(self, salida):
        """Todas las señales que `salida` necesita, la propia incluida."""
        pendientes = [salida]
        vistas = set()
        while pendientes:
            senal = pendientes.pop()
            if senal in vistas or senal in self.entradas:
                continue
            vistas.add(senal)
            pendientes.extend(self.compuertas[senal]["entradas"])
        return vistas

    # ------------------------------------------------------------------
    # Forma expandida
    # ------------------------------------------------------------------
    def expandida_de(self, salida):
        """La expresión de `salida` con solo entradas, o None si es demasiado larga.

        Al recortarla deja el motivo en `avisos[salida]`.
        """
        texto = self._expandir(salida)
        if len(texto) > LIMITE_EXPANDIDA:
            self.avisos[salida] = AVISO_LARGA.format(n=len(texto))
            return None
        return texto

    def _expandir(self, senal):
        """Texto expandido de `senal`, memoizado para no repetir el trabajo."""
        if senal in self.entradas:
            return senal
        if senal in self._expandida:
            return self._expandida[senal]

        compuerta = self.compuertas[senal]
        simbolo, precedencia, negacion = self.reglas[compuerta["compuerta"]]

        if compuerta["compuerta"] == "NOT":
            # «¬(x)»: un solo operando, siempre parentetizado porque puede ser
            # cualquier expresión.
            texto = f"{simbolo}({self._expandir(compuerta['entradas'][0])})"
        else:
            texto = self._operandos(compuerta, precedencia)
            if negacion:
                texto = f"{negacion}({texto})"

        self._cuenta += 1
        self._expandida[senal] = texto
        return texto

    def _operandos(self, compuerta, precedencia_padre):
        """Los operandos unidos con su símbolo, parentetizados si hace falta."""
        simbolo = self.reglas[compuerta["compuerta"]][0]
        partes = []

        for entrada in compuerta["entradas"]:
            if entrada in self.entradas:
                partes.append(entrada)
                continue

            texto = self._expandir(entrada)
            _, precedencia_entrada, _ = self.reglas[self.compuertas[entrada]["compuerta"]]

            # Se parentetiza un operando compuesto cuando su operador se evalúa
            # antes de lo que la precedencia del padre ya garantiza (más débil
            # que el padre), y siempre cuando es XOR u OR: en esos dos casos el
            # paréntesis deja el orden de evaluación explícito.
            if precedencia_entrada <= 2 or precedencia_entrada < precedencia_padre:
                partes.append(f"({texto})")
            else:
                partes.append(texto)

        return f" {simbolo} ".join(partes)