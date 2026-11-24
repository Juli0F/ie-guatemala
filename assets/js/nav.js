// Navegación adaptable: una sola lista que es popover cuando no cabe en la
// cabecera y fila en línea cuando sí cabe. Sin script, queda como popover.
(() => {
  const header = document.querySelector(".site-header");
  if (!header) return;
  const inner = header.querySelector(".header-inner");
  const menu = header.querySelector(".site-menu");
  let ultimoAncho = 0;

  function sincronizar() {
    const ancho = inner.clientWidth;
    const esAncho = header.classList.contains("is-wide");
    // en modo colapsado solo se vuelve a medir si la cabecera creció
    if (!esAncho && ancho <= ultimoAncho) return;
    ultimoAncho = ancho;

    const estabaAbierto = menu.matches(":popover-open, .\\:popover-open");
    header.classList.add("is-measuring", "is-wide");
    menu.removeAttribute("popover");
    const cabe = inner.scrollWidth <= inner.clientWidth;
    if (!cabe) {
      header.classList.remove("is-wide");
      menu.setAttribute("popover", "auto");
      if (estabaAbierto) menu.showPopover?.();
    }
    requestAnimationFrame(() => header.classList.remove("is-measuring"));
  }

  const ro = new ResizeObserver(sincronizar);
  ro.observe(header);
  ro.observe(menu);

  // Cerrar el popover al elegir un enlace a una sección de la misma página
  menu.addEventListener("click", (e) => {
    if (e.target.closest("a") && menu.hasAttribute("popover")) menu.hidePopover?.();
  });
})();

// Botón de tema: dos estados (sistema y su contrario). Se guarda solo si difiere del sistema.
(() => {
  const boton = document.getElementById("tema-boton");
  const meta = document.querySelector('meta[name="color-scheme"]');
  if (!boton || !meta) return;
  const sistema = matchMedia("(prefers-color-scheme: dark)");
  const aplicar = (valor) => {
    meta.content = valor ?? "light dark";
    document.dispatchEvent(new Event("cambio-tema"));
  };
  boton.addEventListener("click", () => {
    const actual = meta.content === "light" || meta.content === "dark" ? meta.content : (sistema.matches ? "dark" : "light");
    const destino = actual === "dark" ? "light" : "dark";
    const delSistema = sistema.matches ? "dark" : "light";
    let guardado = destino === delSistema ? null : destino;
    try {
      if (guardado) localStorage.setItem("color-scheme", guardado); else localStorage.removeItem("color-scheme");
    } catch { /* sin almacenamiento: el cambio se aplica igual en esta visita */ }
    aplicar(guardado);
  });
  addEventListener("storage", (e) => { if (e.key === "color-scheme") aplicar(e.newValue); });
})();

// Quetzal de fondo: aparece cuando la cabecera (con su propio quetzal) sale de la vista
(() => {
  const hero = document.querySelector(".hero");
  if (!hero || !("IntersectionObserver" in window)) return;
  new IntersectionObserver(([e]) => {
    document.body.classList.toggle("con-fondo", e.intersectionRatio < 0.35);
  }, { threshold: [0, 0.35, 1] }).observe(hero);
})();

// Las páginas cargan datos con fetch y módulos JS, que el navegador bloquea en file://
if (location.protocol === "file:") {
  document.addEventListener("DOMContentLoaded", () => {
    const aviso = document.createElement("p");
    aviso.className = "aviso-local";
    aviso.setAttribute("role", "alert");
    aviso.innerHTML = "Abriste el archivo directamente y el navegador bloquea la carga de datos. Ejecuta <code>python -m http.server 8000</code> en la carpeta del proyecto y abre <code>http://localhost:8000</code>.";
    document.body.prepend(aviso);
  });
}

if (!Object.hasOwn(HTMLElement.prototype, "popover")) {
  import("https://unpkg.com/@oddbird/popover-polyfill@latest/dist/popover.min.js");
}
