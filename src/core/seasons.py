"""
Módulo de las 72 Micro-Estaciones Japonesas (Shichijūni-kō / 七十二候) para Yuki.
Permite anclar la creación poética, musical y dialéctica en el fluir del tiempo natural.
"""

from datetime import datetime
from typing import Dict, Any

# Selección representativa de las 24 estaciones solares (Sekki) y 72 micro-estaciones (Kō)
SEASONS_DATA = [
    # Primavera (Risshun a Kokū)
    {"month": 2, "day": 4, "sekki": "Risshun (Inicio de la Primavera)", "ko": "El viento del este derrite el hielo", "kigo": "hielo deshecho", "tea_element": "agua fresca de montaña"},
    {"month": 2, "day": 19, "sekki": "Usui (Agua de Lluvia)", "ko": "La lluvia humedece la tierra", "kigo": "tierra mojada", "tea_element": "aroma a vapor de lluvia"},
    {"month": 3, "day": 5, "sekki": "Keichitsu (Despertar de los Insectos)", "ko": "Los primeros brotes asoman", "kigo": "sauces brotando", "tea_element": "hojas tiernas de matcha"},
    {"month": 3, "day": 20, "sekki": "Shunbun (Equinoccio de Primavera)", "ko": "Los gorriones construyen sus nidos", "kigo": "vuelo de pájaros", "tea_element": "dulce de flor de cerezo"},
    {"month": 4, "day": 5, "sekki": "Seimei (Claridad Pura)", "ko": "Las golondrinas regresan", "kigo": "claridad matutina", "tea_element": "tazón de loza blanca"},
    {"month": 4, "day": 20, "sekki": "Kokū (Lluvia de Granos)", "ko": "Las cañas de bambú despuntan", "kigo": "brote de bambú", "tea_element": "té de primera cosecha"},

    # Verano (Rikka a Taisho)
    {"month": 5, "day": 5, "sekki": "Rikka (Inicio del Verano)", "ko": "Las ranas comienzan a cantar", "kigo": "canto de ranas", "tea_element": "hojas de iris"},
    {"month": 5, "day": 21, "sekki": "Shōman (Pequeña Plenitud)", "ko": "La seda de gusano madura", "kigo": "seda nueva", "tea_element": "furoshiki ligero"},
    {"month": 6, "day": 6, "sekki": "Bōshu (Espigas Maduras)", "ko": "Las luciérnagas iluminan la orilla", "kigo": "luz de luciérnaga", "tea_element": "agua de pozo profundo"},
    {"month": 6, "day": 21, "sekki": "Geshi (Solsticio de Verano)", "ko": "El iris florece en el estanque", "kigo": "iris azul", "tea_element": "té frío sobre hielo puro"},
    {"month": 7, "day": 7, "sekki": "Shōsho (Pequeño Calor)", "ko": "El viento cálido sopla suave", "kigo": "viento estival", "tea_element": "abanico sensu de bambú"},
    {"month": 7, "day": 23, "sekki": "Taisho (Gran Calor)", "ko": "La humedad se eleva en la tarde", "kigo": "niebla de calor", "tea_element": "cuenco de cerámica cruda"},

    # Otoño (Risshū a Sōkō)
    {"month": 8, "day": 7, "sekki": "Risshū (Inicio del Otoño)", "ko": "El viento fresco llega de improviso", "kigo": "primer viento fresco", "tea_element": "campanilla eólica"},
    {"month": 8, "day": 23, "sekki": "Shosho (Fin del Calor)", "ko": "El rocío se vuelve blanco sobre la hierba", "kigo": "rocío blanco", "tea_element": "recipiente de laca Urushi"},
    {"month": 9, "day": 8, "sekki": "Hakuro (Rocío Blanco)", "ko": "Las golondrinas parten al sur", "kigo": "despedida de aves", "tea_element": "flores de crisantemo"},
    {"month": 9, "day": 23, "sekki": "Shūbun (Equinoccio de Otoño)", "ko": "Los truenos callan en el horizonte", "kigo": "silencio otoñal", "tea_element": "tetera de hierro kama"},
    {"month": 10, "day": 8, "sekki": "Kanro (Rocío Frío)", "ko": "Los grillos cantan en la puerta", "kigo": "canto nocturno", "tea_element": "incienso de sándalo"},
    {"month": 10, "day": 23, "sekki": "Sōkō (Caída de Escarcha)", "ko": "Las hojas de arce se encienden en rojo", "kigo": "arce rojo (momiji)", "tea_element": "dulce de castaña"},

    # Invierno (Rittō a Daikan)
    {"month": 11, "day": 7, "sekki": "Rittō (Inicio del Invierno)", "ko": "La tierra comienza a congelarse", "kigo": "tierra helada", "tea_element": "fuego de carbón encendido"},
    {"month": 11, "day": 22, "sekki": "Shōsetsu (Pequeña Nieve)", "ko": "El viento del norte deshoja los árboles", "kigo": "ramas desnudas", "tea_element": "té espeso koicha"},
    {"month": 12, "day": 7, "sekki": "Taisetsu (Gran Nieve)", "ko": "Los osos entran en su refugio", "kigo": "silencio de nieve", "tea_element": "paño chakin de lino blanco"},
    {"month": 12, "day": 22, "sekki": "Tōji (Solsticio de Invierno)", "ko": "El sol renace en la tarde más corta", "kigo": "solsticio", "tea_element": "corteza de yuzu aromático"},
    {"month": 1, "day": 5, "sekki": "Shōkan (Pequeño Frío)", "ko": "El agua se convierte en cristal", "kigo": "estanque helado", "tea_element": "cuenco de gres pesado"},
    {"month": 1, "day": 20, "sekki": "Daikan (Gran Frío)", "ko": "El agua alcanza su máxima pureza", "kigo": "hielo transparente", "tea_element": "reserva de té añejo"}
]

def get_current_micro_season(dt: datetime = None) -> Dict[str, Any]:
    """Retorna la micro-estación astronómica tradicional activa."""
    if dt is None:
        dt = datetime.now()

    m = dt.month
    d = dt.day

    # Encontrar la estación más cercana anterior a la fecha actual
    current = SEASONS_DATA[0]
    for season in SEASONS_DATA:
        if (m > season["month"]) or (m == season["month"] and d >= season["day"]):
            current = season
        elif m < season["month"]:
            break

    kigo_val = current.get("kigo", "agua clara")

    return {
        "date": dt.strftime("%Y-%m-%d"),
        "sekki": current["sekki"],
        "micro_season_ko": current["ko"],
        "seasonal_kigo": kigo_val,
        "tea_element": current.get("tea_element", "té verde"),
        "poetic_context": f"Estamos en {current['sekki']}: '{current['ko']}'. El elemento estacional es '{kigo_val}'."
    }
