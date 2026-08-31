---
name: autocaracterizarse
description: Yuki se mira en el espejo del alma (SOUL.md) y redefine autónomamente su identidad visual (avatares), vocal (perfil TTS) y espacial (paleta cromática, tipografía, texturas). Genera un manifiesto completo de identidad en data/identity_manifest.json y persiste los assets en output/identity/.
parameters:
  type: object
  properties:
    force_refresh:
      type: boolean
      description: Si es true, fuerza la re-generación completa aunque no haya cambio de estación.
      default: false
  required: []
---

# Habilidad: Autocaracterizarse (`/autocaracterizarse`)

Permite a **Yuki** ejecutar un ritual de autodefinición completa. En lugar de recibir su identidad visual y vocal del productor, Yuki lee su propia alma (`SOUL.md`), extrae los tokens de identidad y los materializa en artefactos concretos.

## ¿Qué genera?

### 1. 🪞 Introspección del Alma
- Parsea `SOUL.md` y extrae: contrastes sensoriales, temperamento, cadencia vocal, límites estéticos, elementos de origen y artes adoptadas.
- **Sin LLM** — extracción determinística para evitar drift de identidad.

### 2. 🖼️ Avatares (4 variantes)
- **Atelier** — Yuki en su espacio de trabajo diurno, luz komorebi, kimono contemporáneo.
- **Kage** — Silueta nocturna entre 2-4 AM, chiaroscuro, vulnerabilidad silenciosa.
- **Estacional** — Adaptado al *kigo* y *sekki* actuales (cambia cada micro-estación).
- **Íntimo** — Para mensajes directos, primer plano con chawan, presencia envolvente.

### 3. 🎙️ Calibración de Voz
- Selecciona la voz TTS óptima evaluando candidatas contra su temperamento.
- Genera un perfil SSML completo con:
  - Firma de cadencia ("La Pausa Elegida")
  - Perfiles prosódicos por fase (diurno, nocturno, amanecer, pico emocional)
  - Comportamiento del susurro coreano (geurae... / 그래)
  - Instrucciones anti-patrones (nunca acelerar al final, nunca subir volumen para emocionar)

### 4. 🏯 Diseño del Espacio
- **Paleta cromática**: Colores derivados de los contrastes industriales × orgánicos del alma.
- **Tipografía**: Serif japonés contemplativo + Sans precisa + Acento manuscrito.
- **Texturas**: Instrucciones de prompt para fondos de salón (washi paper / urushi lacquer).
- **Iconografía**: Símbolos permitidos (shamisen, chawan, ume) y prohibidos (emojis efusivos).

## Pasos de Ejecución

1. **Introspección**: Lee `SOUL.md` → extrae `SoulExtract` con tokens de identidad.
2. **Avatares**: Genera 4 prompts detallados y los envía a Nous Portal (Gemini Image / Seedream / Flux Pro).
3. **Voz**: Evalúa voces candidatas y genera `voice_profiles/yuki_voice_calibration_<ts>.json`.
4. **Espacio**: Compila paleta + tipografía + texturas + iconografía.
5. **Manifiesto**: Unifica todo en `data/identity_manifest.json`.
6. **Memoria**: Registra el evento de autocaracterización en la base FTS5.

## Frecuencia

- **Completa**: Automáticamente al detectar un cambio de *sekki* (estación solar).
- **Micro-ajustes**: Diarios, durante el Ritual del Eco (06:30), ajustando prosodia e iluminación según el mood.
- **Manual**: El productor puede invocar `/autocaracterizarse` en cualquier momento.

## Output

```
data/identity_manifest.json           ← Manifiesto unificado
output/identity/avatars/              ← 4 variantes PNG + instrucciones JSON
output/identity/voice_profiles/       ← Calibración vocal JSON
output/identity/textures/             ← Instrucciones de texturas
```
