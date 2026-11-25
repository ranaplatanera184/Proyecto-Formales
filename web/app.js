/* ==========================================================================
   INTERFAZ WEB DE JACE
   Secciones:
     1. Estado y utilidades          5. Análisis
     2. Fondo (ruta /background)     6. Pestañas de resultados
     3. Navegación (#/)              7. Diagrama: zoom, desplazamiento, modal
     4. Editor y validación rápida   8. Tabla de verdad y tokens
     9. Expresiones booleanas
    10. Errores · 11. Historial · 12. Exportar · 13. Inicio
   ========================================================================== */

const $ = (selector) => document.querySelector(selector);

const EJEMPLO = [
  "ENTRADA[a, b, c]",
  "AND[a, b] -> x1",
  "OR[x1, c] -> x2",
  "XOR[x2, a] -> x3",
  "NAND[x3, b] -> salida"
].join("\n");

const COLOR_INICIAL = "#FFFFFF";
const CLAVE_FONDO = "jace.fondo";
const FILAS_POR_BLOQUE = 32;      // la tabla de verdad se dibuja de 32 en 32
const ESPERA_VALIDACION = 600;    // debounce para validar mientras se escribe
const INTERVALO_PASOS_MS = 700;
const ZOOM_MINIMO = 0.2;
const ZOOM_MAXIMO = 6;

/* ======================================================================== */
/* 1. Estado y utilidades                                                    */
/* ======================================================================== */
const estado = {
  fondo: COLOR_INICIAL,
  resultado: null,            // última respuesta de /analizar
  pestanaActiva: "diagrama",  // se recuerda al volver a analizar
  zoom: { k: 1, tx: 0, ty: 0 },
  autoAjustar: true,          // mientras sea true se reajusta al redimensionar
  tabla: { senales: [], filas: [], senalFiltro: "", valorFiltro: "", mostradas: 0 },
  tokens: [],
  ast: null,
  tablaSimbolos: [],
  depurador: { valoresEntrada: {}, indice: 0, temporizador: null, pasos: [] },
  expresionNotacion: "simbolos",  // símbolos (¬ · ⊕ +) o ascii (! & ^ |)
  controladorValidacion: null,
};

const lienzo = $("#lienzo");

function limitar(valor, minimo, maximo) {
  return Math.min(maximo, Math.max(minimo, valor));
}

function esTextoNumero(valor) {
  return /^-?\d+(\.\d+)?$/.test(String(valor).trim());
}

/* ======================================================================== */
/* 2. Fondo visual (rutas GET/POST /background)                              */
/* ======================================================================== */
function normalizarColor(valor) {
  if (typeof valor !== "string") return null;
  let c = valor.trim();
  if (!c.startsWith("#")) return null;
  c = c.slice(1);
  if (!/^[0-9a-fA-F]+$/.test(c)) return null;
  if (c.length === 3) c = c.split("").map((ch) => ch + ch).join("");
  if (c.length !== 6) return null;
  return ("#" + c).toUpperCase();
}

function luminancia(color) {
  const c = color.slice(1);
  const r = parseInt(c.slice(0, 2), 16);
  const g = parseInt(c.slice(2, 4), 16);
  const b = parseInt(c.slice(4, 6), 16);
  return (0.299 * r + 0.587 * g + 0.114 * b) / 255;
}

function aplicarTema(color) {
  const oscuro = luminancia(color) < 0.5;
  const variables = oscuro
    ? {
        "--texto": "#e5e7eb",
        "--tenue": "#9ca3af",
        "--panel": "rgba(15, 23, 42, 0.55)",
        "--panel-solido": "#111a2e",
        "--panel-borde": "rgba(255, 255, 255, 0.16)",
      "--acento": "#8fbd91",
      "--acento-texto": "#102015",
      "--error": "#ff8e83",
      "--ok": "#83d497",
      "--menta": "#25392d",
      "--celeste": "#243a39",
        "--sombra": "0 1px 2px rgba(0, 0, 0, 0.4), 0 8px 24px rgba(0, 0, 0, 0.35)"
      }
    : {
      "--texto": "#26372c",
      "--tenue": "#738175",
      "--panel": "rgba(255, 255, 255, 0.86)",
      "--panel-solido": "#fffefa",
      "--panel-borde": "rgba(54, 91, 61, 0.14)",
      "--acento": "#4b8058",
        "--acento-texto": "#ffffff",
      "--error": "#b94d48",
      "--ok": "#438253",
      "--menta": "#e8f1e4",
      "--celeste": "#e5f1ef",
      "--sombra": "0 16px 42px rgba(48, 72, 50, 0.09)"
      };

  variables["--fondo"] = color;
  for (const [nombre, valor] of Object.entries(variables)) {
    document.documentElement.style.setProperty(nombre, valor);
  }
  document.documentElement.dataset.tema = oscuro ? "oscuro" : "claro";

  $("#muestraFondo").style.background = color;
  $("#textoFondo").textContent = color;
  $("#colorRapido").value = color.toLowerCase();
  $("#colorLibre").value = color.toLowerCase();
  $("#colorTexto").value = color;
}

async function cargarFondo() {
  const guardado = normalizarColor(localStorage.getItem(CLAVE_FONDO));
  try {
    const datos = await (await fetch("/background")).json();
    estado.fondo = normalizarColor(datos.fondo) || COLOR_INICIAL;
    dibujarPresets(datos.fondos || []);
    aplicarTema(estado.fondo);
    if (guardado && guardado !== estado.fondo) {
      await fijarFondo(guardado, { guardar: false });
    }
  } catch (error) {
    estado.fondo = guardado || COLOR_INICIAL;
    aplicarTema(estado.fondo);
  }
}

async function fijarFondo(color, opciones = {}) {
  const destino = opciones.destino || "#/";
  const respuesta = await fetch("/background", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fondo: color })
  });
  const datos = await respuesta.json();

  if (!respuesta.ok) {
    $("#errorColor").textContent = (datos.errores || ["Fondo no válido"]).join(" ");
    $("#errorColor").classList.remove("oculto");
    return false;
  }

  $("#errorColor").classList.add("oculto");
  estado.fondo = normalizarColor(datos.fondo) || COLOR_INICIAL;
  aplicarTema(estado.fondo);
  if (opciones.guardar !== false) localStorage.setItem(CLAVE_FONDO, estado.fondo);
  marcarPresetActivo();
  window.location.hash = destino;
  return true;
}

function dibujarPresets(fondos) {
  const contenedor = $("#presets");
  contenedor.innerHTML = "";
  for (const item of fondos) {
    const boton = document.createElement("button");
    boton.className = "preset";
    boton.dataset.color = normalizarColor(item.color);
    boton.innerHTML = `<span class="muestra"></span><span>${item.nombre}</span>`;
    boton.querySelector(".muestra").style.background = item.color;
    boton.addEventListener("click", () => fijarFondo(boton.dataset.color));
    contenedor.appendChild(boton);
  }
  marcarPresetActivo();
}

function marcarPresetActivo() {
  document.querySelectorAll(".preset").forEach((boton) => {
    boton.classList.toggle("activo", boton.dataset.color === estado.fondo);
  });
}

/* ======================================================================== */
/* 3. Navegación (vistas #/, #/historial, #/background)                     */
/* ======================================================================== */
function vistaActual() {
  const hash = window.location.hash;
  if (hash.startsWith("#/historial")) return "historial";
  if (hash.startsWith("#/background")) return "background";
  return "analisis";
}

function mostrarVista() {
  const vista = vistaActual();
  if (vista !== "analisis") detenerReproduccion();
  $("#vista-analisis").classList.toggle("oculto", vista !== "analisis");
  $("#vista-historial").classList.toggle("oculto", vista !== "historial");
  $("#vista-background").classList.toggle("oculto", vista !== "background");

  document.querySelectorAll(".barra nav a").forEach((enlace) => {
    enlace.classList.toggle("activa", enlace.dataset.vista === vista);
  });

  if (vista === "historial") cargarHistorial();
  if (vista === "analisis") requestAnimationFrame(ajustarDiagrama);
}

/* ======================================================================== */
/* 4. Editor: ejemplo, atajos y validación automática (POST /validar)        */
/* ======================================================================== */
function avisar(mensaje, esError) {
  const aviso = $("#aviso");
  aviso.textContent = mensaje;
  aviso.classList.toggle("error", Boolean(esError));
}

function programarValidacion() {
  clearTimeout(estado.temporizadorValidacion);
  estado.temporizadorValidacion = setTimeout(validar, ESPERA_VALIDACION);
}

async function validar() {
  // Se envía el texto tal cual (sin trim): así los números de línea que
  // devuelve el compilador coinciden con los del editor.
  const codigo = $("#codigo").value;
  if (!codigo.trim()) return;

  // Se cancela la validación anterior si todavía no ha respondido.
  if (estado.controladorValidacion) estado.controladorValidacion.abort();
  const controlador = new AbortController();
  estado.controladorValidacion = controlador;

  try {
    const respuesta = await fetch("/validar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ codigo }),
      signal: controlador.signal
    });
    const datos = await respuesta.json();
    // La validación aporta los tokens para ubicar la columna del error.
    estado.tokens = datos.tokens || [];
    estado.ast = datos.ast || null;
    estado.tablaSimbolos = datos.tabla_simbolos || [];
    pintarTokens(estado.tokens);
    pintarAst();
    pintarTablaSimbolos();
    pintarErrores(datos.errores || [], {
      automatico: true,
      advertencias: datos.advertencias || []
    });
  } catch (error) {
    if (error.name !== "AbortError") {
      avisar(`No se pudo validar: ${error}`, true);
    }
  }
}

// El compilador analiza el texto tal cual y conserva los comentarios y las
// líneas vacías, así que los números de línea que devuelve ya son los del
// editor: no hay que aplicar ningún desplazamiento.
function saltarALinea(linea) {
  const editor = $("#codigo");
  const lineas = editor.value.split("\n");
  if (!linea || linea < 1 || linea > lineas.length) return;

  let inicio = 0;
  for (let i = 0; i < linea - 1; i++) inicio += lineas[i].length + 1;
  const fin = inicio + lineas[linea - 1].length;

  editor.focus();
  editor.setSelectionRange(inicio, fin);
  // Altura de línea aproximada (14 px de fuente * 1.6) para centrar la línea.
  const alturaLinea = 22;
  editor.scrollTop = Math.max(0, (linea - 3) * alturaLinea);
}

/* ======================================================================== */
/* 5. Análisis (POST /analizar)                                              */
/* ======================================================================== */
async function analizar() {
  const boton = $("#analizar");
  const codigo = $("#codigo").value;

  if (!codigo.trim()) {
    avisar("Escribe un circuito o pulsa «Cargar ejemplo».", true);
    return;
  }

  boton.disabled = true;
  detenerReproduccion();
  const inicio = performance.now();
  avisar("Analizando...");
  $("#errorColor").classList.add("oculto");

  try {
    const respuesta = await fetch("/analizar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ codigo, fondo: estado.fondo })
    });
    const datos = await respuesta.json();
    mostrarResultado(datos, (performance.now() - inicio) / 1000);
  } catch (error) {
    avisar(`No se pudo analizar: ${error}`, true);
  } finally {
    boton.disabled = false;
  }
}

function mostrarResultado(datos, segundos) {
  estado.resultado = datos;
  estado.tokens = datos.tokens || [];
  estado.ast = datos.ast || null;
  estado.tablaSimbolos = datos.tabla_simbolos || [];

  const tabla = datos.tabla_verdad || {};
  const filas = tabla.filas || [];

  $("#resumen").classList.remove("oculto");
  $("#datoCompuertas").textContent = (datos.compuertas || []).length;
  $("#datoFilas").textContent = filas.length;
  $("#datoColumnas").textContent = (tabla.señales || []).length;
  $("#datoTiempo").textContent = segundos.toFixed(1);

  const errores = datos.errores || [];
  pintarErrores(errores, { advertencias: datos.advertencias || [] });
  pintarDiagrama(datos.diagrama_svg || "");
  pintarTablaVerdad(tabla);
  pintarExpresiones();
  pintarTokens(estado.tokens);
  pintarAst();
  pintarTablaSimbolos();
  prepararDepurador(datos);

  const hayDiagrama = Boolean(datos.diagrama_svg);
  $("#botonExportar").disabled = !datos.exito;
  $("#descargarSvg").disabled = !hayDiagrama;

  if (datos.exito) {
    avisar(`Análisis exitoso en ${segundos.toFixed(1)} s.`, false);
    if (estado.pestanaActiva === "errores" && errores.length === 0) {
      activarPestana("diagrama");
    }
  } else {
    avisar(`${errores.length} error(es). Revisa la pestaña «Errores».`, true);
    if (!hayDiagrama) {
      $("#diagramaVacio").textContent = "Sin diagrama: el circuito tiene errores.";
    }
  }

  // La vista Historial refleja el análisis recién registrado.
  if (vistaActual() === "historial") cargarHistorial();
}

function prepararDepurador(datos) {
  detenerReproduccion();
  const depurador = estado.depurador;
  depurador.indice = 0;
  depurador.pasos = [];
  depurador.valoresEntrada = Object.fromEntries(
    (datos.entradas || []).map((senal) => [senal, 0])
  );

  const disponible = Boolean(
    datos.exito && datos.tabla_verdad?.filas?.length &&
    datos.orden_topologico?.length
  );
  $("#simuladorPasos").classList.toggle("oculto", !disponible);
  $("#pasosVacio").classList.toggle("oculto", disponible);

  if (!disponible) {
    $("#pasosVacio").textContent = datos.exito
      ? "No hay pasos de compuerta para mostrar."
      : "Analiza un circuito válido para ejecutar sus compuertas paso a paso.";
    $("#entradasPaso").replaceChildren();
    $("#listaPasos").replaceChildren();
    return;
  }

  pintarEntradasSimulacion();
  pintarDepurador();
}

function pintarEntradasSimulacion() {
  const contenedor = $("#entradasPaso");
  contenedor.replaceChildren();

  for (const senal of estado.resultado.entradas || []) {
    const boton = document.createElement("button");
    const valor = estado.depurador.valoresEntrada[senal];
    boton.type = "button";
    boton.className = "entrada-simulacion";
    boton.setAttribute("aria-pressed", String(valor === 1));
    boton.setAttribute("aria-label", `Cambiar entrada ${senal}, valor actual ${valor}`);
    const nombre = document.createElement("span");
    nombre.className = "mono";
    nombre.textContent = senal;
    const indicador = document.createElement("strong");
    indicador.textContent = String(valor);
    boton.append(nombre, indicador);
    boton.classList.toggle("activa", valor === 1);
    boton.addEventListener("click", () => {
      detenerReproduccion();
      estado.depurador.valoresEntrada[senal] =
        estado.depurador.valoresEntrada[senal] === 1 ? 0 : 1;
      estado.depurador.indice = 0;
      pintarEntradasSimulacion();
      pintarDepurador();
    });
    contenedor.appendChild(boton);
  }
}

function valoresDeCombinacionActual() {
  const tabla = estado.resultado?.tabla_verdad;
  if (!tabla?.señales || !tabla?.filas) return null;

  const entradas = estado.resultado.entradas || [];
  const indices = entradas.map((senal) => tabla.señales.indexOf(senal));
  if (indices.some((indice) => indice < 0)) return null;

  const fila = tabla.filas.find((candidata) =>
    indices.every((indice, posicion) =>
      candidata[indice] === estado.depurador.valoresEntrada[entradas[posicion]])
  );
  if (!fila) return null;

  return Object.fromEntries(tabla.señales.map((senal, indice) => [senal, fila[indice]]));
}

function pasosDeCombinacion(valores) {
  if (!valores) return null;
  return (estado.resultado.orden_topologico || []).map((compuerta) => ({
    compuerta: compuerta.compuerta,
    salida: compuerta.salida,
    linea: compuerta.linea,
    entradas: compuerta.entradas.map((senal) => ({
      senal,
      valor: valores[senal],
    })),
    valor: valores[compuerta.salida],
  }));
}

function pintarDepurador() {
  const depurador = estado.depurador;
  const valores = valoresDeCombinacionActual();
  const pasos = pasosDeCombinacion(valores);
  const lista = $("#listaPasos");
  lista.replaceChildren();

  if (!pasos) {
    depurador.pasos = [];
    $("#contadorPasos").textContent = "No se encontró esa combinación.";
    $("#tituloPasoActual").textContent = "No se pudo simular";
    $("#detallePasoActual").textContent = "";
    $("#resultadoSimulacion").textContent = "";
    return;
  }

  depurador.pasos = pasos;
  depurador.indice = limitar(depurador.indice, 0, pasos.length - 1);
  const pasoActual = pasos[depurador.indice];
  $("#contadorPasos").textContent = `Paso ${depurador.indice + 1} de ${pasos.length}`;
  $("#tituloPasoActual").textContent =
    `${pasoActual.compuerta} → ${pasoActual.salida} (línea ${pasoActual.linea})`;
  $("#detallePasoActual").textContent =
    `${pasoActual.compuerta}[${pasoActual.entradas
      .map(({ senal, valor }) => `${senal}=${valor}`)
      .join(", ")}] → ${pasoActual.salida} = ${pasoActual.valor}`;

  const compuertas = estado.resultado.compuertas || [];
  const usadas = new Set(compuertas.flatMap((compuerta) => compuerta.entradas));
  const salidas = compuertas
    .map((compuerta) => compuerta.salida)
    .filter((senal) => !usadas.has(senal));
  $("#resultadoSimulacion").textContent =
    depurador.indice === pasos.length - 1
      ? `Salidas: ${salidas.map((senal) => `${senal} = ${
          valores[senal]
        }`).join(" · ")}`
      : "Las salidas finales aparecerán al terminar los pasos.";

  pasos.forEach((paso, indice) => {
    const elemento = document.createElement("li");
    const boton = document.createElement("button");
    const pendiente = indice > depurador.indice;
    boton.type = "button";
    boton.className = "paso-item";
    if (indice === depurador.indice) {
      boton.setAttribute("aria-current", "step");
    }

    const cuerpo = pendiente
      ? `${paso.compuerta} → ${paso.salida} (pendiente)`
      : `${paso.compuerta}[${paso.entradas
          .map(({ senal, valor }) => `${senal}=${valor}`)
          .join(", ")}] → ${paso.salida} = ${paso.valor}`;
    boton.textContent = `${indice + 1}. ${cuerpo}`;
    boton.addEventListener("click", () => {
      detenerReproduccion();
      depurador.indice = indice;
      pintarDepurador();
    });
    elemento.appendChild(boton);
    lista.appendChild(elemento);
  });

  $("#pasoPrimero").disabled = depurador.indice === 0;
  $("#pasoAnterior").disabled = depurador.indice === 0;
  $("#pasoSiguiente").disabled = depurador.indice === pasos.length - 1;
  $("#pasoUltimo").disabled = depurador.indice === pasos.length - 1;
  $("#pasoReproducir").disabled = pasos.length < 2;
  $("#pasoReproducir").setAttribute(
    "aria-pressed",
    String(depurador.temporizador !== null)
  );
  $("#pasoReproducir").textContent =
    depurador.temporizador !== null ? "⏸ Pausar" : "▶ Reproducir";
}

function detenerReproduccion() {
  if (estado.depurador.temporizador !== null) {
    clearInterval(estado.depurador.temporizador);
    estado.depurador.temporizador = null;
  }
  const boton = $("#pasoReproducir");
  if (boton) {
    boton.textContent = "▶ Reproducir";
    boton.setAttribute("aria-pressed", "false");
  }
}

function cambiarPaso(indice) {
  detenerReproduccion();
  if (!estado.depurador.pasos.length) return;
  estado.depurador.indice = limitar(indice, 0, estado.depurador.pasos.length - 1);
  pintarDepurador();
}

function alternarReproduccion() {
  const depurador = estado.depurador;
  if (depurador.temporizador !== null) {
    detenerReproduccion();
    pintarDepurador();
    return;
  }
  if (depurador.pasos.length < 2) return;
  if (depurador.indice === depurador.pasos.length - 1) depurador.indice = 0;

  depurador.temporizador = setInterval(() => {
    if (depurador.indice >= depurador.pasos.length - 1) {
      detenerReproduccion();
      pintarDepurador();
      return;
    }
    depurador.indice += 1;
    pintarDepurador();
    if (depurador.indice === depurador.pasos.length - 1) {
      detenerReproduccion();
      pintarDepurador();
    }
  }, INTERVALO_PASOS_MS);
  pintarDepurador();
}

/* ======================================================================== */
/* 6. Pestañas del panel de resultados                                       */
/* ======================================================================== */
function activarPestana(nombre) {
  estado.pestanaActiva = nombre;
  document.querySelectorAll(".pestana").forEach((pestana) => {
    pestana.classList.toggle("activa", pestana.dataset.panel === nombre);
  });
  document.querySelectorAll(".panel-contenido").forEach((panel) => {
    panel.classList.toggle("activa", panel.id === `panel-${nombre}`);
  });
  if (nombre === "diagrama") requestAnimationFrame(ajustarDiagrama);
}

function actualizarPestanaErrores(cantidad, advertencias = 0) {
  const pestana = document.querySelector('.pestana[data-panel="errores"]');
  $("#badgeErrores").textContent = cantidad + advertencias;
  pestana.classList.toggle("oculto", cantidad === 0 && advertencias === 0);
}

/* ======================================================================== */
/* 7. Diagrama: zoom con rueda, desplazamiento, ajustar y pantalla completa  */
/* ======================================================================== */
function tamañoNatural(svg) {
  const vista = svg.getAttribute("viewBox");
  if (vista) {
    const partes = vista.split(/\s+/).map(Number);
    if (partes.length === 4 && partes[2] > 0 && partes[3] > 0) {
      return { ancho: partes[2], alto: partes[3] };
    }
  }
  return {
    ancho: parseFloat(svg.getAttribute("width")) || 1000,
    alto: parseFloat(svg.getAttribute("height")) || 600
  };
}

function pintarDiagrama(svgTexto) {
  const vacio = $("#diagramaVacio");
  if (!svgTexto) {
    lienzo.innerHTML = "";
    vacio.classList.remove("oculto");
    vacio.textContent = "Analiza un circuito para ver el diagrama.";
    return;
  }

  vacio.classList.add("oculto");
  lienzo.innerHTML = svgTexto;

  const svg = lienzo.querySelector("svg");
  if (!svg) return;
  const natural = tamañoNatural(svg);
  svg.removeAttribute("width");
  svg.removeAttribute("height");
  svg.style.width = natural.ancho + "px";
  svg.style.height = natural.alto + "px";

  estado.autoAjustar = true;
  ajustarDiagrama();
}

function aplicarTransform() {
  const { k, tx, ty } = estado.zoom;
  lienzo.style.transform = `translate(${tx}px, ${ty}px) scale(${k})`;
  const porcentaje = Math.round(k * 100) + "%";
  $("#zoomValor").textContent = porcentaje;
  $("#modalZoomValor").textContent = porcentaje;
}

function ajustarDiagrama() {
  const contenedor = lienzo.parentElement;
  const ancho = contenedor.clientWidth;
  const alto = contenedor.clientHeight;
  const svg = lienzo.querySelector("svg");
  if (!svg || !ancho || !alto) return;

  const natural = tamañoNatural(svg);
  const k = Math.min(1, (ancho - 24) / natural.ancho);
  estado.zoom.k = limitar(k, ZOOM_MINIMO, ZOOM_MAXIMO);
  estado.zoom.tx = (ancho - natural.ancho * estado.zoom.k) / 2;
  estado.zoom.ty = (alto - natural.alto * estado.zoom.k) / 2;
  aplicarTransform();
}

function zoomEn(x, y, factor) {
  const { k, tx, ty } = estado.zoom;
  const nuevo = limitar(k * factor, ZOOM_MINIMO, ZOOM_MAXIMO);
  // Se mantiene fijo el punto del cursor mientras se hace zoom.
  const mundoX = (x - tx) / k;
  const mundoY = (y - ty) / k;
  estado.zoom.k = nuevo;
  estado.zoom.tx = x - mundoX * nuevo;
  estado.zoom.ty = y - mundoY * nuevo;
  estado.autoAjustar = false;
  aplicarTransform();
}

function conectarVisor(visor) {
  visor.addEventListener("wheel", (evento) => {
    const svg = lienzo.querySelector("svg");
    if (!svg) return;
    evento.preventDefault();
    const caja = visor.getBoundingClientRect();
    zoomEn(evento.clientX - caja.left, evento.clientY - caja.top,
           evento.deltaY < 0 ? 1.15 : 1 / 1.15);
  }, { passive: false });

  let arrastrando = false;
  let origen = { x: 0, y: 0 };

  visor.addEventListener("pointerdown", (evento) => {
    if (!lienzo.querySelector("svg")) return;
    arrastrando = true;
    origen = { x: evento.clientX, y: evento.clientY };
    visor.classList.add("arrastrando");
    visor.setPointerCapture(evento.pointerId);
  });

  visor.addEventListener("pointermove", (evento) => {
    if (!arrastrando) return;
    estado.zoom.tx += evento.clientX - origen.x;
    estado.zoom.ty += evento.clientY - origen.y;
    origen = { x: evento.clientX, y: evento.clientY };
    estado.autoAjustar = false;
    aplicarTransform();
  });

  const soltar = () => {
    arrastrando = false;
    visor.classList.remove("arrastrando");
  };
  visor.addEventListener("pointerup", soltar);
  visor.addEventListener("pointercancel", soltar);
  visor.addEventListener("pointerleave", soltar);
}

function zoomDesdeBoton(factor) {
  const contenedor = lienzo.parentElement;
  zoomEn(contenedor.clientWidth / 2, contenedor.clientHeight / 2, factor);
}

function abrirPantallaCompleta() {
  if (!lienzo.querySelector("svg")) return;
  $("#modalVisor").appendChild(lienzo);       // el mismo nodo, otro contenedor
  $("#modalDiagrama").classList.remove("oculto");
  estado.autoAjustar = true;
  requestAnimationFrame(ajustarDiagrama);
}

function cerrarPantallaCompleta() {
  if ($("#modalDiagrama").classList.contains("oculto")) return;
  $("#visor").appendChild(lienzo);
  $("#modalDiagrama").classList.add("oculto");
  requestAnimationFrame(ajustarDiagrama);
}

/* ======================================================================== */
/* 8. Tabla de verdad y tokens (scroll interno, filtros y bloques de filas)   */
/* ======================================================================== */
function indiceColumna(nombre) {
  return estado.tabla.senales.indexOf(nombre);
}

// La señal escrita no existe en el circuito y se pidió un valor concreto.
function filaFiltroInvalida() {
  const { senales, senalFiltro, valorFiltro } = estado.tabla;
  if (!valorFiltro || !senalFiltro) return false;
  return indiceColumna(senalFiltro) < 0;
}

function filasFiltradas() {
  const { senales, filas, senalFiltro, valorFiltro } = estado.tabla;
  const columna = senalFiltro ? indiceColumna(senalFiltro) : senales.length - 1;
  if (columna < 0) return filas;
  if (valorFiltro === "") return filas;
  return filas.filter((fila) => String(fila[columna]) === valorFiltro);
}

function pintarTablaVerdad(tablaVerdad) {
  const senales = (tablaVerdad && tablaVerdad.señales) || [];
  estado.tabla.senales = senales;
  estado.tabla.filas = (tablaVerdad && tablaVerdad.filas) || [];
  estado.tabla.mostradas = FILAS_POR_BLOQUE;

  // Sugerencias con los nombres reales del circuito: evita escribir a ciegas.
  const sugerencias = $("#listaSenales");
  sugerencias.innerHTML = "";
  for (const senal of senales) {
    const opcion = document.createElement("option");
    opcion.value = senal;
    sugerencias.appendChild(opcion);
  }

  // El filtro de salida por defecto es la última señal (la salida final).
  const filtroSalida = $("#filtroSalida");
  const ultima = senales.length ? senales[senales.length - 1] : "";
  if (!filtroSalida.dataset.tocado) filtroSalida.value = ultima;
  estado.tabla.senalFiltro = filtroSalida.value.trim() || ultima;

  pintarTabla();
}

function pintarTabla() {
  const tabla = $("#tablaVerdad");
  const total = filasFiltradas().length;
  const visibles = Math.min(estado.tabla.mostradas, total);

  tabla.innerHTML = "";
  const cabecera = document.createElement("thead");
  const filaCabecera = document.createElement("tr");
  for (const senal of estado.tabla.senales) {
    const celda = document.createElement("th");
    celda.textContent = senal;
    filaCabecera.appendChild(celda);
  }
  cabecera.appendChild(filaCabecera);
  tabla.appendChild(cabecera);

  const cuerpo = document.createElement("tbody");
  for (const fila of filasFiltradas().slice(0, visibles)) {
    const tr = document.createElement("tr");
    fila.forEach((valor, indice) => {
      const celda = document.createElement("td");
      celda.textContent = valor;
      if (esTextoNumero(valor)) {
        celda.classList.add(valor === "1" ? "uno" : "cero");
      } else if (indice > 0) {
        celda.classList.add("cero");
      }
      tr.appendChild(celda);
    });
    cuerpo.appendChild(tr);
  }
  tabla.appendChild(cuerpo);

  const descripcion = `Mostrando ${visibles} de ${total} fila(s)` +
    (estado.tabla.valorFiltro ? ` con salida = ${estado.tabla.valorFiltro}` : "");
  const info = $("#infoFilas");
  info.textContent = descripcion;
  info.classList.remove("error");
  // Si la señal escrita no existe en el circuito se avisa: sin filtro la tabla
  // se vería igual y parecería que el filtro no funciona.
  if (filaFiltroInvalida()) {
    info.textContent = `«${estado.tabla.senalFiltro}» no es una señal de este circuito` +
      ` (hay ${estado.tabla.senales.length}): se muestran todas las filas`;
  }

  const boton = $("#cargarMas");
  boton.classList.toggle("oculto", visibles >= total);
  boton.textContent = `Cargar más filas (${FILAS_POR_BLOQUE})`;
}

function pintarTokens(tokens) {
  const selector = $("#filtroToken");
  const tipos = [...new Set(tokens.map((t) => t.token))].sort();
  const elegido = selector.value;
  selector.innerHTML = '<option value="">Todos</option>';
  for (const tipo of tipos) {
    const opcion = document.createElement("option");
    opcion.value = tipo;
    opcion.textContent = tipo;
    selector.appendChild(opcion);
  }
  if (tipos.includes(elegido)) selector.value = elegido;

  pintarTablaTokens();
}

function pintarTablaTokens() {
  const tabla = $("#tablaTokens");
  const filtro = $("#filtroToken").value;
  const tokens = filtro ? estado.tokens.filter((t) => t.token === filtro) : estado.tokens;

  tabla.innerHTML = "<thead><tr><th>Token</th><th>Valor</th><th>Línea</th><th>Columna</th></tr></thead>";
  const cuerpo = document.createElement("tbody");
  for (const t of tokens) {
    const fila = document.createElement("tr");
    for (const valor of [t.token, JSON.stringify(t.valor), t.linea, t.columna]) {
      const celda = document.createElement("td");
      celda.textContent = valor;
      fila.appendChild(celda);
    }
    cuerpo.appendChild(fila);
  }
  tabla.appendChild(cuerpo);
  $("#infoTokens").textContent = `${tokens.length} de ${estado.tokens.length} token(s)`;
}

function pintarAst() {
  const arbol = $("#arbolSintactico");
  const disponible = Boolean(estado.ast);
  arbol.textContent = disponible ? JSON.stringify(estado.ast, null, 2) : "";
  arbol.classList.toggle("oculto", !disponible);
  $("#arbolVacio").classList.toggle("oculto", disponible);
}

function pintarTablaSimbolos() {
  const tabla = $("#tablaSimbolos");
  const simbolos = estado.tablaSimbolos;
  tabla.innerHTML = "<thead><tr><th>Señal</th><th>Tipo</th><th>Línea de declaración</th><th>Líneas de uso</th></tr></thead>";
  const cuerpo = document.createElement("tbody");
  for (const simbolo of simbolos) {
    const fila = document.createElement("tr");
    for (const valor of [
      simbolo.senal,
      simbolo.tipo,
      simbolo.linea_declaracion,
      simbolo.lineas_uso.join(", ") || "—"
    ]) {
      const celda = document.createElement("td");
      celda.textContent = valor;
      fila.appendChild(celda);
    }
    cuerpo.appendChild(fila);
  }
  tabla.appendChild(cuerpo);
  const disponible = simbolos.length > 0;
  tabla.classList.toggle("oculto", !disponible);
  $("#simbolosVacio").classList.toggle("oculto", disponible);
}

/* ======================================================================== */
/* 9. Expresiones booleanas (forma intermedia y expandida)                   */
/* ======================================================================== */
function expresionDe(salida) {
  // El backend manda las dos notaciones ya calculadas: aquí solo se elige
  // cuál mostrar según el selector, sin reescribir operadores.
  const datos = (estado.resultado?.expresiones_booleanas || {})[salida];
  if (!datos) return null;

  const ascii = estado.expresionNotacion === "ascii";
  return {
    intermedia: ascii ? datos.intermedia_ascii : datos.intermedia,
    expandida: ascii ? datos.expandida_ascii : datos.expandida,
    aviso: datos.aviso,
  };
}

function pintarExpresiones() {
  const contenedor = $("#listaExpresiones");
  const vacio = $("#expresionVacio");
  const salidas = Object.keys(estado.resultado?.expresiones_booleanas || {});

  contenedor.innerHTML = "";
  vacio.classList.toggle("oculto", salidas.length > 0);

  for (const salida of salidas) {
    const datos = expresionDe(salida);
    if (!datos) continue;

    const bloque = document.createElement("section");
    bloque.className = "bloque-expresion";

    const titulo = document.createElement("h3");
    titulo.textContent = `Expresión de ${salida}`;
    bloque.appendChild(titulo);

    const etiquetaIntermedia = document.createElement("h4");
    etiquetaIntermedia.textContent = "Forma intermedia";
    bloque.appendChild(etiquetaIntermedia);

    const intermedia = document.createElement("pre");
    intermedia.className = "codigo-expresion mono";
    intermedia.textContent = datos.intermedia.join("\n");
    bloque.appendChild(intermedia);

    const etiquetaExpandida = document.createElement("h4");
    etiquetaExpandida.textContent = "Forma expandida";
    bloque.appendChild(etiquetaExpandida);

    if (datos.expandida) {
      const expandida = document.createElement("pre");
      expandida.className = "codigo-expresion mono";
      expandida.textContent = datos.expandida;
      bloque.appendChild(expandida);
    } else {
      const aviso = document.createElement("p");
      aviso.className = "aviso-expresion";
      aviso.textContent = datos.aviso || "Expresión expandida no disponible.";
      bloque.appendChild(aviso);
    }

    contenedor.appendChild(bloque);
  }

  const omitidas = salidas.filter((s) => !expresionDe(s).expandida).length;
  $("#infoExpresion").textContent =
    `${salidas.length} salida(s)` + (omitidas ? `, ${omitidas} sin expandir` : "");
  $("#copiarExpresion").disabled = salidas.length === 0;
}

function textoParaCopiar() {
  const salidas = Object.keys(estado.resultado?.expresiones_booleanas || {});
  const partes = [];

  for (const salida of salidas) {
    const datos = expresionDe(salida);
    if (!datos) continue;

    partes.push(`// ${salida} — forma intermedia`);
    partes.push(...datos.intermedia);
    partes.push("");
    if (datos.expandida) {
      partes.push(`// ${salida} — forma expandida`);
      partes.push(datos.expandida);
    } else {
      partes.push(`// ${salida} — ${datos.aviso}`);
    }
    partes.push("");
  }

  return partes.join("\n");
}

async function copiarExpresiones() {
  const texto = textoParaCopiar();
  if (!texto) return;

  try {
    await navigator.clipboard.writeText(texto);
    avisar("Expresiones copiadas al portapapeles.", false);
  } catch {
    // Sin permiso de portapapeles (contexto no seguro) se usa el copia de
    // siempre con un textarea oculto.
    const auxiliar = document.createElement("textarea");
    auxiliar.value = texto;
    auxiliar.setAttribute("readonly", "");
    auxiliar.style.position = "fixed";
    auxiliar.style.opacity = "0";
    document.body.appendChild(auxiliar);
    auxiliar.select();
    const copiado = document.execCommand("copy");
    auxiliar.remove();
    avisar(copiado
      ? "Expresiones copiadas al portapapeles."
      : "No se pudo copiar al portapapeles.", copiado);
  }
}

/* ======================================================================== */
/* 10. Errores (con salto a la línea del editor)                             */
/* ======================================================================== */
function analizarError(mensaje) {
  const texto = String(mensaje);
  const coincidencia = /^(Error|Advertencia)(?:\s+(\S+))?\s+línea\s+(\d+)(?:[^:]*columna\s+(\d+))?:\s*([\s\S]*)$/i.exec(texto);
  if (coincidencia) {
    return {
      tipo: coincidencia[2] || coincidencia[1],
      linea: parseInt(coincidencia[3], 10),
      columna: coincidencia[4] ? parseInt(coincidencia[4], 10) : null,
      mensaje: coincidencia[5]
    };
  }
  return { tipo: "Error", linea: null, columna: null, mensaje: texto };
}

function columnaDeLinea(linea) {
  if (!linea) return null;
  const token = estado.tokens.find((t) => t.linea === linea);
  return token ? token.columna : null;
}

function pintarErrores(errores, opciones = {}) {
  const lista = $("#listaErrores");
  const listaAdvertencias = $("#listaAdvertencias");
  const advertencias = opciones.advertencias || [];
  lista.innerHTML = "";
  listaAdvertencias.innerHTML = "";

  for (const mensaje of errores) {
    const info = analizarError(mensaje);
    const item = document.createElement("li");

    const posicion = document.createElement("span");
    posicion.className = "posicion";
    const columna = info.columna !== null ? info.columna : columnaDeLinea(info.linea);
    posicion.textContent = info.linea
      ? `línea ${info.linea}${columna !== null ? `, col ${columna}` : ""}`
      : "general";

    const cuerpo = document.createElement("span");
    cuerpo.textContent = `${info.tipo}: ${info.mensaje}`;

    const detalle = document.createElement("span");
    detalle.className = "detalle";
    detalle.textContent = "Clic para ir a esa línea del circuito";

    item.appendChild(posicion);
    item.appendChild(cuerpo);
    item.appendChild(detalle);
    if (info.linea) item.addEventListener("click", () => saltarALinea(info.linea));
    lista.appendChild(item);
  }

  for (const mensaje of advertencias) {
    const info = analizarError(mensaje);
    const item = document.createElement("li");
    item.classList.add("advertencia");

    const posicion = document.createElement("span");
    posicion.className = "posicion";
    posicion.textContent = info.linea ? `línea ${info.linea}` : "general";

    const cuerpo = document.createElement("span");
    cuerpo.textContent = `${info.tipo}: ${info.mensaje}`;

    item.appendChild(posicion);
    item.appendChild(cuerpo);
    if (info.linea) item.addEventListener("click", () => saltarALinea(info.linea));
    listaAdvertencias.appendChild(item);
  }

  actualizarPestanaErrores(errores.length, advertencias.length);
  // Con validación automática solo se muestran; el resultado anterior se conserva.
  if (errores.length > 0 && !opciones.automatico) activarPestana("errores");
}

/* ======================================================================== */
/* 11. Historial (rutas GET/DELETE /historial)                               */
/* ======================================================================== */
function formatoFecha(iso) {
  if (!iso) return "sin fecha";
  const fecha = new Date(iso);
  if (Number.isNaN(fecha.getTime())) return iso;
  return fecha.toLocaleString("es", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit"
  });
}

function cargarEnEditor(entrada) {
  $("#codigo").value = entrada;
  avisar("Circuito cargado del historial. Pulsa «Analizar» para ejecutarlo.", false);
  window.location.hash = "#/";
  mostrarVista();
}

async function cargarHistorial() {
  const lista = $("#listaHistorial");
  try {
    const datos = await (await fetch("/historial")).json();
    const analisis = datos.analisis || [];
    lista.innerHTML = "";

    if (analisis.length === 0) {
      lista.innerHTML = '<p class="ayuda">Todavía no hay análisis. Analiza un circuito.</p>';
      return;
    }

    for (const item of analisis.slice().reverse()) {
      const compuertas = (item.entrada.match(/->/g) || []).length;
      const tarjeta = document.createElement("article");
      tarjeta.className = "tarjeta";

      const cabecera = document.createElement("div");
      cabecera.className = "tarjeta-cabecera";
      const chip = document.createElement("span");
      chip.className = "estado-chip" + (item.resultado ? "" : " error");
      chip.textContent = item.resultado ? "EXITOSO" : "ERRORES";
      const fecha = document.createElement("span");
      fecha.className = "fecha";
      fecha.textContent = formatoFecha(item.fecha);
      const meta = document.createElement("span");
      meta.className = "meta";
      meta.textContent = `${compuertas} compuerta(s)` +
        (item.resultado ? "" : ` · ${(item.errores || []).length} error(es)`);
      cabecera.append(chip, fecha, meta);

      const primera = document.createElement("pre");
      primera.className = "primera-linea mono";
      primera.textContent = item.primera_linea || "(vacío)";

      const acciones = document.createElement("div");
      acciones.className = "tarjeta-acciones";
      const cargar = document.createElement("button");
      cargar.textContent = "Cargar en el editor";
      const borrar = document.createElement("button");
      borrar.className = "borrar";
      borrar.textContent = "Borrar";
      acciones.append(cargar, borrar);

      tarjeta.append(cabecera, primera, acciones);
      tarjeta.addEventListener("click", (evento) => {
        if (evento.target.closest("button")) return;
        cargarEnEditor(item.entrada);
      });
      cargar.addEventListener("click", () => cargarEnEditor(item.entrada));
      borrar.addEventListener("click", async () => {
        await fetch(`/historial/${item.indice}`, { method: "DELETE" });
        cargarHistorial();
      });

      lista.appendChild(tarjeta);
    }
  } catch (error) {
    lista.innerHTML = `<p class="error">No se pudo leer el historial: ${error}</p>`;
  }
}

async function limpiarHistorial() {
  if (!confirm("¿Borrar todo el historial de análisis? Esta acción no se puede deshacer.")) return;
  await fetch("/historial", { method: "DELETE" });
  cargarHistorial();
}

/* ======================================================================== */
/* 12. Exportar (SVG, CSV y JSON desde la respuesta de /analizar)            */
/* ======================================================================== */
function descargar(texto, nombre, tipo) {
  const url = URL.createObjectURL(new Blob([texto], { type: tipo }));
  const enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = nombre;
  document.body.appendChild(enlace);
  enlace.click();
  enlace.remove();
  URL.revokeObjectURL(url);
}

function exportar(tipo) {
  const datos = estado.resultado;
  if (!datos || !datos.exito) return;

  if (tipo === "svg") {
    descargar(Exportacion.construirSVG(datos),
              Exportacion.nombreArchivo("svg"), "image/svg+xml");
  } else if (tipo === "csv") {
    descargar(Exportacion.construirCSV(datos.tabla_verdad),
              Exportacion.nombreArchivo("csv"), "text/csv");
  } else if (tipo === "json") {
    descargar(Exportacion.construirJSON(datos),
              Exportacion.nombreArchivo("json"), "application/json");
  }
  cerrarMenuExportar();
}

/* ======================================================================== */
/* 13. Inicio                                                                */
/* ======================================================================== */
function cerrarMenuExportar() {
  $("#listaExportar").classList.add("oculto");
}

function toggleMenuExportar() {
  $("#listaExportar").classList.toggle("oculto");
}

function conectarEventos() {
  // Editor
  $("#analizar").addEventListener("click", analizar);
  $("#ejemplo").addEventListener("click", () => {
    $("#codigo").value = EJEMPLO;
    avisar("Ejemplo cargado. Pulsa «Analizar».", false);
  });
  $("#codigo").addEventListener("input", programarValidacion);
  $("#codigo").addEventListener("keydown", (evento) => {
    if (evento.key === "Enter" && (evento.ctrlKey || evento.metaKey)) {
      evento.preventDefault();
      analizar();
    }
  });

  // Navegación
  window.addEventListener("hashchange", mostrarVista);

  // Pestañas
  document.querySelectorAll(".pestana").forEach((pestana) => {
    pestana.addEventListener("click", () => activarPestana(pestana.dataset.panel));
  });

  // Diagrama
  conectarVisor($("#visor"));
  conectarVisor($("#modalVisor"));
  $("#zoomMas").addEventListener("click", () => zoomDesdeBoton(1.2));
  $("#zoomMenos").addEventListener("click", () => zoomDesdeBoton(1 / 1.2));
  $("#zoomAjustar").addEventListener("click", ajustarDiagrama);
  $("#pantallaCompleta").addEventListener("click", abrirPantallaCompleta);
  $("#modalCerrar").addEventListener("click", cerrarPantallaCompleta);
  $("#modalMas").addEventListener("click", () => zoomDesdeBoton(1.2));
  $("#modalMenos").addEventListener("click", () => zoomDesdeBoton(1 / 1.2));
  $("#modalAjustar").addEventListener("click", ajustarDiagrama);

  // Tabla de verdad y tokens
  $("#filtroSalida").addEventListener("input", (evento) => {
    evento.target.dataset.tocado = "1";
    estado.tabla.senalFiltro = evento.target.value.trim();
    estado.tabla.mostradas = FILAS_POR_BLOQUE;
    pintarTabla();
  });
  $("#filtroValor").addEventListener("change", (evento) => {
    estado.tabla.valorFiltro = evento.target.value;
    estado.tabla.mostradas = FILAS_POR_BLOQUE;
    pintarTabla();
  });
  $("#cargarMas").addEventListener("click", () => {
    estado.tabla.mostradas += FILAS_POR_BLOQUE;
    pintarTabla();
  });
  $("#tablaScroll").addEventListener("scroll", (evento) => {
    const caja = evento.target;
    if (caja.scrollTop + caja.clientHeight >= caja.scrollHeight - 40) {
      const total = filasFiltradas().length;
      if (estado.tabla.mostradas < total) {
        estado.tabla.mostradas += FILAS_POR_BLOQUE;
        pintarTabla();
      }
    }
  });
  $("#filtroToken").addEventListener("change", pintarTablaTokens);

  // Depurador por pasos sobre la tabla de verdad y el orden topológico.
  $("#pasoPrimero").addEventListener("click", () => cambiarPaso(0));
  $("#pasoAnterior").addEventListener("click", () =>
    cambiarPaso(estado.depurador.indice - 1));
  $("#pasoReproducir").addEventListener("click", alternarReproduccion);
  $("#pasoSiguiente").addEventListener("click", () =>
    cambiarPaso(estado.depurador.indice + 1));
  $("#pasoUltimo").addEventListener("click", () =>
    cambiarPaso(estado.depurador.pasos.length - 1));

  // Expresiones booleanas
  $("#notacionExpresion").addEventListener("change", (evento) => {
    estado.expresionNotacion = evento.target.value;
    pintarExpresiones();
  });
  $("#copiarExpresion").addEventListener("click", copiarExpresiones);

  // Exportar
  $("#botonExportar").addEventListener("click", (evento) => {
    evento.stopPropagation();
    toggleMenuExportar();
  });
  $("#listaExportar").addEventListener("click", (evento) => {
    const boton = evento.target.closest("[data-exportar]");
    if (boton) exportar(boton.dataset.exportar);
  });
  $("#descargarSvg").addEventListener("click", () => exportar("svg"));
  document.addEventListener("click", (evento) => {
    if (!evento.target.closest("#menuExportar")) cerrarMenuExportar();
  });

  // Historial
  $("#limpiarHistorial").addEventListener("click", limpiarHistorial);

  // Background
  $("#aplicarColor").addEventListener("click", () => {
    const color = normalizarColor($("#colorTexto").value || $("#colorLibre").value);
    if (!color) {
      $("#errorColor").textContent = "Color no válido: use #RGB o #RRGGBB.";
      $("#errorColor").classList.remove("oculto");
      return;
    }
    fijarFondo(color);
  });
  $("#colorRapido").addEventListener("change", (evento) => {
    fijarFondo(normalizarColor(evento.target.value));
  });
  $("#colorLibre").addEventListener("input", (evento) => {
    $("#colorTexto").value = evento.target.value.toUpperCase();
  });
  $("#restablecer").addEventListener("click", () => fijarFondo(COLOR_INICIAL));

  // Ventana y teclado
  window.addEventListener("resize", () => {
    if (estado.autoAjustar) ajustarDiagrama();
  });
  document.addEventListener("keydown", (evento) => {
    if (evento.key === "Escape") cerrarPantallaCompleta();
  });
}

function iniciar() {
  conectarEventos();
  mostrarVista();
  cargarFondo();
  actualizarPestanaErrores(0);
  pintarExpresiones();
}

document.addEventListener("DOMContentLoaded", iniciar);
