# 🚀 Guía de Despliegue: VPS ($5/mes), Docker y Serverless (Modal)

Este manual cubre todas las opciones de despliegue en producción para **Yuki**, garantizando un consumo mínimo de recursos y alta disponibilidad.

---

## Opción 1: Despliegue en VPS Económico ($5/mes)

Ideal para servidores como Hetzner CX22, DigitalOcean Basic Droplet o Linode Nanode (1 vCPU, 1GB-2GB RAM).

### 1. Clonar y Configurar
```bash
# 1. Clonar repositorio
git clone <url-del-repo> /opt/yuki
cd /opt/yuki

# 2. Configurar variables de entorno
cp .env.example .env
nano .env # Coloca tus claves API y tokens de Telegram/Discord
```

### 2. Despliegue con Docker Compose
```bash
# Construir e iniciar en segundo plano
docker-compose up -d --build

# Verificar logs en tiempo real
docker-compose logs -f
```

### 3. Servicio del Sistema (Systemd Alternativo)
Si prefieres ejecutar directamente con Python sin Docker:

```ini
# /etc/systemd/system/yuki.service
[Unit]
Description=Yuki Digital Diva Daemon
After=network.target

[Service]
Type=simple
User=yuki
WorkingDirectory=/opt/yuki
ExecStart=/usr/bin/python3 /opt/yuki/cli.py run-daemon
Restart=always
RestartSec=10
EnvironmentFile=/opt/yuki/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now yuki
```

---

## Opción 2: Despliegue Serverless en Modal (Zero Idle Cost)

Modal permite ejecutar a Yuki sin pagar por servidores encendidos 24/7. El contenedor permanece apagado y se activa en menos de 400ms al recibir una mención o un evento cron.

### 1. Instalar y Autenticar Modal
```bash
pip install modal
modal setup
```

### 2. Desplegar la Aplicación
```bash
# Despliegue en la nube
modal deploy src/serverless/modal_app.py
```

### 3. Configurar el Webhook de Telegram
Modal te proporcionará una URL pública para el endpoint `telegram_webhook`. Configúralo en Telegram con:

```bash
curl -F "url=https://<tu-subdominio>.modal.run/telegram_webhook" https://api.telegram.org/bot<TU_TELEGRAM_BOT_TOKEN>/setWebhook
```

---

## 4. Monitorización y Salud del Sistema

- **Uso de Memoria:** Yuki consume típicamente **~120MB - 180MB de RAM**.
- **Almacenamiento:** La base de datos SQLite en `data/yuki_memory.db` ocupa menos de **10MB** para decenas de miles de interacciones indexadas.
- **Backups:** Es suficiente con respaldar el directorio `data/` periódicamente.
