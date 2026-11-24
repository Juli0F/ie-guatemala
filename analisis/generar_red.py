"""
Proyecto 1 - Análisis de Redes de Influencia y Detección de Comunidades (SOCMINT)
==================================================================================

Genera un ecosistema SINTÉTICO de cuentas de TikTok e Instagram alrededor de una
narrativa de desinformación ficticia ("escasez de agua" en el área metropolitana
de Guatemala: Guatemala, Mixco y Villa Nueva), calcula métricas de análisis de
redes sociales (SNA) y exporta:

  data/red_influencia.json   -> consumido por el sitio (grafo interactivo)
  data/nodos.csv             -> tabla de nodos con métricas (Excel / pandas)
  data/aristas.csv           -> lista de aristas ponderadas
  neo4j/import.cypher        -> script de carga para Neo4j

Solo usa la biblioteca estándar de Python (3.9+), para que se pueda ejecutar
sin dependencias. Las implementaciones siguen los algoritmos de referencia:

  * Grado / grado ponderado
  * Intermediación (Betweenness) - algoritmo de Brandes (2001)
  * PageRank dirigido y ponderado - iteración de potencias
  * Comunidades - Louvain (Blondel et al., 2008) con modularidad de Newman

Si tienes NetworkX instalado, `validar_con_networkx()` compara los resultados.

Uso:
    python analisis/generar_red.py
"""

from __future__ import annotations

import csv
import json
import math
import random
from collections import defaultdict
from pathlib import Path

import sna

SEMILLA = 20261124
RAIZ = Path(__file__).resolve().parent.parent
DATA = RAIZ / "data"
NEO4J = RAIZ / "neo4j"

# ---------------------------------------------------------------------------
# 1. Definición del escenario (grupos planificados)
# ---------------------------------------------------------------------------
# Cada grupo representa un segmento del ecosistema. La red se genera con un
# modelo de bloques estocásticos (SBM): alta densidad dentro de cada grupo,
# baja entre grupos, más un conjunto de cuentas "puente" que conectan grupos.

GRUPOS = [
    # clave, etiqueta, plataforma dominante, n, p_interna, postura
    ("origen", "Núcleo emisor de la narrativa", "tiktok", 10, 0.55, "pro"),
    ("memes", "Amplificadores de memes y humor", "tiktok", 26, 0.16, "pro"),
    ("vecinos", "Grupos vecinales y COCODE", "instagram", 30, 0.12, "neutral"),
    ("jovenes", "Universitarios y creadores jóvenes", "tiktok", 24, 0.15, "neutral"),
    ("medios", "Medios y periodistas guatemaltecos", "instagram", 14, 0.30, "contra"),
    ("instituciones", "Municipalidades y salud pública", "instagram", 10, 0.40, "contra"),
]

# Probabilidad de enlace entre grupos (simétrica). Lo que no aparece usa P_BASE.
P_BASE = 0.004
P_ENTRE = {
    ("origen", "memes"): 0.20,
    ("memes", "jovenes"): 0.035,
    ("memes", "vecinos"): 0.020,
    ("vecinos", "medios"): 0.030,
    ("medios", "instituciones"): 0.12,
    ("jovenes", "vecinos"): 0.015,
}

TIPOS_ARISTA = {
    "tiktok": ["dueto", "stitch", "repost", "mencion"],
    "instagram": ["mencion", "repost_historia", "colaboracion", "comentario"],
}


def _p_entre(a: str, b: str) -> float:
    return P_ENTRE.get((a, b)) or P_ENTRE.get((b, a)) or P_BASE


def generar_ecosistema(rng: random.Random):
    nodos: list[dict] = []
    for clave, etiqueta, plataforma, n, _, postura in GRUPOS:
        for i in range(n):
            # 15 % de cuentas en la plataforma "secundaria" del grupo
            plat = plataforma if rng.random() > 0.15 else (
                "instagram" if plataforma == "tiktok" else "tiktok")
            # seguidores: distribución log-normal (colas pesadas)
            seguidores = int(math.exp(rng.gauss(8.2, 1.3)))
            if clave in ("medios", "instituciones"):
                seguidores = int(seguidores * 2.5)
            nodos.append({
                "id": f"{'tt' if plat == 'tiktok' else 'ig'}_{clave[:3]}_{i:02d}",
                "grupo": clave,
                "plataforma": plat,
                "postura": postura if rng.random() > 0.12 else "neutral",
                "seguidores": seguidores,
                "engagement": round(min(0.25, max(0.004, rng.gauss(
                    0.065 if plat == "tiktok" else 0.032, 0.02))), 4),
            })

    # Cuentas puente: personas con presencia en varios grupos (multiplataforma)
    puentes = [
        ("br_00", ["memes", "vecinos"], "tiktok", "pro"),
        ("br_01", ["memes", "jovenes"], "tiktok", "neutral"),
        ("br_02", ["vecinos", "medios"], "instagram", "contra"),
        ("br_03", ["jovenes", "vecinos"], "instagram", "neutral"),
        ("br_04", ["origen", "vecinos"], "instagram", "pro"),
        ("br_05", ["jovenes", "instituciones"], "tiktok", "contra"),
    ]
    for pid, _, plat, postura in puentes:
        nodos.append({
            "id": f"{'tt' if plat == 'tiktok' else 'ig'}_{pid}",
            "grupo": "puentes",
            "plataforma": plat,
            "postura": postura,
            "seguidores": int(math.exp(rng.gauss(9.0, 0.7))),
            "engagement": round(rng.uniform(0.04, 0.09), 4),
        })

    idx = {n["id"]: k for k, n in enumerate(nodos)}
    por_grupo = defaultdict(list)
    for n in nodos:
        por_grupo[n["grupo"]].append(n["id"])

    p_interna = {g[0]: g[4] for g in GRUPOS}
    aristas: dict[tuple[str, str], dict] = {}

    def agregar(u: str, v: str):
        """Arista dirigida u -> v: u amplifica/interactúa con contenido de v."""
        if u == v:
            return
        plat = nodos[idx[u]]["plataforma"]
        clave = (u, v)
        if clave not in aristas:
            aristas[clave] = {"origen": u, "destino": v, "peso": 0,
                              "tipo": rng.choice(TIPOS_ARISTA[plat])}
        aristas[clave]["peso"] += rng.randint(1, 6)

    grupos_claves = [g[0] for g in GRUPOS]
    for a_i, a in enumerate(grupos_claves):
        for b in grupos_claves[a_i:]:
            p = p_interna[a] if a == b else _p_entre(a, b)
            for u in por_grupo[a]:
                for v in por_grupo[b]:
                    if u >= v and a == b:
                        continue
                    if rng.random() < p:
                        # la dirección favorece a la cuenta con más seguidores
                        su, sv = nodos[idx[u]]["seguidores"], nodos[idx[v]]["seguidores"]
                        if rng.random() < sv / (su + sv):
                            agregar(u, v)
                        else:
                            agregar(v, u)
                        if rng.random() < 0.25:  # reciprocidad parcial
                            agregar(v, u) if (u, v) in aristas else agregar(u, v)

    # Conexiones de los puentes
    for pid, grupos, plat, _ in puentes:
        nid = f"{'tt' if plat == 'tiktok' else 'ig'}_{pid}"
        for g in grupos:
            for v in rng.sample(por_grupo[g], k=min(7, len(por_grupo[g]))):
                agregar(v, nid) if rng.random() < 0.6 else agregar(nid, v)

    # Hubs del núcleo emisor: todo "memes" tiende a amplificarlos
    for hub in por_grupo["origen"][:3]:
        for v in rng.sample(por_grupo["memes"], k=12):
            agregar(v, hub)

    return nodos, list(aristas.values())


# ---------------------------------------------------------------------------
# 2. Métricas de red (algoritmos en sna.py)
# ---------------------------------------------------------------------------

def no_dirigido(nodos, aristas):
    return sna.no_dirigido([n["id"] for n in nodos], [(e["origen"], e["destino"], e["peso"]) for e in aristas])


def pagerank(nodos, aristas):
    return sna.pagerank([n["id"] for n in nodos], [(e["origen"], e["destino"], e["peso"]) for e in aristas])


intermediacion_brandes = sna.intermediacion
modularidad = sna.modularidad
louvain = sna.louvain


def layout_fruchterman_reingold(adj, rng):
    return sna.layout_fr(adj, rng, iteraciones=400)


# ---------------------------------------------------------------------------
# 3. Interpretación: roles y resumen por comunidad
# ---------------------------------------------------------------------------

def asignar_roles(nodos):
    """Roles operativos a partir de percentiles de las métricas."""
    def pct(clave, q):
        vals = sorted(n[clave] for n in nodos)
        return vals[int(q * (len(vals) - 1))]
    p_pr, p_bt, p_gr = pct("pagerank", 0.9), pct("intermediacion", 0.9), pct("grado", 0.75)
    for n in nodos:
        if n["intermediacion"] >= p_bt and n["pagerank"] < p_pr:
            n["rol"] = "Puente (broker)"
        elif n["pagerank"] >= p_pr:
            n["rol"] = "Nodo de influencia"
        elif n["grado"] >= p_gr:
            n["rol"] = "Amplificador"
        else:
            n["rol"] = "Periférico"


def resumen_comunidades(nodos, aristas, particion):
    res = defaultdict(lambda: {"miembros": 0, "tiktok": 0, "instagram": 0,
                               "pro": 0, "neutral": 0, "contra": 0,
                               "seguidores": 0, "aristas_internas": 0, "aristas_externas": 0})
    for n in nodos:
        r = res[n["comunidad"]]
        r["miembros"] += 1
        r[n["plataforma"]] += 1
        r[n["postura"]] += 1
        r["seguidores"] += n["seguidores"]
    for e in aristas:
        cu, cv = particion[e["origen"]], particion[e["destino"]]
        if cu == cv:
            res[cu]["aristas_internas"] += 1
        else:
            res[cu]["aristas_externas"] += 1
            res[cv]["aristas_externas"] += 1
    salida = []
    for c in sorted(res):
        r = res[c]
        miembros = [n for n in nodos if n["comunidad"] == c]
        lider = max(miembros, key=lambda n: n["pagerank"])
        grupo_dom = max({n["grupo"] for n in miembros},
                        key=lambda g: sum(1 for n in miembros if n["grupo"] == g))
        r.update({
            "id": c,
            "lider": lider["id"],
            "grupo_dominante": grupo_dom,
            "postura_dominante": max(("pro", "neutral", "contra"), key=lambda p: r[p]),
            "aislamiento": round(r["aristas_internas"] / max(1, r["aristas_internas"] + r["aristas_externas"]), 3),
        })
        salida.append(r)
    return salida


# ---------------------------------------------------------------------------
# 4. Exportaciones
# ---------------------------------------------------------------------------

def exportar(nodos, aristas, comunidades, q, etiquetas):
    DATA.mkdir(exist_ok=True)
    NEO4J.mkdir(exist_ok=True)

    campos = ["id", "plataforma", "grupo", "postura", "seguidores", "engagement",
              "grado", "grado_ponderado", "intermediacion", "pagerank", "comunidad", "rol"]
    with open(DATA / "nodos.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(nodos, key=lambda n: -n["pagerank"]))
    with open(DATA / "aristas.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["origen", "destino", "tipo", "peso"])
        w.writeheader()
        w.writerows(aristas)

    densidad = len(aristas) / (len(nodos) * (len(nodos) - 1))
    salida = {
        "meta": {
            "descripcion": "Ecosistema sintético TikTok/Instagram - narrativa ficticia 'escasez de agua' (área metropolitana de Guatemala)",
            "semilla": SEMILLA,
            "nodos": len(nodos),
            "aristas": len(aristas),
            "densidad": round(densidad, 4),
            "modularidad": round(q, 4),
            "comunidades": len(comunidades),
            "grupos": etiquetas,
        },
        "comunidades": comunidades,
        "nodos": [{k: n[k] for k in campos + ["x", "y"]} for n in nodos],
        "aristas": [[e["origen"], e["destino"], e["peso"], e["tipo"]] for e in aristas],
    }
    with open(DATA / "red_influencia.json", "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, separators=(",", ":"))

    lineas = [
        "// Carga del ecosistema sintético en Neo4j (generado por analisis/generar_red.py)",
        "// Copia data/nodos.csv y data/aristas.csv a la carpeta import/ de Neo4j.",
        "CREATE CONSTRAINT cuenta_id IF NOT EXISTS FOR (c:Cuenta) REQUIRE c.id IS UNIQUE;",
        "",
        "LOAD CSV WITH HEADERS FROM 'file:///nodos.csv' AS fila",
        "MERGE (c:Cuenta {id: fila.id})",
        "SET c.plataforma = fila.plataforma, c.grupo = fila.grupo, c.postura = fila.postura,",
        "    c.seguidores = toInteger(fila.seguidores), c.engagement = toFloat(fila.engagement),",
        "    c.pagerank = toFloat(fila.pagerank), c.intermediacion = toFloat(fila.intermediacion),",
        "    c.comunidad = toInteger(fila.comunidad), c.rol = fila.rol;",
        "",
        "LOAD CSV WITH HEADERS FROM 'file:///aristas.csv' AS fila",
        "MATCH (a:Cuenta {id: fila.origen}), (b:Cuenta {id: fila.destino})",
        "MERGE (a)-[r:AMPLIFICA {tipo: fila.tipo}]->(b)",
        "SET r.peso = toInteger(fila.peso);",
        "",
        "// --- Consultas de análisis -------------------------------------------",
        "// Top 10 nodos de influencia",
        "MATCH (c:Cuenta) RETURN c.id, c.plataforma, c.pagerank, c.rol ORDER BY c.pagerank DESC LIMIT 10;",
        "",
        "// Puentes entre comunidades: cuentas con vecinos en 2+ comunidades distintas",
        "MATCH (c:Cuenta)-[:AMPLIFICA]-(v:Cuenta)",
        "WITH c, count(DISTINCT v.comunidad) AS comunidades_tocadas",
        "WHERE comunidades_tocadas >= 3",
        "RETURN c.id, c.comunidad, comunidades_tocadas, c.intermediacion ORDER BY c.intermediacion DESC;",
        "",
        "// Camino más corto entre el núcleo emisor y la comunidad vecinal (ruta de difusión)",
        "MATCH (o:Cuenta {grupo:'origen'}), (v:Cuenta {grupo:'vecinos'})",
        "MATCH p = shortestPath((o)-[:AMPLIFICA*..6]->(v))",
        "RETURN p ORDER BY length(p) LIMIT 5;",
        "",
        "// Opcional con Graph Data Science: Leiden y PageRank nativos",
        "// CALL gds.graph.project('eco', 'Cuenta', {AMPLIFICA: {orientation:'UNDIRECTED', properties:'peso'}});",
        "// CALL gds.leiden.write('eco', {relationshipWeightProperty:'peso', writeProperty:'leiden'});",
        "// CALL gds.pageRank.write('eco', {relationshipWeightProperty:'peso', writeProperty:'pr_gds'});",
    ]
    (NEO4J / "import.cypher").write_text("\n".join(lineas) + "\n", encoding="utf-8")


def validar_con_networkx(nodos, aristas):  # pragma: no cover - opcional
    try:
        import networkx as nx
    except ImportError:
        print("NetworkX no instalado: se omite la validación cruzada.")
        return
    G = nx.DiGraph()
    for e in aristas:
        G.add_edge(e["origen"], e["destino"], weight=e["peso"])
    pr = nx.pagerank(G, weight="weight")
    bt = nx.betweenness_centrality(G.to_undirected())
    dif_pr = max(abs(pr[n["id"]] - n["pagerank"]) for n in nodos if n["id"] in pr)
    dif_bt = max(abs(bt[n["id"]] - n["intermediacion"]) for n in nodos if n["id"] in bt)
    print(f"Validación NetworkX -> dif. máx PageRank {dif_pr:.2e}, Betweenness {dif_bt:.2e}")


def main():
    rng = random.Random(SEMILLA)
    nodos, aristas = generar_ecosistema(rng)
    adj = no_dirigido(nodos, aristas)

    bt = intermediacion_brandes(adj)
    pr = pagerank(nodos, aristas)
    particion = louvain(adj, random.Random(SEMILLA))
    q = modularidad(adj, particion)
    pos = layout_fruchterman_reingold(adj, random.Random(SEMILLA))

    for n in nodos:
        u = n["id"]
        n["grado"] = len(adj[u])
        n["grado_ponderado"] = int(sum(adj[u].values()))
        n["intermediacion"] = round(bt[u], 5)
        n["pagerank"] = round(pr[u], 5)
        n["comunidad"] = particion[u]
        n["x"], n["y"] = pos[u]
    asignar_roles(nodos)
    comunidades = resumen_comunidades(nodos, aristas, particion)

    etiquetas = {g[0]: g[1] for g in GRUPOS}
    etiquetas["puentes"] = "Cuentas puente multiplataforma"
    exportar(nodos, aristas, comunidades, q, etiquetas)

    print(f"Nodos: {len(nodos)}  Aristas: {len(aristas)}  Comunidades: {len(comunidades)}  Q={q:.3f}")
    print("Top 5 PageRank:")
    for n in sorted(nodos, key=lambda n: -n["pagerank"])[:5]:
        print(f"  {n['id']:<16} {n['plataforma']:<10} PR={n['pagerank']:.4f}  rol={n['rol']}")
    print("Top 5 intermediación:")
    for n in sorted(nodos, key=lambda n: -n["intermediacion"])[:5]:
        print(f"  {n['id']:<16} {n['grupo']:<14} BC={n['intermediacion']:.4f}")
    validar_con_networkx(nodos, aristas)


if __name__ == "__main__":
    main()
