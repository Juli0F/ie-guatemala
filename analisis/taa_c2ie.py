"""
Proyectos 2 y 3 - TAA (Target Audience Analysis) y simulación de campaña C2IE
==============================================================================

Lee la red generada por `generar_red.py` y produce:

  data/taa.json    -> segmentos de audiencia, encuesta sintética (n=600),
                      confiabilidad (alfa de Cronbach), correlaciones y matriz
                      de priorización (susceptibilidad x accesibilidad x efecto)
  data/c2ie.json   -> simulación de difusión (cascada independiente, Monte Carlo)
                      con 4 estrategias de intervención, serie semanal
                      tratamiento vs. control, diferencias en diferencias (DiD)
                      y tabla de MOP / MOE.
  data/encuesta_taa.csv -> microdatos de la encuesta (Excel / R / SPSS)

Todo es SINTÉTICO y reproducible (semilla fija). Solo biblioteca estándar.

Uso:
    python analisis/generar_red.py   # primero
    python analisis/taa_c2ie.py
"""

from __future__ import annotations

import csv
import json
import math
import random
import statistics as st
from collections import defaultdict
from pathlib import Path

SEMILLA = 20261124
RAIZ = Path(__file__).resolve().parent.parent
DATA = RAIZ / "data"

# ---------------------------------------------------------------------------
# TAA - definición de audiencias objetivo (proceso de 8 pasos)
# ---------------------------------------------------------------------------
# Constructos de la encuesta (escala Likert 1-5, 4 ítems cada uno):
#   CI  confianza institucional
#   PR  percepción de riesgo (escasez)
#   AM  alfabetización mediática
#   IC  intención de compartir contenido no verificado
CONSTRUCTOS = {
    "CI": "Confianza institucional",
    "PR": "Percepción de riesgo",
    "AM": "Alfabetización mediática",
    "IC": "Intención de compartir sin verificar",
}

SEGMENTOS = [
    {
        "id": "TA1",
        "nombre": "Madres y padres de familia de colonias de Mixco y Villa Nueva",
        "plataforma": "instagram",
        "edad": "30-50",
        "n": 170,
        "medias": {"CI": 2.4, "PR": 4.2, "AM": 2.6, "IC": 3.6},
        "condiciones": "Cortes de agua recurrentes y dependencia de camiones cisterna en varias colonias; poca información municipal sobre horarios de servicio.",
        "vulnerabilidades": ["Miedo a no poder llenar toneles y pilas del hogar", "Desconfianza hacia el servicio municipal de agua", "Grupos vecinales como fuente principal"],
        "motivaciones": ["Proteger a la familia", "Previsibilidad", "Pertenencia a la colonia"],
        "formatos": ["Historias con datos de la colonia", "Carruseles explicativos", "Reels cortos de líderes del COCODE"],
        "horario": "19:00-22:00",
        "voces_creibles": ["Presidentes de COCODE", "Enfermeras del centro de salud"],
        "comportamiento_deseado": "Consultar el horario oficial de servicio de su municipalidad antes de compartir y no acaparar agua.",
        "accesibilidad": 4.4,
    },
    {
        "id": "TA2",
        "nombre": "Universitarios y creadores jóvenes de la Ciudad de Guatemala",
        "plataforma": "tiktok",
        "edad": "18-24",
        "n": 160,
        "medias": {"CI": 2.1, "PR": 2.9, "AM": 3.7, "IC": 2.5},
        "condiciones": "Alta exposición a contenido viral; escepticismo hacia las instituciones; sensibles a la autenticidad.",
        "vulnerabilidades": ["Rechazo al tono institucional", "Recompensa social por publicar primero"],
        "motivaciones": ["Autenticidad", "Humor", "Reconocimiento entre pares"],
        "formatos": ["Duetos/stitch que desmontan el bulo", "Tendencias de audio", "Retos de verificación"],
        "horario": "21:00-01:00",
        "voces_creibles": ["Creadores guatemaltecos de divulgación", "Estudiantes de ingeniería ambiental"],
        "comportamiento_deseado": "Crear y compartir respuestas tipo stitch que expliquen la técnica de manipulación.",
        "accesibilidad": 3.9,
    },
    {
        "id": "TA3",
        "nombre": "Consumidores habituales de memes políticos",
        "plataforma": "tiktok",
        "edad": "20-40",
        "n": 150,
        "medias": {"CI": 1.7, "PR": 3.4, "AM": 2.3, "IC": 4.1},
        "condiciones": "Núcleo que ya acepta la narrativa; identidad de grupo definida por oposición a las autoridades.",
        "vulnerabilidades": ["Sesgo de confirmación fuerte", "Efecto contraproducente (backfire) ante desmentidos directos"],
        "motivaciones": ["Identidad de grupo", "Indignación", "Entretenimiento"],
        "formatos": ["Humor que no ataca al grupo", "Mensajes de interés propio (ahorro, salud)"],
        "horario": "12:00-14:00 y 20:00-23:00",
        "voces_creibles": ["Pares dentro del grupo", "Dueños de tiendas de barrio"],
        "comportamiento_deseado": "Reducir la reproducción del contenido; no se busca un cambio de actitud a corto plazo.",
        "accesibilidad": 2.6,
    },
    {
        "id": "TA4",
        "nombre": "Tiendas de barrio y expendios de agua purificada (garrafones)",
        "plataforma": "instagram",
        "edad": "25-60",
        "n": 120,
        "medias": {"CI": 2.9, "PR": 3.8, "AM": 2.9, "IC": 3.0},
        "condiciones": "Se ven afectados por compras de pánico (desabasto y quejas) pero también obtienen ventas a corto plazo.",
        "vulnerabilidades": ["Incentivo económico ambivalente", "Clientes que les piden confirmación"],
        "motivaciones": ["Estabilidad del negocio", "Reputación en el barrio"],
        "formatos": ["Material imprimible para mostrador", "Publicaciones en colaboración", "Audios cortos en español y kaqchikel"],
        "horario": "07:00-09:00",
        "voces_creibles": ["Asociaciones de comerciantes del municipio", "Otros tenderos"],
        "comportamiento_deseado": "Exhibir información verificada y limitar ventas por cliente durante picos.",
        "accesibilidad": 4.0,
    },
]


def likert(rng: random.Random, media: float, sd: float = 0.9) -> int:
    return max(1, min(5, round(rng.gauss(media, sd))))


def generar_encuesta(rng: random.Random):
    filas = []
    folio = 0
    for s in SEGMENTOS:
        for _ in range(s["n"]):
            folio += 1
            fila = {"folio": folio, "segmento": s["id"], "plataforma": s["plataforma"]}
            # rasgo latente por persona + ruido por ítem -> confiabilidad realista
            latentes = {c: rng.gauss(m, 0.75) for c, m in s["medias"].items()}
            # relación teórica: mayor AM -> menor IC
            latentes["IC"] -= 0.45 * (latentes["AM"] - s["medias"]["AM"])
            for c, lat in latentes.items():
                for i in range(1, 5):
                    fila[f"{c}{i}"] = likert(rng, lat, 0.7)
            filas.append(fila)
    return filas


def alfa_cronbach(filas, prefijo: str) -> float:
    items = [[f[f"{prefijo}{i}"] for f in filas] for i in range(1, 5)]
    k = len(items)
    var_items = sum(st.pvariance(it) for it in items)
    totales = [sum(v) for v in zip(*items)]
    return k / (k - 1) * (1 - var_items / st.pvariance(totales))


def pearson(x, y) -> float:
    mx, my = st.fmean(x), st.fmean(y)
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    den = math.sqrt(sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y))
    return num / den


def analizar_taa(filas):
    puntaje = lambda f, c: st.fmean(f[f"{c}{i}"] for i in range(1, 5))
    alfas = {c: round(alfa_cronbach(filas, c), 3) for c in CONSTRUCTOS}
    por_seg = []
    for s in SEGMENTOS:
        sub = [f for f in filas if f["segmento"] == s["id"]]
        medias = {c: round(st.fmean(puntaje(f, c) for f in sub), 2) for c in CONSTRUCTOS}
        de = {c: round(st.stdev(puntaje(f, c) for f in sub), 2) for c in CONSTRUCTOS}
        # Susceptibilidad: qué tan probable es que el segmento cambie de conducta
        # ante un mensaje correctivo. Alta PR (motivación) y AM media ayudan;
        # IC muy alta + CI muy baja indica resistencia (riesgo de backfire).
        susc = 1 + 4 * (0.35 * (medias["PR"] - 1) / 4 + 0.35 * (medias["CI"] - 1) / 4
                        + 0.30 * (1 - abs(medias["AM"] - 3) / 2))
        # Efecto potencial: cuánto daño evita cambiar a este segmento (IC x tamaño relativo)
        efecto = 1 + 4 * ((medias["IC"] - 1) / 4 * 0.7 + s["n"] / 170 * 0.3)
        prioridad = susc * s["accesibilidad"] * efecto
        por_seg.append({
            **{k: v for k, v in s.items() if k not in ("medias",)},
            "medias": medias,
            "de": de,
            "susceptibilidad": round(susc, 2),
            "efecto": round(efecto, 2),
            "prioridad": round(prioridad, 1),
        })
    por_seg.sort(key=lambda s: -s["prioridad"])
    for i, s in enumerate(por_seg, 1):
        s["rango"] = i

    am = [puntaje(f, "AM") for f in filas]
    ic = [puntaje(f, "IC") for f in filas]
    ci = [puntaje(f, "CI") for f in filas]
    pr = [puntaje(f, "PR") for f in filas]
    correl = {
        "AM_IC": round(pearson(am, ic), 3),
        "CI_IC": round(pearson(ci, ic), 3),
        "PR_IC": round(pearson(pr, ic), 3),
        "CI_PR": round(pearson(ci, pr), 3),
    }
    # Dispersión AM vs IC (muestra de 240 puntos para el gráfico)
    rng = random.Random(SEMILLA)
    muestra = rng.sample(range(len(filas)), 240)
    dispersion = [[round(am[i], 2), round(ic[i], 2), filas[i]["segmento"]] for i in muestra]
    return {
        "constructos": CONSTRUCTOS,
        "n_total": len(filas),
        "alfa_cronbach": alfas,
        "correlaciones": correl,
        "segmentos": por_seg,
        "dispersion_am_ic": dispersion,
    }


# ---------------------------------------------------------------------------
# C2IE - simulación de campaña sobre la red real del Proyecto 1
# ---------------------------------------------------------------------------

def cargar_red():
    d = json.loads((DATA / "red_influencia.json").read_text(encoding="utf-8"))
    vecinos = defaultdict(list)  # quién ve el contenido de u: los que lo amplifican
    for u, v, w, _ in d["aristas"]:
        # u amplifica a v  -> el contenido de v llega a u, y u lo re-difunde
        p = 1 - math.exp(-0.06 * w)
        vecinos[v].append((u, p))
        vecinos[u].append((v, p * 0.5))  # exposición inversa más débil
    return d, vecinos


def cascada(vecinos, semillas, inoculados, rng, pasos=10, eficacia=0.75):
    """Cascada independiente. Los nodos inoculados (prebunking) rechazan el
    contenido con probabilidad `eficacia` y además no lo re-difunden."""
    activos = set(semillas)
    frontera = list(semillas)
    por_paso = [len(activos)]
    for _ in range(pasos):
        nueva = []
        for u in frontera:
            for v, p in vecinos[u]:
                if v in activos:
                    continue
                if v in inoculados and rng.random() < eficacia:
                    continue
                if rng.random() < p:
                    activos.add(v)
                    nueva.append(v)
        frontera = nueva
        por_paso.append(len(activos))
    return por_paso


def simular_c2ie():
    d, vecinos = cargar_red()
    nodos = d["nodos"]
    n = len(nodos)
    semillas = [x["id"] for x in nodos if x["grupo"] == "origen"]
    candidatos = [x for x in nodos if x["grupo"] != "origen"]
    k = 8  # presupuesto: 8 cuentas a las que se puede llegar con prebunking/alianza

    def top(clave):
        return {x["id"] for x in sorted(candidatos, key=lambda x: -x[clave])[:k]}

    rng_sel = random.Random(SEMILLA)
    estrategias = {
        "sin_intervencion": ("Sin intervención (línea base)", set()),
        "aleatoria": ("8 cuentas al azar", set(x["id"] for x in rng_sel.sample(candidatos, k))),
        "seguidores": ("8 cuentas con más seguidores", top("seguidores")),
        "pagerank": ("8 cuentas con mayor PageRank", top("pagerank")),
        "intermediacion": ("8 puentes (mayor intermediación)", top("intermediacion")),
    }
    corridas = 600
    resultados = []
    for clave, (etiqueta, inoc) in estrategias.items():
        rng = random.Random(SEMILLA)
        finales, curvas = [], []
        for _ in range(corridas):
            c = cascada(vecinos, semillas, inoc, rng)
            curvas.append(c)
            finales.append(c[-1])
        curva_media = [round(st.fmean(c[i] for c in curvas) / n * 100, 2) for i in range(len(curvas[0]))]
        finales_pct = sorted(f / n * 100 for f in finales)
        resultados.append({
            "id": clave,
            "etiqueta": etiqueta,
            "inoculados": sorted(inoc),
            "alcance_medio_pct": round(st.fmean(finales_pct), 2),
            "ic95": [round(finales_pct[int(0.025 * corridas)], 2), round(finales_pct[int(0.975 * corridas)], 2)],
            "curva": curva_media,
        })
    base = resultados[0]["alcance_medio_pct"]
    for r in resultados:
        r["reduccion_vs_base_pct"] = round((base - r["alcance_medio_pct"]) / base * 100, 1)
    return resultados


def serie_semanal(rng: random.Random):
    """12 semanas: 4 de línea base, 6 de campaña, 2 de sostenimiento.
    Región tratada (área metropolitana: Guatemala, Mixco, Villa Nueva) vs.
    región de control (Quetzaltenango)."""
    semanas = []
    for s in range(1, 13):
        fase = "base" if s <= 4 else ("campaña" if s <= 10 else "sostenimiento")
        tendencia = 0.6 * s  # crecimiento orgánico de la narrativa en ambas regiones
        efecto = 0 if s <= 4 else min(14, 2.6 * (s - 4)) if s <= 10 else 13
        ctl = 22 + tendencia + rng.gauss(0, 1.2)
        trt = 24 + tendencia - efecto + rng.gauss(0, 1.2)
        alcance_contra = 0 if s <= 4 else int(18000 * (1 - math.exp(-0.45 * (s - 4))) + rng.gauss(0, 800))
        semanas.append({
            "semana": s,
            "fase": fase,
            "narrativa_tratada_pct": round(trt, 1),
            "narrativa_control_pct": round(ctl, 1),
            "alcance_contramensaje": max(0, alcance_contra),
            "verificaciones_calendario": int(300 + (0 if s <= 4 else 420 * min(1, (s - 4) / 4)) + rng.gauss(0, 40)),
            "compras_panico_idx": round(100 + rng.gauss(0, 3) - (0 if s <= 4 else min(28, 5 * (s - 4))), 1),
        })
    pre_t = st.fmean(w["narrativa_tratada_pct"] for w in semanas if w["semana"] <= 4)
    post_t = st.fmean(w["narrativa_tratada_pct"] for w in semanas if w["semana"] >= 9)
    pre_c = st.fmean(w["narrativa_control_pct"] for w in semanas if w["semana"] <= 4)
    post_c = st.fmean(w["narrativa_control_pct"] for w in semanas if w["semana"] >= 9)
    did = (post_t - pre_t) - (post_c - pre_c)
    return semanas, {
        "pre_tratada": round(pre_t, 2), "post_tratada": round(post_t, 2),
        "pre_control": round(pre_c, 2), "post_control": round(post_c, 2),
        "did_pp": round(did, 2),
    }


def main():
    rng = random.Random(SEMILLA)
    filas = generar_encuesta(rng)
    with open(DATA / "encuesta_taa.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)
    taa = analizar_taa(filas)
    (DATA / "taa.json").write_text(json.dumps(taa, ensure_ascii=False, indent=1), encoding="utf-8")

    estrategias = simular_c2ie()
    semanas, did = serie_semanal(random.Random(SEMILLA + 1))
    ultima = semanas[-1]
    c2ie = {
        "estrategias": estrategias,
        "semanas": semanas,
        "did": did,
        "mop": [
            {"indicador": "Piezas publicadas por las voces aliadas", "meta": 120, "logro": 134},
            {"indicador": "Cuentas puente con prebunking entregado", "meta": 8, "logro": 8},
            {"indicador": "Alcance acumulado de contramensajes", "meta": 90000,
             "logro": sum(w["alcance_contramensaje"] for w in semanas)},
            {"indicador": "Comerciantes con material de mostrador", "meta": 60, "logro": 47},
        ],
        "moe": [
            {"indicador": "Proporción de publicaciones que reproducen la narrativa (DiD)",
             "base": did["pre_tratada"], "final": did["post_tratada"], "unidad": "%", "direccion": "baja"},
            {"indicador": "Índice de compras de pánico (base 100)",
             "base": 100, "final": ultima["compras_panico_idx"], "unidad": "", "direccion": "baja"},
            {"indicador": "Consultas semanales al calendario oficial",
             "base": semanas[0]["verificaciones_calendario"], "final": ultima["verificaciones_calendario"],
             "unidad": "", "direccion": "sube"},
        ],
    }
    (DATA / "c2ie.json").write_text(json.dumps(c2ie, ensure_ascii=False, indent=1), encoding="utf-8")

    print("Alfa de Cronbach:", taa["alfa_cronbach"])
    print("Correlaciones:", taa["correlaciones"])
    for s in taa["segmentos"]:
        print(f"  {s['rango']}. {s['id']} prioridad={s['prioridad']} S={s['susceptibilidad']} A={s['accesibilidad']} E={s['efecto']}")
    for e in estrategias:
        print(f"  {e['etiqueta']:<38} alcance={e['alcance_medio_pct']:5.1f}%  reducción={e['reduccion_vs_base_pct']}%")
    print("DiD:", did)


if __name__ == "__main__":
    main()
