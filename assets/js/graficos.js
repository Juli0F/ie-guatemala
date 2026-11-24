// Utilidades de gráficos en SVG puro (sin dependencias).
// Los colores se leen de variables CSS para respetar el tema claro/oscuro.

const SVG_NS = "http://www.w3.org/2000/svg";

export function el(tag, attrs = {}, padre) {
  const n = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (padre) padre.appendChild(n);
  return n;
}

const sonda = document.createElement("span");
sonda.style.display = "none";
document.documentElement.appendChild(sonda);

/** Resuelve una variable CSS (incluidas las que usan light-dark()) a rgb(). */
export function color(variable) {
  sonda.style.color = `var(${variable})`;
  return getComputedStyle(sonda).color;
}

/** Ejecuta `fn` ahora y cada vez que cambie el esquema de color del sistema. */
export function alCambiarTema(fn) {
  fn();
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", fn);
}

export const fmt = {
  n: (v) => new Intl.NumberFormat("es").format(v),
  p: (v, d = 1) => `${v.toLocaleString("es", { minimumFractionDigits: d, maximumFractionDigits: d })} %`,
  d: (v, d = 2) => v.toLocaleString("es", { minimumFractionDigits: d, maximumFractionDigits: d }),
};

function escala(d0, d1, r0, r1) {
  return (v) => r0 + ((v - d0) / (d1 - d0 || 1)) * (r1 - r0);
}

function ticks(max, n = 5) {
  const paso = Math.pow(10, Math.floor(Math.log10(max / n)));
  const mult = [1, 2, 2.5, 5, 10].find((m) => max / (paso * m) <= n) ?? 10;
  const s = paso * mult;
  const out = [];
  for (let v = 0; v <= max + 1e-9; v += s) out.push(+v.toFixed(6));
  return out;
}

/**
 * Barras horizontales.
 * datos: [{ etiqueta, valor, color?, resaltar? }]
 */
export function barrasH(contenedor, datos, { formato = (v) => v, titulo = "", max } = {}) {
  const ancho = 640, alto_barra = 30, sep = 12, margen = { s: 8, i: 30, iz: 290, d: 70 };
  const alto = margen.s + margen.i + datos.length * (alto_barra + sep);
  const tope = max ?? Math.max(...datos.map((d) => d.valor)) * 1.05;
  const x = escala(0, tope, margen.iz, ancho - margen.d);
  const svg = el("svg", { viewBox: `0 0 ${ancho} ${alto}`, role: "img", "aria-label": titulo });

  const rej = el("g", { class: "rejilla" }, svg);
  for (const t of ticks(tope, 4)) {
    el("line", { x1: x(t), x2: x(t), y1: margen.s, y2: alto - margen.i }, rej);
    el("text", { x: x(t), y: alto - 10, "text-anchor": "middle" }, svg).textContent = formato(t);
  }
  datos.forEach((d, i) => {
    const y = margen.s + i * (alto_barra + sep);
    const t = el("text", { x: margen.iz - 10, y: y + alto_barra / 2 + 4, "text-anchor": "end" }, svg);
    t.textContent = d.etiqueta;
    if (d.resaltar) t.setAttribute("style", `fill:${color("--text")};font-weight:600`);
    el("rect", {
      x: margen.iz, y, width: Math.max(0, x(d.valor) - margen.iz), height: alto_barra, rx: 4,
      fill: d.color ?? color("--accent"),
    }, svg);
    el("text", { x: x(d.valor) + 6, y: y + alto_barra / 2 + 4, class: "etiqueta-valor" }, svg).textContent = formato(d.valor);
  });
  contenedor.replaceChildren(svg);
}

/**
 * Líneas.
 * series: [{ nombre, valores:[n], color, discontinua? }], xs: etiquetas del eje x
 * bandas: [{ desde, hasta, etiqueta }] índices del eje x sombreados
 */
export function lineas(contenedor, xs, series, { formato = (v) => v, titulo = "", tituloX = "", tituloY = "", bandas = [], min = 0, max } = {}) {
  const ancho = 640, alto = 360, m = { s: 28, i: 52, iz: 56, d: 150 };
  const todos = series.flatMap((s) => s.valores);
  const marcas = ticks(max ?? Math.max(1, ...todos) * 1.05, 5);
  const tope = marcas.at(-1);
  const x = escala(0, xs.length - 1, m.iz, ancho - m.d);
  const y = escala(min, tope, alto - m.i, m.s);
  const svg = el("svg", { viewBox: `0 0 ${ancho} ${alto}`, role: "img", "aria-label": titulo });

  for (const b of bandas) {
    el("rect", {
      x: x(b.desde - 0.5 < 0 ? 0 : b.desde - 0.5), y: m.s,
      width: x(Math.min(xs.length - 1, b.hasta + 0.5)) - x(Math.max(0, b.desde - 0.5)),
      height: alto - m.s - m.i, fill: color("--accent"), opacity: 0.07,
    }, svg);
    el("text", { x: (x(Math.max(0, b.desde - 0.5)) + x(Math.min(xs.length - 1, b.hasta + 0.5))) / 2, y: m.s - 8, "text-anchor": "middle" }, svg).textContent = b.etiqueta;
  }
  const rej = el("g", { class: "rejilla" }, svg);
  for (const v of marcas) {
    if (v < min) continue;
    el("line", { x1: m.iz, x2: ancho - m.d, y1: y(v), y2: y(v) }, rej);
    el("text", { x: m.iz - 8, y: y(v) + 5, "text-anchor": "end" }, svg).textContent = formato(v);
  }
  xs.forEach((etq, i) => {
    el("text", { x: x(i), y: alto - m.i + 18, "text-anchor": "middle" }, svg).textContent = etq;
  });
  if (tituloX) el("text", { x: (m.iz + ancho - m.d) / 2, y: alto - 6, "text-anchor": "middle", class: "titulo-eje" }, svg).textContent = tituloX;
  if (tituloY) el("text", { x: 14, y: alto / 2, transform: `rotate(-90 14 ${alto / 2})`, "text-anchor": "middle", class: "titulo-eje" }, svg).textContent = tituloY;

  // etiquetas finales sin solaparse
  const finales = series.map((s) => ({ s, yy: y(s.valores.at(-1)) })).sort((a, b) => a.yy - b.yy);
  for (let i = 1; i < finales.length; i++) {
    if (finales[i].yy - finales[i - 1].yy < 18) finales[i].yy = finales[i - 1].yy + 18;
  }
  for (const s of series) {
    const d = s.valores.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
    el("path", {
      d, fill: "none", stroke: s.color, "stroke-width": s.grosor ?? 2.5,
      "stroke-linejoin": "round", "stroke-linecap": "round",
      ...(s.discontinua ? { "stroke-dasharray": "6 5" } : {}),
    }, svg);
    s.valores.forEach((v, i) => el("circle", { cx: x(i), cy: y(v), r: 2.6, fill: s.color }, svg)
      .appendChild(el("title")).append(`${s.nombre} · ${xs[i]}: ${formato(v)}`));
    const f = finales.find((f) => f.s === s);
    el("text", { x: ancho - m.d + 8, y: f.yy + 4, style: `fill:${s.color};font-weight:600` }, svg).textContent = s.nombre;
  }
  contenedor.replaceChildren(svg);
}

/**
 * Dispersión. puntos: [[x, y, grupo]], colores: { grupo: color }
 */
export function dispersion(contenedor, puntos, colores, { titulo = "", tituloX = "", tituloY = "", dominio = [1, 5], tendencia = true } = {}) {
  const ancho = 560, alto = 380, m = { s: 16, i: 48, iz: 52, d: 16 };
  const x = escala(dominio[0], dominio[1], m.iz, ancho - m.d);
  const y = escala(dominio[0], dominio[1], alto - m.i, m.s);
  const svg = el("svg", { viewBox: `0 0 ${ancho} ${alto}`, role: "img", "aria-label": titulo });
  const rej = el("g", { class: "rejilla" }, svg);
  for (let v = dominio[0]; v <= dominio[1]; v++) {
    el("line", { x1: x(v), x2: x(v), y1: m.s, y2: alto - m.i }, rej);
    el("line", { x1: m.iz, x2: ancho - m.d, y1: y(v), y2: y(v) }, rej);
    el("text", { x: x(v), y: alto - m.i + 18, "text-anchor": "middle" }, svg).textContent = v;
    el("text", { x: m.iz - 8, y: y(v) + 4, "text-anchor": "end" }, svg).textContent = v;
  }
  el("text", { x: (m.iz + ancho - m.d) / 2, y: alto - 6, "text-anchor": "middle", class: "titulo-eje" }, svg).textContent = tituloX;
  el("text", { x: 14, y: alto / 2, transform: `rotate(-90 14 ${alto / 2})`, "text-anchor": "middle", class: "titulo-eje" }, svg).textContent = tituloY;
  // pequeño desplazamiento para que no se apilen los puntos sobre la rejilla
  let semilla = 7;
  const azar = () => ((semilla = (semilla * 16807) % 2147483647) / 2147483647 - 0.5) * 0.12;
  for (const [px, py, g] of puntos) {
    el("circle", { cx: x(px + azar()), cy: y(py + azar()), r: 3.6, fill: colores[g], "fill-opacity": 0.65 }, svg);
  }
  if (tendencia) {
    const n = puntos.length;
    const mx = puntos.reduce((s, p) => s + p[0], 0) / n;
    const my = puntos.reduce((s, p) => s + p[1], 0) / n;
    const b = puntos.reduce((s, p) => s + (p[0] - mx) * (p[1] - my), 0) / puntos.reduce((s, p) => s + (p[0] - mx) ** 2, 0);
    const a = my - b * mx;
    const [x0, x1] = dominio;
    el("line", { x1: x(x0), y1: y(a + b * x0), x2: x(x1), y2: y(a + b * x1), stroke: color("--text"), "stroke-width": 2, "stroke-dasharray": "6 5" }, svg);
  }
  contenedor.replaceChildren(svg);
}

/** Datos para la leyenda: [{ etiqueta, color, forma: "punto"|"cuadro" }] */
export function leyenda(ul, items) {
  ul.replaceChildren(...items.map((it) => {
    const li = document.createElement("li");
    const m = document.createElement("span");
    m.className = it.forma ?? "punto";
    if ((it.forma ?? "punto") === "punto") m.style.background = it.color;
    else m.style.color = it.color;
    m.setAttribute("aria-hidden", "true");
    li.append(m, it.etiqueta);
    return li;
  }));
}

export async function cargar(ruta) {
  const r = await fetch(ruta);
  if (!r.ok) throw new Error(`No se pudo cargar ${ruta} (${r.status})`);
  return r.json();
}
