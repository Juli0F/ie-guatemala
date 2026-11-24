// Proyecto 3 - C2IE: simulación, DiD e indicadores.
import { color, alCambiarTema, fmt, barrasH, lineas, cargar } from "./graficos.js";

const d = await cargar("../data/c2ie.json");
const est = d.estrategias;
const base = est.find((e) => e.id === "sin_intervencion");
const puentes = est.find((e) => e.id === "intermediacion");
const seguidores = est.find((e) => e.id === "seguidores");
const { did, semanas } = d;

document.getElementById("kpis").innerHTML = [
  [fmt.p(base.alcance_medio_pct), "alcance sin intervención"],
  [`−${fmt.p(puentes.reduccion_vs_base_pct)}`, "reducción con 8 puentes"],
  [`−${fmt.p(seguidores.reduccion_vs_base_pct)}`, "reducción con 8 «más seguidores»"],
  [`${fmt.d(did.did_pp, 1)} pp`, "efecto DiD de la campaña"],
  ["600", "corridas Monte Carlo por estrategia"],
].map(([v, n]) => `<div class="kpi"><span class="valor">${v}</span><span class="nombre">${n}</span></div>`).join("");

document.getElementById("resumen-texto").innerHTML = `
  Sin intervención, la narrativa alcanza en promedio el <strong>${fmt.p(base.alcance_medio_pct)}</strong> de las cuentas del ecosistema.
  Si se interviene sobre las 8 cuentas puente identificadas en el análisis de redes, el alcance baja al
  <strong>${fmt.p(puentes.alcance_medio_pct)}</strong> (−${fmt.p(puentes.reduccion_vs_base_pct)}). Elegir a las 8 cuentas con más seguidores
  solo lo reduce un ${fmt.p(seguidores.reduccion_vs_base_pct)}. En campo, la proporción de publicaciones que reproducen la narrativa
  en la región tratada bajó <strong>${fmt.d(Math.abs(did.did_pp), 1)} puntos porcentuales</strong> respecto a la región de control
  (diferencias en diferencias), y las compras de pánico cayeron un ${fmt.d(100 - semanas.at(-1).compras_panico_idx, 0)} %.`;

document.querySelector("#tabla-estrategias tbody").innerHTML = est.map((e) => `
  <tr${e.id === "intermediacion" ? ' style="font-weight:600"' : ""}>
    <td>${e.etiqueta}</td>
    <td class="num">${fmt.p(e.alcance_medio_pct)}</td>
    <td class="num">${fmt.d(e.ic95[0], 1)}–${fmt.d(e.ic95[1], 1)}</td>
    <td class="num">${e.reduccion_vs_base_pct ? "−" + fmt.p(e.reduccion_vs_base_pct) : "—"}</td>
    <td>${e.inoculados.length ? e.inoculados.map((i) => `<code>${i}</code>`).join(" ") : "—"}</td>
  </tr>`).join("");

const cambio = (a, b) => `${b - a > 0 ? "+" : ""}${fmt.d(b - a, 1)}`;
document.querySelector("#tabla-did tbody").innerHTML = `
  <tr><td>Tratada (área metropolitana)</td><td class="num">${fmt.d(did.pre_tratada, 1)}</td><td class="num">${fmt.d(did.post_tratada, 1)}</td><td class="num">${cambio(did.pre_tratada, did.post_tratada)}</td></tr>
  <tr><td>Control (Quetzaltenango)</td><td class="num">${fmt.d(did.pre_control, 1)}</td><td class="num">${fmt.d(did.post_control, 1)}</td><td class="num">${cambio(did.pre_control, did.post_control)}</td></tr>
  <tr><td><strong>Diferencia en diferencias</strong></td><td></td><td></td><td class="num"><strong>${fmt.d(did.did_pp, 1)} pp</strong></td></tr>`;
document.getElementById("did-texto").innerHTML = `En la región de control, la narrativa siguió creciendo
  (${cambio(did.pre_control, did.post_control)} pp). En la región tratada, cayó (${cambio(did.pre_tratada, did.post_tratada)} pp).
  La diferencia, <strong>${fmt.d(did.did_pp, 1)} puntos porcentuales</strong>, es el efecto atribuible a la campaña,
  una vez descontada la tendencia común a ambas regiones.`;

document.querySelector("#tabla-mop tbody").innerHTML = d.mop.map((m) => {
  const p = (m.logro / m.meta) * 100;
  return `<tr><td>${m.indicador}</td><td class="num">${fmt.n(m.meta)}</td><td class="num">${fmt.n(m.logro)}</td>
    <td class="num" style="color:var(${p >= 100 ? "--contra" : "--pro"})">${fmt.d(p, 0)} %</td></tr>`;
}).join("");
document.querySelector("#tabla-moe tbody").innerHTML = d.moe.map((m) => {
  const ok = m.direccion === "baja" ? m.final < m.base : m.final > m.base;
  const delta = ((m.final - m.base) / m.base) * 100;
  return `<tr><td>${m.indicador}</td><td class="num">${fmt.d(m.base, 1)}${m.unidad}</td><td class="num">${fmt.d(m.final, 1)}${m.unidad}</td>
    <td><span style="color:var(${ok ? "--contra" : "--pro"})" aria-hidden="true">${ok ? "▲" : "▼"}</span> ${ok ? "Logrado" : "No logrado"} (${delta > 0 ? "+" : ""}${fmt.d(delta, 0)} %)</td></tr>`;
}).join("");

function graficar() {
  const cols = {
    sin_intervencion: color("--neutral"), aleatoria: color("--com-2"), seguidores: color("--com-4"),
    pagerank: color("--com-3"), intermediacion: color("--com-0"),
  };
  barrasH(document.getElementById("g-alcance"),
    est.map((e) => ({ etiqueta: e.etiqueta, valor: e.alcance_medio_pct, color: cols[e.id], resaltar: e.id === "intermediacion" })),
    { formato: (v) => fmt.p(v, 0), titulo: "Alcance final de la narrativa por estrategia", max: 50 });

  const ciclos = base.curva.map((_, i) => String(i));
  const corto = { sin_intervencion: "Base", aleatoria: "Azar", seguidores: "Seguidores", pagerank: "PageRank", intermediacion: "Puentes" };
  lineas(document.getElementById("g-curvas"), ciclos,
    est.map((e) => ({ nombre: corto[e.id], valores: e.curva, color: cols[e.id], grosor: e.id === "intermediacion" ? 3.5 : 2, discontinua: e.id === "sin_intervencion" })),
    { formato: (v) => `${v}`, tituloX: "Ciclo de difusión", tituloY: "% de cuentas alcanzadas", titulo: "Curvas de difusión por estrategia" });

  const xs = semanas.map((s) => `S${s.semana}`);
  const banda = [{ desde: 4, hasta: 9, etiqueta: "Campaña" }];
  lineas(document.getElementById("g-did"), xs, [
    { nombre: "Tratada", valores: semanas.map((s) => s.narrativa_tratada_pct), color: color("--com-0"), grosor: 3 },
    { nombre: "Control", valores: semanas.map((s) => s.narrativa_control_pct), color: color("--neutral"), discontinua: true },
  ], { formato: (v) => `${v}`, bandas: banda, tituloY: "% de publicaciones", titulo: "Serie semanal tratada frente a control" });

  lineas(document.getElementById("g-conducta"), xs, [
    { nombre: "Compras de pánico", valores: semanas.map((s) => s.compras_panico_idx), color: color("--pro"), grosor: 3 },
    { nombre: "Consultas ÷ 10", valores: semanas.map((s) => Math.round(s.verificaciones_calendario / 10)), color: color("--contra"), grosor: 3 },
  ], { formato: (v) => `${v}`, bandas: banda, titulo: "Conducta observable por semana" });
}
alCambiarTema(graficar);
