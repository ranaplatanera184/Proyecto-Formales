# ============================================================================
# ALMACENAMIENTO - HISTORIAL DE ANÁLISIS Y EXPORTACIÓN
# ----------------------------------------------------------------------------
# Mantiene el historial de análisis realizados (entrada, resultado y errores)
# y permite exportar un reporte en .txt con los resultados de un análisis.
# El historial se guarda en memoria (lo usa el menú HISTORIAL de la consola y
# la vista «Historial» de la interfaz web) y cada registro guarda su fecha.
# ============================================================================

from datetime import datetime


def copiar_expresiones(expresiones):
    """Copia profunda de las expresiones para que el historial no se aliase con
    el diccionario que se está construyendo: si el llamador lo modifica después
    de registrar, el reporte exportaría algo que nunca se analizó."""
    if not expresiones:
        return {}

    copia = {}
    for salida, datos in expresiones.items():
        copia[salida] = dict(datos)
        for clave in ("intermedia", "intermedia_ascii"):
            if isinstance(datos.get(clave), list):
                copia[salida][clave] = list(datos[clave])
    return copia


class Almacenamiento:

    def __init__(self):
        self.historial_analisis = []

    def agregar_analisis(self, entrada, resultado, errores, expresiones=None):
        """Guarda un análisis: la entrada, el resultado y la lista de errores.

        `expresiones` son las formas intermedia y expandida por salida de salida
        (las produce `expresiones.generar_expresiones`). Se guarda aparte para
        que el reporte .txt pueda incluirlas sin volver a analizar el circuito.
        """
        self.historial_analisis.append({
            "entrada": entrada,
            "resultado": bool(resultado),
            "errores": list(errores),
            "expresiones": copiar_expresiones(expresiones),
            "fecha": datetime.now().isoformat(timespec="seconds"),
        })

    def obtener_historial(self):
        """Devuelve la lista completa de análisis registrados."""
        return self.historial_analisis

    def eliminar_analisis(self, indice):
        """Borra un análisis por su posición. Devuelve True si se borró."""
        if not isinstance(indice, int) or indice < 0:
            return False
        if indice >= len(self.historial_analisis):
            return False
        self.historial_analisis.pop(indice)
        return True

    def limpiar_historial(self):
        """Borra todos los análisis registrados y devuelve cuántos había."""
        total = len(self.historial_analisis)
        self.historial_analisis.clear()
        return total

    def exportar_reporte_txt(self, ruta="reporte_circuito.txt"):
        """Genera un reporte en .txt con el resultado del último análisis."""
        if not self.historial_analisis:
            return None

        analisis = self.historial_analisis[-1]

        lineas = []
        lineas.append("REPORTE DE ANÁLISIS DE CIRCUITO")
        lineas.append("=" * 40)
        lineas.append("")
        lineas.append("ENTRADA:")
        lineas.append(analisis["entrada"])
        lineas.append("")
        lineas.append("RESULTADO: " + ("ANÁLISIS EXITOSO" if analisis["resultado"] else "ANÁLISIS CON ERRORES"))
        lineas.append("")

        if analisis["errores"]:
            lineas.append("ERRORES:")
            for error in analisis["errores"]:
                lineas.append(f"  - {error}")

        lineas.extend(self._seccion_expresiones(analisis.get("expresiones") or {}))

        with open(ruta, "w", encoding="utf-8") as archivo:
            archivo.write("\n".join(lineas) + "\n")

        return ruta

    def _seccion_expresiones(self, expresiones):
        """Líneas del reporte con las expresiones, en las dos notaciones.

        Devuelve una lista vacía si el análisis no tiene expresiones (por
        ejemplo, si terminó con errores), para no dejar un encabezado solo.
        """
        if not expresiones:
            return []

        lineas = ["", "EXPRESIONES BOOLEANAS:"]

        for salida, datos in expresiones.items():
            lineas.append("")
            lineas.append(f"  Salida: {salida}")

            lineas.append("")
            lineas.append("    Forma intermedia (símbolos):")
            for linea in datos.get("intermedia") or []:
                lineas.append(f"      {linea}")

            lineas.append("")
            lineas.append("    Forma intermedia (ASCII):")
            for linea in datos.get("intermedia_ascii") or []:
                lineas.append(f"      {linea}")

            lineas.append("")
            lineas.append("    Forma expandida (símbolos):")
            lineas.extend(self._linea_expandida(datos.get("expandida"), datos.get("aviso")))

            lineas.append("")
            lineas.append("    Forma expandida (ASCII):")
            lineas.extend(self._linea_expandida(datos.get("expandida_ascii"), datos.get("aviso")))

        return lineas

    @staticmethod
    def _linea_expandida(expandida, aviso):
        """La expresión o, si se omitió por larga, el motivo de la omisión."""
        if expandida:
            return [f"      {expandida}"]
        return [f"      (no disponible) {aviso}" if aviso
                else "      (no disponible)"]