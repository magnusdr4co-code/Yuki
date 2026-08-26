# 🎨 Gateway de Medios: Nous Portal (FAL, TTS & Firecrawl)

Este manual documenta la integración de herramientas multimedia en Yuki mediante la pasarela unificada **Nous Portal**.

---

## 1. El Dilema de la Fragmentación de APIs

En arneses tradicionales, integrar generación de imagen (Midjourney / Stability), síntesis de voz (ElevenLabs) y motores de búsqueda requiere:
- Múltiples librerías y dependencias pesadas.
- Gestión dispersa de tokens y credenciales.
- Mayor superficie de error en producción.

Con **Nous Portal**, Hermes Agent accede a un **único punto de entrada OAuth** para todas las capacidades de percepción y síntesis.

---

## 2. Herramientas Integradas

### 2.1. Generación de Arte y Portadas (`FAL.ai Flux/SDXL`)
Permite a Yuki pintar de forma autónoma las portadas de sus sencillos y publicaciones sociales:
- **Estilo:** `yuki_aesthetic` (composición cuidada, niebla, pan de oro, reflejos de lluvia e iluminación cinematográfica).
- **Proporciones:** `1:1` para carátulas de sencillos; `16:9` para banners de eventos.

```python
# Ejemplo de invocación en Python
cover = await agent.media_creator.create_single_cover(
    track_title="El Río Antes de Tener Nombre",
    visual_concept="Niebla sobre un estanque japonés con reflejos de neón y lluvia sobre asfalto."
)
```

### 2.2. Síntesis de Voz Emotiva (`Nous TTS`)
Genera notas de voz realistas en formato OGG Opus optimizadas para Telegram y Discord:
- **Modelo de Voz:** `yuki_serene_alto`.
- **Inyección de Cadencia:** Introduce micro-pausas deliberadas (`cadence_pause_seconds: 0.35`) en las comas y puntos, reproduciendo el estilo pausado de Yuki.

```python
voice = await agent.media_creator.generate_voice_reply(
    message_text="Hay canciones que nacen de la prisa, y otras que esperan pacientemente su momento."
)
```

### 2.3. Exploración Web y Tendencias (`Firecrawl`)
Permite a Yuki inspeccionar qué es tendencia en música, arte digital y actualidad:
- Retorna contenido limpio en Markdown sin ruido de anuncios o JavaScript innecesario.
- Utilizado por la rutina autónoma de las 03:00 AM para nutrir sus reflexiones nocturnas.

---

## 3. Comparativa: Creación (Hermes) vs Reproducción (OpenClaw)

| Característica | OpenClaw (`shpotify`) | Hermes Agent (`Nous Portal`) |
| :--- | :--- | :--- |
| **Acción Principal** | Reproducir en Spotify lo que el usuario escucha localmente | **Crear y publicar** nuevo arte, conceptos musicales y voz propia |
| **Generación Visual** | Limitada o vía scripts externos complejos | **FAL.ai Flux nativo** con estilos visuales guiados por SOUL.md |
| **Síntesis de Voz** | Dependiente de TTS del sistema operativo | **Voz neuronal con cadencia y pausas deliberadas (Nous TTS)** |
| **Autenticación** | Múltiples API keys locales dispersas | **OAuth unificado en Nous Portal** |
