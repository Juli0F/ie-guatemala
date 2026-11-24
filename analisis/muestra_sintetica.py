"""
Genera una MUESTRA SINTÉTICA de publicaciones de TikTok e Instagram en Guatemala
con el mismo formato que `data/crudo/plantilla_publicaciones.csv`.

Sirve para probar el pipeline y publicar el portafolio mientras se reúnen datos
reales. Las cuentas, los textos y las cifras son inventados: no describen a
personas, medios ni instituciones reales.

Salida: data/crudo/muestra_sintetica.csv

Uso:
    python analisis/muestra_sintetica.py
"""

from __future__ import annotations

import csv
import json
import math
import random
from datetime import date, timedelta
from pathlib import Path

SEMILLA = 20261124
RAIZ = Path(__file__).resolve().parent.parent
GEO = json.loads((RAIZ / "analisis" / "geografia_gt.json").read_text(encoding="utf-8"))
SALIDA = RAIZ / "data" / "crudo" / "muestra_sintetica.csv"

INICIO = date(2026, 9, 7)  # lunes; 12 semanas
SEMANAS = 12
N_CUENTAS = 240
N_PUBLICACIONES = 2600

# Peso poblacional aproximado por departamento (para repartir cuentas)
PESO_DEPTO = {
    "guatemala": 30, "quetzaltenango": 7, "escuintla": 5, "alta_verapaz": 6, "huehuetenango": 6,
    "san_marcos": 5, "quiche": 5, "peten": 4, "izabal": 3, "sacatepequez": 3, "chimaltenango": 4,
    "suchitepequez": 3, "solola": 3, "totonicapan": 2.5, "jutiapa": 2.5, "chiquimula": 2.5,
    "santa_rosa": 2, "retalhuleu": 2, "zacapa": 1.5, "baja_verapaz": 1.5, "jalapa": 2, "el_progreso": 1.2,
}

# Interés base por tema y ajustes regionales (sintéticos, para que los filtros muestren contraste)
INTERES_BASE = {"agua": 1.0, "politica": 1.2, "narcopolitica": 0.6, "estado": 1.2}
AJUSTE_REGION = {
    "guatemala": {"agua": 1.8},
    "escuintla": {"agua": 1.3},
    "izabal": {"agua": 1.5, "narcopolitica": 1.6},
    "zacapa": {"agua": 1.4, "narcopolitica": 1.4},
    "quetzaltenango": {"agua": 1.3, "estado": 1.2},
    "peten": {"narcopolitica": 2.0},
    "huehuetenango": {"narcopolitica": 1.7},
    "san_marcos": {"narcopolitica": 1.6},
    "alta_verapaz": {"agua": 1.3, "estado": 1.2},
    "solola": {"agua": 1.6},
}

# Eventos: (tema, semana inicial, semana final, multiplicador, departamento o None = nacional)
EVENTOS = [
    ("agua", 2, 4, 2.6, "guatemala"),
    ("agua", 6, 7, 2.2, "quetzaltenango"),
    ("narcopolitica", 7, 8, 2.8, None),
    ("politica", 9, 10, 2.4, None),
    ("estado", 4, 5, 1.6, None),
]

PLANTILLAS = {
    "agua_escasez": [
        ("Ya van {n} días sin agua en {lugar} y el camión cisterna no llega", "#SinAgua"),
        ("En {lugar} no cae agua desde el lunes, a llenar toneles cuando se pueda", "#CortesDeAgua"),
        ("Dicen que la otra semana hay racionamiento en {lugar}, ¿alguien sabe si es cierto?", "#SinAgua"),
        ("La pila vacía otra vez. {lugar} merece agua todos los días", "#QueremosAgua"),
    ],
    "agua_privatizacion": [
        ("La ley de aguas no puede ser para privatizar el agua. Desde {lugar} decimos que el agua es un derecho", "#ElAguaNoSeVende"),
        ("Explicamos en un minuto qué propone la ley de aguas y qué no", "#LeyDeAguas"),
        ("Otra hidroeléctrica desvió el río cerca de {lugar} y las comunidades se quedaron sin agua", "#AguaEsVida"),
    ],
    "agua_contaminacion": [
        ("Así está el río Motagua esta semana, pura basura en el río", "#SalvemosElMotagua"),
        ("El lago de Amatitlán sigue con cianobacteria, ¿hasta cuándo?", "#Amatitlan"),
        ("Aguas residuales directo al lago de Atitlán desde {lugar}", "#Atitlan"),
    ],
    "agua_gestion": [
        ("Pago puntual el recibo del agua en {lugar} y el servicio de agua no mejora", "#Empagua"),
        ("Hay una tubería rota en {lugar} desde hace dos semanas, se pierde el agua potable", ""),
        ("¿Por qué subió la tarifa de agua en {lugar} si el agua solo cae dos días?", ""),
    ],
    "pol_elecciones": [
        ("El TSE tiene que explicar las actas de {lugar}", "#TSE"),
        ("Hablemos de cómo se cuentan los votos, sin teorías de fraude electoral", "#Elecciones"),
        ("En {lugar} piden revisar el padrón electoral antes de las próximas elecciones", "#GuateVota"),
    ],
    "pol_congreso": [
        ("Los diputados aprobaron el presupuesto general sin discutirlo con nadie", "#CongresoGT"),
        ("¿Qué hizo tu diputado por {lugar} este año? Revisá la iniciativa de ley que presentó", "#Diputados"),
        ("Otra sesión del Congreso sin quórum, la bancada no llegó", "#CongresoGT"),
    ],
    "pol_ruptura": [
        ("Esto ya es persecución política, dicen desde {lugar}", "#RenunciaYa"),
        ("Unos hablan de golpe de Estado y otros de Estado de derecho, ¿qué dice la Corte de Constitucionalidad?", "#DefendamosLaDemocracia"),
        ("La criminalización de líderes comunitarios en {lugar} no es nueva", ""),
    ],
    "narco_financiamiento": [
        ("¿Quién financia las campañas en {lugar}? Muchos hablan de dinero del narco", "#Narcopolitica"),
        ("Financiamiento electoral ilícito: lo que se sabe y lo que no", "#NarcoEstado"),
        ("Otro caso de lavado de dinero vinculado a un alcalde, ¿narcoalcaldes en {lugar}?", "#Narcopolitica"),
    ],
    "narco_territorio": [
        ("Encontraron otra pista clandestina cerca de {lugar}", "#Narcotrafico"),
        ("Reportan decomiso de cocaína en {lugar}, el cargamento venía por la costa", "#Narco"),
        ("La ruta de la droga pasa por {lugar} y todos lo saben", ""),
    ],
    "narco_extradicion": [
        ("Otro extraditado de {lugar}. En las cortes de Estados Unidos van a salir nombres", "#Extradicion"),
        ("Pedido de extradición contra una estructura criminal que operaba en {lugar}", "#Extradicion"),
    ],
    "est_corrupcion": [
        ("Plazas fantasma y obra fantasma en {lugar}, la Contraloría no dice nada", "#PactoDeCorruptos"),
        ("Corrupción en la compra de medicinas otra vez", "#Corrupcion"),
        ("Sobrevaloración en la carretera de {lugar}, ¿quién responde?", "#NoALaCorrupcion"),
    ],
    "est_justicia": [
        ("El Ministerio Público abrió otra investigación, esta vez en {lugar}", "#MP"),
        ("Jueces en el exilio y periodistas presos: así está la justicia", "#JusticiaGT"),
        ("La fiscal general y la FECI vuelven a ser tendencia", "#FiscalGeneral"),
    ],
    "est_servicios": [
        ("En el hospital de {lugar} no hay medicinas otra vez", "#SinMedicinas"),
        ("La carretera a {lugar} está llena de hoyos, ya van tres accidentes", "#CarreterasGT"),
        ("La escuela de {lugar} sigue sin techo y los maestros sin pago", ""),
    ],
    "est_seguridad": [
        ("La extorsión en {lugar} no para y la PNC no hace nada", "#Extorsion"),
        ("Las maras cobran a los buses de {lugar}, ¿estado de prevención otra vez?", "#SeguridadGT"),
        ("Otra fuga de reos, el sistema penitenciario no aguanta", "#PNC"),
    ],
}
SUB_POR_TEMA = {
    "agua": ["agua_escasez", "agua_escasez", "agua_privatizacion", "agua_contaminacion", "agua_gestion"],
    "politica": ["pol_elecciones", "pol_congreso", "pol_congreso", "pol_ruptura"],
    "narcopolitica": ["narco_financiamiento", "narco_territorio", "narco_territorio", "narco_extradicion"],
    "estado": ["est_corrupcion", "est_justicia", "est_servicios", "est_servicios", "est_seguridad"],
}
RUIDO = [
    "Feliz domingo desde {lugar}", "Receta de pepián como la de la abuela", "Así amaneció {lugar} hoy",
    "Partido de fut en {lugar}, ¡vamos!", "Tutorial de maquillaje rápido", "Mi rutina de mañana",
    "Probando los shucos de {lugar}", "Atardecer en {lugar}",
]
TIPOS = [("ciudadano", 0.58), ("creador", 0.18), ("medio", 0.10), ("activista", 0.09), ("institucional", 0.05)]


def elegir(rng, pares):
    total = sum(p for _, p in pares)
    r = rng.random() * total
    for v, p in pares:
        r -= p
        if r <= 0:
            return v
    return pares[-1][0]


def main():
    rng = random.Random(SEMILLA)
    deptos = {d["id"]: d for d in GEO["departamentos"]}

    cuentas = []
    for i in range(N_CUENTAS):
        tipo = elegir(rng, TIPOS)
        depto = "guatemala" if tipo == "medio" and rng.random() < 0.65 else elegir(rng, list(PESO_DEPTO.items()))
        plataforma = "tiktok" if rng.random() < (0.45 if tipo in ("medio", "institucional") else 0.62) else "instagram"
        base = {"ciudadano": 6.8, "creador": 9.6, "medio": 10.6, "activista": 8.6, "institucional": 9.4}[tipo]
        interes = {}
        for t, b in INTERES_BASE.items():
            interes[t] = b * AJUSTE_REGION.get(depto, {}).get(t, 1.0) * rng.uniform(0.3, 1.7)
        # algunos activistas y creadores se especializan en un tema
        if tipo in ("activista", "creador") and rng.random() < 0.6:
            interes[rng.choice(list(interes))] *= 4
        cuentas.append({
            "cuenta": f"@{'tt' if plataforma == 'tiktok' else 'ig'}_{tipo[:4]}_{i:03d}",
            "plataforma": plataforma,
            "tipo": tipo,
            "depto": depto,
            "seguidores": int(math.exp(rng.gauss(base, 1.0))),
            "bio": rng.choice(deptos[depto]["alias"]) if rng.random() < 0.6 else "",
            "interes": interes,
            "actividad": {"ciudadano": 1, "creador": 3, "medio": 4, "activista": 3, "institucional": 1.5}[tipo] * rng.uniform(0.4, 1.6),
        })

    def multiplicador(tema, semana, depto):
        m = 1.0
        for t, s0, s1, f, d in EVENTOS:
            if t == tema and s0 <= semana <= s1 and (d is None or d == depto):
                m *= f
        return m

    filas = []
    for k in range(N_PUBLICACIONES):
        autor = elegir(rng, [(c, c["actividad"]) for c in cuentas])
        semana = rng.randrange(SEMANAS)
        dia = INICIO + timedelta(days=semana * 7 + rng.randrange(7))
        depto_pub = autor["depto"] if rng.random() < 0.82 else elegir(rng, list(PESO_DEPTO.items()))
        lugar = rng.choice(deptos[depto_pub]["alias"])

        if rng.random() < 0.16:
            tema, sub = None, None
            texto, hashtag = rng.choice(RUIDO).format(lugar=lugar), ""
        else:
            pesos = [(t, w * multiplicador(t, semana, depto_pub)) for t, w in autor["interes"].items()]
            tema = elegir(rng, pesos)
            sub = rng.choice(SUB_POR_TEMA[tema])
            texto, hashtag = rng.choice(PLANTILLAS[sub])
            texto = texto.format(lugar=lugar, n=rng.randint(3, 12))
            # cruce frecuente narcopolítica + política
            if tema == "narcopolitica" and rng.random() < 0.3:
                texto += ". ¿Y los diputados qué dicen?"

        # interacción: TikTok usa dueto/stitch; Instagram repost/colaboración
        if rng.random() < 0.35:
            interaccion, objetivo = "original", None
        else:
            opciones = ["dueto", "stitch", "mencion", "comentario"] if autor["plataforma"] == "tiktok" else ["repost", "colaboracion", "mencion", "comentario"]
            interaccion = rng.choice(opciones)
            candidatas = []
            for c in cuentas:
                if c is autor:
                    continue
                w = math.log10(c["seguidores"] + 10)
                if c["depto"] == depto_pub:
                    w *= 3.5
                if tema:
                    w *= 0.3 + c["interes"][tema]
                if c["tipo"] == "medio":
                    w *= 1.8
                if c["plataforma"] != autor["plataforma"] and interaccion not in ("mencion", "comentario"):
                    w *= 0.08  # dueto/stitch/repost solo dentro de la misma plataforma (casi siempre)
                candidatas.append((c, w))
            objetivo = elegir(rng, candidatas)

        menciones = ""
        if rng.random() < 0.12:
            m = rng.choice([c for c in cuentas if c["tipo"] in ("institucional", "medio")])
            if m is not autor:
                menciones = m["cuenta"]

        geotag = ""
        if rng.random() < (0.38 if autor["plataforma"] == "instagram" else 0.18):
            geotag = rng.choice(deptos[depto_pub]["alias"])
        elif rng.random() < 0.08 and depto_pub == "guatemala":
            geotag = f"Zona {rng.randint(1, 21)}"

        vistas = int(math.exp(rng.gauss(7.5, 1.4)) * (1 + autor["seguidores"] / 20000))
        filas.append({
            "id_publicacion": f"{'tt' if autor['plataforma'] == 'tiktok' else 'ig'}_{k:05d}",
            "plataforma": autor["plataforma"],
            "fecha": dia.isoformat(),
            "cuenta": autor["cuenta"],
            "tipo_cuenta": autor["tipo"],
            "seguidores": autor["seguidores"],
            "bio_ubicacion": autor["bio"],
            "texto": texto,
            "hashtags": hashtag,
            "transcripcion": "",
            "ubicacion_etiquetada": geotag,
            "interaccion": interaccion,
            "cuenta_objetivo": objetivo["cuenta"] if objetivo else "",
            "menciones": menciones,
            "vistas": vistas,
            "me_gusta": int(vistas * rng.uniform(0.02, 0.09)),
            "comentarios": int(vistas * rng.uniform(0.002, 0.01)),
            "compartidos": int(vistas * rng.uniform(0.002, 0.02)),
        })

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    with open(SALIDA, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)
    print(f"{len(filas)} publicaciones de {len(cuentas)} cuentas -> {SALIDA.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
