# ============================================================================
# CÓDIGO INTERMEDIO (CÓDIGO DE TRES DIRECCIONES)
# ----------------------------------------------------------------------------
# Representación intermedia del circuito ya validado: una instrucción por
# compuerta, en orden topológico, con la forma
#
#       _t1 = AND a, b
#       _t2 = NOT c
#       y   = OR _t1, _t2
#
# Cada instrucción recuerda la línea del .jace de la que sale. Además de las
# siete compuertas, el optimizador puede producir dos operaciones auxiliares:
#       y = BUF x      (copia: y vale lo mismo que x)
#       y = CONST 1    (y es constante)
# ============================================================================

from dataclasses import dataclass, field, asdict
from typing import List

from evaluador import Programa

COMPUERTAS = ("AND", "OR", "NOT", "XOR", "NAND", "NOR", "XNOR")
AUXILIARES = ("BUF", "CONST")


@dataclass
class Instruccion:
    destino: str
    operacion: str
    argumentos: List[str] = field(default_factory=list)
    linea: int = 0

    def texto(self, ancho=0):
        return f"{self.destino.ljust(ancho)} = {self.operacion} {', '.join(self.argumentos)}"

    def a_json(self):
        datos = asdict(self)
        datos["texto"] = self.texto()
        return datos

    def copia(self, **cambios):
        datos = {"destino": self.destino, "operacion": self.operacion,
                 "argumentos": list(self.argumentos), "linea": self.linea}
        datos.update(cambios)
        return Instruccion(**datos)


def generar_ir(semantico):
    """Código de tres direcciones de un circuito validado, en orden topológico."""
    return [Instruccion(c["salida"], c["compuerta"], list(c["entradas"]), c["linea"])
            for c in semantico.orden_topologico()]


def texto_ir(instrucciones):
    """Listado legible, con los destinos alineados."""
    ancho = max((len(i.destino) for i in instrucciones), default=0)
    return "\n".join(i.texto(ancho) for i in instrucciones)


def programa_de(entradas, instrucciones):
    """El IR listo para el evaluador por bloques (para comprobar equivalencias)."""
    traducidas = []
    for i in instrucciones:
        if i.operacion == "CONST":
            traducidas.append(("buf", [i.argumentos[0]], i.destino))
        else:
            traducidas.append((i.operacion.lower(), i.argumentos, i.destino))
    return Programa(entradas, traducidas)
