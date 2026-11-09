/* ==========================================================================
   EXPORTACIÓN DE RESULTADOS (JACE)
   Generadores de contenido (SVG, CSV y JSON) sin DOM, para poder verificarse
   también desde Node. Todo se arma a partir de la respuesta de /analizar:
   el SVG ya viene en `diagrama_svg` y la tabla en `tabla_verdad`.
   ========================================================================== */

(function (raiz) {
  "use strict";

  function escapar(valor) {
    const texto = valor === null || valor === undefined ? "" : String(valor);
    if (/[",\n;]/.test(texto)) {
      return '"' + texto.replace(/"/g, '""') + '"';
    }
    return texto;
  }

  /** Tabla de verdad completa en CSV (encabezado + filas). */
  function construirCSV(tablaVerdad, separador) {
    const sep = separador || ",";
    const tabla = tablaVerdad || {};
    const senales = tabla.señales || [];
    const filas = tabla.filas || [];

    const lineas = [senales.map(escapar).join(sep)];
    for (const fila of filas) {
      lineas.push(fila.map(escapar).join(sep));
    }
    return lineas.join("\n") + "\n";
  }

  /** Resultado completo del análisis en JSON (indentado, legible). */
  function construirJSON(datos, sangria) {
    return JSON.stringify(datos, null, sangria === undefined ? 2 : sangria) + "\n";
  }

  /** Contenido a descargar: el SVG tal cual lo generó el diagrama. */
  function construirSVG(datos) {
    return (datos && datos.diagrama_svg) || "";
  }

  /** Nombre de archivo con fecha y hora (para las descargas). */
  function nombreArchivo(extension, fecha) {
    const ahora = fecha || new Date();
    const partes = [
      ahora.getFullYear(),
      String(ahora.getMonth() + 1).padStart(2, "0"),
      String(ahora.getDate()).padStart(2, "0"),
      "-",
      String(ahora.getHours()).padStart(2, "0"),
      String(ahora.getMinutes()).padStart(2, "0"),
    ];
    return `jace_${partes.join("")}.${extension}`;
  }

  raiz.Exportacion = {
    construirCSV,
    construirJSON,
    construirSVG,
    nombreArchivo,
    escapar,
  };
})(typeof window !== "undefined" ? window : globalThis);
