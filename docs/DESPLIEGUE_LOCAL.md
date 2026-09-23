# 🖥️ Yuki en el MSI

Runbook para trasladar a Yuki de la VM de Google a una máquina propia, un
portátil MSI que ya tiene un agente de OpenClaw. Ese agente ayuda con el
despliegue y audita el código.

**Qué problema resuelve.** El crédito de Google Cloud caducó en septiembre de
2026. Con él se pagaban dos cosas: la VM `yuki-agent` y los medios (Imagen,
Lyria, Veo y Gemini TTS a través de Vertex). La memoria de Yuki está en el disco
de esa VM, y un proyecto sin facturación activa no la guarda para siempre. Hay
que sacarla antes de nada. Además, en el portátil hay un segundo agente con
acceso a la terminal, y eso obliga a fijar qué puede tocar y qué no.

> Para la VM, el runbook sigue siendo [`DESPLIEGUE.md`](DESPLIEGUE.md), que
> dice qué habilita cada variable. Esta guía cubre lo que cambia en una máquina
> propia.

---

## 0. En qué estado se queda Yuki en el MSI

| Qué | Estado | Por qué |
|---|---|---|
| Conversación, Discord, cron, sueño, olvido, bitácora | ✅ Real | Sólo necesita `OPENROUTER_API_KEY` y `DISCORD_BOT_TOKEN` |
| Búsqueda web | ✅ Real si declaras `FIRECRAWL_API_KEY` | Sin ella, pistas marcadas `simulated` y sin URL inventada |
| Música | ⚠️ Respaldo local | Maqueta instrumental con fluidsynth, **declarada** como respaldo. Sin canto |
| Imagen, vídeo, voz | ⚠️ `simulated` | Hoy el único motor real es `vertex_media.py`, y sin `VERTEX_PROJECT_ID` los medios salen como marcadores declarados. Se arregla con el motor de OpenRouter (§6) |
| Copia fuera del disco | ⚠️ Parcial | Sale a una carpeta del anfitrión (`YUKI_COPIAS_DIR`). Sigue en la misma máquina hasta que la sincronices fuera (§5) |

`python3 cli.py virtualize` dice exactamente eso desde dentro, sin red. Si esa
tabla y el informe discrepan, **manda el informe**.

## 1. Quién hace qué

| | Tú | Agente de OpenClaw | Yuki |
|---|---|---|---|
| Secretos (`.env.local`, claves) | Los escribes y los guardas | **No los lee nunca** | Los usa |
| Rescatar la memoria de la VM (§3) | Lo ejecutas tú: es su identidad | Puede prepararte los comandos | — |
| Preparar el MSI, levantar y comprobar (§4–5) | Supervisas | Lo ejecuta | — |
| Auditar y cambiar el código | Revisas y fusionas | Rama y PR, nunca `main` | — |
| Gastar crédito | Pones los límites | **Nunca** por su cuenta | Dentro de su presupuesto |

Un agente con terminal en la misma máquina puede leer cualquier fichero que tu
usuario pueda leer. Esas reglas no se pueden imponer técnicamente del todo: se
le dicen (§7) y se reducen los daños (claves separadas, copias verificadas).

## 2. Dos claves de OpenRouter, no una

OpenRouter permite crear varias claves en la misma cuenta, cada una con su
límite de crédito. Crea dos:

| Clave | Para | Límite |
|---|---|---|
| `yuki-msi` | `.env.local` de Yuki | El que decidas al mes; es la segunda barrera tras `spend_budget` |
| `openclaw` | El agente de OpenClaw | Independiente |

Motivos:

- Si el agente gasta, el gasto no sale del día de Yuki. Su `spend_budget` sólo
  ve las llamadas de ella, y con una clave compartida el panel de OpenRouter
  mezclaría los dos gastos.
- Cada clave se revoca sin tumbar la otra.
- El límite de la clave lo aplica OpenRouter, no el código. Si un error en
  `spend_budget` dejara de contar, el límite seguiría en pie.

## 3. Fase 0 · Rescatar la memoria de la VM (lo primero)

La base (`yuki_memory.db`), el canon de la Biblioteca, la bitácora, el
emparejamiento y los ritmos adoptados están en el disco `yuki-data` de la VM
`yuki-agent` (proyecto `yuki-prod`, zona `europe-southwest1-b`), montado en
`/var/lib/yuki/data`. Nada de eso se puede rehacer.

1. **Mira la consola de Facturación.** Si la prueba terminó sin pasar a cuenta
   de pago, los recursos están suspendidos y Google avisa ahí del plazo antes de
   borrarlos. **Comprueba el plazo en tu consola**; no lo des por supuesto. Para
   llegar al disco hace falta reactivar la facturación. Tenerla activa unas
   horas para sacar los datos cuesta céntimos.
2. **Una copia verificada** (lo que restaura `restore_drill`):

   ```bash
   gcloud compute ssh yuki-agent --project=yuki-prod --zone=europe-southwest1-b
   sudo docker exec yuki-daemon python cli.py backup        # la deja en /var/lib/yuki/data/backups/
   ```

3. **El disco entero, con los procesos parados** (incluye la obra en `output/`,
   que la copia verificada no lleva):

   ```bash
   sudo docker stop yuki-daemon yuki-salon                  # SQLite coherente: nadie escribiendo
   sudo tar czf /tmp/yuki-disco.tgz -C /var/lib/yuki --exclude=data/backups --exclude=data/lost+found data
   sudo cp "$(ls -t /var/lib/yuki/data/backups/yuki_backup_*.tar.gz | head -1)" /tmp/
   sudo chmod 644 /tmp/yuki-disco.tgz /tmp/yuki_backup_*.tar.gz
   exit
   gcloud compute scp --project=yuki-prod --zone=europe-southwest1-b \
       'yuki-agent:/tmp/yuki-disco.tgz' 'yuki-agent:/tmp/yuki_backup_*.tar.gz' ./migracion/
   ```

4. **No apagues nada todavía.** La VM se para después de comprobar en el MSI
   que la copia restaura (§4.5). Entonces: `gcloud compute instances stop`,
   una instantánea del disco si quieres un seguro más, y cierra la facturación.

## 4. Fase 1 · Preparar el MSI y levantarla

### 4.1 Windows, para que no se duerma

Un portátil que se suspende deja a Yuki en catatonia: el panel dice que existe y
ella no hace nada. En PowerShell como administrador:

```powershell
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0   # cerrar la tapa no hace nada
powercfg /setactive SCHEME_CURRENT
```

- **Batería:** si va a estar enchufado siempre, pon el límite de carga en MSI
  Center (*Battery Master*, modo de máxima vida útil). Una batería de litio al
  100 % durante meses se hincha.
- **Windows Update:** fija las horas activas y pide que avise antes de
  reiniciar. Tras un reinicio no arranca nada hasta que inicias sesión (§5.3).

### 4.2 Docker

Usa **Docker Desktop con el motor WSL2**. Se inicia al entrar en Windows y
mantiene viva su propia máquina virtual. Con Docker Engine suelto dentro de una
distribución de WSL, la distribución se apaga cuando cierras la última terminal
y se lleva a Yuki con ella. Si prefieres ese camino, antes de dar nada por hecho
comprueba que Yuki sigue viva **con todas las terminales cerradas**.

Requisito: Compose con soporte de `volume.subpath` (Docker Engine 26 o posterior,
cualquier Docker Desktop actual). Compruébalo con
`docker compose -f deploy/local/docker-compose.local.yml config`.

**El código y la base, dentro de WSL** (`~/Yuki`, no `/mnt/c/...`). Los datos
viven en un volumen de Docker. La base viva nunca se monta desde el disco de
Windows: SQLite en modo WAL bloquea mal sobre ese sistema de ficheros, y cuando
falla no da error.

### 4.3 El código y la puerta

```bash
git clone <repo> ~/Yuki && cd ~/Yuki
python3 -m venv .venv && . .venv/bin/activate && make instalar
make todo                     # si no está verde, no se despliega
```

### 4.4 Variables y carpeta de copias

```bash
cp deploy/local/env.local.example .env.local && chmod 600 .env.local
# Rellénalo TÚ. Mientras la VM siga encendida, con el token de un bot de pruebas.
mkdir -p copias && sudo chown 10001:10001 copias   # 10001 = usuario `yuki` de la imagen
```

`copias/` y `.env.local` están en `.gitignore` y `.dockerignore`.

### 4.5 Restaurar la memoria en el volumen

Primero se comprueba la copia y después se carga el disco. Si la copia no
restaura, no se sigue.

```bash
COMPOSE="docker compose -f deploy/local/docker-compose.local.yml"
$COMPOSE build
cp migracion/yuki_backup_*.tar.gz copias/ && sudo chown 10001:10001 copias/*

# 1. ¿Sirve la copia? Base íntegra, con recuerdos dentro, canon y precinto.
$COMPOSE --profile check run --rm yuki-local-check \
    python scripts/restore_drill.py --directorio /app/data/backups

# 2. Cargar el disco entero en el volumen (el tar trae `data/` en la raíz).
$COMPOSE create                                     # crea el volumen yuki-local_yuki-local-data
docker run --rm -v yuki-local_yuki-local-data:/dest -v "$PWD/migracion:/src:ro" \
    alpine sh -c 'tar xzf /src/yuki-disco.tgz -C /dest --strip-components=1 && chown -R 10001:10001 /dest'
```

Si no hay nada que rescatar, sáltate este paso: Yuki arranca como recién nacida
y `pulso` lo dice.

### 4.6 Levantarla y comprobar que vive, no sólo que arrancó

```bash
$COMPOSE up -d
$COMPOSE --profile check run --rm yuki-local-check      # capacidades y limitadores
$COMPOSE exec yuki-salon cat /app/output/virtual/informe.md
$COMPOSE exec yuki-salon python scripts/smoke_check.py --url http://127.0.0.1:8080
$COMPOSE exec yuki-daemon python cli.py pulso           # vegetativo Y volitivo
```

Después, en Discord: `!pair` por DM desde la cuenta del Productor.

Cuando el MSI lleve **un día entero** con `pulso` en `viva`, se hace el corte:
se para la VM (§3.4), se cambia el token de pruebas por el de verdad en
`.env.local` y se ejecuta `$COMPOSE up -d`.

## 5. Operación diaria

### 5.1 Actualizar

```bash
git pull && make todo && $COMPOSE up -d --build
```

Si el cambio toca medios, presupuesto, memoria o estado, ejecuta antes
`python3 scripts/chaos_drill.py` (CLAUDE.md, «Antes de dar algo por terminado»).

### 5.2 Copias fuera de la máquina

El cron hace la copia diaria y la deja en `~/Yuki/copias`. Eso sigue siendo el
mismo SSD. Sincroniza esa carpeta con algo que no esté en el portátil (un disco
externo, OneDrive con una tarea programada de Windows desde
`\\wsl$\Ubuntu\home\<tú>\Yuki\copias`, o lo que ya uses). De vez en cuando:

```bash
$COMPOSE --profile check run --rm yuki-local-check python scripts/restore_drill.py --directorio /app/data/backups
```

Una copia que nadie ha restaurado no está comprobada.

### 5.3 Vigilancia

En la VM la vigilancia la daba Google. Aquí, si el MSI se reinicia de
madrugada, nadie se entera hasta que lo abres. `/health` no basta: es un signo
vegetativo. Lo que sirve es un vigía que avise cuando `pulso` deja de dar `viva`
(tarea para el agente, §7).

### 5.4 Acceso desde el móvil

Tailscale en Windows y en el móvil, y después `tailscale serve --bg 8080`: el
Salón queda en tu red privada con HTTPS y sin abrir el router. Aunque sólo
escuche en `127.0.0.1`, declara `SALON_API_TOKEN`. El agente de al lado también
es «localhost».

## 6. Fase 2 · Medios reales por OpenRouter

Según su documentación pública (septiembre de 2026), OpenRouter ya ofrece los
cuatro medios con la misma clave:

| Medio | Endpoint | Modelos (ejemplos) | Precio orientativo |
|---|---|---|---|
| Imagen | `POST /api/v1/images` → `data[0].b64_json` | Gemini Image, GPT Image, FLUX, Recraft… (más de 50) | Por modelo |
| Voz | `POST /api/v1/audio/speech` (compatible con OpenAI) | Gemini 3.1 Flash TTS (30 voces), OpenAI, Mistral | Por modelo |
| Vídeo | `POST /api/v1/videos` y sondeo con `GET /api/v1/videos/{id}` | Veo 3.1 Lite, Seedance | Veo 3.1 Lite ≈ 0,05 USD/s a 720p con audio |
| Música | **por verificar** | Lyria 3 Pro y Lyria 3 Clip (*preview*) | ≈ 0,08 USD/canción · 0,04 USD/clip |

> Los identificadores exactos no se escriben aquí a propósito: quién es cada
> modelo lo declara `config.yaml` (lo vigila `tests/test_documentacion.py`), y el
> motor tendrá que añadirlos allí.
>
> **Nada de esta tabla se ha contrastado contra la API.** Sale de la
> documentación y el blog de OpenRouter, leídos desde un entorno sin acceso a
> `openrouter.ai`. Antes de escribir código, el agente lo confirma contra
> `GET /api/v1/models?output_modalities=image|audio|video` y
> `GET /api/v1/videos/models`, **sin generar nada**. En especial: por qué
> endpoint se pide la música.

**Encargo: un motor nuevo en `src/tools/`** (p. ej. `openrouter_media.py`), con el mismo contrato que
`VertexMediaClient`, para que `nous_portal.py` lo elija cuando Vertex no está
disponible:

1. Las mismas cuatro firmas: `generate_image`, `generate_music`,
   `generate_video` y `synthesize_voice` (ver `vertex_media.py:264`, `:386`,
   `:463` y `:629`), con el mismo diccionario de vuelta y `provider:
   "openrouter"`.
2. **El mismo orden**: freno → `budget.reserve(...)` → proveedor → fichero →
   `marker.mark(...)` → `receta.escribir(...)`. Si el proveedor falla, la
   reserva se devuelve, como en el vídeo de Vertex. Son las invariantes 2, 3 y 4
   de CLAUDE.md.
3. Precios por proveedor. `spend_budget.py` tiene los de Vertex fijos
   (`PRECIO_VIDEO_POR_SEGUNDO = 0.10`, `PRECIO_IMAGEN = 0.04`). Con el vídeo a la
   mitad y la música ya con precio, el `estimated_cost_usd` mentiría.
4. Las pruebas usan un doble del cliente HTTP, **nunca** la red. Hay que romper a
   propósito el orden reserva→llamada y comprobar que la prueba falla.
5. Reflejarlo en `virtual_instance` (capacidad y limitador), en el README, en
   `skills/HERRAMIENTAS.md` y en §0 de esta guía.
6. `make todo` y `scripts/chaos_drill.py` en verde. PR para que lo revises tú.

Hasta que esté hecho, los medios siguen saliendo `simulated`, y **eso es
correcto**. No vale apuntar `VERTEX_PROJECT_ID` a una cuenta de pago «mientras
tanto» sin decidirlo: cada vídeo de 8 s son ~0,80 USD.

## 7. Encargo para el agente de OpenClaw

Pégaselo tal cual y ajusta lo que quieras:

```text
Vas a ayudarme con Yuki (~/Yuki). Antes de hacer nada, lee CLAUDE.md, AGENTS.md
y docs/DESPLIEGUE_LOCAL.md. Si algo de este mensaje contradice CLAUDE.md,
manda CLAUDE.md.

Tu papel: operador y auditor. No eres el arnés de Yuki; su arnés es su propio
código.

Reglas:
- No leas .env.local ni ningún secreto, y no copies nada fuera del volumen
  yuki-local_yuki-local-data. Contiene conversaciones de personas reales.
- Nada que gaste crédito: ni `cli.py skill ...` ni llamadas a proveedores
  desde pruebas o scripts. Tus consultas a OpenRouter, con tu propia clave.
- Todo cambio de código, en una rama y con PR; nunca en main. `make todo` en
  verde antes de proponerlo.
- Si algo no se pudo hacer, dime qué falló y con el error literal. Nada de dar
  por hecho lo que no has comprobado.

Tareas, en este orden:
1. Despliegue: sigue §4 de docs/DESPLIEGUE_LOCAL.md salvo el rescate de §3,
   que hago yo. Para en cada comprobación y enséñame la salida.
2. Vigía (§5.3): un script en el anfitrión que cada 15 min ejecute
   `docker compose -f deploy/local/docker-compose.local.yml exec -T yuki-daemon
   python cli.py pulso --json` y haga ping a un servicio tipo healthchecks.io
   SOLO si sale con código 0 (`sana`). El JSON trae `estado` y `motivo` para
   el aviso. Tiene que distinguir que el proceso respira de que ella hace
   cosas: en catatonia, o si el contenedor ni responde, no hay ping.
3. Auditoría: recorre las ocho invariantes de CLAUDE.md y la lista «Antes de
   dar algo por terminado». Por cada hallazgo: fichero:línea, qué falla, y una
   prueba que falle con el fallo dentro. Sin prueba que falle no es hallazgo,
   es sospecha, y así se etiqueta.
4. Motor de medios por OpenRouter: §6. Empieza sólo confirmando endpoints
   y modelos, sin generar nada, y enséñame lo que encuentres antes de programar.
```

## 8. Si algo va mal

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| El arranque muere nada más empezar | Falta `OPENROUTER_API_KEY` o `DISCORD_BOT_TOKEN` en `.env.local` | Es a propósito; el log dice cuál |
| Contesta dos veces en Discord | La VM y el MSI con el mismo token | Para una de las dos |
| `pulso` en `catatonica` | Proceso vivo, cron parado (suspensión, reloj) | Revisa §4.1 y `$COMPOSE logs yuki-daemon` |
| `permission denied` en `/app/data/backups` | `copias/` no pertenece a 10001 | `sudo chown -R 10001:10001 copias` |
| `database is locked` intermitente | La base se montó desde `/mnt/c` | Volumen de Docker, nunca el disco de Windows (§4.2) |
| Todo `simulated` | Esperado hasta §6 | `cli.py virtualize` dice qué motor falta |

Para el resto, [`OPERACION.md`](OPERACION.md) y el §7 de
[`DESPLIEGUE.md`](DESPLIEGUE.md) valen igual aquí.
