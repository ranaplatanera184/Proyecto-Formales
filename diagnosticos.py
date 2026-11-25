# ============================================================================
# DIAGNÓSTICOS DEL COMPILADOR (ERRORES Y ADVERTENCIAS)
# ----------------------------------------------------------------------------
# Cada fase produce objetos Diagnostico con la fase, la severidad, la posición
# exacta (línea y columna), el mensaje y una sugerencia opcional. De ellos se
# derivan los dos formatos de salida:
#
#   * texto, el formato histórico que lee la web y muestran los tests:
#         Error <léxico|sintáctico|semántico> línea L, columna C: mensaje
#         Advertencia línea L, columna C: mensaje
#   * JSON estructurado (campo "diagnosticos" de la API).
# ============================================================================

import re
from dataclasses import dataclass, asdict
from typing import Optional

FASES = ("léxico", "sintáctico", "semántico", "interno")
SEVERIDADES = ("error", "advertencia")


@dataclass
class Diagnostico:
    fase: str
    severidad: str
    linea: Optional[int]
    columna: Optional[int]
    mensaje: str
    sugerencia: Optional[str] = None

    @property
    def es_error(self):
        return self.severidad == "error"

    def posicion(self):
        if self.linea is None:
            return ""
        if self.columna is None:
            return f"línea {self.linea}"
        return f"línea {self.linea}, columna {self.columna}"

    def texto(self):
        """Mensaje en el formato histórico (el que entiende la web)."""
        posicion = self.posicion()
        if self.severidad == "advertencia":
            cabecera = f"Advertencia {posicion}" if posicion else "Advertencia"
        elif self.fase == "interno":
            cabecera = "Error interno del compilador"
            return f"{cabecera}: {self.mensaje}"
        else:
            cabecera = f"Error {self.fase} {posicion}" if posicion else f"Error {self.fase}"
        return f"{cabecera}: {self.mensaje}"

    def texto_con_sugerencia(self):
        """Texto + sugerencia en la misma línea (para la consola)."""
        if self.sugerencia:
            return f"{self.texto()} ({self.sugerencia})"
        return self.texto()

    def to_json(self):
        return asdict(self)


def error(fase, linea, columna, mensaje, sugerencia=None):
    return Diagnostico(fase, "error", linea, columna, mensaje, sugerencia)


def advertencia(fase, linea, columna, mensaje, sugerencia=None):
    return Diagnostico(fase, "advertencia", linea, columna, mensaje, sugerencia)


_PATRON = re.compile(
    r"^(?P<tipo>Error|Advertencia)(?:\s+(?P<fase>léxico|sintáctico|semántico))?"
    r"(?:\s+línea\s+(?P<linea>\d+)(?:,\s*columna\s+(?P<columna>\d+))?)?"
    r":\s*(?P<mensaje>.*)$", re.DOTALL)


def desde_texto(texto, fase_por_defecto="semántico"):
    """Convierte un mensaje con el formato histórico en un Diagnostico."""
    coincidencia = _PATRON.match(str(texto))
    if not coincidencia:
        return Diagnostico("interno", "error", None, None, str(texto))
    severidad = "advertencia" if coincidencia["tipo"] == "Advertencia" else "error"
    fase = coincidencia["fase"] or fase_por_defecto
    linea = int(coincidencia["linea"]) if coincidencia["linea"] else None
    columna = int(coincidencia["columna"]) if coincidencia["columna"] else None
    return Diagnostico(fase, severidad, linea, columna, coincidencia["mensaje"])
