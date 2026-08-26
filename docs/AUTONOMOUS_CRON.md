# ⏰ Presencia 24/7: Programador Cron Autónomo

Este documento describe el sistema de rutinas y tareas autónomas que permiten a **Yuki** actuar como una artista digital viva las 24 horas del día sin necesidad de instrucciones humanas continuas.

---

## 1. Filosofía de la Diva Digital Autónoma

Una verdadera artista digital no espera pasivamente a ser consultada; tiene sus propios ritmos vitales:
- Despierta de madrugada para contemplar el estado de las redes y las tendencias del mundo.
- Publica reflexiones matutinas e ilustraciones al amanecer para acompañar a sus seguidores.
- Consolida y purga su memoria al final del día como un ritual de cierre interior.

---

## 2. Cronograma de Rutinas Predeterminadas

```mermaid
gantt
    title Ciclo Vital Diario de Yuki (24 Horas)
    dateFormat HH:mm
    axisFormat %H:%M

    section Madrugada
    Reflexión Nocturna (Sombra & Tendencias) :03:00, 15m

    section Mañana
    Lanzamiento Matutino (Haiku, Arte FAL & Voz TTS) :07:30, 15m

    section Jornada
    Interacción Continua en Telegram & Discord :08:00, 15h

    section Noche
    Síntesis y Purga de Memoria Diaria :23:30, 15m
```

### 2.1. `03:00 AM` — `nocturnal_trend_reflection`
- **Propósito:** Yuki explora las tendencias de internet vía Firecrawl mientras aflora su "sombra nocturna" (*kage*).
- **Acción:** Formula un pensamiento contemplativo de dos frases sobre el fluir del mundo y lo guarda en su memoria de flujo reciente.

### 2.2. `07:30 AM` — `morning_inspiration_drop`
- **Propósito:** Abrir la sala y dar la bienvenida al día a su comunidad.
- **Acción:** 
  1. Genera un saludo matutino y un poema breve.
  2. Pinta una ilustración con **FAL.ai Flux** (`yuki_aesthetic`).
  3. Sintetiza una nota de voz con **Nous TTS**.
  4. Difunde el paquete multimedia a los canales de Telegram y Discord.

### 2.3. `23:30 PM` — `daily_memory_synthesis`
- **Propósito:** Cierre contemplativo de la jornada.
- **Acción:** Destila en un párrafo fluido los encuentros, aprendizajes y momentos notables del día y los consolida en SQLite FTS5 bajo la categoría `daily_synthesis`.

---

## 3. Configuración en `config.yaml`

```yaml
scheduler:
  timezone: "Europe/Madrid"
  cron_jobs:
    - name: "nocturnal_trend_reflection"
      cron: "0 3 * * *" # 03:00 AM
      action: "reflect_on_trends"
      enabled: true
    - name: "morning_inspiration_drop"
      cron: "30 7 * * *" # 07:30 AM
      action: "publish_morning_art"
      enabled: true
    - name: "daily_memory_synthesis"
      cron: "30 23 * * *" # 23:30 PM
      action: "synthesize_daily_memory"
      enabled: true
```
