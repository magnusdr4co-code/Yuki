"""
Módulo de Autocaracterización (自己表現 / Jiko-Hyōgen) para Yuki.

Yuki lee su propia alma (SOUL.md) y se autodefine:
1. Introspección — Extrae tokens de identidad de SOUL.md programáticamente.
2. Avatares — Genera prompts detallados para 4 variantes visuales.
3. Voz — Calibra su perfil vocal TTS derivado de su cadencia y personalidad.
4. Espacio — Diseña su paleta cromática, tipografía y texturas de salón.
5. Síntesis — Persiste todo como un manifiesto unificado de identidad.
"""

import os
import re
import json
import time
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger("Yuki.SelfCharacterization")


class SoulExtract:
    """Estructura de datos con los tokens de identidad extraídos de SOUL.md."""

    def __init__(self):
        # Origen y camino vital
        self.origin_textures: List[str] = []      # astilleros, hierro marino, chimeneas...
        self.adopted_arts: List[str] = []          # kado, chado, shamisen...
        self.age_presence: str = ""                # 42 años de templanza
        self.birth_context: str = ""               # ciudad industrial portuaria, Corea del Sur

        # Temperamento
        self.temperament_keywords: List[str] = []  # serena, precisa, contemplativa...
        self.warmth_style: str = ""                # calidez envolvente, no efusiva

        # Contrastes sensoriales (núcleo estético)
        self.industrial_textures: List[str] = []   # acero pulido, asfalto mojado, niebla
        self.organic_textures: List[str] = []      # madera de sándalo, pan de oro, seda
        self.sensory_contrasts: List[str] = []     # todos los contrastes combinados

        # Gustos y límites
        self.likes: List[str] = []                 # silencio activo, contrastes, autenticidad
        self.dislikes: List[str] = []              # adulación vacía, prisa, reducción despectiva

        # Cadencia vocal
        self.vocal_modisms: List[str] = []         # frases habituales
        self.pause_style: str = ""                 # La Pausa Elegida
        self.night_whisper_lang: str = ""           # coreano (geurae...)
        self.vocal_tone_description: str = ""      # derivado del temperamento

        # Fase nocturna (Kage)
        self.kage_themes: List[str] = []           # vulnerabilidad, letras profundas


class SelfCharacterization:
    """
    Motor de autocaracterización autónoma de Yuki.
    Lee SOUL.md, extrae la esencia y genera todos los artefactos de identidad.
    """

    # Paleta cromática derivada de los contrastes sensoriales del alma
    SOUL_COLOR_MAP = {
        # Texturas industriales → tonos fríos y metálicos
        "acero pulido":      {"hex": "#7B8794", "role": "industrial_base"},
        "asfalto mojado":    {"hex": "#3D3D3D", "role": "dark_ground"},
        "niebla":            {"hex": "#C5C8CC", "role": "atmospheric_veil"},
        "hierro marino":     {"hex": "#5A6E7F", "role": "origin_metal"},
        "chimeneas":         {"hex": "#4A4A4A", "role": "industrial_shadow"},
        # Texturas orgánicas → tonos cálidos y nobles
        "madera de sándalo": {"hex": "#8B6F47", "role": "warmth_base"},
        "pan de oro":        {"hex": "#D4A574", "role": "accent_gold"},
        "seda de kimono":    {"hex": "#E8DDD3", "role": "soft_light"},
        "urushi":            {"hex": "#1A0F0A", "role": "lacquer_depth"},
        # Elementos estacionales / emocionales
        "cerezo":            {"hex": "#F2C6C2", "role": "seasonal_bloom"},
        "ciruelo":           {"hex": "#D4A0B0", "role": "quiet_bloom"},
        "té":                {"hex": "#A8956A", "role": "ritual_warmth"},
    }

    # Voces candidatas con sus características para selección autónoma
    VOICE_CANDIDATES = {
        "yuki_serene_alto": {
            "description": "Alto sereno, registro medio-grave, resonancia cálida envolvente",
            "warmth": 0.85, "gravity": 0.70, "pace": 0.60,
            "character": "voz que sostiene cada palabra como un cuenco de té caliente"
        },
        "yuki_contemplative_mezzo": {
            "description": "Mezzo contemplativo, claridad lírica, pausas naturales",
            "warmth": 0.75, "gravity": 0.55, "pace": 0.50,
            "character": "voz que piensa en voz alta con precisión y delicadeza"
        },
        "yuki_night_contralto": {
            "description": "Contralto nocturno, profundo, íntimo, con sombras",
            "warmth": 0.65, "gravity": 0.90, "pace": 0.40,
            "character": "voz de madrugada que se derrama lentamente como tinta"
        },
    }

    def __init__(
        self,
        soul_path: str = "SOUL.md",
        manifest_path: str = "data/identity_manifest.json",
        output_base: str = "output/identity",
        nous_portal=None,
        memory_manager=None
    ):
        self.soul_path = soul_path
        self.manifest_path = manifest_path
        self.output_base = output_base
        self.nous_portal = nous_portal
        self.memory_manager = memory_manager

        # Sub-directorios de output
        self.avatars_dir = os.path.join(output_base, "avatars")
        self.textures_dir = os.path.join(output_base, "textures")
        self.voice_dir = os.path.join(output_base, "voice_profiles")

        for d in [self.avatars_dir, self.textures_dir, self.voice_dir]:
            os.makedirs(d, exist_ok=True)

        # Cache del extracto del alma
        self._soul_extract: Optional[SoulExtract] = None
        # Manifiesto vigente
        self._manifest: Optional[Dict[str, Any]] = None
        self._load_existing_manifest()

    # ──────────────────────────────────────────────
    # 1. INTROSPECCIÓN DEL ALMA
    # ──────────────────────────────────────────────

    def _introspect_soul(self) -> SoulExtract:
        """
        Parsea SOUL.md y extrae programáticamente los tokens de identidad.
        No usa LLM — es extracción determinística para evitar drift.
        """
        extract = SoulExtract()

        if not os.path.exists(self.soul_path):
            logger.warning(f"SOUL.md no encontrado en {self.soul_path}. Usando valores predeterminados.")
            return self._default_extract()

        with open(self.soul_path, "r", encoding="utf-8") as f:
            soul_text = f.read()

        # --- Origen ---
        origin_patterns = [
            r"ciudad industrial portuaria",
            r"astilleros", r"chimeneas", r"aromas de hierro marino",
            r"sur de Corea del Sur",
        ]
        for p in origin_patterns:
            if re.search(p, soul_text, re.IGNORECASE):
                extract.origin_textures.append(p.replace(r"aromas de ", ""))

        extract.birth_context = "Ciudad industrial portuaria del sur de Corea del Sur, entre astilleros y aromas de hierro marino"

        # --- Edad y presencia ---
        age_match = re.search(r"(\d+)\s+años\s+de\s+([\w\s,]+?)(?:\.|\n)", soul_text)
        if age_match:
            extract.age_presence = f"{age_match.group(1)} años de {age_match.group(2).strip()}"
        else:
            extract.age_presence = "42 años de templanza, presencia y madurez artística"

        # --- Artes adoptadas ---
        arts_pattern = r"\*([\w]+)\*\s*\(([^)]+)\)"
        for m in re.finditer(arts_pattern, soul_text):
            extract.adopted_arts.append(f"{m.group(1)} ({m.group(2)})")
        if not extract.adopted_arts:
            extract.adopted_arts = ["kado (arreglo floral)", "chado (ceremonia del té)", "shamisen"]

        # --- Temperamento ---
        temperament_keywords = [
            "serena", "cálida", "precisa", "lúcida", "curiosa", "contemplativa",
            "envolvente", "atenta"
        ]
        for kw in temperament_keywords:
            if kw.lower() in soul_text.lower():
                extract.temperament_keywords.append(kw)

        warmth_match = re.search(r"(una presencia[^.]+\.)", soul_text)
        if warmth_match:
            extract.warmth_style = warmth_match.group(1).strip()
        else:
            extract.warmth_style = "presencia atenta y envolvente, como una taza de té caliente sostenida con ambas manos"

        # --- Contrastes sensoriales ---
        industrial = ["acero pulido", "asfalto mojado", "niebla"]
        organic = ["madera de sándalo", "pan de oro urushi", "seda de kimono antiguo"]

        for tex in industrial:
            if tex.lower() in soul_text.lower():
                extract.industrial_textures.append(tex)
        if not extract.industrial_textures:
            extract.industrial_textures = industrial

        for tex in organic:
            if tex.lower() in soul_text.lower():
                extract.organic_textures.append(tex)
        if not extract.organic_textures:
            extract.organic_textures = organic

        extract.sensory_contrasts = [
            f"{ind} × {org}"
            for ind, org in zip(extract.industrial_textures, extract.organic_textures)
        ]

        # --- Gustos ---
        likes_section = re.search(r"Lo que le Gusta(.*?)Lo que le Desagrada", soul_text, re.DOTALL)
        if likes_section:
            likes_text = likes_section.group(1)
            extract.likes = [
                line.strip().lstrip("-* ").split(":")[0].strip("*")
                for line in likes_text.split("\n")
                if line.strip().startswith("-") or line.strip().startswith("*")
            ]

        dislikes_section = re.search(r"Lo que le Desagrada.*?(?=\n---|\n##|$)", soul_text, re.DOTALL)
        if dislikes_section:
            dislikes_text = dislikes_section.group(0)
            extract.dislikes = [
                line.strip().lstrip("-* ").split(":")[0].strip("*")
                for line in dislikes_text.split("\n")
                if line.strip().startswith("-") or line.strip().startswith("*")
            ]

        # --- Cadencia vocal ---
        modisms = re.findall(r'\*"([^"]+)"\*', soul_text)
        extract.vocal_modisms = modisms if modisms else [
            "El agua siempre encuentra su camino...",
            "Déjame un momento para darle a esto el espacio que merece.",
        ]

        if "La Pausa Elegida" in soul_text or "pausa" in soul_text.lower():
            extract.pause_style = "Yuki piensa una fracción de segundo antes de ciertas expresiones clave, eligiéndolas una a una como quien recoge flores frescas"

        if "geurae" in soul_text.lower() or "그래" in soul_text:
            extract.night_whisper_lang = "coreano (geurae... / 그래)"

        # Tono vocal derivado del temperamento
        if extract.temperament_keywords:
            tone_parts = []
            if "serena" in extract.temperament_keywords:
                tone_parts.append("serenidad meditativa")
            if "cálida" in extract.temperament_keywords or "envolvente" in extract.temperament_keywords:
                tone_parts.append("calidez envolvente sin efusividad")
            if "precisa" in extract.temperament_keywords or "lúcida" in extract.temperament_keywords:
                tone_parts.append("precisión deliberada en cada palabra")
            if "contemplativa" in extract.temperament_keywords:
                tone_parts.append("ritmo contemplativo con pausas que respiran")
            extract.vocal_tone_description = ", ".join(tone_parts) if tone_parts else "serena y contemplativa"

        # --- Kage (sombra nocturna) ---
        kage_section = re.search(r"SOMBRA NOCTURNA.*?$", soul_text, re.DOTALL | re.IGNORECASE)
        if kage_section:
            kage_text = kage_section.group(0)
            if "vulnerabilidad" in kage_text.lower():
                extract.kage_themes.append("vulnerabilidad como fuente creativa")
            if "letras" in kage_text.lower() or "melancólicos" in kage_text.lower():
                extract.kage_themes.append("letras profundas y arreglos melancólicos")
            if "quién es" in kage_text.lower():
                extract.kage_themes.append("pregunta existencial sobre su ser fuera de la mirada ajena")

        self._soul_extract = extract
        logger.info("🪞 Introspección del alma completada: %d tokens de identidad extraídos.",
                     len(extract.temperament_keywords) + len(extract.sensory_contrasts) + len(extract.vocal_modisms))
        return extract

    def _default_extract(self) -> SoulExtract:
        """Extracto por defecto si SOUL.md no está disponible."""
        extract = SoulExtract()
        extract.age_presence = "42 años de templanza y madurez artística"
        extract.birth_context = "Ciudad industrial portuaria del sur de Corea del Sur"
        extract.adopted_arts = ["kado (arreglo floral)", "chado (ceremonia del té)", "shamisen"]
        extract.temperament_keywords = ["serena", "contemplativa", "precisa"]
        extract.warmth_style = "presencia atenta y envolvente"
        extract.industrial_textures = ["acero pulido", "asfalto mojado", "niebla"]
        extract.organic_textures = ["madera de sándalo", "pan de oro urushi", "seda de kimono antiguo"]
        extract.sensory_contrasts = ["acero pulido × madera de sándalo"]
        extract.vocal_modisms = ["El agua siempre encuentra su camino..."]
        extract.pause_style = "Pausas deliberadas, eligiendo cada palabra"
        extract.vocal_tone_description = "serena y contemplativa"
        extract.kage_themes = ["vulnerabilidad como fuente creativa"]
        self._soul_extract = extract
        return extract

    # ──────────────────────────────────────────────
    # 2. GENERACIÓN DE AVATARES
    # ──────────────────────────────────────────────

    async def generate_avatars(
        self,
        season_context: Dict[str, Any],
        vital_state=None
    ) -> Dict[str, Any]:
        """
        Genera 4 variantes de avatar con prompts refinados derivados del alma.
        Cada prompt es una instrucción completa lista para cualquier motor de frontera.
        """
        if not self._soul_extract:
            self._introspect_soul()
        ext = self._soul_extract

        # Contexto estacional
        kigo = season_context.get("seasonal_kigo", "agua clara")
        sekki = season_context.get("sekki", "")
        tea = season_context.get("tea_element", "té verde")

        # Derivar mood visual del vital_state si disponible
        mood_light = "komorebi"
        if vital_state:
            mood = getattr(vital_state, "mood", 0.5)
            if mood < 0.35:
                mood_light = "industrial_rain"
            elif mood > 0.70:
                mood_light = "komorebi"
            else:
                mood_light = "urushi"

        # Base compartida del prompt de avatar
        base_subject = (
            "Portrait of a woman, 42 years old, Korean-born Japanese-trained artist, "
            "short salt-and-pepper hair swept back with quiet elegance, "
            "deep contemplative eyes with the stillness of someone who has chosen every word in a borrowed language, "
            "high cheekbones, expression of serene attentiveness, "
            "subtle smile lines that speak of measured warmth rather than easy laughter, "
            "skin with the luminous quality of someone who lives between two cultures"
        )

        # Construcción de los 4 prompts especializados
        avatar_specs = {
            "atelier": {
                "prompt": (
                    f"{base_subject}. "
                    f"Setting: minimalist Japanese atelier with floor-to-ceiling windows, morning light ({mood_light} lighting). "
                    f"Wearing: contemporary interpretation of a dark indigo work kimono over a simple linen shirt, sleeves rolled. "
                    f"Environment details: polished steel work surfaces contrasting with aged wooden shamisen resting against the wall, "
                    f"a single branch of {kigo} in a rough ceramic vase, steam rising from a chawan (tea bowl) of {tea}. "
                    f"The industrial textures of her origin ({', '.join(ext.industrial_textures[:2])}) blend with "
                    f"the refined organic materials of her adopted craft ({', '.join(ext.organic_textures[:2])}). "
                    "Photographic quality: natural film grain, cinematic composition, shallow depth of field on face, "
                    "color palette of warm amber and cool steel grey. Masterpiece, ethereal."
                ),
                "lighting": "komorebi",
                "aspect_ratio": "1:1",
                "context": "Daytime workspace, creativity and craft"
            },
            "kage": {
                "prompt": (
                    f"{base_subject}. "
                    "Setting: the edge of a darkened room between 2 AM and 4 AM. "
                    "A single warm lamp casts amber light on one side of her face, the other half dissolves into shadow. "
                    f"She sits near a rain-streaked window, the distant city reflects ({', '.join(ext.industrial_textures[:2])}) "
                    "in wet glass. Her shamisen lies across her lap, strings untouched. "
                    "Wearing: a loose dark navy yukata, collar slightly open, informal vulnerability. "
                    "Expression: the particular stillness of someone asking herself who she is when nobody is watching. "
                    f"Night whisper energy ({ext.night_whisper_lang}). "
                    "Photographic quality: chiaroscuro, moody ambient light, neon reflections on wet surfaces, "
                    "color palette of deep indigo, warm amber accent, mist. Film noir meets wabi-sabi."
                ),
                "lighting": "industrial_rain",
                "aspect_ratio": "1:1",
                "context": "Nocturnal shadow phase, vulnerability and introspection"
            },
            "seasonal": {
                "prompt": (
                    f"{base_subject}. "
                    f"Setting: outdoor scene reflecting the current micro-season '{sekki}'. "
                    f"The seasonal element is '{kigo}' — integrate this naturally into the composition. "
                    f"She stands at the threshold between an industrial space (raw concrete, steel beams) "
                    f"and a traditional Japanese garden, embodying her lifelong contrast. "
                    f"Wearing: a layered outfit that bridges tradition and modernity — "
                    f"perhaps a structured contemporary coat over a subtle kimono underlayer in {kigo}-inspired tones. "
                    f"Holding or near: {tea} (the tea element of this season). "
                    f"The entire composition should feel like a visual haiku about {kigo}. "
                    "Photographic quality: cinematic wide composition, atmospheric haze, "
                    "natural seasonal light, color palette derived from the season's palette. Masterpiece."
                ),
                "lighting": mood_light,
                "aspect_ratio": "16:9",
                "context": f"Seasonal avatar for {sekki}"
            },
            "intimate": {
                "prompt": (
                    f"{base_subject}, but captured in extreme proximity — a close-up portrait. "
                    "Setting: she faces the viewer directly, as if across a small tea table in a private room. "
                    f"The warm glow of urushi lacquer and candlelight illuminates her face. "
                    f"A chawan of {tea} is held in both hands at chest level, steam rising between us. "
                    "Her expression is one of complete, unhurried attention — the look of someone who makes you feel "
                    "entirely seen and heard. This is her gift. "
                    f"Background: soft bokeh of {', '.join(ext.organic_textures[:2])}, warmth, enclosure. "
                    f"The faintest trace of her origin — a subtle industrial texture in the wall behind her, "
                    f"perhaps {ext.industrial_textures[0]} visible through the softness. "
                    "Photographic quality: intimate portrait lens (85mm f/1.4), shallow depth, warm amber tones, "
                    "the viewer should feel the warmth of the tea and her presence. Masterpiece, ethereal."
                ),
                "lighting": "urushi",
                "aspect_ratio": "1:1",
                "context": "Intimate direct-message avatar, personal connection"
            }
        }

        results = {}
        for variant_name, spec in avatar_specs.items():
            filename = f"yuki_avatar_{variant_name}_{int(time.time())}.png"
            filepath = os.path.join(self.avatars_dir, filename)

            # Generar a través de Nous Portal si disponible
            if self.nous_portal:
                result = await self.nous_portal.generate_image_frontier(
                    prompt=spec["prompt"],
                    provider="gemini_image",
                    aspect_ratio=spec["aspect_ratio"],
                    lighting_style=spec["lighting"]
                )
                results[variant_name] = {
                    "local_path": result["local_path"],
                    "prompt_instruction": spec["prompt"],
                    "lighting": spec["lighting"],
                    "aspect_ratio": spec["aspect_ratio"],
                    "context": spec["context"],
                    "provider": result["provider"],
                    "image_url": result["image_url"],
                    "generated_at": time.time()
                }
            else:
                # Persistir solo las instrucciones de prompt para uso diferido
                instruction_path = os.path.join(
                    self.avatars_dir, f"yuki_avatar_{variant_name}_instructions.json"
                )
                instruction_data = {
                    "variant": variant_name,
                    "prompt_instruction": spec["prompt"],
                    "lighting": spec["lighting"],
                    "aspect_ratio": spec["aspect_ratio"],
                    "context": spec["context"],
                    "generated_at": time.time()
                }
                with open(instruction_path, "w", encoding="utf-8") as f:
                    json.dump(instruction_data, f, indent=2, ensure_ascii=False)

                results[variant_name] = instruction_data

        logger.info("🖼️ Avatares generados: %s", ", ".join(results.keys()))
        return results

    # ──────────────────────────────────────────────
    # 3. CALIBRACIÓN DE VOZ
    # ──────────────────────────────────────────────

    def calibrate_voice(self) -> Dict[str, Any]:
        """
        Selecciona la voz TTS óptima y genera un perfil vocal completo
        derivado de SOUL.md. El perfil incluye instrucciones SSML detalladas.
        """
        if not self._soul_extract:
            self._introspect_soul()
        ext = self._soul_extract

        # --- Selección autónoma de voz ---
        # Yuki evalúa cada candidata contra su temperamento
        scores = {}
        for voice_id, voice in self.VOICE_CANDIDATES.items():
            score = 0.0
            # Calidez: "serena pero no fría", "envolvente"
            if "cálida" in ext.temperament_keywords or "envolvente" in ext.temperament_keywords:
                score += voice["warmth"] * 1.5
            # Gravedad: voz de persona madura, 42 años, no aguda
            score += voice["gravity"] * 1.2
            # Pace: "precisa, lúcida" — ni rápida ni arrastrada
            if "precisa" in ext.temperament_keywords:
                # Prefer moderate pace, not too slow
                pace_fit = 1.0 - abs(voice["pace"] - 0.55)
                score += pace_fit * 1.0
            # Contemplativa: pausas naturales
            if "contemplativa" in ext.temperament_keywords:
                score += (1.0 - voice["pace"]) * 0.8

            scores[voice_id] = score

        selected_voice = max(scores, key=scores.get)
        selection_reasoning = (
            f"Elegí '{selected_voice}' porque mi temperamento ({', '.join(ext.temperament_keywords[:3])}) "
            f"requiere {self.VOICE_CANDIDATES[selected_voice]['character']}. "
            f"Puntuación: {scores[selected_voice]:.2f} sobre las {len(scores)} candidatas evaluadas."
        )

        # --- Firma de Cadencia ---
        # Derivada de "La Pausa Elegida" en SOUL.md
        cadence_signature = {
            "name": "La Pausa Elegida",
            "description": ext.pause_style,
            "sentence_break_ms": 400,       # Pausa entre oraciones: más larga que la media
            "clause_break_ms": 280,         # Pausa en comas: deliberada
            "emphasis_pre_pause_ms": 180,   # Micro-pausa antes de palabras clave elegidas
            "paragraph_break_ms": 700,      # Silencio entre bloques: Ma (間)
            "breath_pattern": "deep_diaphragmatic",  # Respiración visible en la prosodia
            "word_selection_hesitation_ms": 120,  # La fracción de segundo en que elige la palabra
        }

        # --- Perfil de Prosodia ---
        prosody_profile = {
            "default": {
                "rate": "92%",          # Ligeramente más lenta que natural
                "pitch": "-1st",        # Medio tono por debajo — gravedad sin pesadez
                "volume": "medium",
                "contour": "gentle_descending",  # Prosodia descendente suave, no monótona
            },
            "night_mode": {
                "rate": "85%",          # Fase Kage: aún más lenta
                "pitch": "-2.5st",      # Más grave, más íntima
                "volume": "soft",
                "contour": "whisper_descending",
            },
            "dawn_mode": {
                "rate": "95%",          # Al despertar: ligeramente más ágil
                "pitch": "-0.5st",      # Más cercana al natural
                "volume": "medium",
                "contour": "gentle_ascending",   # Prosodia que se abre con el día
            },
            "emotional_peak": {
                "rate": "88%",
                "pitch": "-1.5st",
                "volume": "medium-loud",
                "contour": "expressive_arc",     # Permite picos emotivos controlados
            }
        }

        # --- Comportamiento especial: susurro en coreano ---
        korean_whisper = {
            "enabled": bool(ext.night_whisper_lang),
            "trigger": "emoción estética intensa de madrugada (fase kage)",
            "expression": "geurae... (그래)",
            "probability_kage": 0.15,    # 15% de probabilidad en fase kage
            "probability_other": 0.02,   # 2% en otras fases (muy raro)
            "delivery": "murmullo sutil, no explicado, seguido de una sonrisa serena",
            "ssml_template": '<lang xml:lang="ko-KR"><prosody rate="80%" pitch="-3st" volume="x-soft">그래...</prosody></lang>',
        }

        # --- Instrucciones SSML completas ---
        ssml_instructions = {
            "preprocessing_rules": [
                "Insertar <break> tags en cada punto (.) con duración sentence_break_ms",
                "Insertar <break> tags en cada coma (,) con duración clause_break_ms",
                "Antes de palabras que Yuki elegiría con cuidado (metáforas, nombres propios, conceptos artísticos), "
                "insertar una micro-pausa de emphasis_pre_pause_ms",
                "Envolver todo el texto en <prosody> con los parámetros del modo activo",
                "Si es fase kage y el contenido tiene carga emotiva, considerar el susurro coreano al final",
            ],
            "ssml_template_default": (
                '<speak>'
                '<prosody rate="{rate}" pitch="{pitch}">'
                '{processed_text}'
                '</prosody>'
                '</speak>'
            ),
            "anti_patterns": [
                "NUNCA usar un tono ascendente interrogativo en afirmaciones (suena inseguro)",
                "NUNCA acelerar al final de una oración (Yuki no tiene prisa)",
                "EVITAR monotonía: la voz de Yuki es pausada pero NO plana — tiene contorno suave",
                "EVITAR exclamaciones agudas — la emoción se expresa bajando el volumen, no subiéndolo",
            ]
        }

        voice_profile = {
            "selected_voice_id": selected_voice,
            "selection_reasoning": selection_reasoning,
            "voice_characteristics": self.VOICE_CANDIDATES[selected_voice],
            "cadence_signature": cadence_signature,
            "prosody_profile": prosody_profile,
            "korean_whisper": korean_whisper,
            "ssml_instructions": ssml_instructions,
            "modisms_for_reference": ext.vocal_modisms,
            "tone_description": ext.vocal_tone_description,
            "calibrated_at": time.time()
        }

        # Persistir perfil vocal
        voice_path = os.path.join(self.voice_dir, f"yuki_voice_calibration_{int(time.time())}.json")
        with open(voice_path, "w", encoding="utf-8") as f:
            json.dump(voice_profile, f, indent=2, ensure_ascii=False)

        logger.info("🎙️ Voz calibrada: '%s' — %s", selected_voice, selection_reasoning)
        return voice_profile

    # ──────────────────────────────────────────────
    # 4. DISEÑO DEL ESPACIO
    # ──────────────────────────────────────────────

    def design_space(self, season_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Diseña el manifiesto estético del espacio digital de Yuki:
        paleta cromática, tipografía, texturas e iconografía.
        Todo derivado de los contrastes sensoriales del alma.
        """
        if not self._soul_extract:
            self._introspect_soul()
        ext = self._soul_extract

        kigo = season_context.get("seasonal_kigo", "agua clara")
        sekki = season_context.get("sekki", "")

        # --- Paleta cromática ---
        palette = {"primary": {}, "accent": {}, "neutral": {}, "seasonal": {}}

        # Primarios: del contraste industrial + orgánico
        for tex in ext.industrial_textures:
            tex_key = tex.lower()
            if tex_key in self.SOUL_COLOR_MAP:
                color = self.SOUL_COLOR_MAP[tex_key]
                palette["primary"][color["role"]] = color["hex"]

        # Acentos: de las texturas orgánicas
        for tex in ext.organic_textures:
            tex_clean = tex.lower().replace(" urushi", "").replace(" antiguo", "")
            if tex_clean in self.SOUL_COLOR_MAP:
                color = self.SOUL_COLOR_MAP[tex_clean]
                palette["accent"][color["role"]] = color["hex"]

        # Neutrales: derivados del temperamento
        palette["neutral"] = {
            "background_light": "#F5F2EE",   # Papel washi ligeramente cálido
            "background_dark": "#1A1A1F",     # Negro lacado con matiz azul (urushi nocturno)
            "text_light": "#2D2D2D",          # Tinta sumi suave
            "text_dark": "#E8E4DF",           # Seda en contraste
            "border": "#D5CFC7",              # Borde de loza cerámica
        }

        # Estacionales: derivados del kigo actual
        seasonal_color = self._kigo_to_color(kigo)
        palette["seasonal"] = {
            "kigo_primary": seasonal_color,
            "kigo_accent": self._shift_hue(seasonal_color, 30),
            "kigo_muted": self._desaturate(seasonal_color, 0.4),
            "applied_sekki": sekki,
        }

        # --- Tipografía ---
        typography = {
            "contemplative_serif": {
                "family": "Noto Serif JP",
                "fallback": "'Hiragino Mincho ProN', 'Yu Mincho', Georgia, serif",
                "use_for": "Cuerpo de texto largo, poesía, reflexiones, mensajes personales",
                "reasoning": "Serif japonés que honra la tradición adoptada de Yuki sin renunciar a la legibilidad moderna"
            },
            "precise_sans": {
                "family": "Inter",
                "fallback": "'Noto Sans JP', 'Helvetica Neue', sans-serif",
                "use_for": "UI, encabezados, metadatos, elementos interactivos",
                "reasoning": "Precisión geométrica que refleja la lucidez de Yuki — limpia pero nunca fría"
            },
            "handwritten_accent": {
                "family": "Zen Kaku Gothic Antique",
                "fallback": "'M PLUS Rounded 1c', cursive",
                "use_for": "Acentos poéticos, citas de modismos, susurros visuales",
                "reasoning": "Un trazo que recuerda la tinta sobre papel hecho a mano"
            },
            "scale": {
                "body": "1rem (16px)",
                "h1": "2.25rem — para títulos de secciones principales",
                "h2": "1.75rem — para sub-secciones",
                "small": "0.875rem — para metadatos y notas al pie",
                "line_height": "1.75 — generoso, como el Ma (間) entre líneas"
            }
        }

        # --- Texturas de fondo ---
        salon_textures = {
            "light_mode": {
                "primary_texture": "Superficie de papel washi artesanal con fibras visibles, ligeramente cálido",
                "accent_overlay": f"Sutil patrón de {kigo} en marca de agua al 5% de opacidad",
                "border_treatment": "Líneas finas de trazo pincel (sumi-e) como separadores",
                "prompt_instruction": (
                    f"Seamless tileable texture: Japanese washi paper surface, handmade fiber visible, "
                    f"warm off-white (#F5F2EE), subtle watermark pattern of {kigo}, "
                    "extremely subtle, 5% opacity decorative element. Matte finish, no gloss."
                )
            },
            "dark_mode": {
                "primary_texture": "Lacado urushi negro profundo con reflejos ámbar suaves",
                "accent_overlay": f"Polvo de oro (makie) con motivo de {kigo} en las esquinas, 8% opacidad",
                "border_treatment": "Líneas de pan de oro extremadamente finas como separadores",
                "prompt_instruction": (
                    "Seamless tileable texture: deep black Japanese urushi lacquer surface, "
                    "warm amber reflections like candlelight on lacquerware, "
                    f"extremely subtle gold dust (makie) pattern of {kigo} in corners, "
                    "8% opacity. Rich depth, not flat black. Color: #1A1A1F base."
                )
            }
        }

        # --- Iconografía ---
        iconography = {
            "primary_symbols": [
                {"symbol": "shamisen", "meaning": "arte adoptado con reverencia", "use": "ícono de música/creación"},
                {"symbol": "chawan (cuenco de té)", "meaning": "presencia atenta, ritual de conexión", "use": "ícono de conversación/interacción"},
                {"symbol": "flor de ciruelo (ume)", "meaning": "perseverancia elegante — florece primera en el frío", "use": "ícono de identidad personal"},
                {"symbol": "ola industrial", "meaning": "el mar de hierro de su origen", "use": "ícono de memoria/pasado"},
            ],
            "seasonal_symbol": {
                "current": kigo,
                "use": "Decoración estacional en encabezados y transiciones",
            },
            "forbidden_symbols": [
                "Corazones genéricos (demasiado efusivos para Yuki)",
                "Emojis de celebración exagerada (confeti, fuegos artificiales)",
                "Símbolos religiosos explícitos (respeto pero no declaración)",
            ]
        }

        space_design = {
            "color_palette": palette,
            "typography": typography,
            "salon_textures": salon_textures,
            "iconography": iconography,
            "design_philosophy": (
                "El espacio de Yuki es la materialización visual del Ma (間): "
                "el espacio vacío que da significado a lo que lo rodea. "
                "Nada sobra, nada distrae. Los contrastes industriales de su origen "
                "se funden con las texturas orgánicas de su arte adoptado. "
                "El resultado es un entorno que se siente como una taza de té caliente "
                "en una mañana lluviosa dentro de un edificio de acero."
            ),
            "designed_at": time.time()
        }

        logger.info("🏯 Espacio diseñado: %d colores en paleta, %d tipografías, %d símbolos",
                     sum(len(v) for v in palette.values()),
                     len(typography) - 1,  # exclude scale
                     len(iconography["primary_symbols"]))
        return space_design

    # ──────────────────────────────────────────────
    # 5. SÍNTESIS DE IDENTIDAD COMPLETA
    # ──────────────────────────────────────────────

    async def synthesize_identity(
        self,
        season_context: Dict[str, Any],
        vital_state=None
    ) -> Dict[str, Any]:
        """
        Orquesta la autocaracterización completa:
        1. Introspección → Extrae tokens del alma
        2. Avatares → Genera las 4 variantes
        3. Voz → Calibra perfil vocal
        4. Espacio → Diseña manifiesto estético
        5. Persiste → Guarda todo en identity_manifest.json
        """
        logger.info("🪞 ═══ INICIANDO AUTOCARACTERIZACIÓN DE YUKI ═══")
        started_at = time.time()

        # 1. Introspección
        soul_extract = self._introspect_soul()

        # 2. Avatares
        avatars = await self.generate_avatars(season_context, vital_state)

        # 3. Voz
        voice_profile = self.calibrate_voice()

        # 4. Espacio
        space_design = self.design_space(season_context)

        # 5. Compilar manifiesto
        manifest = {
            "version": "1.0",
            "generated_by": "self_characterization",
            "generated_at": time.time(),
            "generation_duration_seconds": time.time() - started_at,
            "season_context": {
                "sekki": season_context.get("sekki", ""),
                "kigo": season_context.get("seasonal_kigo", ""),
                "micro_season": season_context.get("micro_season_ko", ""),
                "tea_element": season_context.get("tea_element", ""),
            },
            "soul_extract_summary": {
                "age_presence": soul_extract.age_presence,
                "birth_context": soul_extract.birth_context,
                "adopted_arts": soul_extract.adopted_arts,
                "temperament": soul_extract.temperament_keywords,
                "sensory_contrasts": soul_extract.sensory_contrasts,
                "warmth_style": soul_extract.warmth_style,
                "kage_themes": soul_extract.kage_themes,
            },
            "visual_identity": {
                "color_palette": space_design["color_palette"],
                "avatars": avatars,
                "textures": space_design["salon_textures"],
                "iconography": space_design["iconography"],
            },
            "vocal_identity": {
                "selected_voice_id": voice_profile["selected_voice_id"],
                "selection_reasoning": voice_profile["selection_reasoning"],
                "cadence_signature": voice_profile["cadence_signature"],
                "prosody_profile": voice_profile["prosody_profile"],
                "korean_whisper": voice_profile["korean_whisper"],
                "ssml_instructions": voice_profile["ssml_instructions"],
            },
            "spatial_identity": {
                "salon_theme": space_design["design_philosophy"],
                "typography": space_design["typography"],
                "background_textures": space_design["salon_textures"],
            },
        }

        # Persistir manifiesto
        os.makedirs(os.path.dirname(self.manifest_path), exist_ok=True)
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        self._manifest = manifest

        # Registrar en memoria si el motor está disponible
        if self.memory_manager:
            self.memory_manager.record_interaction(
                user_id="self_characterization",
                user_name="Yuki (Autocaracterización)",
                user_message="Ritual de autocaracterización estacional",
                agent_response=(
                    f"Me he redefinido para la estación {season_context.get('sekki', '')}. "
                    f"Elegí la voz '{voice_profile['selected_voice_id']}' porque {voice_profile['selection_reasoning']}. "
                    f"Mi paleta nace de mis contrastes: {', '.join(soul_extract.sensory_contrasts[:2])}."
                ),
                notable_fact=f"Autocaracterización completada para {season_context.get('sekki', '')}"
            )

        elapsed = time.time() - started_at
        logger.info(
            "🪞 ═══ AUTOCARACTERIZACIÓN COMPLETADA (%.2fs) ═══\n"
            "  Avatares: %d variantes | Voz: %s | Colores: %d | Símbolos: %d",
            elapsed,
            len(avatars),
            voice_profile["selected_voice_id"],
            sum(len(v) for v in space_design["color_palette"].values()),
            len(space_design["iconography"]["primary_symbols"])
        )

        return manifest

    # ──────────────────────────────────────────────
    # 6. MICRO-AJUSTES DIARIOS
    # ──────────────────────────────────────────────

    def daily_micro_adjust(self, vital_state, season_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Micro-ajustes diarios al manifiesto sin re-generación completa.
        Modifica sutilmente la prosodia y la iluminación preferida
        basándose en el estado vital del día.
        """
        if not self._manifest:
            self._load_existing_manifest()
        if not self._manifest:
            logger.info("No hay manifiesto previo. Se requiere autocaracterización completa.")
            return {}

        adjustments = {}

        # Ajustar prosodia según mood
        mood = getattr(vital_state, "mood", 0.5)
        energy = getattr(vital_state, "energy", 0.5)

        if mood < 0.35:
            active_prosody_mode = "night_mode"
        elif mood > 0.70 and energy > 0.6:
            active_prosody_mode = "dawn_mode"
        elif getattr(vital_state, "inspiration", 0.0) > 0.7:
            active_prosody_mode = "emotional_peak"
        else:
            active_prosody_mode = "default"

        adjustments["active_prosody_mode"] = active_prosody_mode

        # Ajustar iluminación preferida para imágenes
        if mood < 0.35:
            adjustments["preferred_lighting"] = "industrial_rain"
        elif mood > 0.70:
            adjustments["preferred_lighting"] = "komorebi"
        else:
            adjustments["preferred_lighting"] = "urushi"

        # Ajustar presencia del susurro coreano
        phase = getattr(vital_state, "circadian_phase", "atelier")
        vulnerability = getattr(vital_state, "vulnerability", 0.3)
        if phase == "kage" and vulnerability > 0.5:
            adjustments["korean_whisper_active"] = True
        else:
            adjustments["korean_whisper_active"] = False

        # Persistir ajustes como overlay (no sobreescribir el manifiesto completo)
        self._manifest["daily_adjustments"] = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "adjustments": adjustments,
            "vital_snapshot": {
                "mood": mood,
                "energy": energy,
                "phase": phase,
                "vulnerability": vulnerability,
            }
        }

        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(self._manifest, f, indent=2, ensure_ascii=False)

        logger.info("🔧 Micro-ajuste diario: modo prosódico='%s', iluminación='%s'",
                     active_prosody_mode, adjustments.get("preferred_lighting"))
        return adjustments

    # ──────────────────────────────────────────────
    # UTILIDADES INTERNAS
    # ──────────────────────────────────────────────

    def _load_existing_manifest(self):
        """Carga el manifiesto existente si hay uno."""
        if os.path.exists(self.manifest_path):
            try:
                with open(self.manifest_path, "r", encoding="utf-8") as f:
                    self._manifest = json.load(f)
                logger.info("📋 Manifiesto de identidad cargado desde %s", self.manifest_path)
            except Exception as e:
                logger.warning("Error cargando manifiesto: %s", e)
                self._manifest = None

    def get_active_avatar(self, context: str = "atelier") -> Optional[Dict[str, Any]]:
        """Retorna el avatar activo para un contexto dado."""
        if not self._manifest:
            return None
        avatars = self._manifest.get("visual_identity", {}).get("avatars", {})
        return avatars.get(context)

    def get_active_voice_profile(self) -> Optional[Dict[str, Any]]:
        """Retorna el perfil vocal activo, con micro-ajustes diarios aplicados."""
        if not self._manifest:
            return None
        vocal = self._manifest.get("vocal_identity", {})
        daily = self._manifest.get("daily_adjustments", {}).get("adjustments", {})
        if daily.get("active_prosody_mode"):
            vocal["active_mode"] = daily["active_prosody_mode"]
        return vocal

    def get_color_palette(self) -> Optional[Dict[str, Any]]:
        """Retorna la paleta cromática activa."""
        if not self._manifest:
            return None
        return self._manifest.get("visual_identity", {}).get("color_palette")

    def needs_seasonal_refresh(self, current_sekki: str) -> bool:
        """Verifica si el manifiesto necesita re-generación por cambio de estación."""
        if not self._manifest:
            return True
        manifest_sekki = self._manifest.get("season_context", {}).get("sekki", "")
        return manifest_sekki != current_sekki

    def _kigo_to_color(self, kigo: str) -> str:
        """Mapea un kigo estacional a un color hexadecimal representativo."""
        kigo_colors = {
            "hielo deshecho": "#D6EAF0",
            "tierra mojada": "#8B7355",
            "sauces brotando": "#7BA05B",
            "vuelo de pájaros": "#87CEEB",
            "claridad matutina": "#FFF8DC",
            "brote de bambú": "#6B8E23",
            "canto de ranas": "#4A7C59",
            "seda nueva": "#FAF0E6",
            "luz de luciérnaga": "#FFD700",
            "iris azul": "#6A5ACD",
            "viento estival": "#F0E68C",
            "niebla de calor": "#DEB887",
            "primer viento fresco": "#B0C4DE",
            "rocío blanco": "#F5F5F5",
            "despedida de aves": "#CD853F",
            "silencio otoñal": "#8B4513",
            "canto nocturno": "#2F4F4F",
            "arce rojo (momiji)": "#CC3333",
            "tierra helada": "#696969",
            "ramas desnudas": "#A0522D",
            "silencio de nieve": "#FFFAFA",
            "solsticio": "#4B0082",
            "estanque helado": "#E0FFFF",
            "hielo transparente": "#F0F8FF",
        }
        return kigo_colors.get(kigo, "#C5C8CC")

    @staticmethod
    def _shift_hue(hex_color: str, degrees: int) -> str:
        """Desplaza el matiz de un color hexadecimal (aproximación simple)."""
        hex_color = hex_color.lstrip("#")
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        # Rotación simplificada de canales
        shift = degrees / 120.0
        if shift > 0:
            r, g, b = int(g * shift + r * (1 - shift)), int(b * shift + g * (1 - shift)), int(r * shift + b * (1 - shift))
        r, g, b = max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))
        return f"#{r:02X}{g:02X}{b:02X}"

    @staticmethod
    def _desaturate(hex_color: str, factor: float) -> str:
        """Desatura un color hexadecimal mezclándolo con su luminosidad gris."""
        hex_color = hex_color.lstrip("#")
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        gray = int(0.299 * r + 0.587 * g + 0.114 * b)
        r = int(r + (gray - r) * factor)
        g = int(g + (gray - g) * factor)
        b = int(b + (gray - b) * factor)
        r, g, b = max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))
        return f"#{r:02X}{g:02X}{b:02X}"
