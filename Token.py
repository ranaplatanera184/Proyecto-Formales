class Token:

    def __init__(self, token, valor, linea=None, columna=None):
        # Representa una unidad léxica; se guarda su posición (línea y columna)
        # para poder reportar errores con ubicación exacta en el archivo.
        self.token = token
        self.valor = valor
        self.linea = linea
        self.columna = columna

    def to_json(self):
        return {
            "token": self.token,
            "valor": self.valor,
            "linea": self.linea,
            "columna": self.columna,
        }

    def __repr__(self):
        return f"Token(token={self.token}, valor={self.valor!r}, línea={self.linea}, columna={self.columna})"