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

const COLOR_INICIAL = "#FFFFFF";
const CLAVE_FONDO = "jace.fondo";
const FILAS_POR_BLOQUE = 32;      // la tabla de verdad se dibuja de 32 en 32
const FILAS_POR_PETICION = 256;   // filas que se piden a /tabla en cada bloque
const FILAS_POR_PETICION_CSV = 4096;
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
  pestanaActiva: "tokens",       // se recuerda al volver a analizar
  subActiva: "diagrama",         // subpestaña de «6 Resultados»
  zoom: { k: 1, tx: 0, ty: 0 },
  autoAjustar: true,          // mientras sea true se reajusta al redimensionar
  // `remota` = la tabla no vino en /analizar (demasiadas entradas) y se pide
  // por bloques a /tabla; `totales` es el número real de filas.
  tabla: { senales: [], filas: [], senalFiltro: "", valorFiltro: "", mostradas: 0,
           remota: false, totales: 0, cargando: false, codigo: "" },
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
      "--tenue": "#4f5d52",
      "--panel": "rgba(255, 255, 255, 0.86)",
      "--panel-solido": "#fffefa",
      "--panel-borde": "rgba(54, 91, 61, 0.14)",
      "--acento": "#3f6f4b",
        "--acento-texto": "#ffffff",
      "--error": "#b94d48",
      "--ok": "#3a7349",
      "--menta": "#e8f1e4",
      "--celeste": "#e5f1ef",
      "--sombra": "0 16px 42px rgba(48, 72, 50, 0.09)"
      };

  variables["--fondo"] = color;
  // El degradado de la página se calcula sobre el color elegido; en oscuro
  // no debe aclararse hacia el verde pálido del tema claro.
  variables["--fondo-pagina"] = oscuro
    ? `linear-gradient(145deg, ${color}, ${color})`
    : "radial-gradient(ellipse at 9% 9%, rgba(196, 220, 183, .32), transparent 30rem)," +
      "radial-gradient(ellipse at 94% 31%, rgba(190, 224, 222, .32), transparent 33rem)," +
      `linear-gradient(145deg, ${color}, #f7f7ef 58%, #edf4ed)`;
  for (const [nombre, valor] of Object.entries(variables)) {
    document.documentElement.style.setProperty(nombre, valor);
  }
  document.documentElement.dataset.tema = oscuro ? "oscuro" : "claro";
  // Barras de desplazamiento y controles nativos acordes al tema.
  document.documentElement.style.colorScheme = oscuro ? "dark" : "light";

  $("#muestraFondo").style.background = color;
  $("#botonFondo").title = `Fondo: ${color}`;
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
    boton.addEventListener("click", async () => {
      if (await fijarFondo(boton.dataset.color)) cerrarPopoverFondo();
    });
    contenedor.appendChild(boton);
  }
  marcarPresetActivo();
  // Si el popover se abrió (por ejemplo desde #/background) antes de que
  // existieran los presets, el foco entra ahora.
  if (!$("#popoverFondo").classList.contains("oculto")) {
    (document.querySelector(".preset.activo") || document.querySelector(".preset"))?.focus();
  }
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
  return "analisis";
}

function mostrarVista() {
  // La antigua ruta #/background abre el selector de fondo de la barra.
  if (window.location.hash.startsWith("#/background")) {
    history.replaceState(null, "", "#/");
    abrirPopoverFondo();
  }
  const vista = vistaActual();
  if (vista !== "analisis") detenerReproduccion();
  $("#vista-analisis").classList.toggle("oculto", vista !== "analisis");
  $("#vista-historial").classList.toggle("oculto", vista !== "historial");

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
  if (!codigo.trim()) {
    // Editor vacío: no quedan diagnósticos de un texto que ya no existe.
    estado.tokens = [];
    estado.ast = null;
    estado.tablaSimbolos = [];
    pintarTokens(estado.tokens);
    pintarAst();
    pintarTablaSimbolos();
    pintarDiagnosticos([], { automatico: true });
    return;
  }

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
    pintarDiagnosticos(diagnosticosDe(datos), { automatico: true });
  } catch (error) {
    if (error.name !== "AbortError") {
      avisar(`No se pudo validar: ${error}`, true);
    }
  }
}

// El compilador analiza el texto tal cual y conserva los comentarios y las
// líneas vacías, así que los números de línea que devuelve ya son los del
// editor: no hay que aplicar ningún desplazamiento.
function saltarALinea(linea, columna) {
  const editor = $("#codigo");
  const lineas = editor.value.split("\n");
  if (!linea || linea < 1 || linea > lineas.length) return;

  let inicio = 0;
  for (let i = 0; i < linea - 1; i++) inicio += lineas[i].length + 1;
  const texto = lineas[linea - 1];
  let desde = inicio;
  let hasta = inicio + texto.length;

  // Con columna se selecciona exactamente la palabra (o el símbolo) señalado.
  if (columna && columna >= 1 && columna <= texto.length + 1) {
    const resto = texto.slice(columna - 1);
    const palabra = /^(->|[^\s\[\],#]+|\S)/.exec(resto);
    desde = inicio + columna - 1;
    hasta = desde + (palabra ? palabra[0].length : 0);
  }

  editor.focus();
  editor.setSelectionRange(desde, hasta);
  const estilo = getComputedStyle(editor);
  const alturaLinea = parseFloat(estilo.lineHeight) || 22;
  editor.scrollTop = Math.max(0, (linea - 3) * alturaLinea);
}

/* ======================================================================== */
/* 5. Análisis (POST /analizar)                                              */
/* ======================================================================== */
async function analizar() {
  const boton = $("#analizar");
  const codigo = $("#codigo").value;

  if (!codigo.trim()) {
    avisar("Escribe un circuito o elige uno en «Ejemplos».", true);
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
  const omitida = datos.tabla_omitida || null;

  $("#resumen").classList.remove("oculto");
  $("#datoCompuertas").textContent = (datos.compuertas || []).length;
  $("#datoFilas").textContent = (omitida ? omitida.filas_totales : filas.length)
    .toLocaleString("es");
  $("#datoColumnas").textContent = (tabla.señales || []).length;
  $("#datoTiempo").textContent = segundos.toFixed(1);

  const diagnosticos = diagnosticosDe(datos);
  const errores = diagnosticos.filter((d) => d.severidad === "error");
  pintarDiagnosticos(diagnosticos);
  pintarDiagrama(datos.diagrama_svg || "");
  pintarTablaVerdad(tabla, omitida, datos.exito ? $("#codigo").value : "");
  pintarIntermedio();
  pintarVerilog();
  pintarExpresiones();
  pintarTokens(estado.tokens);
  pintarAst();
  pintarTablaSimbolos();
  prepararDepurador(datos);

  const hayDiagrama = Boolean(datos.diagrama_svg);
  $("#botonExportar").disabled = !datos.exito;
  document.querySelector('[data-exportar="svg"]').disabled = !hayDiagrama;
  if (datos.exito && datos.diagrama_omitido) {
    $("#diagramaVacio").textContent = `${datos.diagrama_omitido.motivo}.`;
  }

  if (datos.exito) {
    avisar(`Análisis exitoso en ${segundos.toFixed(1)} s.`, false);
    if (["errores", "tokens"].includes(estado.pestanaActiva) && errores.length === 0) {
      activarPestana("resultados");
    }
    estado.codigoAnalizado = $("#codigo").value;
  } else {
    avisar(`${errores.length} error(es). Revisa la pestaña «4 Diagnósticos».`, true);
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

  const disponible = Boolean(datos.exito && datos.orden_topologico?.length);
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
    indicador.className = "valor-bit";
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

// Operación de cada compuerta sobre valores 0/1 (la misma semántica que el
// compilador: XOR/XNOR con N entradas son la paridad impar/par).
const OPERACIONES = {
  AND: (v) => v.every(Boolean),
  OR: (v) => v.some(Boolean),
  NOT: (v) => !v[0],
  XOR: (v) => v.filter(Boolean).length % 2 === 1,
  NAND: (v) => !v.every(Boolean),
  NOR: (v) => !v.some(Boolean),
  XNOR: (v) => v.filter(Boolean).length % 2 === 0,
};

// Evalúa el circuito en orden topológico con los valores que eligió el
// usuario. Antes se buscaba la fila dentro de la tabla de verdad completa,
// que ya no viaja en la respuesta cuando el circuito tiene muchas entradas.
function valoresDeCombinacionActual() {
  const resultado = estado.resultado;
  if (!resultado) return null;
  const valores = { "0": 0, "1": 1, ...estado.depurador.valoresEntrada };
  for (const compuerta of resultado.orden_topologico || []) {
    const operacion = OPERACIONES[compuerta.compuerta];
    if (!operacion) return null;
    const argumentos = compuerta.entradas.map((senal) => valores[senal]);
    if (argumentos.some((valor) => valor === undefined)) return null;
    valores[compuerta.salida] = operacion(argumentos) ? 1 : 0;
  }
  return valores;
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

  const salidas = salidasFinales();
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
    boton.textContent = cuerpo;
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
function activarPestana(nombre, opciones = {}) {
  estado.pestanaActiva = nombre;
  document.querySelectorAll(".pestana").forEach((pestana) => {
    const activa = pestana.dataset.panel === nombre;
    pestana.classList.toggle("activa", activa);
    pestana.setAttribute("aria-selected", String(activa));
    pestana.tabIndex = activa ? 0 : -1;
    if (activa && opciones.foco) pestana.focus();
  });
  document.querySelectorAll(".panel-contenido").forEach((panel) => {
    panel.classList.toggle("activa", panel.id === `panel-${nombre}`);
  });
  if (nombre === "resultados" && estado.subActiva === "diagrama") {
    requestAnimationFrame(ajustarDiagrama);
  }
}

function activarSubpestana(nombre, opciones = {}) {
  estado.subActiva = nombre;
  document.querySelectorAll(".subpestana").forEach((pestana) => {
    const activa = pestana.dataset.sub === nombre;
    pestana.classList.toggle("activa", activa);
    pestana.setAttribute("aria-selected", String(activa));
    pestana.tabIndex = activa ? 0 : -1;
    if (activa && opciones.foco) pestana.focus();
  });
  document.querySelectorAll(".subpanel").forEach((panel) => {
    panel.classList.toggle("activa", panel.id === `panel-${nombre}`);
  });
  if (nombre === "diagrama") requestAnimationFrame(ajustarDiagrama);
}

// Flechas izquierda/derecha, Inicio y Fin para moverse entre pestañas (patrón
// de pestañas accesibles de WAI-ARIA).
function navegarConTeclado(evento, selector, clave, activar) {
  const pestanas = [...document.querySelectorAll(selector)];
  const actual = pestanas.indexOf(evento.target);
  if (actual < 0) return;
  let destino = null;
  if (evento.key === "ArrowRight") destino = (actual + 1) % pestanas.length;
  else if (evento.key === "ArrowLeft") destino = (actual - 1 + pestanas.length) % pestanas.length;
  else if (evento.key === "Home") destino = 0;
  else if (evento.key === "End") destino = pestanas.length - 1;
  if (destino === null) return;
  evento.preventDefault();
  activar(pestanas[destino].dataset[clave], { foco: true });
}

function actualizarPestanaErrores(cantidad, advertencias = 0) {
  // La pestaña 4 nunca desaparece: muestra la cuenta o un ✔ si no hay nada.
  const badge = $("#badgeErrores");
  badge.classList.toggle("con-errores", cantidad > 0);
  badge.classList.toggle("con-advertencias", cantidad === 0 && advertencias > 0);
  badge.textContent = cantidad === 0 && advertencias === 0 ? "✔" : String(cantidad + advertencias);
  $("#textoBadge").textContent = cantidad === 0 && advertencias === 0
    ? "sin diagnósticos"
    : `${cantidad} error(es) y ${advertencias} advertencia(s)`;
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
  // Cabe a lo ancho y a lo alto del visor (que tiene altura acotada).
  const k = Math.min(1, (ancho - 24) / natural.ancho, (alto - 24) / natural.alto);
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

function pintarTablaVerdad(tablaVerdad, omitida = null, codigo = "") {
  const senales = (tablaVerdad && tablaVerdad.señales) || [];
  estado.tabla.senales = senales;
  estado.tabla.filas = (tablaVerdad && tablaVerdad.filas) || [];
  estado.tabla.mostradas = FILAS_POR_BLOQUE;
  estado.tabla.remota = Boolean(omitida);
  estado.tabla.totales = omitida ? omitida.filas_totales : estado.tabla.filas.length;
  estado.tabla.codigo = codigo;
  estado.tabla.cargando = false;

  // «Mostrar temporales» solo aparece si el circuito tiene compuertas anidadas.
  $("#opcionTemporales").hidden = !(estado.resultado?.temporales || []).length;

  // Tabla omitida: se avisa y se ofrece generarla por bloques.
  $("#avisoTabla").classList.toggle("oculto", !omitida);
  if (omitida) {
    $("#motivoTabla").textContent = `${omitida.motivo}. Se calcula por bloques, ` +
      "solo las filas que veas.";
    $("#generarTabla").textContent =
      `Generar tabla (${omitida.filas_totales.toLocaleString("es")} filas)`;
    $("#generarTabla").classList.remove("oculto");
    $("#tablaScroll").classList.add("oculto");
  } else {
    $("#tablaScroll").classList.remove("oculto");
  }

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

// Pide a /tabla el siguiente bloque de filas (solo esas filas se calculan).
async function cargarBloqueRemoto() {
  const tabla = estado.tabla;
  if (!tabla.remota || tabla.cargando || tabla.filas.length >= tabla.totales) return;
  tabla.cargando = true;
  $("#infoFilas").textContent = "Calculando filas...";
  try {
    const datos = await pedirFilas(tabla.codigo, tabla.filas.length, FILAS_POR_PETICION);
    if (!datos.exito) throw new Error((datos.errores || ["sin detalle"]).join(" "));
    tabla.filas.push(...datos.filas);
    tabla.mostradas = Math.max(tabla.mostradas, FILAS_POR_BLOQUE);
  } catch (error) {
    avisar(`No se pudo calcular la tabla: ${error.message || error}`, true);
  } finally {
    tabla.cargando = false;
    pintarTabla();
  }
}

async function pedirFilas(codigo, desde, cantidad) {
  const respuesta = await fetch("/tabla", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ codigo, desde, cantidad })
  });
  return respuesta.json();
}

async function generarTablaRemota() {
  $("#generarTabla").classList.add("oculto");
  $("#tablaScroll").classList.remove("oculto");
  await cargarBloqueRemoto();
}

// Índices de las columnas que se muestran: las temporales (_t1...) se ocultan
// salvo que se marque «Mostrar temporales».
function columnasVisibles() {
  const temporales = new Set(estado.resultado?.temporales || []);
  const mostrar = $("#mostrarTemporales").checked;
  return estado.tabla.senales
    .map((senal, indice) => [senal, indice])
    .filter(([senal]) => mostrar || !temporales.has(senal))
    .map(([, indice]) => indice);
}

function pintarTabla() {
  const tabla = $("#tablaVerdad");
  const filas = filasFiltradas();
  const total = filas.length;
  const visibles = Math.min(estado.tabla.mostradas, total);
  const columnas = columnasVisibles();

  tabla.innerHTML = "";
  const cabecera = document.createElement("thead");
  const filaCabecera = document.createElement("tr");
  for (const indice of columnas) {
    const celda = document.createElement("th");
    celda.textContent = estado.tabla.senales[indice];
    celda.scope = "col";
    filaCabecera.appendChild(celda);
  }
  cabecera.appendChild(filaCabecera);
  tabla.appendChild(cabecera);

  const cuerpo = document.createElement("tbody");
  for (const fila of filas.slice(0, visibles)) {
    const tr = document.createElement("tr");
    for (const indice of columnas) {
      const valor = fila[indice];
      const celda = document.createElement("td");
      celda.textContent = valor;
      celda.classList.add(String(valor) === "1" ? "uno" : "cero");
      tr.appendChild(celda);
    }
    cuerpo.appendChild(tr);
  }
  tabla.appendChild(cuerpo);

  const remota = estado.tabla.remota;
  const esperandoGenerar = remota && !$("#generarTabla").classList.contains("oculto");
  const calculadas = estado.tabla.filas.length.toLocaleString("es");
  const totales = estado.tabla.totales.toLocaleString("es");
  let descripcion;
  if (esperandoGenerar) {
    descripcion = "";
  } else if (remota) {
    descripcion = estado.tabla.valorFiltro
      ? `${visibles.toLocaleString("es")} fila(s) con salida = ${estado.tabla.valorFiltro} ` +
        `entre las ${calculadas} calculadas de ${totales}`
      : `Mostrando ${visibles.toLocaleString("es")} fila(s) de ${totales}`;
  } else {
    descripcion = `Mostrando ${visibles} de ${total} fila(s)` +
      (estado.tabla.valorFiltro ? ` con salida = ${estado.tabla.valorFiltro}` : "");
  }
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
  const quedanLocales = visibles < total;
  const quedanRemotas = remota && !esperandoGenerar &&
    estado.tabla.filas.length < estado.tabla.totales;
  boton.classList.toggle("oculto", !(quedanLocales || quedanRemotas));
  boton.textContent = quedanLocales
    ? `Mostrar ${FILAS_POR_BLOQUE} filas más`
    : `Calcular ${FILAS_POR_PETICION} filas más`;
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

const NOMBRE_NODO = {
  circuito: "Circuito",
  declaracion_entradas: "Entradas",
  declaracion_salidas: "Salidas",
  asignacion: "Asignación",
  compuerta: "Compuerta",
  senal: "Señal",
  constante: "Constante",
};

function etiquetaNodo(nodo) {
  const boton = document.createElement("button");
  boton.type = "button";
  boton.className = `nodo-arbol nodo-${nodo.tipo}`;
  const tipo = document.createElement("span");
  tipo.className = "nodo-tipo";
  tipo.textContent = NOMBRE_NODO[nodo.tipo] || nodo.tipo;
  boton.appendChild(tipo);
  if (nodo.valor !== undefined) {
    const valor = document.createElement("span");
    valor.className = "nodo-valor mono";
    valor.textContent = nodo.tipo === "asignacion" ? `→ ${nodo.valor}` : nodo.valor;
    boton.appendChild(valor);
  }
  const posicion = document.createElement("span");
  posicion.className = "nodo-posicion mono";
  posicion.textContent = `L${nodo.linea}`;
  boton.appendChild(posicion);
  boton.title = `línea ${nodo.linea}, columna ${nodo.columna}: ir al editor`;
  boton.addEventListener("click", (evento) => {
    evento.preventDefault();          // dentro de <summary> no pliega el nodo
    saltarALinea(nodo.linea, nodo.columna);
  });
  return boton;
}

// Árbol jerárquico con <details>: se pliega con el triángulo y un clic en la
// etiqueta lleva a la posición del nodo en el editor.
function nodoArbol(nodo, profundidad, abiertoHasta) {
  const item = document.createElement("li");
  const hijos = nodo.hijos || [];
  if (!hijos.length) {
    item.appendChild(etiquetaNodo(nodo));
    return item;
  }
  const detalles = document.createElement("details");
  detalles.open = profundidad < abiertoHasta;
  const resumen = document.createElement("summary");
  resumen.appendChild(etiquetaNodo(nodo));
  const lista = document.createElement("ul");
  for (const hijo of hijos) lista.appendChild(nodoArbol(hijo, profundidad + 1, abiertoHasta));
  detalles.append(resumen, lista);
  item.appendChild(detalles);
  return item;
}

function pintarAst() {
  const arbol = $("#arbolSintactico");
  const ast = estado.ast;
  const disponible = Boolean(ast && ast.hijos);
  arbol.replaceChildren();
  if (disponible) {
    // Con muchas instrucciones solo se despliega el primer nivel.
    const abiertoHasta = ast.hijos.length > 60 ? 1 : 8;
    const raiz = document.createElement("ul");
    raiz.className = "arbol-raiz";
    raiz.appendChild(nodoArbol(ast, 0, abiertoHasta));
    arbol.appendChild(raiz);
  }
  arbol.classList.toggle("oculto", !disponible);
  $("#arbolVacio").classList.toggle("oculto", disponible);
}

// Salidas del circuito: las declaradas con SALIDA o, si no hay, las señales
// que no alimentan a ninguna compuerta.
function salidasFinales() {
  const resultado = estado.resultado || {};
  if (resultado.salidas && resultado.salidas.length) return resultado.salidas;
  const compuertas = resultado.compuertas || [];
  const usadas = new Set(compuertas.flatMap((compuerta) => compuerta.entradas));
  return compuertas.map((c) => c.salida).filter((senal) => !usadas.has(senal));
}

/* Pestaña 5: código intermedio (orden de evaluación de las compuertas). */
function bloqueCodigo(titulo, instrucciones) {
  const seccion = document.createElement("section");
  seccion.className = "bloque-intermedio";
  const encabezado = document.createElement("h3");
  encabezado.textContent = titulo;
  const pre = document.createElement("pre");
  pre.className = "codigo-expresion mono";
  const ancho = Math.max(0, ...instrucciones.map((i) => i.destino.length));
  pre.textContent = instrucciones.length
    ? instrucciones.map((i) =>
        `${i.destino.padEnd(ancho)} = ${i.operacion} ${i.argumentos.join(", ")}`).join("\n")
    : "(sin instrucciones)";
  seccion.append(encabezado, pre);
  return seccion;
}

function tablaSimple(titulo, cabeceras, filas) {
  const seccion = document.createElement("section");
  seccion.className = "bloque-intermedio";
  const encabezado = document.createElement("h3");
  encabezado.textContent = titulo;
  const contenedor = document.createElement("div");
  contenedor.className = "tabla-scroll tabla-corta";
  const tabla = document.createElement("table");
  const thead = document.createElement("thead");
  const tr = document.createElement("tr");
  for (const texto of cabeceras) {
    const th = document.createElement("th");
    th.scope = "col";
    th.textContent = texto;
    tr.appendChild(th);
  }
  thead.appendChild(tr);
  const tbody = document.createElement("tbody");
  for (const fila of filas) {
    const filaTabla = document.createElement("tr");
    for (const valor of fila) {
      const td = document.createElement("td");
      td.textContent = valor;
      filaTabla.appendChild(td);
    }
    tbody.appendChild(filaTabla);
  }
  tabla.append(thead, tbody);
  contenedor.appendChild(tabla);
  seccion.append(encabezado, contenedor);
  return seccion;
}

function pintarIntermedio() {
  const contenedor = $("#contenidoIntermedio");
  const datos = estado.resultado?.exito ? estado.resultado : null;
  contenedor.replaceChildren();
  const disponible = Boolean(datos && datos.ir && datos.optimizacion);
  $("#intermedioVacio").classList.toggle("oculto", disponible);
  if (!disponible) return;

  const optimizacion = datos.optimizacion;
  const antes = optimizacion.metricas_antes;
  const despues = optimizacion.metricas_despues;
  const columnas = document.createElement("div");
  columnas.className = "columnas-intermedio";
  columnas.append(bloqueCodigo("Código intermedio (tres direcciones)", datos.ir),
                  bloqueCodigo("Código optimizado", optimizacion.ir_optimizado));
  contenedor.appendChild(columnas);

  contenedor.appendChild(tablaSimple("Métricas", ["Métrica", "Antes", "Después"], [
    ["Compuertas", antes.compuertas, despues.compuertas],
    ["Profundidad máxima", antes.profundidad, despues.profundidad],
    ["Entradas usadas", antes.entradas_usadas, despues.entradas_usadas],
  ]));

  if (optimizacion.bitacora.length) {
    contenedor.appendChild(tablaSimple(
      `Bitácora del optimizador (${optimizacion.bitacora.length} cambios)`,
      ["Pase", "Línea", "Antes", "Después", "Motivo"],
      optimizacion.bitacora.map((b) => [b.pase, b.linea, b.antes, b.despues, b.motivo])));
  } else {
    const nota = document.createElement("p");
    nota.className = "ayuda";
    nota.textContent = "El optimizador no encontró nada que simplificar.";
    contenedor.appendChild(nota);
  }
}

/* Subpestaña Verilog. */
function pintarVerilog() {
  const codigo = estado.resultado?.exito ? estado.resultado.verilog : null;
  const pre = $("#codigoVerilog");
  const conTestbench = $("#verilogTestbench").checked;
  const texto = codigo
    ? (conTestbench && codigo.testbench ? `${codigo.modulo}\n${codigo.testbench}` : codigo.modulo)
    : "";
  pre.textContent = texto;
  pre.classList.toggle("oculto", !texto);
  $("#verilogVacio").classList.toggle("oculto", Boolean(texto));
  $("#copiarVerilog").disabled = !texto;
  $("#verilogTestbench").disabled = !(codigo && codigo.testbench);
  $("#infoVerilog").textContent = codigo && !codigo.testbench && estado.resultado?.exito
    ? (codigo.aviso_testbench || "") : "";
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
  await copiarTexto(textoParaCopiar(), "Expresiones copiadas al portapapeles.");
}

async function copiarTexto(texto, mensaje) {
  if (!texto) return;

  try {
    await navigator.clipboard.writeText(texto);
    avisar(mensaje, false);
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
    avisar(copiado ? mensaje : "No se pudo copiar al portapapeles.", !copiado);
  }
}

/* ======================================================================== */
/* 10. Errores (con salto a la línea del editor)                             */
/* ======================================================================== */
const NOMBRE_FASE = {
  "léxico": "Léxico",
  "sintáctico": "Sintáctico",
  "semántico": "Semántico",
  "interno": "Interno",
};

// Diagnósticos estructurados de la respuesta. Una respuesta antigua (sin el
// campo) se interpreta a partir del texto «Error <fase> línea L, columna C».
function diagnosticosDe(datos) {
  if (Array.isArray(datos.diagnosticos)) return datos.diagnosticos;
  const convertir = (texto, severidad) => {
    const m = /^(Error|Advertencia)(?:\s+(léxico|sintáctico|semántico))?(?:\s+línea\s+(\d+)(?:,\s*columna\s+(\d+))?)?:\s*([\s\S]*)$/.exec(String(texto));
    return m
      ? { fase: m[2] || "semántico", severidad, linea: m[3] ? +m[3] : null,
          columna: m[4] ? +m[4] : null, mensaje: m[5], sugerencia: null }
      : { fase: "interno", severidad, linea: null, columna: null,
          mensaje: String(texto), sugerencia: null };
  };
  return [
    ...(datos.errores || []).map((t) => convertir(t, "error")),
    ...(datos.advertencias || []).map((t) => convertir(t, "advertencia")),
  ];
}

function elementoDiagnostico(d) {
  const item = document.createElement("li");
  item.className = `diagnostico ${d.severidad === "error" ? "es-error" : "es-advertencia"}`;

  const posicion = document.createElement("span");
  posicion.className = "chip-posicion mono";
  posicion.textContent = d.linea
    ? `L${d.linea}${d.columna ? ` · C${d.columna}` : ""}`
    : "general";
  posicion.title = d.linea
    ? `línea ${d.linea}${d.columna ? `, columna ${d.columna}` : ""}`
    : "sin posición";

  const cuerpo = document.createElement("div");
  cuerpo.className = "diagnostico-cuerpo";
  const fase = document.createElement("span");
  fase.className = "diagnostico-fase";
  fase.textContent = NOMBRE_FASE[d.fase] || d.fase;
  const mensaje = document.createElement("p");
  mensaje.className = "diagnostico-mensaje";
  mensaje.textContent = d.mensaje;
  cuerpo.append(fase, mensaje);
  if (d.sugerencia) {
    const sugerencia = document.createElement("p");
    sugerencia.className = "diagnostico-sugerencia";
    sugerencia.textContent = d.sugerencia;
    cuerpo.appendChild(sugerencia);
  }

  item.append(posicion, cuerpo);
  if (d.linea) {
    item.tabIndex = 0;
    item.setAttribute("role", "button");
    item.setAttribute("aria-label",
      `${fase.textContent}, ${posicion.title}: ${d.mensaje}. Ir a esa posición`);
    const ir = () => saltarALinea(d.linea, d.columna);
    item.addEventListener("click", ir);
    item.addEventListener("keydown", (evento) => {
      if (evento.key === "Enter" || evento.key === " ") {
        evento.preventDefault();
        ir();
      }
    });
  }
  return item;
}

const porPosicion = (a, b) => (a.linea || 0) - (b.linea || 0) || (a.columna || 0) - (b.columna || 0);

function pintarDiagnosticos(diagnosticos, opciones = {}) {
  const errores = diagnosticos.filter((d) => d.severidad === "error").sort(porPosicion);
  const advertencias = diagnosticos.filter((d) => d.severidad !== "error").sort(porPosicion);
  estado.diagnosticos = diagnosticos;

  $("#listaErrores").replaceChildren(...errores.map(elementoDiagnostico));
  $("#listaAdvertencias").replaceChildren(...advertencias.map(elementoDiagnostico));
  $("#cuentaErrores").textContent = errores.length;
  $("#cuentaAdvertencias").textContent = advertencias.length;
  $("#bloqueErrores").classList.toggle("oculto", errores.length === 0);
  $("#bloqueAdvertencias").classList.toggle("oculto", advertencias.length === 0);
  $("#sinDiagnosticos").classList.toggle("oculto", diagnosticos.length > 0);

  actualizarPestanaErrores(errores.length, advertencias.length);
  actualizarMargen();
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

async function exportar(tipo) {
  const datos = estado.resultado;
  cerrarMenuExportar();
  if (!datos || !datos.exito) return;

  if (tipo === "svg") {
    descargar(Exportacion.construirSVG(datos),
              Exportacion.nombreArchivo("svg"), "image/svg+xml");
  } else if (tipo === "csv") {
    if (datos.tabla_omitida) {
      await exportarCsvPorBloques(datos);
    } else {
      const columnas = columnasVisibles();
      descargar(Exportacion.construirCSV({
        señales: columnas.map((i) => datos.tabla_verdad.señales[i]),
        filas: datos.tabla_verdad.filas.map((fila) => columnas.map((i) => fila[i])),
      }), Exportacion.nombreArchivo("csv"), "text/csv");
    }
  } else if (tipo === "json") {
    descargar(Exportacion.construirJSON(datos),
              Exportacion.nombreArchivo("json"), "application/json");
  } else if (tipo === "verilog" && datos.verilog) {
    const codigo = $("#verilogTestbench").checked && datos.verilog.testbench
      ? `${datos.verilog.modulo}\n${datos.verilog.testbench}` : datos.verilog.modulo;
    descargar(codigo, Exportacion.nombreArchivo("v"), "text/plain");
  }
}

// Una tabla de 2^20 filas no se arma nunca en memoria del servidor: se piden
// bloques a /tabla y se van juntando las partes en un Blob.
async function exportarCsvPorBloques(datos) {
  const total = datos.tabla_omitida.filas_totales;
  const codigo = estado.tabla.codigo || $("#codigo").value;
  const columnas = columnasVisibles();
  const partes = [Exportacion.construirCSV({
    señales: columnas.map((i) => datos.tabla_verdad.señales[i]), filas: [] })];
  try {
    for (let desde = 0; desde < total; desde += FILAS_POR_PETICION_CSV) {
      avisar(`Exportando CSV: ${Math.round((desde / total) * 100)} %...`, false);
      const bloque = await pedirFilas(codigo, desde, FILAS_POR_PETICION_CSV);
      if (!bloque.exito) throw new Error((bloque.errores || ["sin detalle"]).join(" "));
      partes.push(Exportacion.filasCSV(bloque.filas.map((fila) => columnas.map((i) => fila[i]))));
    }
  } catch (error) {
    avisar(`No se pudo exportar el CSV: ${error.message || error}`, true);
    return;
  }
  const url = URL.createObjectURL(new Blob(partes, { type: "text/csv" }));
  const enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = Exportacion.nombreArchivo("csv");
  document.body.appendChild(enlace);
  enlace.click();
  enlace.remove();
  URL.revokeObjectURL(url);
  avisar(`CSV exportado (${total.toLocaleString("es")} filas).`, false);
}

/* ======================================================================== */
/* 13. Inicio                                                                */
/* ======================================================================== */
function cerrarMenuExportar() {
  $("#listaExportar").classList.add("oculto");
  $("#botonExportar").setAttribute("aria-expanded", "false");
}

function toggleMenuExportar() {
  const abierto = $("#listaExportar").classList.toggle("oculto") === false;
  $("#botonExportar").setAttribute("aria-expanded", String(abierto));
}

function conectarEventos() {
  // Editor
  $("#analizar").addEventListener("click", analizar);
  $("#botonEjemplos").addEventListener("click", (evento) => {
    evento.stopPropagation();
    alternarMenu("#listaEjemplos", "#botonEjemplos");
  });
  $("#codigo").addEventListener("input", () => {
    programarValidacion();
    actualizarMargen();
    // El resultado mostrado ya no corresponde al texto: se avisa.
    if (estado.resultado && $("#codigo").value !== estado.codigoAnalizado) {
      avisar("Hay cambios sin analizar (Ctrl+Enter).", false);
    }
  });
  $("#codigo").addEventListener("scroll", sincronizarMargen);
  $("#codigo").addEventListener("keydown", (evento) => {
    if (evento.key === "Enter" && (evento.ctrlKey || evento.metaKey)) {
      evento.preventDefault();
      analizar();
    }
  });

  // Navegación
  window.addEventListener("hashchange", mostrarVista);

  // Pestañas y subpestañas (clic y flechas del teclado)
  document.querySelectorAll(".pestana").forEach((pestana) => {
    pestana.addEventListener("click", () => activarPestana(pestana.dataset.panel));
  });
  $("#pestanas").addEventListener("keydown", (evento) =>
    navegarConTeclado(evento, ".pestana", "panel", activarPestana));
  document.querySelectorAll(".subpestana").forEach((pestana) => {
    pestana.addEventListener("click", () => activarSubpestana(pestana.dataset.sub));
  });
  document.querySelector(".subpestanas").addEventListener("keydown", (evento) =>
    navegarConTeclado(evento, ".subpestana", "sub", activarSubpestana));

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
    if (estado.tabla.remota && estado.tabla.mostradas >= filasFiltradas().length) {
      cargarBloqueRemoto();
      return;
    }
    estado.tabla.mostradas += FILAS_POR_BLOQUE;
    pintarTabla();
  });
  $("#generarTabla").addEventListener("click", generarTablaRemota);
  $("#tablaScroll").addEventListener("scroll", (evento) => {
    const caja = evento.target;
    if (caja.scrollTop + caja.clientHeight >= caja.scrollHeight - 40) {
      const total = filasFiltradas().length;
      if (estado.tabla.mostradas < total) {
        estado.tabla.mostradas += FILAS_POR_BLOQUE;
        pintarTabla();
      } else if (estado.tabla.remota) {
        cargarBloqueRemoto();
      }
    }
  });
  $("#filtroToken").addEventListener("change", pintarTablaTokens);
  $("#mostrarTemporales").addEventListener("change", pintarTabla);

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
  $("#verilogTestbench").addEventListener("change", pintarVerilog);
  $("#copiarVerilog").addEventListener("click", () =>
    copiarTexto($("#codigoVerilog").textContent, "Código Verilog copiado."));

  // Exportar
  $("#botonExportar").addEventListener("click", (evento) => {
    evento.stopPropagation();
    toggleMenuExportar();
  });
  $("#listaExportar").addEventListener("click", (evento) => {
    const boton = evento.target.closest("[data-exportar]");
    if (boton) exportar(boton.dataset.exportar);
  });
  document.addEventListener("click", (evento) => {
    if (!evento.target.closest("#menuExportar")) cerrarMenuExportar();
    if (!evento.target.closest("#menuEjemplos")) cerrarMenu("#listaEjemplos", "#botonEjemplos");
    if (!evento.target.closest(".fondo-control")) cerrarPopoverFondo();
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
  $("#botonFondo").addEventListener("click", (evento) => {
    evento.stopPropagation();
    if ($("#popoverFondo").classList.contains("oculto")) abrirPopoverFondo();
    else cerrarPopoverFondo();
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
    if (evento.key !== "Escape") return;
    cerrarPantallaCompleta();
    cerrarMenuExportar();
    cerrarMenu("#listaEjemplos", "#botonEjemplos");
    if (!$("#popoverFondo").classList.contains("oculto")) {
      cerrarPopoverFondo();
      $("#botonFondo").focus();
    }
  });
}

/* ======================================================================== */
/* 14. Fondo (popover), galería de ejemplos y margen del editor              */
/* ======================================================================== */
function abrirPopoverFondo() {
  $("#popoverFondo").classList.remove("oculto");
  $("#botonFondo").setAttribute("aria-expanded", "true");
  marcarPresetActivo();
  const activo = document.querySelector(".preset.activo") || document.querySelector(".preset");
  if (activo) activo.focus();
}

function cerrarPopoverFondo() {
  $("#popoverFondo").classList.add("oculto");
  $("#botonFondo").setAttribute("aria-expanded", "false");
}

function alternarMenu(lista, boton) {
  const abierto = $(lista).classList.toggle("oculto") === false;
  $(boton).setAttribute("aria-expanded", String(abierto));
}

function cerrarMenu(lista, boton) {
  $(lista).classList.add("oculto");
  $(boton).setAttribute("aria-expanded", "false");
}

async function cargarEjemplos() {
  const lista = $("#listaEjemplos");
  try {
    const { ejemplos } = await (await fetch("/ejemplos")).json();
    const grupos = new Map();
    for (const ejemplo of ejemplos) {
      if (!grupos.has(ejemplo.grupo)) grupos.set(ejemplo.grupo, []);
      grupos.get(ejemplo.grupo).push(ejemplo);
    }
    lista.replaceChildren();
    for (const [grupo, elementos] of grupos) {
      const titulo = document.createElement("p");
      titulo.className = "submenu-grupo";
      titulo.textContent = grupo;
      lista.appendChild(titulo);
      for (const ejemplo of elementos) {
        const boton = document.createElement("button");
        boton.type = "button";
        const nombre = document.createElement("span");
        nombre.textContent = ejemplo.titulo;
        const detalle = document.createElement("small");
        detalle.textContent = ejemplo.descripcion;
        boton.append(nombre, detalle);
        boton.addEventListener("click", () => {
          $("#codigo").value = ejemplo.codigo;
          cerrarMenu("#listaEjemplos", "#botonEjemplos");
          avisar(`Ejemplo «${ejemplo.titulo}» cargado. Pulsa «Analizar».`, false);
          actualizarMargen();
          programarValidacion();
          $("#codigo").focus();
        });
        lista.appendChild(boton);
      }
    }
  } catch (error) {
    lista.textContent = "No se pudieron cargar los ejemplos.";
  }
}

// Números de línea en un margen sincronizado con el textarea, con una marca
// en las líneas que tienen errores o advertencias.
function actualizarMargen() {
  const margen = $("#margen");
  const total = $("#codigo").value.split("\n").length;
  const marcas = new Map();
  for (const d of estado.diagnosticos || []) {
    if (!d.linea) continue;
    if (d.severidad === "error" || !marcas.has(d.linea)) marcas.set(d.linea, d);
  }
  const fragmento = document.createDocumentFragment();
  for (let linea = 1; linea <= total; linea++) {
    const numero = document.createElement("div");
    numero.textContent = linea;
    const marca = marcas.get(linea);
    if (marca) {
      numero.className = marca.severidad === "error" ? "marca-error" : "marca-advertencia";
      numero.title = marca.mensaje;
    }
    fragmento.appendChild(numero);
  }
  // Relleno para que el margen pueda desplazarse tanto como el textarea.
  const relleno = document.createElement("div");
  relleno.className = "margen-relleno";
  fragmento.appendChild(relleno);
  margen.replaceChildren(fragmento);
  sincronizarMargen();
}

function sincronizarMargen() {
  $("#margen").scrollTop = $("#codigo").scrollTop;
}

function iniciar() {
  conectarEventos();
  mostrarVista();
  cargarFondo();
  cargarEjemplos();
  actualizarMargen();
  new ResizeObserver(sincronizarMargen).observe($("#codigo"));
  actualizarPestanaErrores(0);
  activarSubpestana(estado.subActiva);
  pintarExpresiones();
}

document.addEventListener("DOMContentLoaded", iniciar);
