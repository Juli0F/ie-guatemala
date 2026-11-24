"""
Proyecto 1 - Narrativas, territorio y redes de influencia en Guatemala
======================================================================

Pipeline para publicaciones REALES (o la muestra sintética) de TikTok e Instagram:

  1. Lee un CSV con el formato de data/crudo/plantilla_publicaciones.csv
  2. Clasifica cada publicación por tema y subnarrativa (analisis/libro_codigos.json)
  3. Geolocaliza publicaciones y cuentas por departamento (analisis/geografia_gt.json)
  4. Seudonimiza las cuentas (salvo las de data/crudo/cuentas_publicas.csv)
  5. Construye la red de interacciones (dueto, stitch, repost, colaboración,
     mención, comentario; en X: respuesta, cita y mención) y calcula métricas para CADA combinación
     tema x departamento (y a nivel nacional)
  6. Exporta:
       data/narrativas.json                  -> sitio web (mapa, filtros, grafo)
       data/cuentas_narrativas.csv           -> Excel, cuentas con métricas nacionales
       data/publicaciones_clasificadas.csv   -> Excel, sin texto (publicable)
       data/crudo/publicaciones_clasificadas_completo.csv -> con texto (NO publicar)
       data/crudo/muestra_validacion.csv     -> 200 casos para codificación manual
       neo4j/narrativas.cypher               -> carga en Neo4j

Uso:
    python analisis/pipeline_narrativas.py                      # usa data/crudo/publicaciones.csv o la muestra
    python analisis/pipeline_narrativas.py --entrada otro.csv
    python analisis/pipeline_narrativas.py --sin-seudonimizar   # solo para análisis local

Solo biblioteca estándar de Python 3.9+.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import secrets
import unicodedata
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import sna

SEMILLA = 20261124
RAIZ = Path(__file__).resolve().parent.parent
ANALISIS = RAIZ / "analisis"
DATA = RAIZ / "data"
CRUDO = DATA / "crudo"
NEO4J = RAIZ / "neo4j"
MIN_ARISTAS_FILTRO = 3
PLATAFORMAS = ["tiktok", "instagram", "x"]  # índice usado en las publicaciones compactas del sitio


# ---------------------------------------------------------------------------
# Normalización de texto
# ---------------------------------------------------------------------------

def sin_tildes(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def normalizar(s: str) -> str:
    """minúsculas, sin tildes, solo letras/dígitos; con espacios a los lados para buscar frases."""
    s = sin_tildes(s or "").lower()
    s = re.sub(r"[^a-z0-9ñ]+", " ", s)
    return f" {s.strip()} "


def normalizar_hashtag(h: str) -> str:
    return re.sub(r"[^a-z0-9]", "", sin_tildes(h).lower())


def extraer_hashtags(*textos: str) -> set[str]:
    out = set()
    for t in textos:
        for h in re.findall(r"#([\wÀ-ÿ]+)", t or ""):
            out.add(normalizar_hashtag(h))
    return out


# ---------------------------------------------------------------------------
# 1. Clasificador por diccionario (libro de códigos)
# ---------------------------------------------------------------------------

class Clasificador:
    def __init__(self, libro: dict):
        self.umbral = libro["reglas"]["umbral_tema"]
        self.temas = libro["temas"]
        self.subs = []  # (tema_id, sub_id, [(termino_norm, peso)], {hashtags})
        self.excluir = {}
        self.hashtags_libro = set()
        for t in self.temas:
            self.excluir[t["id"]] = [normalizar(x).strip() for x in t.get("excluir", [])]
            for s in t["subnarrativas"]:
                terminos = []
                for term in s["terminos"]:
                    tn = normalizar(term).strip()
                    terminos.append((f" {tn} ", 2 if " " in tn else 1))
                hs = {normalizar_hashtag(h) for h in s.get("hashtags", [])}
                self.hashtags_libro |= hs
                self.subs.append((t["id"], s["id"], terminos, hs))

    def clasificar(self, texto_norm: str, hashtags: set[str]):
        puntaje_tema = defaultdict(float)
        puntaje_sub = {}
        texto_tema = {}
        for tema_id, excl in self.excluir.items():
            t = texto_norm
            for e in excl:
                t = t.replace(f" {e} ", " ")
            texto_tema[tema_id] = t
        for tema_id, sub_id, terminos, hs in self.subs:
            t = texto_tema[tema_id]
            p = sum(peso for term, peso in terminos if term in t)
            p += 2 * len(hashtags & hs)
            if p:
                puntaje_sub[sub_id] = (tema_id, p)
                puntaje_tema[tema_id] += p
        temas = sorted(t for t, p in puntaje_tema.items() if p >= self.umbral)
        candidatas = [(p, s) for s, (t, p) in puntaje_sub.items() if t in temas]
        sub_principal = max(candidatas)[1] if candidatas else None
        return temas, sub_principal, dict(puntaje_tema)


# ---------------------------------------------------------------------------
# 2. Geolocalización
# ---------------------------------------------------------------------------

class Geolocalizador:
    def __init__(self, geo: dict):
        self.deptos = geo["departamentos"]
        self.alias = []  # (alias_norm, depto_id), los más largos primero
        for d in self.deptos:
            for a in d["alias"] + [d["nombre"]]:
                an = normalizar(a).strip()
                # "Guatemala" sola es el país, no el departamento
                if an == "guatemala":
                    continue
                self.alias.append((f" {an} ", d["id"]))
        self.alias.sort(key=lambda x: -len(x[0]))
        self.patrones = [(re.compile(p), d) for d, ps in geo.get("patrones_departamento", {}).items() for p in ps]
        self.nacional = [f" {normalizar(x).strip()} " for x in geo.get("nacional", [])]

    def buscar(self, texto_norm: str) -> str | None:
        """Departamento más mencionado en el texto (o None)."""
        conteo = Counter()
        t = texto_norm
        for a, d in self.alias:
            if a in t:
                conteo[d] += t.count(a)
                t = t.replace(a, " ")  # evita contar "Antigua Guatemala" también como "Guatemala"
        for patron, d in self.patrones:
            conteo[d] += len(patron.findall(t))
        conteo = +conteo
        return conteo.most_common(1)[0][0] if conteo else None

    def es_nacional(self, texto_norm: str) -> bool:
        return any(n in texto_norm for n in self.nacional)


# ---------------------------------------------------------------------------
# 3. Seudonimización
# ---------------------------------------------------------------------------

def cargar_sal() -> str:
    ruta = CRUDO / ".sal"
    if not ruta.exists():
        CRUDO.mkdir(parents=True, exist_ok=True)
        ruta.write_text(secrets.token_hex(16), encoding="utf-8")
    return ruta.read_text(encoding="utf-8").strip()


def cargar_publicas() -> set[str]:
    ruta = CRUDO / "cuentas_publicas.csv"
    if not ruta.exists():
        return set()
    with open(ruta, encoding="utf-8-sig") as f:
        return {row["cuenta"].strip().lower() for row in csv.DictReader(f) if row.get("cuenta")}


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def leer(entrada: Path) -> list[dict]:
    with open(entrada, encoding="utf-8-sig", newline="") as f:
        filas = list(csv.DictReader(f))
    obligatorias = {"id_publicacion", "plataforma", "fecha", "cuenta", "texto"}
    faltan = obligatorias - set(filas[0] if filas else {})
    if faltan:
        raise SystemExit(f"Faltan columnas obligatorias en {entrada}: {', '.join(sorted(faltan))}")
    return filas


def entero(v) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--entrada", type=Path)
    ap.add_argument("--sin-seudonimizar", action="store_true", help="conserva los nombres de cuenta (no publicar el resultado)")
    args = ap.parse_args()

    entrada = args.entrada or (CRUDO / "publicaciones.csv")
    es_muestra = False
    if not entrada.exists():
        entrada = CRUDO / "muestra_sintetica.csv"
        es_muestra = True
    es_muestra = es_muestra or entrada.name == "muestra_sintetica.csv"
    filas = leer(entrada)

    libro = json.loads((ANALISIS / "libro_codigos.json").read_text(encoding="utf-8"))
    geo = json.loads((ANALISIS / "geografia_gt.json").read_text(encoding="utf-8"))
    clf = Clasificador(libro)
    geoloc = Geolocalizador(geo)
    temas_ids = [t["id"] for t in libro["temas"]]
    subs_ids = [s["id"] for t in libro["temas"] for s in t["subnarrativas"]]
    deptos_ids = [d["id"] for d in geo["departamentos"]]

    # --- clasificación y geolocalización de cada publicación ------------------
    pubs = []
    for r in filas:
        hashtags = extraer_hashtags(r.get("hashtags", ""), r.get("texto", ""), r.get("transcripcion", ""))
        texto_norm = normalizar(" ".join([r.get("texto", ""), r.get("transcripcion", ""), r.get("hashtags", "").replace("#", " ")]))
        temas, sub, puntajes = clf.clasificar(texto_norm, hashtags)

        depto, conf = None, None
        if r.get("ubicacion_etiquetada"):
            depto = geoloc.buscar(normalizar(r["ubicacion_etiquetada"]))
            conf = "alta" if depto else None
        if not depto:
            depto = geoloc.buscar(texto_norm)
            conf = "media" if depto else None
        fecha = date.fromisoformat(r["fecha"][:10])
        pubs.append({
            "fila": r,
            "id": r["id_publicacion"],
            "plataforma": {"twitter": "x"}.get(r["plataforma"].strip().lower(), r["plataforma"].strip().lower()),
            "fecha": fecha,
            "autor": r["cuenta"].strip(),
            "objetivo": (r.get("cuenta_objetivo") or "").strip(),
            "interaccion": (r.get("interaccion") or "original").strip().lower(),
            "menciones": [m for m in re.split(r"[\s,;]+", r.get("menciones") or "") if m.startswith("@")],
            "temas": temas,
            "sub": sub,
            "puntajes": puntajes,
            "hashtags": hashtags,
            "depto": depto,
            "conf": conf,
            "nacional": geoloc.es_nacional(texto_norm),
            "engagement": entero(r.get("me_gusta")) + entero(r.get("comentarios")) + entero(r.get("compartidos")),
            "vistas": entero(r.get("vistas")),
        })

    # --- cuentas: ubicación por biografía o por moda de sus publicaciones -----
    cuentas: dict[str, dict] = {}

    def cuenta(handle: str) -> dict:
        if handle not in cuentas:
            cuentas[handle] = {"handle": handle, "plataforma": "desconocida", "tipo": "", "seguidores": 0,
                               "depto": None, "conf": None, "publicaciones": 0, "temas": Counter()}
        return cuentas[handle]

    for p in pubs:
        c = cuenta(p["autor"])
        c["plataforma"] = p["plataforma"]
        c["tipo"] = p["fila"].get("tipo_cuenta", "") or c["tipo"]
        c["seguidores"] = max(c["seguidores"], entero(p["fila"].get("seguidores")))
        c["publicaciones"] += 1
        c["temas"].update(p["temas"])
        if not c["depto"] and p["fila"].get("bio_ubicacion"):
            d = geoloc.buscar(normalizar(p["fila"]["bio_ubicacion"]))
            if d:
                c["depto"], c["conf"] = d, "biografia"
        if p["objetivo"]:
            cuenta(p["objetivo"])
        for m in p["menciones"]:
            cuenta(m)
    por_autor = defaultdict(list)
    for p in pubs:
        if p["depto"]:
            por_autor[p["autor"]].append(p["depto"])
    for h, ds in por_autor.items():
        c = cuentas[h]
        if not c["depto"] and len(ds) >= 2:
            d, n = Counter(ds).most_common(1)[0]
            if n / len(ds) >= 0.6:
                c["depto"], c["conf"] = d, "inferida"
    for p in pubs:  # respaldo: ubicación de la cuenta autora
        if not p["depto"] and cuentas[p["autor"]]["depto"]:
            p["depto"], p["conf"] = cuentas[p["autor"]]["depto"], "baja"

    # --- seudonimización ------------------------------------------------------
    seudonimizar = not args.sin_seudonimizar and not es_muestra
    sal = cargar_sal() if seudonimizar else ""
    publicas = cargar_publicas()
    for h, c in cuentas.items():
        pref = {"tiktok": "tt", "instagram": "ig", "x": "x"}.get(c["plataforma"], "cu")
        if not seudonimizar or h.lower() in publicas:
            c["id"] = h.lstrip("@")
        else:
            c["id"] = f"{pref}_{hashlib.sha256((sal + h.lower()).encode()).hexdigest()[:8]}"

    # --- aristas por publicación -------------------------------------------------
    for p in pubs:
        destinos = []
        if p["objetivo"] and p["interaccion"] != "original":
            destinos.append((p["objetivo"], p["interaccion"]))
        destinos += [(m, "mencion") for m in p["menciones"]]
        p["aristas"] = [(cuentas[p["autor"]]["id"], cuentas[d]["id"], tipo) for d, tipo in destinos if d != p["autor"]]

    # --- métricas por filtro (tema x departamento) ----------------------------
    lista_cuentas = sorted(cuentas.values(), key=lambda c: c["id"])
    idx = {c["id"]: i for i, c in enumerate(lista_cuentas)}
    tematicas = [p for p in pubs if p["temas"]]

    def red(sub_pubs):
        pesos = Counter()
        for p in sub_pubs:
            for u, v, _ in p["aristas"]:
                pesos[(u, v)] += 1
        return pesos

    rng = random.Random(SEMILLA)
    subgrafos = {}
    filtros_tema = ["todas"] + temas_ids
    filtros_depto = ["nacional"] + deptos_ids
    for ft in filtros_tema:
        for fd in filtros_depto:
            sp = [p for p in tematicas if (ft == "todas" or ft in p["temas"]) and (fd == "nacional" or p["depto"] == fd)]
            pesos = red(sp)
            if len(pesos) < MIN_ARISTAS_FILTRO:
                continue
            aristas = [(u, v, w) for (u, v), w in pesos.items()]
            ids = sorted({u for u, _, _ in aristas} | {v for _, v, _ in aristas})
            adj = sna.no_dirigido(ids, aristas)
            n = len(ids)
            bt = sna.intermediacion(adj, muestras=300 if n > 1500 else None, rng=rng)
            pr = sna.pagerank(ids, aristas)
            part = sna.louvain(adj, random.Random(SEMILLA))
            q = sna.modularidad(adj, part)
            subgrafos[f"{ft}|{fd}"] = {
                "n": [idx[u] for u in ids],
                "pr": [round(pr[u], 5) for u in ids],
                "bt": [round(bt[u], 5) for u in ids],
                "gr": [len(adj[u]) for u in ids],
                "com": [part[u] for u in ids],
                "q": round(q, 4),
                "aristas": [[idx[u], idx[v], w] for u, v, w in aristas],
                "publicaciones": len(sp),
            }

    # --- layout global (red nacional de todos los temas) ---------------------
    base = subgrafos.get("todas|nacional")
    pos = {}
    if base:
        ids = [lista_cuentas[i]["id"] for i in base["n"]]
        adj = sna.no_dirigido(ids, [(lista_cuentas[u]["id"], lista_cuentas[v]["id"], w) for u, v, w in base["aristas"]])
        pos = sna.layout_fr(adj, random.Random(SEMILLA))

    # --- hashtags emergentes por tema (candidatos para el libro de códigos) ---
    alias_geo = {normalizar_hashtag(a) for d in geo["departamentos"] for a in d["alias"] + [d["nombre"]]}
    emergentes = {}
    for t in temas_ids:
        cnt = Counter(h for p in tematicas if t in p["temas"] for h in p["hashtags"]
                      if h not in clf.hashtags_libro and h not in alias_geo)
        emergentes[t] = [[h, n] for h, n in cnt.most_common(10) if n >= 3]

    # --- serie temporal ---------------------------------------------------------
    f0 = min(p["fecha"] for p in pubs)
    lunes0 = f0 - timedelta(days=f0.weekday())
    n_semanas = (max(p["fecha"] for p in pubs) - lunes0).days // 7 + 1
    semanas = [(lunes0 + timedelta(weeks=i)).isoformat() for i in range(n_semanas)]

    # --- salida para el sitio -----------------------------------------------
    conf_ids = ["alta", "media", "baja"]
    pub_compactas = []
    for p in pubs:
        mascara = sum(1 << temas_ids.index(t) for t in p["temas"])
        pub_compactas.append([
            idx[cuentas[p["autor"]]["id"]], mascara,
            subs_ids.index(p["sub"]) if p["sub"] else -1,
            deptos_ids.index(p["depto"]) if p["depto"] else -1,
            conf_ids.index(p["conf"]) if p["conf"] else -1,
            (p["fecha"] - lunes0).days // 7,
            p["engagement"],
            PLATAFORMAS.index(p["plataforma"]) if p["plataforma"] in PLATAFORMAS else 1,
        ])
    geolocalizadas = Counter(p["conf"] for p in pubs)
    salida = {
        "meta": {
            "fuente": "Muestra sintética (cuentas y textos inventados)" if es_muestra else f"Datos recolectados ({entrada.name})",
            "sintetica": es_muestra,
            "seudonimizada": seudonimizar,
            "plataformas": PLATAFORMAS,
            "desde": min(p["fecha"] for p in pubs).isoformat(),
            "hasta": max(p["fecha"] for p in pubs).isoformat(),
            "publicaciones": len(pubs),
            "clasificadas": len(tematicas),
            "cuentas": len(cuentas),
            "geolocalizacion": {k: geolocalizadas.get(k, 0) for k in conf_ids + [None]},
            "libro_codigos": libro["version"],
            "generado": date.today().isoformat(),
        },
        "temas": [{"id": t["id"], "etiqueta": t["etiqueta"], "descripcion": t["descripcion"],
                   "subnarrativas": [{"id": s["id"], "etiqueta": s["etiqueta"], "marco": s["marco"]} for s in t["subnarrativas"]]}
                  for t in libro["temas"]],
        "departamentos": [{k: d[k] for k in ("id", "nombre", "col", "fila")} for d in geo["departamentos"]],
        "semanas": semanas,
        "cuentas": [{
            "id": c["id"], "plataforma": c["plataforma"], "tipo": c["tipo"], "seguidores": c["seguidores"],
            "depto": deptos_ids.index(c["depto"]) if c["depto"] else -1, "conf_geo": c["conf"] or "",
            "x": pos.get(c["id"], (None, None))[0], "y": pos.get(c["id"], (None, None))[1],
        } for c in lista_cuentas],
        "publicaciones": pub_compactas,
        "subgrafos": subgrafos,
        "emergentes": emergentes,
    }
    (DATA / "narrativas.json").write_text(json.dumps(salida, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # --- exportaciones tabulares -------------------------------------------------
    nac = subgrafos.get("todas|nacional", {"n": [], "pr": [], "bt": [], "gr": [], "com": []})
    met = {i: (pr, bt, gr, cm) for i, pr, bt, gr, cm in zip(nac["n"], nac["pr"], nac["bt"], nac["gr"], nac["com"])}
    nombres_depto = {d["id"]: d["nombre"] for d in geo["departamentos"]}
    with open(DATA / "cuentas_narrativas.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["cuenta", "plataforma", "tipo", "seguidores", "departamento", "conf_ubicacion", "publicaciones",
                    "tema_principal", "pagerank", "intermediacion", "grado", "comunidad"])
        for i, c in enumerate(lista_cuentas):
            pr, bt, gr, cm = met.get(i, ("", "", "", ""))
            tema_p = c["temas"].most_common(1)[0][0] if c["temas"] else ""
            w.writerow([c["id"], c["plataforma"], c["tipo"], c["seguidores"], nombres_depto.get(c["depto"], ""),
                        c["conf"] or "", c["publicaciones"], tema_p, pr, bt, gr, cm])

    campos_pub = ["id_publicacion", "plataforma", "fecha", "cuenta", "temas", "subnarrativa", "departamento",
                  "conf_ubicacion", "interaccion", "cuenta_objetivo", "vistas", "engagement"]
    with open(DATA / "publicaciones_clasificadas.csv", "w", newline="", encoding="utf-8-sig") as f, \
         open(CRUDO / "publicaciones_clasificadas_completo.csv", "w", newline="", encoding="utf-8-sig") as g:
        w, w2 = csv.writer(f), csv.writer(g)
        w.writerow(campos_pub)
        w2.writerow(campos_pub + ["texto", "hashtags", "puntajes"])
        for p in pubs:
            fila = [p["id"], p["plataforma"], p["fecha"].isoformat(), cuentas[p["autor"]]["id"], "|".join(p["temas"]),
                    p["sub"] or "", nombres_depto.get(p["depto"], ""), p["conf"] or "", p["interaccion"],
                    cuentas[p["objetivo"]]["id"] if p["objetivo"] else "", p["vistas"], p["engagement"]]
            w.writerow(fila)
            w2.writerow(fila + [p["fila"].get("texto", ""), p["fila"].get("hashtags", ""), json.dumps(p["puntajes"])])

    # Muestra para validación manual (kappa de Cohen): estratificada por tema clasificado
    rng_v = random.Random(SEMILLA)
    estratos = defaultdict(list)
    for p in pubs:
        estratos[p["temas"][0] if p["temas"] else "sin_tema"].append(p)
    muestra = []
    for lst in estratos.values():
        muestra += rng_v.sample(lst, min(len(lst), max(20, round(200 * len(lst) / len(pubs)))))
    with open(CRUDO / "muestra_validacion.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["id_publicacion", "texto", "hashtags", "temas_diccionario", "subnarrativa_diccionario",
                    "temas_codificador_1", "temas_codificador_2", "postura", "notas"])
        for p in muestra:
            w.writerow([p["id"], p["fila"].get("texto", ""), p["fila"].get("hashtags", ""), "|".join(p["temas"]), p["sub"] or "", "", "", "", ""])

    exportar_cypher(nombres_depto)

    # --- resumen en consola -------------------------------------------------------
    print(f"Fuente: {salida['meta']['fuente']}  ({salida['meta']['desde']} a {salida['meta']['hasta']})")
    print(f"Publicaciones: {len(pubs)}  clasificadas: {len(tematicas)} ({len(tematicas) / len(pubs):.0%})  cuentas: {len(cuentas)}")
    print("Geolocalización:", {k or 'sin ubicación': v for k, v in geolocalizadas.items()})
    print("Por tema:", dict(Counter(t for p in pubs for t in p["temas"])))
    print(f"Filtros con red suficiente: {len(subgrafos)} de {len(filtros_tema) * len(filtros_depto)}")
    if base:
        print(f"Red nacional: {len(base['n'])} cuentas, {len(base['aristas'])} aristas, Q={base['q']}")


def exportar_cypher(nombres_depto):
    lineas = [
        "// Carga del modelo de narrativas en Neo4j (generado por analisis/pipeline_narrativas.py)",
        "// Copia data/cuentas_narrativas.csv y data/publicaciones_clasificadas.csv a la carpeta import/ de Neo4j.",
        "CREATE CONSTRAINT cuenta_id IF NOT EXISTS FOR (c:Cuenta) REQUIRE c.id IS UNIQUE;",
        "CREATE CONSTRAINT pub_id IF NOT EXISTS FOR (p:Publicacion) REQUIRE p.id IS UNIQUE;",
        "CREATE CONSTRAINT tema_id IF NOT EXISTS FOR (t:Tema) REQUIRE t.id IS UNIQUE;",
        "CREATE CONSTRAINT depto_nombre IF NOT EXISTS FOR (d:Departamento) REQUIRE d.nombre IS UNIQUE;",
        "",
        "UNWIND " + json.dumps(sorted(nombres_depto.values()), ensure_ascii=False) + " AS nombre MERGE (:Departamento {nombre: nombre});",
        "",
        "LOAD CSV WITH HEADERS FROM 'file:///cuentas_narrativas.csv' AS f",
        "MERGE (c:Cuenta {id: f.cuenta})",
        "SET c.plataforma = f.plataforma, c.tipo = f.tipo, c.seguidores = toInteger(f.seguidores),",
        "    c.pagerank = toFloat(f.pagerank), c.intermediacion = toFloat(f.intermediacion), c.comunidad = toInteger(f.comunidad)",
        "WITH c, f WHERE f.departamento <> ''",
        "MATCH (d:Departamento {nombre: f.departamento}) MERGE (c)-[:UBICADA_EN {confianza: f.conf_ubicacion}]->(d);",
        "",
        "LOAD CSV WITH HEADERS FROM 'file:///publicaciones_clasificadas.csv' AS f",
        "MATCH (a:Cuenta {id: f.cuenta})",
        "MERGE (p:Publicacion {id: f.id_publicacion})",
        "SET p.plataforma = f.plataforma, p.fecha = date(f.fecha), p.subnarrativa = f.subnarrativa,",
        "    p.interaccion = f.interaccion, p.vistas = toInteger(f.vistas), p.engagement = toInteger(f.engagement)",
        "MERGE (a)-[:PUBLICO]->(p)",
        "FOREACH (t IN CASE WHEN f.temas = '' THEN [] ELSE split(f.temas, '|') END |",
        "  MERGE (tm:Tema {id: t}) MERGE (p)-[:TRATA_SOBRE]->(tm))",
        "WITH p, f",
        "CALL { WITH p, f WITH p, f WHERE f.departamento <> ''",
        "  MATCH (d:Departamento {nombre: f.departamento}) MERGE (p)-[:SOBRE_LUGAR {confianza: f.conf_ubicacion}]->(d) }",
        "WITH p, f WHERE f.cuenta_objetivo <> ''",
        "MATCH (a:Cuenta {id: f.cuenta}), (b:Cuenta {id: f.cuenta_objetivo})",
        "MERGE (a)-[r:AMPLIFICA {tipo: f.interaccion}]->(b) ON CREATE SET r.peso = 0 SET r.peso = r.peso + 1;",
        "",
        "// --- Consultas de análisis ------------------------------------------------",
        "// Volumen por tema y departamento",
        "MATCH (p:Publicacion)-[:TRATA_SOBRE]->(t:Tema), (p)-[:SOBRE_LUGAR]->(d:Departamento)",
        "RETURN t.id AS tema, d.nombre AS departamento, count(p) AS publicaciones ORDER BY publicaciones DESC;",
        "",
        "// Cuentas que conectan varios temas (posibles puentes entre narrativas)",
        "MATCH (c:Cuenta)-[:PUBLICO]->(:Publicacion)-[:TRATA_SOBRE]->(t:Tema)",
        "WITH c, collect(DISTINCT t.id) AS temas WHERE size(temas) >= 3",
        "RETURN c.id, temas, c.intermediacion ORDER BY c.intermediacion DESC LIMIT 20;",
        "",
        "// Red de narcopolítica en Petén: quién amplifica a quién",
        "MATCH (a:Cuenta)-[:PUBLICO]->(p:Publicacion)-[:TRATA_SOBRE]->(:Tema {id:'narcopolitica'}),",
        "      (p)-[:SOBRE_LUGAR]->(:Departamento {nombre:'Petén'}), (a)-[r:AMPLIFICA]->(b:Cuenta)",
        "RETURN a.id, b.id, r.tipo, r.peso ORDER BY r.peso DESC LIMIT 25;",
    ]
    NEO4J.mkdir(exist_ok=True)
    (NEO4J / "narrativas.cypher").write_text("\n".join(lineas) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
