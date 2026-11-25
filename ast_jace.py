# ============================================================================
# ÁRBOL DE SINTAXIS ABSTRACTA (AST) DE JACE
# ----------------------------------------------------------------------------
# Nodos tipados que construye el parser, todos con su línea y columna:
#
#   Circuito
#   ├── DeclaracionEntradas  (Senal...)
#   ├── DeclaracionSalidas   (Senal...)          opcional
#   └── Asignacion...        (Compuerta, Senal destino)
#                              Compuerta (Senal | Constante | Compuerta)...
#
# Además:
#   * desazucarar(): convierte el árbol en la estructura plana que usan las
#     fases siguientes ({entradas, compuertas}). Cada compuerta anidada pasa a
#     ser una señal temporal _t1, _t2... (ningún nombre del usuario puede
#     empezar con '_', así que no hay choques).
#   * a_json() y arbol_ascii(): las dos vistas del árbol (web y consola).
# ============================================================================

from dataclasses import dataclass, field
from typing import List, Optional, Union


@dataclass
class Nodo:
    linea: int
    columna: int

    tipo = "Nodo"

    def valor(self):
        return None

    def hijos(self):
        return []

    def a_json(self):
        """{tipo, valor, linea, columna, hijos}: la misma forma para todos."""
        datos = {"tipo": self.tipo, "linea": self.linea, "columna": self.columna}
        if self.valor() is not None:
            datos["valor"] = self.valor()
        datos["hijos"] = [hijo.a_json() for hijo in self.hijos()]
        return datos


@dataclass
class Senal(Nodo):
    nombre: str = ""
    tipo = "senal"

    def valor(self):
        return self.nombre


@dataclass
class Constante(Nodo):
    valor_logico: int = 0
    tipo = "constante"

    def valor(self):
        return str(self.valor_logico)


@dataclass
class Compuerta(Nodo):
    nombre: str = ""
    argumentos: List[Union["Senal", "Constante", "Compuerta"]] = field(default_factory=list)
    tipo = "compuerta"

    def valor(self):
        return self.nombre

    def hijos(self):
        return list(self.argumentos)


@dataclass
class Asignacion(Nodo):
    compuerta: Optional[Compuerta] = None
    destino: Optional[Senal] = None
    tipo = "asignacion"

    def valor(self):
        return self.destino.nombre if self.destino else None

    def hijos(self):
        return [self.compuerta, self.destino]


@dataclass
class DeclaracionEntradas(Nodo):
    senales: List[Senal] = field(default_factory=list)
    tipo = "declaracion_entradas"

    def hijos(self):
        return list(self.senales)


@dataclass
class DeclaracionSalidas(Nodo):
    senales: List[Senal] = field(default_factory=list)
    tipo = "declaracion_salidas"

    def hijos(self):
        return list(self.senales)


@dataclass
class Circuito(Nodo):
    entradas: Optional[DeclaracionEntradas] = None
    salidas: Optional[DeclaracionSalidas] = None
    instrucciones: List[Asignacion] = field(default_factory=list)
    tipo = "circuito"

    def hijos(self):
        hijos = [self.entradas]
        if self.salidas is not None:
            hijos.append(self.salidas)
        return hijos + list(self.instrucciones)


# ---------------------------------------------------------------------------
# Desazucarado: árbol → estructura plana
# ---------------------------------------------------------------------------
PREFIJO_TEMPORAL = "_t"


def desazucarar(circuito):
    """Estructura plana del circuito a partir del AST.

    Cada compuerta anidada se convierte en una compuerta propia cuya salida
    es una señal temporal (_t1, _t2...). Las temporales se numeran en el
    orden en que se terminan de leer (de dentro hacia fuera y de izquierda a
    derecha) y se colocan antes de la compuerta que las usa.
    """
    compuertas = []
    contador = [0]

    def nueva_temporal():
        contador[0] += 1
        return f"{PREFIJO_TEMPORAL}{contador[0]}"

    def aplanar(compuerta, destino, temporal):
        nombres = []
        posiciones = []
        for argumento in compuerta.argumentos:
            if isinstance(argumento, Compuerta):
                nombre = aplanar(argumento, None, True)
            elif isinstance(argumento, Constante):
                nombre = str(argumento.valor_logico)
            else:
                nombre = argumento.nombre
            nombres.append(nombre)
            posiciones.append([argumento.linea, argumento.columna])

        if destino is None:
            salida = nueva_temporal()
            pos_salida = [compuerta.linea, compuerta.columna]
        else:
            salida = destino.nombre
            pos_salida = [destino.linea, destino.columna]

        datos = {
            "compuerta": compuerta.nombre,
            "entradas": nombres,
            "salida": salida,
            "linea": compuerta.linea,
            "columna": compuerta.columna,
            "pos_entradas": posiciones,
            "pos_salida": pos_salida,
        }
        if temporal:
            datos["temporal"] = True
        compuertas.append(datos)
        return salida

    for asignacion in circuito.instrucciones:
        aplanar(asignacion.compuerta, asignacion.destino, False)

    entradas = circuito.entradas
    salidas = circuito.salidas
    return {
        "entradas": [s.nombre for s in entradas.senales],
        "linea_entrada": entradas.linea,
        "columna_entrada": entradas.columna,
        "pos_entradas": [[s.linea, s.columna] for s in entradas.senales],
        "salidas_declaradas": [s.nombre for s in salidas.senales] if salidas else None,
        "pos_salidas": [[s.linea, s.columna] for s in salidas.senales] if salidas else None,
        "compuertas": compuertas,
    }


def ast_legado(circuito):
    """AST JSON con el formato anterior a la fase 3 (para compatibilidad).

    Las compuertas anidadas aparecen como nodos "compuerta" dentro de las
    entradas y las constantes como nodos "constante".
    """
    def expresion(nodo):
        if isinstance(nodo, Compuerta):
            return {"tipo": "compuerta", "nombre": nodo.nombre,
                    "entradas": [expresion(a) for a in nodo.argumentos]}
        if isinstance(nodo, Constante):
            return {"tipo": "constante", "valor": nodo.valor_logico}
        return {"tipo": "senal", "nombre": nodo.nombre}

    datos = {
        "tipo": "circuito",
        "declaracion_entradas": {
            "tipo": "declaracion_entradas",
            "linea": circuito.entradas.linea,
            "entradas": [{"tipo": "senal", "nombre": s.nombre}
                         for s in circuito.entradas.senales],
        },
        "instrucciones": [{
            "tipo": "asignacion",
            "salida": a.destino.nombre,
            "linea": a.compuerta.linea,
            "expresion": expresion(a.compuerta),
        } for a in circuito.instrucciones],
    }
    if circuito.salidas is not None:
        datos["declaracion_salidas"] = {
            "tipo": "declaracion_salidas",
            "linea": circuito.salidas.linea,
            "salidas": [{"tipo": "senal", "nombre": s.nombre}
                        for s in circuito.salidas.senales],
        }
    return datos


# ---------------------------------------------------------------------------
# Vista en consola: árbol ASCII
# ---------------------------------------------------------------------------
NOMBRES = {
    "circuito": "Circuito",
    "declaracion_entradas": "Entradas",
    "declaracion_salidas": "Salidas",
    "asignacion": "Asignación",
    "compuerta": "Compuerta",
    "senal": "Señal",
    "constante": "Constante",
}


def etiqueta(nodo_json):
    """Texto de un nodo: 'Compuerta AND  (línea 2, col 1)'."""
    texto = NOMBRES.get(nodo_json["tipo"], nodo_json["tipo"])
    if nodo_json["tipo"] == "asignacion":
        texto += f" → {nodo_json.get('valor')}"
    elif "valor" in nodo_json:
        texto += f" {nodo_json['valor']}"
    return f"{texto}  (línea {nodo_json['linea']}, col {nodo_json['columna']})"


def arbol_ascii(nodo):
    """Árbol con ├── └── │ a partir de un nodo o de su JSON (sin recursión)."""
    raiz = nodo.a_json() if isinstance(nodo, Nodo) else nodo
    lineas = [etiqueta(raiz)]
    # Pila de (nodo, prefijo, es_ultimo), en orden inverso para salir en orden.
    pila = [(hijo, "", i == len(raiz["hijos"]) - 1)
            for i, hijo in enumerate(raiz["hijos"])][::-1]
    while pila:
        actual, prefijo, ultimo = pila.pop()
        lineas.append(f"{prefijo}{'└── ' if ultimo else '├── '}{etiqueta(actual)}")
        prefijo_hijos = prefijo + ("    " if ultimo else "│   ")
        hijos = actual["hijos"]
        for i in range(len(hijos) - 1, -1, -1):
            pila.append((hijos[i], prefijo_hijos, i == len(hijos) - 1))
    return "\n".join(lineas)
