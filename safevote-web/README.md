# SafeVote 2026 — Stack web moderno

Auditoría ciudadana colaborativa de actas E-14. Stack:

```
Next.js (React+TS)  ──/api/*──►  NestJS (TS) + Prisma  ──►  PostgreSQL
  render PDF en                  cola de actas (SKIP LOCKED)    persistente
  el navegador                   etiquetas, stats, fraude
```

| Capa | Tecnología | Carpeta |
|---|---|---|
| Frontend | **Next.js 14** + React + **react-pdf** | `web/` |
| Backend | **NestJS 10** + **Prisma** | `api/` |
| Base de datos | **PostgreSQL 16** | (Docker) |
| Infra | Docker Compose + nginx + Certbot | raíz + `nginx/` |

## Por qué este diseño
- **El PDF se renderiza en el navegador** (react-pdf/PDF.js) → el servidor no gasta CPU en imágenes; escala con los usuarios.
- **NestJS + Prisma**: estructura modular, tipado, fácil de mantener y extender.
- **Cola con `FOR UPDATE SKIP LOCKED`**: cada persona recibe una acta distinta, sin colisiones, aunque entren cientos.
- **PostgreSQL**: datos persistentes y concurrentes.

## Desarrollo local
```bash
# 1. datos
mkdir -p data/pdfs
cp ../labeling_app/manifest.csv data/manifest.csv
# (opcional) cp -r ../training/pdfs_train/* data/pdfs/   — si no, baja de la Registraduría

# 2. levantar todo
echo "DB_PASSWORD=clave_local" > .env
docker compose up --build
# Frontend: http://localhost:3000   (cambia el mapeo de puerto del servicio web si hace falta)
```

## Producción (VPS + dominio)
```bash
# en el VPS (Ubuntu): instalar docker, nginx, certbot (ver labeling_app/DEPLOY.md paso 1)
git clone <repo> /opt/safevote && cd /opt/safevote/safevote-web
cp .env.example .env && nano .env            # DB_PASSWORD segura
mkdir -p data/pdfs && cp manifest.csv data/manifest.csv
# subir PDFs (opcional):  scp -r pdfs_train/* VPS:/opt/safevote/safevote-web/data/pdfs/
docker compose up -d --build

# nginx + HTTPS
sudo cp nginx/safevote.conf /etc/nginx/sites-available/safevote
sudo nano /etc/nginx/sites-available/safevote     # tu dominio
sudo ln -s /etc/nginx/sites-available/safevote /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d tudominio.com
```

## Endpoints API (NestJS)
| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/api/actas/next?labeler=` | reparte siguiente acta (sin repetir) |
| GET | `/api/actas/:id/pdf` | sirve el PDF (local o Registraduría) |
| POST | `/api/actas/:id/submit` | guarda etiqueta |
| POST | `/api/actas/:id/flag` | marca posible fraude |
| POST | `/api/actas/:id/skip` | salta (ilegible) |
| GET | `/api/stats` | progreso + ranking |
| GET | `/api/flagged` | actas marcadas como fraude |

## Pendiente al primer arranque
- Ajustar el mapa de posiciones `MAP` en `web/app/page.tsx` si el zoom a las casillas queda corrido (el PDF completo tiene proporciones distintas al recorte que calibramos en Flask).
- `.env.example` con `DB_PASSWORD`.
