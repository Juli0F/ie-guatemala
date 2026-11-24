"""
Algoritmos de análisis de redes sociales (SNA) en Python puro.

Compartidos por todos los scripts del portafolio. Cada función sigue el
algoritmo de referencia citado y no requiere dependencias externas.

    no_dirigido        grafo no dirigido ponderado a partir de aristas dirigidas
    intermediacion     Brandes (2001); exacta o muestreada (Brandes y Pich, 2007)
    pagerank           Page et al. (1999), dirigido y ponderado
    louvain            Blondel et al. (2008)
    modularidad        Newman (2006)
    layout_fr          Fruchterman y Reingold (1991)
"""

from __future__ import annotations

import math
import random
from collections import defaultdict, deque

Arista = tuple[str, str, float]


def no_dirigido(ids, aristas) -> dict[str, dict[str, float]]:
    """aristas: iterable de (u, v, peso). Suma los pesos de u->v y v->u."""
    adj: dict[str, dict[str, float]] = {u: {} for u in ids}
    for u, v, w in aristas:
        if u == v:
            continue
        adj.setdefault(u, {})
        adj.setdefault(v, {})
        adj[u][v] = adj[u].get(v, 0) + w
        adj[v][u] = adj[v].get(u, 0) + w
    return adj


def intermediacion(adj: dict[str, dict[str, float]], muestras: int | None = None,
                   rng: random.Random | None = None) -> dict[str, float]:
    """Betweenness no ponderada y normalizada (grafo no dirigido).

    Con `muestras`, usa solo k nodos fuente elegidos al azar y reescala
    el resultado por n/k (aproximación de Brandes y Pich). Conviene en
    redes con miles de nodos.
    """
    nodos = list(adj)
    n = len(nodos)
    cb = dict.fromkeys(nodos, 0.0)
    fuentes = nodos
    if muestras and muestras < n:
        fuentes = (rng or random.Random(0)).sample(nodos, muestras)
    for s in fuentes:
        pila, pred = [], {w: [] for w in nodos}
        sigma = dict.fromkeys(nodos, 0)
        sigma[s] = 1
        dist = dict.fromkeys(nodos, -1)
        dist[s] = 0
        cola = deque([s])
        while cola:
            v = cola.popleft()
            pila.append(v)
            for w in adj[v]:
                if dist[w] < 0:
                    dist[w] = dist[v] + 1
                    cola.append(w)
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    pred[w].append(v)
        delta = dict.fromkeys(nodos, 0.0)
        while pila:
            w = pila.pop()
            for v in pred[w]:
                delta[v] += sigma[v] / sigma[w] * (1 + delta[w])
            if w != s:
                cb[w] += delta[w]
    escala = 1 / ((n - 1) * (n - 2)) if n > 2 else 1.0  # no dirigido: /2 y *2 se cancelan
    escala *= n / len(fuentes) if fuentes else 1
    return {k: v * escala for k, v in cb.items()}


def pagerank(ids, aristas, d=0.85, tol=1e-10, max_iter=200) -> dict[str, float]:
    """PageRank dirigido y ponderado. La arista u->v transfiere autoridad a v."""
    ids = list(ids)
    salida = defaultdict(float)
    entrantes = defaultdict(list)
    for u, v, w in aristas:
        salida[u] += w
        entrantes[v].append((u, w))
    n = len(ids)
    if n == 0:
        return {}
    pr = dict.fromkeys(ids, 1 / n)
    for _ in range(max_iter):
        colgantes = sum(pr[u] for u in ids if salida[u] == 0)
        nuevo = {}
        for v in ids:
            s = sum(pr[u] * w / salida[u] for u, w in entrantes[v])
            nuevo[v] = (1 - d) / n + d * (s + colgantes / n)
        err = sum(abs(nuevo[k] - pr[k]) for k in ids)
        pr = nuevo
        if err < tol:
            break
    return pr


def modularidad(adj, particion: dict[str, int]) -> float:
    m2 = sum(sum(v.values()) for v in adj.values())  # = 2m
    if m2 == 0:
        return 0.0
    interna = defaultdict(float)
    grado_com = defaultdict(float)
    for u in adj:
        grado_com[particion[u]] += sum(adj[u].values())
        for v, w in adj[u].items():
            if particion[u] == particion[v]:
                interna[particion[u]] += w
    return sum(interna[c] / m2 - (grado_com[c] / m2) ** 2 for c in grado_com)


def louvain(adj, rng: random.Random) -> dict[str, int]:
    """Louvain: optimización local de modularidad + agregación, hasta converger.
    Devuelve comunidades numeradas por tamaño descendente (0 = la mayor)."""
    if not adj:
        return {}
    pertenencia = {u: u for u in adj}
    g = {u: dict(vs) for u, vs in adj.items()}
    while True:
        m2 = sum(sum(v.values()) for v in g.values())
        if m2 == 0:
            break
        k = {u: sum(w for v, w in g[u].items() if v != u) + 2 * g[u].get(u, 0) for u in g}
        com = {u: u for u in g}
        tot = dict(k)
        mejora_global = False
        orden = list(g)
        mejoro = True
        while mejoro:
            mejoro = False
            rng.shuffle(orden)
            for u in orden:
                cu = com[u]
                pesos = defaultdict(float)
                for v, w in g[u].items():
                    if v != u:
                        pesos[com[v]] += w
                tot[cu] -= k[u]
                mejor_c, mejor_gan = cu, pesos.get(cu, 0) - tot[cu] * k[u] / m2
                for c, w in pesos.items():
                    gan = w - tot[c] * k[u] / m2
                    if gan > mejor_gan + 1e-12:
                        mejor_c, mejor_gan = c, gan
                tot[mejor_c] += k[u]
                if mejor_c != cu:
                    com[u] = mejor_c
                    mejoro = mejora_global = True
        if not mejora_global:
            break
        pertenencia = {o: com[n] for o, n in pertenencia.items()}
        nuevo = defaultdict(lambda: defaultdict(float))
        for u in g:
            for v, w in g[u].items():
                nuevo[com[u]][com[v]] += w
        g = {}
        for c, vs in nuevo.items():
            g[c] = {}
            for c2, w in vs.items():
                g[c][c2] = w / 2 if c == c2 else w
    tam = defaultdict(int)
    for c in pertenencia.values():
        tam[c] += 1
    orden = sorted(tam, key=lambda c: -tam[c])
    mapa = {c: i for i, c in enumerate(orden)}
    return {u: mapa[c] for u, c in pertenencia.items()}


def layout_fr(adj, rng: random.Random, iteraciones: int | None = None) -> dict[str, tuple[float, float]]:
    """Fruchterman-Reingold con gravedad al centro. Coordenadas normalizadas a [0, 1].
    Es O(n²) por iteración: con redes grandes se reduce el número de iteraciones."""
    ids = list(adj)
    n = len(ids)
    if n == 0:
        return {}
    if iteraciones is None:
        iteraciones = max(40, min(400, int(4_000_000 / max(1, n * n))))
    pos = {u: [rng.uniform(-1, 1), rng.uniform(-1, 1)] for u in ids}
    kk = math.sqrt(4 / n)
    t = 0.12
    for _ in range(iteraciones):
        disp = {u: [0.0, 0.0] for u in ids}
        for i in range(n):
            u = ids[i]
            pu = pos[u]
            for j in range(i + 1, n):
                v = ids[j]
                dx = pu[0] - pos[v][0]
                dy = pu[1] - pos[v][1]
                d = math.hypot(dx, dy) or 1e-4
                f = kk * kk / d
                disp[u][0] += dx / d * f
                disp[u][1] += dy / d * f
                disp[v][0] -= dx / d * f
                disp[v][1] -= dy / d * f
        for u in ids:
            for v, w in adj[u].items():
                if u < v:
                    dx = pos[u][0] - pos[v][0]
                    dy = pos[u][1] - pos[v][1]
                    d = math.hypot(dx, dy) or 1e-4
                    f = d * d / kk * (1 + math.log1p(w) * 0.15)
                    disp[u][0] -= dx / d * f
                    disp[u][1] -= dy / d * f
                    disp[v][0] += dx / d * f
                    disp[v][1] += dy / d * f
        for u in ids:
            disp[u][0] -= pos[u][0] * 0.6
            disp[u][1] -= pos[u][1] * 0.6
            d = math.hypot(*disp[u]) or 1e-4
            pos[u][0] += disp[u][0] / d * min(d, t)
            pos[u][1] += disp[u][1] / d * min(d, t)
        t = max(0.005, t * 0.99)
    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    sx = (max(xs) - min(xs)) or 1
    sy = (max(ys) - min(ys)) or 1
    return {u: (round((p[0] - min(xs)) / sx, 4), round((p[1] - min(ys)) / sy, 4)) for u, p in pos.items()}
