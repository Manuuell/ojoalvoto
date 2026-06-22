# SafeVote 2026 — Despliegue en VPS con dominio

Stack de producción:
- **Flask + Gunicorn** (4 workers) — app
- **PostgreSQL 16** — base de datos persistente y concurrente
- **Docker Compose** — app + base de datos en contenedores
- **nginx + Certbot (Let's Encrypt)** — reverse proxy + HTTPS
- **PyMuPDF** — render de PDF con caché en disco

```
Internet → nginx (host, :443 TLS) → app (Docker, :8000) → Postgres (Docker)
                                          ↓
                                   /data (manifest, pdfs, cache)
```

---

## 0. Requisitos
- Un VPS Ubuntu 22.04+ (1 vCPU / 2 GB RAM mínimo; 2 vCPU / 4 GB recomendado)
- Un dominio apuntando (registro A) a la IP del VPS

## 1. Instalar Docker y nginx en el VPS
```bash
# Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER && newgrp docker

# nginx + certbot
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx
```

## 2. Subir el proyecto
```bash
# Opción A: git
git clone <tu-repo> /opt/safevote && cd /opt/safevote/labeling_app
# Opción B: scp desde tu PC
#   scp -r labeling_app usuario@IP_VPS:/opt/safevote
```

## 3. Datos (manifest + PDFs)
```bash
mkdir -p data/pdfs data/cache
cp manifest.csv data/manifest.csv
# Subir los PDFs (1.4 GB) — desde tu PC:
#   scp -r training/pdfs_train/* usuario@IP_VPS:/opt/safevote/labeling_app/data/pdfs/
# (Si NO subes los PDFs, la app los baja de la Registraduría on-demand y los cachea.)
# Opcional: pre-llenado IA
#   cp labels_sc.jsonl data/prefills.jsonl
```

## 4. Configurar y levantar
```bash
cp .env.example .env
nano .env          # pon una DB_PASSWORD larga y segura
docker compose up -d --build
docker compose logs -f app      # debe decir "Cargadas N actas en Postgres"
```
La app queda en `127.0.0.1:8000` (solo local; nginx la expone).

## 5. nginx + dominio + HTTPS
```bash
sudo cp nginx/safevote.conf /etc/nginx/sites-available/safevote
sudo nano /etc/nginx/sites-available/safevote   # cambia "tudominio.com"
sudo ln -s /etc/nginx/sites-available/safevote /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# Certificado TLS automático (agrega el bloque 443 y renovación automática)
sudo certbot --nginx -d tudominio.com -d www.tudominio.com
```
Listo: **https://tudominio.com** 🎉

---

## Operación

| Acción | Comando |
|---|---|
| Ver logs | `docker compose logs -f app` |
| Reiniciar | `docker compose restart app` |
| Actualizar código | `git pull && docker compose up -d --build` |
| Backup de la BD | `docker compose exec db pg_dump -U safevote safevote > backup_$(date +%F).sql` |
| Restaurar BD | `cat backup.sql \| docker compose exec -T db psql -U safevote safevote` |
| Descargar etiquetas | `https://tudominio.com/api/export` |
| Descargar fraudes | `https://tudominio.com/api/flagged` |

## Por qué este stack es correcto para mucha gente
- **Postgres** persiste los datos (no se pierden en reinicios) y soporta miles de escrituras concurrentes.
- **FOR UPDATE SKIP LOCKED**: cada usuario recibe una acta distinta sin colisiones, aunque entren 100 a la vez.
- **Gunicorn 4 workers × 2 hilos**: atiende múltiples personas en paralelo.
- **Caché de imágenes**: cada acta se renderiza una sola vez (mucho menos CPU).
- **nginx + TLS**: tráfico cifrado, cacheo de imágenes en el navegador.

## Escalar más (si hiciera falta)
- Subir `--workers` en el Dockerfile (regla: 2×núcleos + 1).
- Mover Postgres a un servicio gestionado (o disco dedicado).
- Añadir Redis para caché de sesiones/imágenes si el tráfico es muy alto.

## Desarrollo local (sin VPS)
```bash
cp .env.example .env
docker compose up --build
# abrir http://localhost:8000  (cambia el puerto a 8000 en docker-compose si quieres acceso directo)
```
La versión SQLite antigua quedó como `app_sqlite_local.py` por si quieres correr sin Docker.
