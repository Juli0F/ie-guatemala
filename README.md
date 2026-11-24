# Evaluación del Entorno de Información en Guatemala (TikTok e Instagram)

Sitio estático para GitHub Pages. Por ahora el sitio muestra solo el proyecto 1.

| Proyecto | Página | Qué demuestra |
|---|---|---|
| 1. Narrativas, territorio y redes de influencia | `proyectos/red-influencia.html` | Libro de códigos (agua, política, narcopolítica, Estado), geolocalización por departamento, SNA por filtro, búsqueda en tiempo real |
| 2. TAA (en pausa) | `proyectos/taa.html` | Sin enlaces desde el sitio y con `noindex` |
| 3. Informe C2IE (en pausa) | `proyectos/c2ie.html` | Sin enlaces desde el sitio y con `noindex` |

> Los datos publicados son **sintéticos**. El proyecto 1 está preparado para datos reales,
> que se guardan en `data/crudo/` y **no** se suben al repositorio.

## Estructura

```
index.html                       Portada
proyectos/                       Páginas de los estudios de caso
assets/css, assets/js            Estilos y scripts (sin dependencias ni compilación)
analisis/sna.py                  Algoritmos de red: Brandes, PageRank, Louvain, modularidad, layout
analisis/libro_codigos.json      Temas, subnarrativas, términos y consultas en vivo
analisis/geografia_gt.json       Nomenclátor de los 22 departamentos
analisis/pipeline_narrativas.py  Proyecto 1: clasifica, geolocaliza, seudonimiza y calcula métricas
analisis/muestra_sintetica.py    Proyecto 1: genera la muestra de demostración
analisis/servidor_local.py       Servidor local con búsqueda en tiempo real
analisis/generar_red.py          Proyectos 2 y 3: red sintética del caso del agua
analisis/taa_c2ie.py             Proyectos 2 y 3: encuesta, TAA y simulación
data/                            JSON para el sitio y CSV para Excel
data/crudo/                      Datos crudos (ignorado por git, salvo plantilla y muestra)
neo4j/                           Carga en Neo4j y consultas de análisis
```

## Proyecto 1 con datos reales

1. Reúne publicaciones con el formato de `data/crudo/plantilla_publicaciones.csv` y guárdalas como
   `data/crudo/publicaciones.csv`. Vías: TikTok Research API, Meta Content Library, herramientas
   académicas de captura (Zeeschuimer + 4CAT) o codificación manual. Respeta los términos de cada plataforma.
2. Opcional: lista en `data/crudo/cuentas_publicas.csv` (columna `cuenta`) las cuentas institucionales o de medios
   que no deben seudonimizarse. Todas las demás se seudonimizan con una sal secreta (`data/crudo/.sal`).
3. Ejecuta:
   ```
   python analisis/pipeline_narrativas.py
   ```
   Si `data/crudo/publicaciones.csv` existe, lo usa. Si no, usa la muestra sintética.
4. Valida el diccionario: dos personas codifican `data/crudo/muestra_validacion.csv` y se calcula
   el kappa de Cohen. Ajusta `libro_codigos.json` con los hashtags emergentes que muestra el explorador.

## Ver en local y buscar en tiempo real

Las páginas cargan JSON con `fetch`, así que hace falta un servidor (no basta con abrir el archivo):

```
python analisis/servidor_local.py
```

Abre <http://127.0.0.1:8000/proyectos/red-influencia.html#tiempo-real>. Además del sitio, el servidor ofrece:

- **Noticias en línea (GDELT)**: medios de Guatemala, gratuita y sin credenciales. Admite como máximo una consulta cada 5 segundos.
- **TikTok Research API**: videos con `region_code = GT`. Requiere acceso aprobado. Antes de iniciar el servidor:
  ```
  $env:TIKTOK_CLIENT_KEY = "..."
  $env:TIKTOK_CLIENT_SECRET = "..."
  ```
  Se solicita en <https://developers.tiktok.com> (producto *Research API*). Es gratuita, pero solo para
  investigadores académicos o de organizaciones sin fines de lucro, con afiliación institucional y propuesta de investigación,
  y en las regiones que TikTok admite.
- **X API v2 (búsqueda reciente)**: posts en español de los últimos 7 días que mencionan Guatemala o el departamento elegido.
  Es de pago por publicación leída. Crea una app en <https://developer.x.com>, copia el *Bearer Token* y, antes de iniciar el servidor:
  ```
  $env:X_BEARER_TOKEN = "..."
  $env:X_MAX_RESULTADOS = "50"   # opcional, 10-100 posts por búsqueda; controla el costo
  ```
  Las respuestas, citas y menciones se guardan como aristas de la red, y la ubicación del perfil, como `bio_ubicacion`.

Los resultados de TikTok y X se pueden guardar en `data/crudo/publicaciones.csv` con un botón. El explorador se regenera solo.
Las búsquedas iguales se guardan en caché 5 minutos, así que repetirlas no vuelve a cobrar.

Instagram no tiene una API pública de búsqueda en tiempo real. Sus datos se incorporan con el CSV.
En GitHub Pages el sitio es estático y el panel de búsqueda explica cómo activarlo en local.

## Regenerar los datos de los proyectos 2 y 3

```
python analisis/generar_red.py
python analisis/taa_c2ie.py
```

Si tienes NetworkX instalado (`pip install networkx`), `generar_red.py` valida PageRank e
intermediación contra esa librería.

## Publicar en GitHub Pages

Repositorio: <https://github.com/Juli0F/ie-guatemala> (remoto `origin`, rama `main`).

1. Crea en GitHub el repositorio público vacío `ie-guatemala`, sin README ni licencia.
2. Desde esta carpeta:
   ```
   git add .
   git commit -m "Sitio IE Guatemala"
   git push -u origin main
   ```
3. En **Settings → Pages**, elige *Deploy from a branch*, rama `main`, carpeta `/ (root)`.
4. El sitio queda en <https://juli0f.github.io/ie-guatemala/>.

Antes de cada `git add`, comprueba con `git status` que no aparezca nada de `data/crudo/` salvo la plantilla y la muestra.

## Personalizar

La biografía está en la sección `#perfil` de `index.html`. Los enlaces de contacto están en esa misma sección.
