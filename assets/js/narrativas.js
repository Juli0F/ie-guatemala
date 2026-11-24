// Proyecto 1 - Explorador de narrativas por tema y departamento.
import { color, alCambiarTema, fmt, lineas, leyenda, cargar } from "./graficos.js";

const D = await cargar("../data/narrativas.json");
const { meta, temas, departamentos, semanas, cuentas, publicaciones, subgrafos, emergentes } = D;
const subnarrativas = temas.flatMap((t) => t.subnarrativas.map((s) => ({ ...s, tema: t.id })));
const TIPOS = { ciudadano: "Ciudadano", creador: "Creador", medio: "Medio", activista: "Activista", institucional: "Institucional", "": "Sin dato" };
const VAR_TEMA = { agua: "--com-0", politica: "--com-4", narcopolitica: "--com-1", estado: "--com-2" };
const VAR_TIPO = { ciudadano: "--neutral", creador: "--com-3", medio: "--com-0", activista: "--com-1", institucional: "--com-2", "": "--neutral" };
const PLAT = {
  tiktok: { nombre: "TikTok", corto: "TT", forma: "punto", formatos: "videos cortos, dueto o stitch con voces locales" },
  instagram: { nombre: "Instagram", corto: "IG", forma: "cuadro", formatos: "carruseles, historias y colaboraciones con cuentas locales" },
  x: { nombre: "X", corto: "X", forma: "rombo", formatos: "hilos breves con fuentes enlazadas y respuestas a cuentas locales con alcance" },
};
const PLAT_IDX = meta.plataformas ?? ["tiktok", "instagram"];
const nombrePlat = (id) => PLAT[id]?.nombre ?? "Plataforma desconocida";
const nombreDepto = (i) => (i >= 0 ? departamentos[i].nombre : "sin ubicación");
const etiquetaTema = (id) => (id === "todas" ? "todos los temas" : temas.find((t) => t.id === id).etiqueta.toLowerCase());
const fechaCorta = (iso) => { const [, m, d] = iso.split("-"); return `${d}/${m}`; };

// ---------------------------------------------------------------- estado y URL
const url = new URLSearchParams(location.search);
const estado = {
  tema: temas.some((t) => t.id === url.get("tema")) ? url.get("tema") : "todas",
  depto: departamentos.some((d) => d.id === url.get("depto")) ? url.get("depto") : "nacional",
};

function sincronizarURL() {
  const p = new URLSearchParams();
  if (estado.tema !== "todas") p.set("tema", estado.tema);
  if (estado.depto !== "nacional") p.set("depto", estado.depto);
  const q = p.toString();
  history.replaceState(null, "", `${location.pathname}${q ? "?" + q : ""}${location.hash}`);
}

// ---------------------------------------------------------------- aviso de fuente
const fechaLarga = (iso) => new Date(`${iso}T12:00:00`).toLocaleDateString("es-GT", { day: "numeric", month: "long", year: "numeric" });
document.getElementById("aviso-fuente").innerHTML = `<p><strong>${meta.sintetica ? "Datos de ejemplo (inventados)." : "Datos reales."}</strong>
  ${fmt.n(meta.publicaciones)} publicaciones de ${fmt.n(meta.cuentas)} cuentas, del ${fechaLarga(meta.desde)} al ${fechaLarga(meta.hasta)}.
  ${meta.seudonimizada ? "Los nombres de cuentas personales están ocultos." : ""}</p>`;

// ---------------------------------------------------------------- controles de filtro
const contTema = document.getElementById("opciones-tema");
contTema.innerHTML = [{ id: "todas", etiqueta: "Todos" }, ...temas].map((t) =>
  `<label><input type="radio" name="tema" value="${t.id}"${t.id === estado.tema ? " checked" : ""}> ${t.etiqueta}</label>`).join("");
const selDepto = document.getElementById("sel-depto");
selDepto.innerHTML = `<option value="nacional">Guatemala · nivel nacional</option>` +
  [...departamentos].sort((a, b) => a.nombre.localeCompare(b.nombre, "es")).map((d) => `<option value="${d.id}">${d.nombre}</option>`).join("");
selDepto.value = estado.depto;

document.getElementById("filtros").addEventListener("change", (e) => {
  if (e.target.name === "tema") estado.tema = e.target.value;
  if (e.target.name === "depto") estado.depto = e.target.value;
  actualizar();
});
document.getElementById("copiar-enlace").addEventListener("click", async (e) => {
  try {
    await navigator.clipboard.writeText(location.href);
    e.target.textContent = "Enlace copiado";
  } catch {
    e.target.textContent = "Copia la dirección del navegador";
  }
  setTimeout(() => (e.target.textContent = "Copiar enlace"), 2000);
});

// ---------------------------------------------------------------- agregaciones de publicaciones
const [P_CUENTA, P_TEMAS, P_SUB, P_DEPTO, , P_SEMANA, P_ENG, P_PLAT] = [0, 1, 2, 3, 4, 5, 6, 7];
const bitTema = (id) => 1 << temas.findIndex((t) => t.id === id);
const deptoIdx = (id) => departamentos.findIndex((d) => d.id === id);

function filtrar({ tema = estado.tema, depto = estado.depto } = {}) {
  const bit = tema === "todas" ? 0 : bitTema(tema);
  const di = depto === "nacional" ? null : deptoIdx(depto);
  return publicaciones.filter((p) => (bit ? p[P_TEMAS] & bit : p[P_TEMAS] > 0) && (di === null || p[P_DEPTO] === di));
}

// ---------------------------------------------------------------- mapa de cuadrícula
const mapa = document.getElementById("mapa-gt");
const filas = Math.max(...departamentos.map((d) => d.fila)) + 1;
const cols = Math.max(...departamentos.map((d) => d.col)) + 1;
mapa.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;
mapa.style.gridTemplateRows = `repeat(${filas}, auto)`;
mapa.innerHTML = departamentos.map((d) => `
  <button type="button" class="casilla" data-depto="${d.id}" style="grid-column:${d.col + 1};grid-row:${d.fila + 1}" aria-pressed="false">
    <span class="nombre">${d.nombre}</span><span class="valor"></span>
  </button>`).join("");
mapa.addEventListener("click", (e) => {
  const b = e.target.closest(".casilla");
  if (!b) return;
  estado.depto = estado.depto === b.dataset.depto ? "nacional" : b.dataset.depto;
  selDepto.value = estado.depto;
  actualizar();
});

function pintarMapa() {
  const conteo = new Array(departamentos.length).fill(0);
  for (const p of filtrar({ depto: "nacional" })) if (p[P_DEPTO] >= 0) conteo[p[P_DEPTO]]++;
  const max = Math.max(1, ...conteo);
  mapa.querySelectorAll(".casilla").forEach((b, i) => {
    const n = conteo[i];
    // escala de raíz cuadrada: la capital no aplasta al resto de departamentos
    const pct = Math.round(8 + Math.sqrt(n / max) * 72);
    b.style.setProperty("--intensidad", `${pct}%`);
    b.classList.toggle("oscura", pct > 48);
    b.querySelector(".valor").textContent = fmt.n(n);
    b.setAttribute("aria-pressed", String(estado.depto === b.dataset.depto));
    b.setAttribute("aria-label", `${departamentos[i].nombre}: ${fmt.n(n)} publicaciones`);
  });
  return conteo;
}

// ---------------------------------------------------------------- tendencia semanal
function serieSemanal(pubs, clave) {
  const s = new Array(semanas.length).fill(0);
  for (const p of pubs) if (clave(p)) s[p[P_SEMANA]]++;
  return s;
}

function pintarTendencia() {
  const pubs = filtrar();
  const xs = semanas.map(fechaCorta);
  let series;
  if (estado.tema === "todas") {
    series = temas.map((t) => ({ nombre: t.etiqueta, valores: serieSemanal(pubs, (p) => p[P_TEMAS] & bitTema(t.id)), color: color(VAR_TEMA[t.id]) }));
    document.getElementById("t-tendencia").textContent = "Cada semana, por tema";
  } else {
    const subs = subnarrativas.filter((s) => s.tema === estado.tema);
    const paleta = ["--com-0", "--com-1", "--com-2", "--com-4", "--com-3"];
    series = subs.map((s, i) => ({
      nombre: s.etiqueta.split(" ").slice(0, 2).join(" "),
      valores: serieSemanal(pubs, (p) => subnarrativas[p[P_SUB]]?.id === s.id),
      color: color(paleta[i % paleta.length]),
    }));
    document.getElementById("t-tendencia").textContent = `Cada semana: ${etiquetaTema(estado.tema)}, por asunto`;
  }
  lineas(document.getElementById("g-tendencia"), xs, series, {
    formato: (v) => fmt.n(v), tituloY: "Publicaciones", titulo: "Publicaciones por semana",
  });
  document.getElementById("cap-tendencia").textContent =
    `Publicaciones por semana en ${estado.depto === "nacional" ? "todo el país" : nombreDepto(deptoIdx(estado.depto))}.`;
}

// ---------------------------------------------------------------- KPIs y lectura automática
function vistaActual() {
  return subgrafos[`${estado.tema}|${estado.depto}`] ?? null;
}

function metricasVista(sg) {
  if (!sg) return [];
  return sg.n.map((ci, k) => ({ ...cuentas[ci], ci, pr: sg.pr[k], bt: sg.bt[k], gr: sg.gr[k], com: sg.com[k] }));
}

function temaPrincipalCuenta(pubs) {
  const porCuenta = new Map();
  for (const p of pubs) {
    const m = porCuenta.get(p[P_CUENTA]) ?? new Array(temas.length).fill(0);
    temas.forEach((t, i) => { if (p[P_TEMAS] & (1 << i)) m[i]++; });
    porCuenta.set(p[P_CUENTA], m);
  }
  return (ci) => {
    const m = porCuenta.get(ci);
    if (!m) return null;
    return temas[m.indexOf(Math.max(...m))].id;
  };
}

function alertas(tema) {
  // departamentos con crecimiento > 40 % (últimas 2 semanas vs 4 anteriores, mín. 10 publicaciones en 6 semanas)
  const pubs = filtrar({ tema, depto: "nacional" });
  const ult = semanas.length;
  return departamentos.map((d, i) => {
    const s = serieSemanal(pubs, (p) => p[P_DEPTO] === i);
    const rec = (s[ult - 1] + s[ult - 2]) / 2;
    const ant = (s[ult - 3] + s[ult - 4] + s[ult - 5] + s[ult - 6]) / 4;
    return { d, rec, ant, cambio: ant ? (rec - ant) / ant : rec > 0 ? Infinity : 0, total: s.slice(-6).reduce((a, b) => a + b, 0) };
  }).filter((x) => x.total >= 10 && x.cambio > 0.4).sort((a, b) => b.cambio - a.cambio);
}

function actualizar() {
  sincronizarURL();
  const pubs = filtrar();
  const todasDelLugar = filtrar({ tema: "todas" });
  const sg = vistaActual();
  const nodos = metricasVista(sg);
  const lugar = estado.depto === "nacional" ? "todo el país" :nombreDepto(deptoIdx(estado.depto));
  const conteoMapa = pintarMapa();
  pintarTendencia();

  const porPlat = PLAT_IDX.map((id, i) => ({ id, pubs: pubs.filter((p) => p[P_PLAT] === i) })).filter((x) => x.pubs.length);
  document.getElementById("kpis").innerHTML = [
    [fmt.n(pubs.length), "publicaciones"],
    [estado.tema === "todas" ? "—" : fmt.p((pubs.length / Math.max(1, todasDelLugar.length)) * 100, 0), "de lo que se habla en el lugar"],
    [fmt.n(new Set(pubs.map((p) => p[P_CUENTA])).size), "cuentas"],
    [sg ? fmt.n(new Set(sg.com).size) : "—", "grupos que conversan"],
  ].map(([v, n]) => `<div class="kpi"><span class="valor">${v}</span><span class="nombre">${n}</span></div>`).join("");

  // subnarrativas
  const conteoSub = new Map();
  for (const p of pubs) if (p[P_SUB] >= 0) conteoSub.set(p[P_SUB], (conteoSub.get(p[P_SUB]) ?? 0) + 1);
  const subsOrden = [...conteoSub.entries()].sort((a, b) => b[1] - a[1]);
  const totalSub = subsOrden.reduce((s, [, n]) => s + n, 0) || 1;
  document.querySelector("#tabla-subnarrativas tbody").innerHTML = subsOrden.slice(0, 10).map(([i, n]) => {
    const s = subnarrativas[i];
    return `<tr><td><span style="color:var(${VAR_TEMA[s.tema]})" aria-hidden="true">●</span> ${s.etiqueta}</td><td class="muted">${s.marco}</td>
      <td class="num">${fmt.n(n)}</td><td class="num">${fmt.d((n / totalSub) * 100, 0)}</td></tr>`;
  }).join("") || `<tr><td colspan="4" class="muted">Sin publicaciones clasificadas.</td></tr>`;

  // tablas de nodos
  const fila = (n, clave, dec) => `<tr><td><code>${n.id}</code> <span class="muted">${PLAT[n.plataforma]?.corto ?? ""}</span></td>
    <td>${TIPOS[n.tipo] ?? n.tipo}</td><td>${nombreDepto(n.depto)}</td><td class="num">${fmt.d(n[clave], dec)}</td></tr>`;
  const vacia = `<tr><td colspan="4" class="muted">Muy pocos datos en esta vista.</td></tr>`;
  const porPR = [...nodos].sort((a, b) => b.pr - a.pr);
  const porBT = [...nodos].sort((a, b) => b.bt - a.bt);
  document.querySelector("#tabla-pagerank tbody").innerHTML = porPR.slice(0, 10).map((n) => fila(n, "pr", 4)).join("") || vacia;
  document.querySelector("#tabla-intermediacion tbody").innerHTML = porBT.slice(0, 10).map((n) => fila(n, "bt", 4)).join("") || vacia;

  // comunidades
  const temaDe = temaPrincipalCuenta(pubs);
  const coms = new Map();
  for (const n of nodos) {
    const c = coms.get(n.com) ?? { id: n.com, miembros: [], };
    c.miembros.push(n);
    coms.set(n.com, c);
  }
  const moda = (arr) => {
    const m = new Map();
    for (const x of arr) if (x !== null && x !== undefined && x !== -1) m.set(x, (m.get(x) ?? 0) + 1);
    return [...m.entries()].sort((a, b) => b[1] - a[1])[0]?.[0];
  };
  const listaComs = [...coms.values()].sort((a, b) => b.miembros.length - a.miembros.length);
  document.querySelector("#tabla-comunidades tbody").innerHTML = listaComs.slice(0, 8).map((c) => {
    const t = moda(c.miembros.map((n) => temaDe(n.ci)));
    const lider = c.miembros.reduce((a, b) => (b.pr > a.pr ? b : a));
    return `<tr><td><span style="color:var(--com-${c.id % 6})" aria-hidden="true">●</span> Grupo ${c.id + 1}</td><td class="num">${c.miembros.length}</td>
      <td>${Object.keys(PLAT).map((p) => [p, c.miembros.filter((n) => n.plataforma === p).length]).filter(([, k]) => k).sort((a, b) => b[1] - a[1]).map(([p, k]) => `${PLAT[p].corto} ${k}`).join(" · ") || "—"}</td>
      <td>${t ? temas.find((x) => x.id === t).etiqueta : "—"}</td><td>${nombreDepto(moda(c.miembros.map((n) => n.depto)) ?? -1)}</td><td><code>${lider.id}</code></td></tr>`;
  }).join("") || `<tr><td colspan="6" class="muted">Muy pocos datos en esta vista.</td></tr>`;

  // emergentes
  const em = estado.tema === "todas" ? Object.entries(emergentes).flatMap(([t, l]) => l.map((x) => [...x, t])) : (emergentes[estado.tema] ?? []).map((x) => [...x, estado.tema]);
  document.getElementById("emergentes").innerHTML = em.length
    ? em.sort((a, b) => b[1] - a[1]).slice(0, 12).map(([h, n]) => `<code>#${h}</code> (${n})`).join(", ") + ". Si corresponden, se agregan al libro de códigos."
    : "Ninguno para este tema.";

  // resumen en lenguaje sencillo
  const semanaPico = (() => { const s = serieSemanal(pubs, () => true); const m = Math.max(...s); return m ? semanas[s.indexOf(m)] : null; })();
  const topDeptos = estado.depto === "nacional"
    ? conteoMapa.map((n, i) => [n, i]).sort((a, b) => b[0] - a[0]).slice(0, 3).filter(([n]) => n > 0).map(([, i]) => departamentos[i].nombre)
    : [];
  const subTop = subsOrden[0] ? subnarrativas[subsOrden[0][0]] : null;
  const puente = porBT.find((n) => n.id !== porPR[0]?.id);
  const cuentaTxt = (n) => `<code>${n.id}</code> (${(TIPOS[n.tipo] ?? "").toLowerCase()}, ${nombreDepto(n.depto)})`;
  const puntos = [
    `<strong>${fmt.n(pubs.length)} publicaciones</strong>${semanaPico ? `; la semana con más actividad empezó el ${fechaCorta(semanaPico)}` : ""}.`,
    subTop ? `<strong>Se habla sobre todo de:</strong> ${subTop.etiqueta.toLowerCase()} (${fmt.d((subsOrden[0][1] / totalSub) * 100, 0)} %). Idea que se repite: «${subTop.marco}»` : "",
    topDeptos.length ? `<strong>Dónde:</strong> ${topDeptos.join(", ")}.` : "",
    sg ? `<strong>Quién lo difunde:</strong> ${cuentaTxt(porPR[0])}${puente ? `. Cuenta puente: ${cuentaTxt(puente)}` : ""}.` : "Hay muy pocas interacciones en esta vista para saber quién lo difunde. Prueba con todo el país o con todos los temas.",
  ].filter(Boolean);
  document.getElementById("lectura").innerHTML = `<p><strong>Resumen: ${etiquetaTema(estado.tema)} en ${lugar}</strong></p><ul>${puntos.map((p) => `<li>${p}</li>`).join("")}</ul>`;

  // sugerencias por reglas
  const recos = [];
  if (sg) {
    const puentes = porBT.filter((n) => n.pr < porPR[Math.min(4, porPR.length - 1)].pr).slice(0, 3);
    if (puentes.length) recos.push(`<strong>Cuentas puente:</strong> ${puentes.map((n) => `<code>${n.id}</code>`).join(", ")}. Conectan grupos distintos. Revisa qué publican antes de contactarlas o vigilarlas.`);
    recos.push(`<strong>Cuentas más influyentes:</strong> <code>${porPR[0].id}</code>${porPR[1] ? ` y <code>${porPR[1].id}</code>` : ""}. Mejor llegar a su público con información verificable que confrontarlas.`);
  }
  const al = alertas(estado.tema).slice(0, 3);
  if (al.length) recos.push(`<strong>Alerta:</strong> ${al.map((a) => `${a.d.nombre} (${a.cambio === Infinity ? "nuevo" : "+" + fmt.d(a.cambio * 100, 0) + " %"})`).join(", ")}. El tema crece rápido ahí en las últimas 2 semanas.`);
  else recos.push(`<strong>Sin alertas:</strong> ningún departamento crece rápido en las últimas 2 semanas.`);
  if (subTop) recos.push(`<strong>Mensaje:</strong> responder a «${subTop.marco.replace(/\.$/, "")}» con datos concretos (horarios, fuentes), sin repetir el rumor.`);
  const canal = porPlat.map((x) => ({ id: x.id, total: x.pubs.reduce((s, p) => s + p[P_ENG], 0) })).sort((a, b) => b.total - a.total)[0];
  if (canal && PLAT[canal.id]) recos.push(`<strong>Dónde publicar:</strong> ${nombrePlat(canal.id)}, la red con más interacción aquí. Formato: ${PLAT[canal.id].formatos}.`);
  document.getElementById("t-reco-vista").textContent = `${etiquetaTema(estado.tema)[0].toUpperCase() + etiquetaTema(estado.tema).slice(1)} en ${lugar}`;
  document.getElementById("recos").innerHTML = recos.map((r) => `<li>${r}</li>`).join("");

  grafo.cargar(nodos, sg, temaDe);
}

// ---------------------------------------------------------------- grafo (Canvas 2D)
const grafo = (() => {
  const lienzo = document.getElementById("lienzo");
  const canvas = document.getElementById("grafo");
  const ctx = canvas.getContext("2d");
  const tooltip = document.getElementById("tooltip");
  const vacio = document.getElementById("grafo-vacio");
  const form = document.getElementById("controles");
  const g = { nodos: [], aristas: [], porCi: new Map(), temaDe: () => null, color: "comunidad", tamano: "pr",
    plataformas: new Set(Object.keys(PLAT)), hover: null, fijo: null, buscado: null, zoom: 1, px: 0, py: 0, ext: {} };
  let W = 0, H = 0, pal = {};

  function leerPaleta() {
    pal = {
      texto: color("--text"), fondo: color("--surface"), muted: color("--muted"),
      com: Array.from({ length: 6 }, (_, i) => color(`--com-${i}`)),
      tema: Object.fromEntries(Object.entries(VAR_TEMA).map(([k, v]) => [k, color(v)])),
      tipo: Object.fromEntries(Object.entries(VAR_TIPO).map(([k, v]) => [k, color(v)])),
    };
  }
  const colorNodo = (n) => {
    if (g.color === "tema") return pal.tema[g.temaDe(n.ci)] ?? pal.muted;
    if (g.color === "tipo") return pal.tipo[n.tipo] ?? pal.muted;
    return n.com < 6 ? pal.com[n.com] : pal.muted;
  };
  const radio = (n) => {
    const [a, b] = g.ext[g.tamano] ?? [0, 1];
    return 3 + Math.sqrt((n[g.tamano] - a) / (b - a || 1)) * 13;
  };
  const visible = (n) => g.plataformas.has(n.plataforma) || n.plataforma === "desconocida";

  function cargar(nodos, sg, temaDe) {
    g.nodos = nodos.filter((n) => n.x !== null);
    g.porCi = new Map(g.nodos.map((n) => [n.ci, n]));
    g.aristas = sg ? sg.aristas.filter(([u, v]) => g.porCi.has(u) && g.porCi.has(v)) : [];
    g.temaDe = temaDe;
    g.fijo = g.hover = null;
    tooltip.hidden = true;
    vacio.hidden = g.nodos.length > 0;
    for (const k of ["pr", "bt", "gr"]) {
      const v = g.nodos.map((n) => n[k]);
      g.ext[k] = [Math.min(...v), Math.max(...v)];
    }
    disposicionLocal(g.nodos, g.aristas);
    // encuadre: normaliza al rectángulo que ocupan los nodos de la vista
    const xs = g.nodos.map((n) => n.x), ys = g.nodos.map((n) => n.y);
    g.caja = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
    Object.assign(g, { zoom: 1, px: 0, py: 0 });
    document.getElementById("lista-cuentas").innerHTML = g.nodos.map((n) => `<option value="${n.id}">`).join("");
    actualizarLeyenda();
    dibujar();
  }

  // Fruchterman-Reingold para la subred de la vista, partiendo de la disposición nacional.
  // Sin esto, una subred pequeña hereda posiciones dispersas de la red completa.
  function disposicionLocal(nodos, aristas) {
    const n = nodos.length;
    if (n < 3) return;
    const ix = new Map(nodos.map((nd, i) => [nd.ci, i]));
    const px = nodos.map((nd) => nd.x), py = nodos.map((nd) => nd.y);
    const k = Math.sqrt(1 / n), iter = n > 300 ? 80 : 200;
    let t = 0.1;
    for (let it = 0; it < iter; it++) {
      const dx = new Float64Array(n), dy = new Float64Array(n);
      for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
        const ex = px[i] - px[j], ey = py[i] - py[j];
        const d2 = ex * ex + ey * ey || 1e-6, f = (k * k) / d2;
        dx[i] += ex * f; dy[i] += ey * f; dx[j] -= ex * f; dy[j] -= ey * f;
      }
      for (const [u, v, w] of aristas) {
        const i = ix.get(u), j = ix.get(v);
        const ex = px[i] - px[j], ey = py[i] - py[j];
        const d = Math.hypot(ex, ey) || 1e-3, f = (d / k) * (1 + Math.log1p(w) * 0.2);
        dx[i] -= ex * f; dy[i] -= ey * f; dx[j] += ex * f; dy[j] += ey * f;
      }
      for (let i = 0; i < n; i++) {
        dx[i] -= (px[i] - 0.5) * 1.5; dy[i] -= (py[i] - 0.5) * 1.5; // gravedad: mantiene unidos los componentes sueltos
        const d = Math.hypot(dx[i], dy[i]) || 1e-6, paso = Math.min(d, t);
        px[i] += (dx[i] / d) * paso; py[i] += (dy[i] / d) * paso;
      }
      t = Math.max(0.002, t * 0.97);
    }
    nodos.forEach((nd, i) => { nd.x = px[i]; nd.y = py[i]; });
  }

  function actualizarLeyenda() {
    let items;
    if (g.color === "tema") items = temas.map((t) => ({ etiqueta: t.etiqueta, color: pal.tema[t.id] }));
    else if (g.color === "tipo") items = Object.entries(TIPOS).filter(([k]) => k).map(([k, e]) => ({ etiqueta: e, color: pal.tipo[k] }));
    else {
      const ids = [...new Set(g.nodos.map((n) => n.com))].sort((a, b) => a - b);
      items = ids.slice(0, 6).map((c) => ({ etiqueta: `Grupo ${c + 1}`, color: pal.com[c] ?? pal.muted }));
      if (ids.length > 6) items.push({ etiqueta: "Otros grupos", color: pal.muted });
    }
    const presentes = new Set(g.nodos.map((n) => n.plataforma));
    items.push(...Object.entries(PLAT).filter(([id]) => presentes.has(id)).map(([, p]) => ({ etiqueta: p.nombre, color: pal.muted, forma: p.forma })));
    leyenda(document.getElementById("leyenda"), items);
  }

  function aPantalla(n) {
    const pad = 34, [x0, x1, y0, y1] = g.caja;
    const x = pad + ((n.x - x0) / (x1 - x0 || 1)) * (W - 2 * pad);
    const y = pad + ((n.y - y0) / (y1 - y0 || 1)) * (H - 2 * pad);
    return [(x - W / 2) * g.zoom + W / 2 + g.px, (y - H / 2) * g.zoom + H / 2 + g.py];
  }

  function dibujar() {
    const dpr = devicePixelRatio || 1;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    if (!g.nodos.length) return;
    const foco = g.fijo ?? g.hover;
    const vecinos = new Set();
    if (foco) for (const [u, v] of g.aristas) { if (u === foco.ci) vecinos.add(v); if (v === foco.ci) vecinos.add(u); }
    const esc = Math.sqrt(g.zoom);
    for (const [u, v, w] of g.aristas) {
      const a = g.porCi.get(u), b = g.porCi.get(v);
      if (!visible(a) || !visible(b)) continue;
      const enFoco = foco && (u === foco.ci || v === foco.ci);
      ctx.globalAlpha = foco ? (enFoco ? 0.8 : 0.03) : 0.12;
      ctx.strokeStyle = enFoco ? colorNodo(foco) : pal.muted;
      ctx.lineWidth = (0.5 + Math.log1p(w) * 0.5) * esc;
      const [x1, y1] = aPantalla(a), [x2, y2] = aPantalla(b);
      ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
    }
    const orden = g.nodos.filter(visible).sort((a, b) => radio(a) - radio(b));
    for (const n of orden) {
      const [x, y] = aPantalla(n);
      const r = radio(n) * esc;
      ctx.globalAlpha = foco && n !== foco && !vecinos.has(n.ci) ? 0.12 : 1;
      ctx.fillStyle = colorNodo(n);
      ctx.strokeStyle = pal.fondo;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      if (n.plataforma === "instagram") ctx.roundRect(x - r * 0.9, y - r * 0.9, r * 1.8, r * 1.8, r * 0.35);
      else if (n.plataforma === "x") { ctx.moveTo(x, y - r * 1.2); ctx.lineTo(x + r * 1.2, y); ctx.lineTo(x, y + r * 1.2); ctx.lineTo(x - r * 1.2, y); ctx.closePath(); }
      else ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fill(); ctx.stroke();
      if (n === foco || n === g.buscado) {
        ctx.globalAlpha = 1; ctx.strokeStyle = pal.texto; ctx.lineWidth = 2.5;
        ctx.beginPath(); ctx.arc(x, y, r + 5, 0, Math.PI * 2); ctx.stroke();
      }
    }
    ctx.globalAlpha = 1;
    ctx.font = "600 11.5px system-ui, sans-serif";
    ctx.textAlign = "center";
    const etiquetar = new Set([...g.nodos].sort((a, b) => b[g.tamano] - a[g.tamano]).slice(0, 5));
    if (foco) etiquetar.add(foco);
    if (g.buscado) etiquetar.add(g.buscado);
    for (const n of etiquetar) {
      if (!visible(n) || (foco && n !== foco && !vecinos.has(n.ci))) continue;
      const [x, y] = aPantalla(n);
      const r = radio(n) * esc;
      ctx.lineWidth = 3.5; ctx.strokeStyle = pal.fondo; ctx.fillStyle = pal.texto;
      ctx.strokeText(n.id, x, y - r - 6); ctx.fillText(n.id, x, y - r - 6);
    }
  }

  function redimensionar() {
    const rect = lienzo.getBoundingClientRect();
    W = rect.width; H = rect.height;
    const dpr = devicePixelRatio || 1;
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    dibujar();
  }

  function nodoEn(mx, my) {
    let mejor = null, dmin = Infinity;
    for (const n of g.nodos) {
      if (!visible(n)) continue;
      const [x, y] = aPantalla(n);
      const d = Math.hypot(x - mx, y - my);
      if (d < radio(n) * Math.sqrt(g.zoom) + 4 && d < dmin) { mejor = n; dmin = d; }
    }
    return mejor;
  }

  function mostrarTooltip(n, mx, my) {
    if (!n) { tooltip.hidden = true; return; }
    const t = g.temaDe(n.ci);
    tooltip.innerHTML = `<strong>${n.id}</strong><br>
      ${nombrePlat(n.plataforma)} · ${TIPOS[n.tipo] ?? n.tipo}<br>
      Lugar: ${nombreDepto(n.depto)}<br>
      Tema: ${t ? temas.find((x) => x.id === t).etiqueta : "—"} · Grupo ${n.com + 1}<br>
      Contactos: ${n.gr} · Seguidores: ${fmt.n(n.seguidores)}`;
    tooltip.hidden = false;
    const tw = tooltip.offsetWidth, th = tooltip.offsetHeight;
    tooltip.style.left = `${Math.max(4, Math.min(W - tw - 8, mx + 14))}px`;
    tooltip.style.top = `${my + th + 20 > H ? Math.max(4, my - th - 14) : my + 14}px`;
  }

  function zoomEn(f, cx = W / 2, cy = H / 2) {
    const z = Math.min(8, Math.max(0.6, g.zoom * f));
    const k = z / g.zoom;
    g.px = (g.px + W / 2 - cx) * k - W / 2 + cx;
    g.py = (g.py + H / 2 - cy) * k - H / 2 + cy;
    g.zoom = z;
    dibujar();
  }

  let arrastre = null;
  canvas.addEventListener("pointerdown", (e) => {
    canvas.setPointerCapture(e.pointerId);
    arrastre = { x: e.offsetX, y: e.offsetY, px: g.px, py: g.py, movido: false };
  });
  canvas.addEventListener("pointermove", (e) => {
    if (arrastre) {
      const dx = e.offsetX - arrastre.x, dy = e.offsetY - arrastre.y;
      if (Math.hypot(dx, dy) > 3) arrastre.movido = true;
      g.px = arrastre.px + dx; g.py = arrastre.py + dy;
      tooltip.hidden = true;
      dibujar();
      return;
    }
    const n = nodoEn(e.offsetX, e.offsetY);
    if (n !== g.hover) { g.hover = n; dibujar(); }
    if (!g.fijo) mostrarTooltip(n, e.offsetX, e.offsetY);
  });
  canvas.addEventListener("pointerup", (e) => {
    if (arrastre && !arrastre.movido) {
      const n = nodoEn(e.offsetX, e.offsetY);
      g.fijo = n && n !== g.fijo ? n : null;
      mostrarTooltip(g.fijo, e.offsetX, e.offsetY);
      dibujar();
    }
    arrastre = null;
  });
  canvas.addEventListener("pointerleave", () => {
    if (!arrastre) { g.hover = null; if (!g.fijo) tooltip.hidden = true; dibujar(); }
  });
  canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    zoomEn(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.offsetX, e.offsetY);
  }, { passive: false });

  form.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.zoom) zoomEn(+b.dataset.zoom);
    if ("reset" in b.dataset) {
      Object.assign(g, { zoom: 1, px: 0, py: 0, fijo: null, buscado: null });
      form.buscar.value = ""; tooltip.hidden = true; dibujar();
    }
  });
  form.addEventListener("input", () => {
    g.color = form.color.value;
    g.tamano = form.tamano.value;
    g.plataformas = new Set([...form.querySelectorAll("[name=plataforma]:checked")].map((i) => i.value));
    const q = form.buscar.value.trim();
    g.buscado = g.nodos.find((n) => n.id === q) ?? null;
    if (g.buscado) {
      g.fijo = g.buscado;
      const [x, y] = aPantalla(g.buscado);
      mostrarTooltip(g.buscado, x, y);
    }
    actualizarLeyenda();
    dibujar();
  });

  new ResizeObserver(redimensionar).observe(lienzo);
  return { cargar, leerPaleta, actualizarLeyenda, dibujar };
})();

alCambiarTema(() => {
  grafo.leerPaleta();
  actualizar();
});
