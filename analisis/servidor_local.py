"""
Servidor local con búsqueda en tiempo real
==========================================

Sirve el portafolio en http://localhost:8000 y agrega una API que solo existe al
ejecutarlo en tu equipo (en GitHub Pages el sitio es estático):

  GET  /api/estado                     -> fuentes disponibles
  GET  /api/buscar?fuente=gdelt&tema=agua&depto=quetzaltenango&periodo=3d&q=texto
  POST /api/guardar                    -> agrega resultados de TikTok a
                                          data/crudo/publicaciones.csv y regenera
                                          data/narrativas.json

Fuentes:
  gdelt   Noticias en línea de medios de Guatemala (GDELT DOC 2.0). Gratuita, sin
          credenciales; se actualiza cada 15 minutos. Clasifica el titular.
  tiktok  TikTok Research API (videos con region_code = GT). Requiere acceso
          aprobado: define TIKTOK_CLIENT_KEY y TIKTOK_CLIENT_SECRET antes de iniciar.
  x       X API v2, búsqueda reciente (7 días). De pago por publicación leída: define
          X_BEARER_TOKEN y, opcional, X_MAX_RESULTADOS (10-100, por defecto 50).

Cada resultado se clasifica con el mismo libro de códigos y nomenclátor que el
pipeline, así que los temas y departamentos son comparables.

Uso:
    python analisis/servidor_local.py            # puerto 8000
    python analisis/servidor_local.py --puerto 8080

Solo escucha en 127.0.0.1. Solo biblioteca estándar.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_narrativas import (  # noqa: E402
    ANALISIS, CRUDO, RAIZ, Clasificador, Geolocalizador, extraer_hashtags, normalizar,
)

LIBRO = json.loads((ANALISIS / "libro_codigos.json").read_text(encoding="utf-8"))
GEO = json.loads((ANALISIS / "geografia_gt.json").read_text(encoding="utf-8"))
CLF = Clasificador(LIBRO)
GEOLOC = Geolocalizador(GEO)
TEMAS = {t["id"]: t for t in LIBRO["temas"]}
DEPTOS = {d["id"]: d for d in GEO["departamentos"]}
PERIODOS = {"24h": 1, "3d": 3, "7d": 7, "30d": 30}
AGENTE = "portafolio-ie-local/1.0 (investigacion academica)"
CAMPOS_CSV = ["id_publicacion", "plataforma", "fecha", "cuenta", "tipo_cuenta", "seguidores", "bio_ubicacion", "texto",
              "hashtags", "transcripcion", "ubicacion_etiquetada", "interaccion", "cuenta_objetivo", "menciones",
              "vistas", "me_gusta", "comentarios", "compartidos"]

_cache: dict[str, tuple[float, dict]] = {}
_bloqueo_gdelt = threading.Lock()
_ultima_gdelt = [0.0]


class ErrorFuente(Exception):
    pass


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def http_json(url: str, datos: bytes | None = None, cabeceras: dict | None = None, timeout=60) -> dict:
    req = urllib.request.Request(url, data=datos, headers={"User-Agent": AGENTE, **(cabeceras or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            cuerpo = r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise ErrorFuente("La fuente limitó las consultas (429). Espera un minuto y vuelve a intentarlo.") from e
        detalle = e.read().decode("utf-8", errors="replace")[:300]
        raise ErrorFuente(f"La fuente respondió {e.code}: {detalle}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        razon = getattr(e, "reason", e)
        raise ErrorFuente(f"No se pudo conectar con la fuente ({razon}). Revisa tu conexión o inténtalo más tarde.") from e
    try:
        return json.loads(cuerpo) if cuerpo.strip() else {}
    except json.JSONDecodeError as e:
        raise ErrorFuente(f"Respuesta no válida de la fuente: {cuerpo[:200]}") from e


def terminos_busqueda(tema: str, extra: str) -> list[str]:
    if extra:
        return [extra]
    if tema in TEMAS:
        return TEMAS[tema]["consulta"]
    # todos los temas: dos términos de cada uno para no exceder la longitud de la consulta
    return [x for t in LIBRO["temas"] for x in t["consulta"][:2]]


def terminos_lugar(depto: str) -> list[str]:
    if depto not in DEPTOS:
        return []
    d = DEPTOS[depto]
    terms = ([d["nombre"]] if d["id"] != "guatemala" else []) + d["alias"][:3]
    return list(dict.fromkeys(t for t in terms if t))


def clasificar(texto: str, hashtags_txt: str = "", transcripcion: str = "", geotag: str = "") -> dict:
    hashtags = extraer_hashtags(hashtags_txt, texto, transcripcion)
    norm = normalizar(" ".join([texto, transcripcion, hashtags_txt.replace("#", " ")]))
    temas, sub, _ = CLF.clasificar(norm, hashtags)
    depto, conf = None, None
    if geotag:
        depto = GEOLOC.buscar(normalizar(geotag))
        conf = "alta" if depto else None
    if not depto:
        depto = GEOLOC.buscar(norm)
        conf = "media" if depto else None
    return {"temas": temas, "subnarrativa": sub, "depto": depto, "conf": conf}


# ---------------------------------------------------------------------------
# Fuente 1: GDELT DOC 2.0 (noticias)
# ---------------------------------------------------------------------------

def buscar_gdelt(tema: str, depto: str, dias: int, extra: str) -> list[dict]:
    def frase(t):
        return f'"{t}"' if " " in t else t
    terms = terminos_busqueda(tema, extra)
    partes = ["(" + " OR ".join(frase(t) for t in terms) + ")" if len(terms) > 1 else frase(terms[0])]
    lugar = terminos_lugar(depto)
    if lugar:
        partes.append("(" + " OR ".join(frase(t) for t in lugar) + ")" if len(lugar) > 1 else frase(lugar[0]))
    def consultar(filtro_pais: list[str]) -> list[dict]:
        params = {"query": " ".join(partes + filtro_pais + ["sourcelang:spanish"]), "mode": "artlist", "format": "json",
                  "maxrecords": "150", "sort": "datedesc", "timespan": f"{dias}d" if dias > 1 else "24h"}
        url = "https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode(params)
        with _bloqueo_gdelt:  # GDELT pide no más de una consulta cada 5 segundos
            espera = 6.5 - (time.time() - _ultima_gdelt[0])
            if espera > 0:
                time.sleep(espera)
            try:
                return http_json(url).get("articles", [])
            finally:
                _ultima_gdelt[0] = time.time()

    # 1) medios con sede en Guatemala; 2) si hay pocos, cualquier medio en español que mencione Guatemala
    articulos = consultar(["sourcecountry:guatemala"])
    if len(articulos) < 15 and not lugar:
        vistos = {a.get("url") for a in articulos}
        articulos += [a for a in consultar(["Guatemala"]) if a.get("url") not in vistos]
    resultados = []
    for a in articulos:
        fecha = a.get("seendate", "")
        try:
            fecha = datetime.strptime(fecha, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            pass
        titulo = a.get("title", "")
        resultados.append({
            "fuente": "gdelt", "id": a.get("url"), "fecha": fecha, "texto": titulo, "url": a.get("url"),
            "origen": a.get("domain", ""), "metricas": {}, **clasificar(titulo),
        })
    return resultados


# ---------------------------------------------------------------------------
# Fuente 2: TikTok Research API
# ---------------------------------------------------------------------------

_token_tiktok = {"valor": None, "expira": 0.0}


def tiktok_disponible() -> bool:
    return bool(os.environ.get("TIKTOK_CLIENT_KEY") and os.environ.get("TIKTOK_CLIENT_SECRET"))


def token_tiktok() -> str:
    if _token_tiktok["valor"] and time.time() < _token_tiktok["expira"] - 60:
        return _token_tiktok["valor"]
    cuerpo = urllib.parse.urlencode({
        "client_key": os.environ["TIKTOK_CLIENT_KEY"], "client_secret": os.environ["TIKTOK_CLIENT_SECRET"],
        "grant_type": "client_credentials",
    }).encode()
    datos = http_json("https://open.tiktokapis.com/v2/oauth/token/", cuerpo,
                      {"Content-Type": "application/x-www-form-urlencoded"})
    if "access_token" not in datos:
        raise ErrorFuente(f"TikTok no entregó un token: {datos}")
    _token_tiktok.update(valor=datos["access_token"], expira=time.time() + int(datos.get("expires_in", 7200)))
    return _token_tiktok["valor"]


def buscar_tiktok(tema: str, depto: str, dias: int, extra: str) -> list[dict]:
    if not tiktok_disponible():
        raise ErrorFuente("TikTok Research API no está configurada. Define TIKTOK_CLIENT_KEY y TIKTOK_CLIENT_SECRET.")
    hoy = datetime.now(timezone.utc).date()
    condiciones = [
        {"operation": "IN", "field_name": "region_code", "field_values": ["GT"]},
        {"operation": "IN", "field_name": "keyword", "field_values": terminos_busqueda(tema, extra)},
    ]
    lugar = terminos_lugar(depto)
    if lugar:
        condiciones.append({"operation": "IN", "field_name": "keyword", "field_values": lugar})
    cuerpo = json.dumps({
        "query": {"and": condiciones},
        "start_date": (hoy - timedelta(days=min(dias, 30) - 1)).strftime("%Y%m%d"),
        "end_date": hoy.strftime("%Y%m%d"),
        "max_count": 100,
    }).encode()
    campos = "id,create_time,username,region_code,video_description,hashtag_names,voice_to_text,view_count,like_count,comment_count,share_count"
    datos = http_json(f"https://open.tiktokapis.com/v2/research/video/query/?fields={campos}", cuerpo,
                      {"Authorization": f"Bearer {token_tiktok()}", "Content-Type": "application/json"})
    if datos.get("error", {}).get("code") not in (None, "ok"):
        raise ErrorFuente(f"TikTok: {datos['error'].get('message', datos['error'])}")
    resultados = []
    for v in datos.get("data", {}).get("videos", []):
        hashtags = " ".join(f"#{h}" for h in v.get("hashtag_names", []))
        texto = v.get("video_description", "")
        transcripcion = v.get("voice_to_text", "") or ""
        fecha = datetime.fromtimestamp(int(v.get("create_time", 0)), tz=timezone.utc).isoformat()
        usuario = v.get("username", "")
        resultados.append({
            "fuente": "tiktok", "id": str(v.get("id")), "fecha": fecha, "texto": texto, "hashtags": hashtags,
            "transcripcion": transcripcion, "url": f"https://www.tiktok.com/@{usuario}/video/{v.get('id')}",
            "origen": f"@{usuario}",
            "metricas": {k: v.get(k, 0) for k in ("view_count", "like_count", "comment_count", "share_count")},
            **clasificar(texto, hashtags, transcripcion),
        })
    return resultados


# ---------------------------------------------------------------------------
# Fuente 3: X API v2 (búsqueda reciente, últimos 7 días)
# ---------------------------------------------------------------------------

def x_disponible() -> bool:
    return bool(os.environ.get("X_BEARER_TOKEN"))


def x_max_resultados() -> int:
    # X cobra por publicación leída: este límite controla el costo de cada búsqueda
    try:
        return max(10, min(100, int(os.environ.get("X_MAX_RESULTADOS", "50"))))
    except ValueError:
        return 50


def buscar_x(tema: str, depto: str, dias: int, extra: str) -> list[dict]:
    if not x_disponible():
        raise ErrorFuente("X API no está configurada. Define X_BEARER_TOKEN antes de iniciar el servidor.")

    def frase(t):
        return f'"{t}"' if " " in t else t

    def grupo(ts):
        return "(" + " OR ".join(frase(t) for t in ts) + ")" if len(ts) > 1 else frase(ts[0])

    lugar = terminos_lugar(depto) or ["Guatemala", "Guate", "chapin", "chapines"]
    terms = terminos_busqueda(tema, extra)
    sufijo = f" {grupo(lugar)} lang:es -is:retweet"
    while terms and len(grupo(terms) + sufijo) > 512:  # límite de longitud de la consulta
        terms = terms[:-1]
    params = {
        "query": grupo(terms) + sufijo,
        "max_results": str(x_max_resultados()),
        "start_time": (datetime.now(timezone.utc) - timedelta(days=min(dias, 7))).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tweet.fields": "created_at,public_metrics,entities,referenced_tweets,author_id,geo,lang",
        "expansions": "author_id,referenced_tweets.id.author_id,geo.place_id",
        "user.fields": "username,location,public_metrics,verified",
        "place.fields": "full_name,country_code",
    }
    datos = http_json("https://api.x.com/2/tweets/search/recent?" + urllib.parse.urlencode(params),
                      cabeceras={"Authorization": f"Bearer {os.environ['X_BEARER_TOKEN']}"})
    if "data" not in datos and datos.get("errors"):
        raise ErrorFuente(f"X: {datos['errors'][0].get('detail') or datos['errors'][0]}")
    inc = datos.get("includes", {})
    usuarios = {u["id"]: u for u in inc.get("users", [])}
    lugares = {p["id"]: p for p in inc.get("places", [])}
    citados = {t["id"]: t for t in inc.get("tweets", [])}
    resultados = []
    for t in datos.get("data", []):
        autor = usuarios.get(t.get("author_id"), {})
        usuario = autor.get("username", "")
        # interacción: respuesta o cita a otra cuenta (arista de la red)
        interaccion, objetivo = "original", ""
        for ref in t.get("referenced_tweets", []):
            tipo = {"replied_to": "respuesta", "quoted": "cita"}.get(ref["type"])
            destino = usuarios.get(citados.get(ref["id"], {}).get("author_id"), {}).get("username")
            if tipo and destino:
                interaccion, objetivo = tipo, f"@{destino}"
                break
        ent = t.get("entities", {})
        menciones = [f"@{m['username']}" for m in ent.get("mentions", []) if f"@{m['username']}" != objetivo]
        hashtags = " ".join(f"#{h['tag']}" for h in ent.get("hashtags", []))
        lugar_tag = lugares.get(t.get("geo", {}).get("place_id"), {})
        geotag = lugar_tag.get("full_name", "") if lugar_tag.get("country_code") == "GT" else ""
        m = t.get("public_metrics", {})
        texto = t.get("text", "")
        resultados.append({
            "fuente": "x", "id": t["id"], "fecha": t.get("created_at", ""), "texto": texto, "hashtags": hashtags,
            "url": f"https://x.com/{usuario}/status/{t['id']}", "origen": f"@{usuario}",
            "bio_ubicacion": autor.get("location", ""), "seguidores": autor.get("public_metrics", {}).get("followers_count", ""),
            "ubicacion_etiquetada": geotag, "interaccion": interaccion, "cuenta_objetivo": objetivo,
            "menciones": " ".join(menciones),
            "metricas": {"view_count": m.get("impression_count", 0), "like_count": m.get("like_count", 0),
                         "comment_count": m.get("reply_count", 0),
                         "share_count": m.get("retweet_count", 0) + m.get("quote_count", 0)},
            **clasificar(texto, hashtags, "", geotag),
        })
    return resultados


FUENTES = {"gdelt": buscar_gdelt, "tiktok": buscar_tiktok, "x": buscar_x}


# ---------------------------------------------------------------------------
# Guardar resultados de TikTok como datos del pipeline
# ---------------------------------------------------------------------------

def guardar(items: list[dict]) -> dict:
    ruta = CRUDO / "publicaciones.csv"
    existentes = set()
    if ruta.exists():
        with open(ruta, encoding="utf-8-sig", newline="") as f:
            existentes = {r["id_publicacion"] for r in csv.DictReader(f)}
    nuevas = []
    for it in items:
        fuente = it.get("fuente")
        if fuente not in ("tiktok", "x"):
            continue
        pid = f"{'tt' if fuente == 'tiktok' else 'x'}_{it['id']}"
        if pid in existentes:
            continue
        m = it.get("metricas", {})
        nuevas.append({
            "id_publicacion": pid, "plataforma": fuente, "fecha": it["fecha"][:10], "cuenta": it.get("origen", ""),
            "tipo_cuenta": "", "seguidores": it.get("seguidores", ""), "bio_ubicacion": it.get("bio_ubicacion", ""),
            "texto": it.get("texto", ""), "hashtags": it.get("hashtags", ""), "transcripcion": it.get("transcripcion", ""),
            "ubicacion_etiquetada": it.get("ubicacion_etiquetada", ""),
            "interaccion": it.get("interaccion", "original"), "cuenta_objetivo": it.get("cuenta_objetivo", ""),
            "menciones": it.get("menciones", ""),
            "vistas": m.get("view_count", ""), "me_gusta": m.get("like_count", ""),
            "comentarios": m.get("comment_count", ""), "compartidos": m.get("share_count", ""),
        })
        existentes.add(pid)
    if nuevas:
        nuevo_archivo = not ruta.exists()
        CRUDO.mkdir(parents=True, exist_ok=True)
        with open(ruta, "a", encoding="utf-8-sig" if nuevo_archivo else "utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CAMPOS_CSV)
            if nuevo_archivo:
                w.writeheader()
            w.writerows(nuevas)
    salida = subprocess.run([sys.executable, str(ANALISIS / "pipeline_narrativas.py")], capture_output=True,
                            text=True, encoding="utf-8", errors="replace", cwd=RAIZ)
    return {"agregadas": len(nuevas), "total": len(existentes), "pipeline_ok": salida.returncode == 0,
            "pipeline": (salida.stdout or salida.stderr)[-1500:]}


# ---------------------------------------------------------------------------
# Servidor HTTP
# ---------------------------------------------------------------------------

class Manejador(SimpleHTTPRequestHandler):
    def end_headers(self):
        # durante el desarrollo local, que el navegador no use versiones viejas de JS, CSS o datos
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def responder(self, codigo: int, datos: dict):
        cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/api/estado":
            return self.responder(200, {
                "local": True,
                "fuentes": {"gdelt": True, "tiktok": tiktok_disponible(), "x": x_disponible()},
                "x_max_resultados": x_max_resultados(),
                "datos_reales": (CRUDO / "publicaciones.csv").exists(),
                "temas": [{"id": t["id"], "etiqueta": t["etiqueta"]} for t in LIBRO["temas"]],
            })
        if u.path == "/api/buscar":
            q = urllib.parse.parse_qs(u.query)
            fuente = q.get("fuente", ["gdelt"])[0]
            tema = q.get("tema", ["todas"])[0]
            depto = q.get("depto", ["nacional"])[0]
            periodo = q.get("periodo", ["3d"])[0]
            extra = q.get("q", [""])[0].strip()[:120]
            if fuente not in FUENTES or (tema != "todas" and tema not in TEMAS) or \
               (depto != "nacional" and depto not in DEPTOS) or periodo not in PERIODOS:
                return self.responder(400, {"error": "Parámetros no válidos."})
            clave = json.dumps([fuente, tema, depto, periodo, extra])
            if clave in _cache and time.time() - _cache[clave][0] < 300:
                return self.responder(200, {**_cache[clave][1], "cache": True})
            try:
                items = FUENTES[fuente](tema, depto, PERIODOS[periodo], extra)
            except ErrorFuente as e:
                return self.responder(502, {"error": str(e)})
            if depto != "nacional":  # deja primero los que el nomenclátor ubica en el departamento
                items.sort(key=lambda it: it["depto"] != depto)
            datos = {"fuente": fuente, "consultado": datetime.now(timezone.utc).isoformat(), "items": items}
            _cache[clave] = (time.time(), datos)
            return self.responder(200, datos)
        if u.path.startswith("/data/crudo/") and not u.path.endswith("plantilla_publicaciones.csv"):
            return self.responder(403, {"error": "Los datos crudos no se sirven por HTTP."})
        return super().do_GET()

    def do_POST(self):
        if self.path != "/api/guardar":
            return self.responder(404, {"error": "No encontrado."})
        origen = self.headers.get("Origin", "")
        if origen and urllib.parse.urlparse(origen).hostname not in ("localhost", "127.0.0.1"):
            return self.responder(403, {"error": "Origen no permitido."})
        try:
            largo = min(int(self.headers.get("Content-Length", 0)), 5_000_000)
            items = json.loads(self.rfile.read(largo)).get("items", [])
        except (ValueError, AttributeError):
            return self.responder(400, {"error": "Cuerpo no válido."})
        return self.responder(200, guardar(items))

    def log_message(self, fmt, *args):
        if "/api/" in (args[0] if args else ""):
            super().log_message(fmt, *args)


def main():
    ap = argparse.ArgumentParser(description="Servidor local del portafolio con búsqueda en tiempo real")
    ap.add_argument("--puerto", type=int, default=8000)
    args = ap.parse_args()
    servidor = ThreadingHTTPServer(("127.0.0.1", args.puerto), partial(Manejador, directory=str(RAIZ)))
    print(f"Portafolio en http://127.0.0.1:{args.puerto}/proyectos/red-influencia.html  (Ctrl+C para detener)", flush=True)
    print(f"Fuentes: GDELT sí · TikTok Research API {'sí' if tiktok_disponible() else 'no (faltan credenciales)'}"
          f" · X API {'sí, hasta ' + str(x_max_resultados()) + ' posts por búsqueda' if x_disponible() else 'no (falta X_BEARER_TOKEN)'}",
          flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
