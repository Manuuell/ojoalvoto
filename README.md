# SafeVote / OjoAlVoto — Auditoría ciudadana de las actas E-14 · Elecciones Colombia 2026

Sistema de **análisis y verificación electoral** de las actas E-14 de la elección presidencial de Colombia (31 de mayo de 2026). Descarga las actas escaneadas publicadas por la Registraduría, las lee (IA + etiquetado humano), valida su coherencia matemática y señala las actas con posibles inconsistencias para revisión ciudadana.

> **Propósito.** Herramienta de **auditoría y transparencia electoral** que trabaja exclusivamente con datos **públicos** publicados por la Registraduría Nacional del Estado Civil. No modifica resultados ni accede a sistemas privados; solo lee, contrasta y visualiza información ya divulgada. Una acta "sospechosa" es una acta cuya aritmética no cuadra a la lectura, **no** una acusación de fraude: requiere verificación humana.

---

## 📋 Tabla de contenido

- [¿Qué hace?](#-qué-hace)
- [Arquitectura y fases](#-arquitectura-y-fases)
- [Estructura del repositorio](#-estructura-del-repositorio)
- [Requisitos](#-requisitos)
- [Instalación](#-instalación)
- [Descargar las actas (PDFs)](#-descargar-las-actas-pdfs)
- [Pipeline de procesamiento](#-pipeline-de-procesamiento)
- [Aplicaciones web de etiquetado](#-aplicaciones-web-de-etiquetado)
- [APIs públicas descubiertas](#-apis-públicas-descubiertas)
- [El formulario E-14](#-el-formulario-e-14)
- [Análisis estadístico](#-análisis-estadístico)
- [Notas importantes](#-notas-importantes)

---

## 🎯 ¿Qué hace?

La Registraduría publica **121.041 actas E-14** (de 122.020 mesas) como PDFs escaneados. Cada acta es el formulario físico que los jurados llenan **a mano** con el conteo de votos de su mesa.

El reto: leer números **manuscritos** de forma confiable a gran escala. La estrategia del proyecto:

1. **Descargar** las actas desde la API pública (índice `allTransmissionCodes.json` → URL de cada PDF).
2. **Leer** cada acta. El E-14 tiene **redundancia matemática**:
   `suma(candidatos) + blanco + nulo + no_marcadas == suma_total` (o `== votos en urna`).
   - Si la ecuación **cuadra** → la lectura es correcta automáticamente (etiqueta limpia, gratis).
   - Si **no cuadra** → candidata a inconsistencia → revisión humana.
3. **Validar** y **etiquetar** (IA profesora Qwen2.5-VL + etiquetado humano colaborativo).
4. **Visualizar** las actas sospechosas en una web de auditoría.
5. (Futuro) **Escalar** a las 121.041 actas con un modelo Donut destilado.

El detector de inconsistencias **es** la validación matemática: tras un voto de mayoría de varias lecturas (self-consistency), las actas que siguen sin cuadrar son las que merecen ojo humano.

---

## 🏗 Arquitectura y fases

```
   API Registraduría                    Lectura                      Auditoría
 ┌───────────────────┐         ┌───────────────────────┐      ┌──────────────────┐
 │ allTransmission   │  PDFs   │ Qwen2.5-VL (profesor) │      │  Web etiquetado  │
 │   Codes.json      │ ──────► │   + validación        │ ───► │  + dashboard     │
 │ (índice 121.041)  │         │   matemática E-14     │      │  (humano revisa) │
 └───────────────────┘         └───────────────────────┘      └──────────────────┘
                                          │                            │
                                          ▼                            ▼
                               resultado_clean.jsonl        resultado_sospechosas.jsonl
                               (etiquetas para Donut)        (candidatas a revisión)
```

| Fase | Estado | Descripción |
|------|--------|-------------|
| **1. Descarga estratificada** | ✅ | Muestra geográficamente diversa: 250 actas/departamento + 2 deptos completos de holdout (Tolima, Caldas) |
| **2. Auto-etiquetado** | 🔄 | Notebook Qwen2.5-VL-7B + validación matemática (self-consistency 3×, voto mayoría) |
| **3. Entrenar Donut** | ⏳ | Modelo rápido destilado a partir de etiquetas limpias |
| **4. Inferencia masiva** | ⏳ | Las 121.041 actas |
| **5. Dashboard web** | 🔄 | Visualización de actas sospechosas con evidencia |

El estado de trabajo detallado, decisiones de diseño y resultados de experimentos están en **[PROYECTO.md](PROYECTO.md)** (bitácora técnica).

---

## 📁 Estructura del repositorio

```
SafeVote/
├── PROYECTO.md                 # Bitácora técnica detallada (lee esto para el contexto completo)
├── README.md                   # Este archivo
│
├── cache/                      # Índices JSON de la API (¡se necesitan para descargar!)
│   ├── allTransmissionCodes.json   # CLAVE: mapeo mesa → hash SHA256 del PDF (~35 MB)
│   ├── departmentsTree.json        # Árbol dept → mun → zona → puesto → mesas
│   └── allMviewGetProgress...json  # Progreso de publicación
│
├── scraper/                    # Cliente de la API de la Registraduría
│   ├── registraduria_client.py     # Cliente de descarga por índice de hashes
│   ├── api_endpoints.py            # Mapa de todos los endpoints públicos
│   └── requirements.txt
│
├── pipeline/                   # Descarga + OCR por departamento
│   ├── download_dept.py            # Descarga TODAS las actas de un departamento
│   ├── ocr_dept.py                 # OCR con Tesseract (precisión ~60-70%, obsoleto vs IA)
│   └── preprocess.py               # Preprocesamiento de imágenes
│
├── training/                   # FASE 1-2: muestra de entrenamiento + auto-etiquetado
│   ├── download_training_sample.py # Descarga estratificada (toda Colombia)
│   ├── manifest_train.csv          # Metadata de cada acta de entrenamiento
│   ├── manifest_holdout.csv        # Metadata del holdout (Tolima + Caldas)
│   ├── fase2_autolabel_v2.ipynb    # Notebook actual (Qwen2.5-VL + validación)
│   ├── make_notebook_autolabel_v2.py  # Generador del notebook
│   └── pdfs_train/ , pdfs_holdout/    # PDFs descargados (IGNORADOS por git, ver abajo)
│
├── precon/                     # Resultados oficiales PRECON
│   ├── download_precon.py          # Descarga todos los JSONs de resultados
│   ├── analyze_precon.py            # Análisis estadístico (Benford, participación, histórico)
│   └── cache/                       # ~1.224 JSONs (nacional, departamentos, municipios)
│
├── analyzer/
│   └── fraud_detector.py            # Reglas de detección de inconsistencias
│
├── labeling_app/               # App web de etiquetado v1 — Flask + PostgreSQL/SQLite
│   ├── app.py                      # Versión producción (Postgres + PyMuPDF)
│   ├── app_sqlite_local.py         # Versión local (SQLite)
│   ├── templates/                  # UI con zoom por casilla
│   ├── docker-compose.yml , Dockerfile , nginx/
│   └── DEPLOY.md                   # Guía de despliegue
│
├── safevote-web/               # App web de etiquetado v2 — Next.js + NestJS + Postgres
│   ├── api/                        # Backend NestJS 10 + Prisma
│   ├── web/                        # Frontend Next.js 14 + react-pdf (render en navegador)
│   ├── docker-compose.yml          # db + api + web
│   ├── nginx/                      # Reverse proxy + TLS
│   └── README.md
│
├── resultados/                 # Salidas de OCR (CSV)
├── analyze_now.py              # Análisis rápido de progreso
├── run_pipeline.py             # Orquestador (descarga + OCR)
├── gen_full_manifest.py        # Genera manifest completo
├── inspect_csv.py , inspect_pdf.py , test_*.py   # Utilidades de inspección
```

---

## ⚙ Requisitos

- **Python 3.11+** (el proyecto se desarrolló con 3.13)
- **Tesseract OCR 5.x** con `spa.traineddata` (solo para el pipeline OCR clásico; la IA no lo necesita)
- **Poppler** (para `pdf2image`)
- Para las apps web: **Docker + Docker Compose** (o Node.js 20 + PostgreSQL 16 para correr a mano)
- Para el auto-etiquetado (Fase 2): **GPU** — pensado para **Google Colab Pro (A100)**

### Dependencias de Python

```
httpx[http2]  aiofiles  pytesseract  pdf2image  Pillow  pandas  numpy  scipy  pymupdf
```

---

## 🚀 Instalación

```bash
git clone https://github.com/Manuuell/ojoalvoto.git
cd ojoalvoto

# Entorno virtual
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# Dependencias
pip install -r scraper/requirements.txt

# Tesseract + Poppler (solo si vas a usar el OCR clásico)
# macOS:
brew install tesseract tesseract-lang poppler
# Ubuntu:
# sudo apt install tesseract-ocr tesseract-ocr-spa poppler-utils
```

---

## 📥 Descargar las actas (PDFs)

> Los PDFs **no se versionan en git** (son ~2.9 GB y regenerables). Están en `.gitignore`. Cualquiera que clone el repo reconstruye los datos con estos scripts a partir del índice `cache/allTransmissionCodes.json`, que **sí** está en el repo.

### Opción A — Muestra de entrenamiento (toda Colombia, estratificada)

Descarga ~250 actas por departamento a `training/pdfs_train/` y reserva Tolima + Caldas completos como holdout. Genera los manifests CSV.

```bash
python training/download_training_sample.py --per-dept 250
```

| Flag | Default | Descripción |
|------|---------|-------------|
| `--per-dept` | 250 | Actas por departamento |
| `--concurrency` | 20 | Descargas en paralelo |

### Opción B — Un departamento completo

Descarga **todas** las actas de un departamento a `pdfs/{dept}/...`

```bash
python pipeline/download_dept.py --dept 60        # 60 = AMAZONAS
```

**Códigos de departamento:** `01` Antioquia · `05` Bolívar · `07` Boyacá · `09` Caldas · `11` Cauca · `15` Cundinamarca · `16` Bogotá · `23` Nariño · `29` Tolima · `31` Valle · `60` Amazonas · `88` Consulados … (lista completa en los scripts).

Ambos scripts son **idempotentes**: si un PDF ya existe y pesa >500 bytes, lo saltan, así que puedes reanudar sin re-descargar.

### Descargar resultados oficiales (PRECON)

```bash
python precon/download_precon.py     # nacional + 34 deptos + ~1.189 municipios
```

---

## 🔬 Pipeline de procesamiento

### OCR clásico (Tesseract — referencia, precisión limitada)

```bash
python pipeline/download_dept.py --dept 60     # 1. descargar
python pipeline/preprocess.py                  # 2. preprocesar imágenes
python pipeline/ocr_dept.py --dept 60          # 3. OCR → CSV en resultados/
```

> El OCR de números manuscritos rinde ~60-70%, insuficiente para auditoría. Por eso el proyecto migró a un **VLM** (Qwen2.5-VL) con validación matemática.

### Auto-etiquetado con IA (Fase 2 — Google Colab)

1. Sube `training/pdfs_train.zip` a tu Google Drive (`safevote/`).
2. Abre `training/fase2_autolabel_v2.ipynb` en **Colab Pro (A100)**.
3. Corre el notebook. Es **reanudable** y acumula entre departamentos.

**Salidas** (en Drive `safevote/`):
- `labels_sc.jsonl` — lecturas crudas con voto de mayoría
- `resultado_clean.jsonl` — actas consistentes → etiquetas para entrenar Donut
- `resultado_sospechosas.jsonl` — actas que no cuadran → revisión en la web

**Config validada** (lo que funciona, ver detalles en [PROYECTO.md](PROYECTO.md)):

| Parámetro | Valor |
|-----------|-------|
| Modelo | Qwen2.5-VL-7B |
| Resolución | `max_pixels = 2560·28·28` (~2M) — bajarla mata la precisión |
| Recorte | encabezado superior, ancho completo |
| Lectura | **self-consistency**: 3 lecturas + voto de mayoría (temp 0.3) → yield 32% → 53% |
| Validación | `suma(cand)+blanco+nulo+no_marc == suma_total` (o `== votos_urna`) |

---

## 🌐 Aplicaciones web de etiquetado

Como el techo de la IA es ~40-53%, se complementa con **etiquetado humano** (etiquetas perfectas que entrenan mejor a Donut). Hay dos versiones:

### v1 — `labeling_app/` (Flask, prototipo probado)

- Flask + Gunicorn + PostgreSQL (`app.py`) o SQLite (`app_sqlite_local.py`)
- Render del PDF en el **servidor** con PyMuPDF + caché
- Cola con bloqueo de 15 min (reparte actas sin repetir)
- Visor con **zoom por casilla** calibrado, navegación con Enter
- Reglas: `urna > votantes` o `votos > votantes` → posible inconsistencia

```bash
cd labeling_app
cp .env.example .env
docker compose up --build        # o: pip install -r requirements.txt && python app_sqlite_local.py
```

Guía de despliegue: [labeling_app/DEPLOY.md](labeling_app/DEPLOY.md).

### v2 — `safevote-web/` (stack moderno)

- **Frontend:** Next.js 14 + React + `react-pdf` (renderiza el PDF en el **navegador**)
- **Backend:** NestJS 10 + Prisma
- **DB:** PostgreSQL 16, cola con `FOR UPDATE SKIP LOCKED`
- **Infra:** Docker Compose (db + api + web) + nginx + Certbot
- Landing con estadísticas en vivo (se refrescan cada 15 s desde `/api/stats`)

```bash
cd safevote-web
cp .env.example .env
docker compose up --build        # api en :3000, web en :4500
```

**Endpoints NestJS:** `GET /api/actas/next` · `GET /api/actas/:id/pdf` · `POST /api/actas/:id/{submit,flag,skip}` · `GET /api/stats` · `GET /api/flagged`

Más detalle: [safevote-web/README.md](safevote-web/README.md).

---

## 🔌 APIs públicas descubiertas

Todas son `GET` públicos, sin autenticación (servidos por CDN, cache 60 s).

### Visor E-14 (PDFs escaneados)

```
BASE = https://divulgacione14presidente.registraduria.gov.co/assets/temis
```

| Endpoint | Descripción |
|----------|-------------|
| `/divipol_json/allTransmissionCodes.json` | **Clave:** mapeo mesa → hash SHA256 del PDF (~35 MB) |
| `/divipol_json/departmentsTree.json` | Árbol completo dept→mun→zona→puesto→mesa |
| `/divipol_json/allDepartments.json` | 34 departamentos |
| `/divipol_json/allMviewGetProgress...json` | Progreso de publicación |

**URL de un PDF E-14:**
```
GET {BASE}/pdf/{dept}/{mun}/{zona:03d}/{stand}/{mesa:03d}/PRE/{sha256}.pdf?uuid={uuid4}
```
- `sha256` = `expectedName` del `allTransmissionCodes.json`
- `zona` se rellena a 3 dígitos con `zfill(3)` para la URL (en el índice viene sin ceros)
- `uuid` es solo cache-busting, no es autenticación

### PRECON (resultados oficiales)

```
BASE = https://resultados.registraduria.gov.co/json/ACT/PR/
```
`/00.json` nacional · `/{DD}.json` departamento · `/{DD}{MMM}.json` municipio.

> PRECON **no** tiene datos por mesa (URLs de 7+ dígitos dan 404). El PDF E-14 es la única fuente a nivel de mesa.

---

## 📄 El formulario E-14

Cada acta tiene **3 páginas**:

- **Página 1** — Nivelación de la mesa (`votantes E-11`, `votos en urna`, `incinerados`) + candidatos 1-7
- **Página 2** — Candidatos 8-13 + `en blanco` / `nulos` / `no marcadas` / **SUMA TOTAL**
- **Página 3** — Firmas de jurados + ¿hubo recuento?

Los votos se escriben en celdas de **3 cajitas** `[centena][decena][unidad]`. Una casilla vacía es un **punto** (`•`) = 0:

```
[•][5][5] = 055 = 55 votos
[•][•][2] = 002 =  2 votos
[•][•][•] = 000 =  0 votos
```

Renderizado a 300 DPI: ~3705 × 10842 px.

---

## 📊 Análisis estadístico

`precon/analyze_precon.py` corre, sobre los resultados oficiales:

- **Ley de Benford** — distribución del primer dígito por departamento/candidato (anomalías con Chi² alto en Nariño, Boyacá, Cundinamarca, Cauca, Valle…)
- **Participación anormal** — municipios muy por encima/debajo del promedio nacional (57.89%)
- **Histórico del conteo** — saltos anómalos en la curva de carga de mesas

```bash
python precon/analyze_precon.py
```

> Estas anomalías estadísticas son **indicios para priorizar revisión**, no pruebas. Se cruzan con la lectura de las actas E-14 para verificar caso por caso.

---

## ⚠ Notas importantes

- **Datos pesados fuera de git.** `pdfs/`, `training/pdfs_*`, `*.pdf`, `*.zip`, `*.tar.gz` están en `.gitignore`. Se regeneran con los scripts de descarga. El índice `cache/allTransmissionCodes.json` sí se versiona porque es lo que permite reconstruir todo.
- **Uso responsable.** Trabaja solo con datos públicos. Una acta marcada es una acta a **verificar**, no una denuncia. Cualquier conclusión pública debe basarse en revisión humana de la evidencia.
- **Bitácora técnica.** El detalle de decisiones, experimentos y resultados está en **[PROYECTO.md](PROYECTO.md)**.

---

*Proyecto de auditoría ciudadana · Elección Presidencial Colombia 2026 · Datos: Registraduría Nacional del Estado Civil.*
