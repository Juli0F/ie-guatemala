// Búsqueda en tiempo real: solo funciona con analisis/servidor_local.py.
// Usa el tema y el departamento elegidos en el explorador (leídos de la URL).

const $ = (id) => document.getElementById(id);
const form = $("tr-form");
const estadoTxt = $("tr-estado");
let temas = [], departamentos = [], ultimos = [];
const NOMBRE_FUENTE = { gdelt: "noticias", tiktok: "TikTok", x: "X" };

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const filtroActual = () => {
  const p = new URLSearchParams(location.search);
  return { tema: p.get("tema") ?? "todas", depto: p.get("depto") ?? "nacional" };
};
const nombreTema = (id) => temas.find((t) => t.id === id)?.etiqueta ?? id;
const nombreDepto = (id) => departamentos.find((d) => d.id === id)?.nombre ?? id;
const fecha = (iso) => {
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleString("es-GT", { dateStyle: "medium", timeStyle: "short" });
};

async function iniciar() {
  let estado;
  try {
    const r = await fetch("/api/estado");
    if (!r.ok) return;
    estado = await r.json();
  } catch {
    return; // sitio estático: queda visible el aviso
  }
  const datos = await (await fetch("../data/narrativas.json")).json();
  temas = estado.temas;
  departamentos = datos.departamentos;
  $("tr-no-disponible").hidden = true;
  form.hidden = false;
  for (const id of ["tiktok", "x"]) {
    const op = form.fuente.querySelector(`[value="${id}"]`);
    if (!estado.fuentes[id]) {
      op.disabled = true;
      op.textContent += " (sin configurar)";
    } else if (id === "x") {
      op.textContent += ` · ${estado.x_max_resultados} posts por búsqueda`;
    }
  }
  if (estado.datos_reales) {
    estadoTxt.textContent = "El explorador usa tus datos reales.";
  }
  mostrarFiltro();
  addEventListener("popstate", mostrarFiltro);
  // el explorador actualiza la URL con replaceState: refrescamos la etiqueta al cambiar sus filtros
  $("filtros")?.addEventListener("change", () => setTimeout(mostrarFiltro));
  $("mapa-gt")?.addEventListener("click", () => setTimeout(mostrarFiltro));
}

function mostrarFiltro() {
  const { tema, depto } = filtroActual();
  $("tr-filtro").textContent = `Buscará ${tema === "todas" ? "todos los temas" : nombreTema(tema).toLowerCase()} en ${depto === "nacional" ? "todo el país" : nombreDepto(depto)}.`;
}

form.addEventListener("submit", async () => {
  const { tema, depto } = filtroActual();
  const p = new URLSearchParams({ fuente: form.fuente.value, periodo: form.periodo.value, tema, depto, q: form.q.value.trim() });
  $("tr-buscar").disabled = true;
  estadoTxt.textContent = "Consultando la fuente…";
  $("tr-lista").replaceChildren();
  $("tr-resumen").hidden = $("tr-acciones").hidden = true;
  try {
    const r = await fetch(`/api/buscar?${p}`);
    const datos = await r.json();
    if (!r.ok) throw new Error(datos.error ?? `Error ${r.status}`);
    ultimos = datos.items;
    pintar(datos, depto);
  } catch (e) {
    estadoTxt.textContent = `No se pudo completar la búsqueda: ${e.message}`;
  } finally {
    $("tr-buscar").disabled = false;
  }
});

function chips(ul, conteo, nombre) {
  ul.innerHTML = [...conteo.entries()].sort((a, b) => b[1] - a[1])
    .map(([k, n]) => `<li class="chip">${esc(nombre(k))} · <strong>${n}</strong></li>`).join("") || `<li class="muted">Sin datos</li>`;
}

function pintar(datos, depto) {
  const items = datos.items;
  const clasificados = items.filter((it) => it.temas.length);
  const enDepto = depto === "nacional" ? null : items.filter((it) => it.depto === depto).length;
  estadoTxt.textContent = `${items.length} resultados de ${NOMBRE_FUENTE[datos.fuente] ?? datos.fuente} (${fecha(datos.consultado)}). `
    + `${clasificados.length} tratan de los temas`
    + (enDepto !== null ? `; ${enDepto} mencionan ${nombreDepto(depto)} y van primero.` : ".")
    + (datos.fuente === "x" ? " En X solo se buscan los últimos 7 días." : "");
  const porTema = new Map(), porDepto = new Map();
  for (const it of items) {
    for (const t of it.temas.length ? it.temas : ["sin_tema"]) porTema.set(t, (porTema.get(t) ?? 0) + 1);
    const d = it.depto ?? "sin_ubicacion";
    porDepto.set(d, (porDepto.get(d) ?? 0) + 1);
  }
  chips($("tr-temas"), porTema, (k) => (k === "sin_tema" ? "Sin tema" : nombreTema(k)));
  chips($("tr-deptos"), porDepto, (k) => (k === "sin_ubicacion" ? "Sin ubicación" : nombreDepto(k)));
  $("tr-resumen").hidden = items.length === 0;
  $("tr-acciones").hidden = !(datos.fuente !== "gdelt" && items.length);

  $("tr-lista").innerHTML = items.slice(0, 100).map((it) => `
    <li>
      <a href="${esc(it.url)}" target="_blank" rel="noopener noreferrer">${esc(it.texto || "(sin texto)")}</a>
      <div class="muted">${esc(it.origen)} · ${esc(fecha(it.fecha))}${it.metricas?.view_count ? ` · ${Number(it.metricas.view_count).toLocaleString("es-GT")} vistas` : ""}</div>
      <ul class="chips">
        ${it.temas.map((t) => `<li class="chip">${esc(nombreTema(t))}</li>`).join("")}
        ${it.depto ? `<li class="chip">${esc(nombreDepto(it.depto))} · ${esc(it.conf)}</li>` : ""}
      </ul>
    </li>`).join("");
}

$("tr-guardar").addEventListener("click", async (e) => {
  const boton = e.currentTarget;
  boton.disabled = true;
  estadoTxt.textContent = "Guardando y regenerando el explorador…";
  try {
    const r = await fetch("/api/guardar", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ items: ultimos }) });
    const res = await r.json();
    if (!r.ok || !res.pipeline_ok) throw new Error(res.error ?? res.pipeline ?? "error desconocido");
    estadoTxt.textContent = `Se agregaron ${res.agregadas} publicaciones. Recarga la página para verlas.`;
  } catch (err) {
    estadoTxt.textContent = `No se pudo guardar: ${err.message}`;
  } finally {
    boton.disabled = false;
  }
});

iniciar();
