// Proyecto 2 - TAA: tablas, perfiles y gráficos.
import { color, alCambiarTema, fmt, barrasH, dispersion, leyenda, cargar } from "./graficos.js";

const d = await cargar("../data/taa.json");
const C = d.constructos;
const segs = d.segmentos;
const porId = Object.fromEntries(segs.map((s) => [s.id, s]));
const varSeg = { TA1: "--com-0", TA2: "--com-2", TA3: "--com-1", TA4: "--com-4" };
const CORTO = { TA1: "Familias (Mixco / Villa Nueva)", TA2: "Universitarios", TA3: "Memes políticos", TA4: "Tiendas de barrio" };

const alfas = Object.values(d.alfa_cronbach);
document.getElementById("kpis").innerHTML = [
  [segs.length, "audiencias objetivo"],
  [fmt.n(d.n_total), "encuestas (sintéticas)"],
  [`${fmt.d(Math.min(...alfas), 2)}–${fmt.d(Math.max(...alfas), 2)}`, "rango α de Cronbach"],
  [fmt.d(d.correlaciones.AM_IC, 2), "r alfabetización ↔ compartir"],
  [segs[0].id, "audiencia prioritaria"],
].map(([v, n]) => `<div class="kpi"><span class="valor">${v}</span><span class="nombre">${n}</span></div>`).join("");
document.getElementById("n-total").textContent = fmt.n(d.n_total);

const valorar = (a) => (a >= 0.9 ? "Excelente" : a >= 0.8 ? "Buena" : a >= 0.7 ? "Aceptable" : "Insuficiente");
document.querySelector("#tabla-alfa tbody").innerHTML = Object.entries(d.alfa_cronbach).map(([k, a]) =>
  `<tr><td>${C[k]} <span class="muted">(${k})</span></td><td class="num">4</td><td class="num">${fmt.d(a, 3)}</td><td>${valorar(a)}</td></tr>`).join("");

const leerR = (r) => {
  const f = Math.abs(r);
  const fuerza = f >= 0.5 ? "fuerte" : f >= 0.3 ? "moderada" : f >= 0.1 ? "débil" : "despreciable";
  return `${fuerza}${f >= 0.1 ? (r < 0 ? ", negativa" : ", positiva") : ""}`;
};
const pares = { AM_IC: ["AM", "IC"], CI_IC: ["CI", "IC"], PR_IC: ["PR", "IC"], CI_PR: ["CI", "PR"] };
document.querySelector("#tabla-correl tbody").innerHTML = Object.entries(d.correlaciones).map(([k, r]) =>
  `<tr><td>${C[pares[k][0]]} ↔ ${C[pares[k][1]]}</td><td class="num">${fmt.d(r, 3)}</td><td>${leerR(r)}</td></tr>`).join("");
document.getElementById("cap-dispersion").textContent +=
  ` r = ${fmt.d(d.correlaciones.AM_IC, 2)}: a mayor alfabetización mediática, menor intención de compartir sin verificar.`;

// Perfiles
const barra = (nombre, v) => `
  <div class="barra-mini"><span>${nombre}</span>
    <span class="pista" role="presentation"><span class="relleno" style="inline-size:${((v - 1) / 4) * 100}%"></span></span>
    <span class="v">${fmt.d(v, 2)}</span></div>`;
document.getElementById("segmentos").innerHTML = [...segs].sort((a, b) => a.id.localeCompare(b.id)).map((s) => `
  <article class="segmento">
    <header>
      <h3><span style="color:var(${varSeg[s.id]})" aria-hidden="true">●</span> ${s.id} · ${s.nombre}</h3>
      <span class="rango">Prioridad #${s.rango}</span>
    </header>
    <ul class="chips"><li class="chip ${s.plataforma}">${s.plataforma === "tiktok" ? "TikTok" : "Instagram"}</li><li class="chip">${s.edad} años</li><li class="chip">n = ${s.n}</li></ul>
    <div style="display:grid;gap:.35rem;margin-block:.9rem">
      ${Object.keys(C).map((k) => barra(C[k], s.medias[k])).join("")}
    </div>
    <dl>
      <dt>Condiciones</dt><dd>${s.condiciones}</dd>
      <dt>Vulnerabilidades</dt><dd>${s.vulnerabilidades.join("; ")}</dd>
      <dt>Motivaciones</dt><dd>${s.motivaciones.join(", ")}</dd>
      <dt>Voces creíbles</dt><dd>${s.voces_creibles.join(", ")}</dd>
      <dt>Formatos</dt><dd>${s.formatos.join("; ")}</dd>
      <dt>Horario</dt><dd>${s.horario}</dd>
      <dt>Conducta deseada</dt><dd>${s.comportamiento_deseado}</dd>
    </dl>
  </article>`).join("");

document.querySelector("#tabla-prioridad tbody").innerHTML = segs.map((s) => `
  <tr><td class="num">${s.rango}</td><td>${s.id} · ${s.nombre}</td><td>${s.plataforma === "tiktok" ? "TikTok" : "Instagram"}</td>
  <td class="num">${fmt.d(s.susceptibilidad, 2)}</td><td class="num">${fmt.d(s.accesibilidad, 1)}</td>
  <td class="num">${fmt.d(s.efecto, 2)}</td><td class="num"><strong>${fmt.d(s.prioridad, 1)}</strong></td></tr>`).join("");

function graficar() {
  const colores = Object.fromEntries(Object.entries(varSeg).map(([k, v]) => [k, color(v)]));
  barrasH(document.getElementById("g-prioridad"),
    segs.map((s, i) => ({ etiqueta: `${s.id} · ${s.plataforma === "tiktok" ? "TikTok" : "Instagram"}`, valor: s.prioridad, color: colores[s.id], resaltar: i === 0 })),
    { formato: (v) => fmt.d(v, 0), titulo: "Índice de prioridad por audiencia" });
  dispersion(document.getElementById("g-dispersion"), d.dispersion_am_ic, colores, {
    titulo: "Dispersión entre alfabetización mediática e intención de compartir",
    tituloX: "Alfabetización mediática (1-5)", tituloY: "Intención de compartir (1-5)",
  });
  leyenda(document.getElementById("ley-dispersion"),
    Object.keys(varSeg).map((k) => ({ etiqueta: `${k} · ${CORTO[k]}`, color: colores[k] })));
}
alCambiarTema(graficar);
