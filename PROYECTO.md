# SafeVote — Sistema de Análisis Electoral Colombia 2026
**Última actualización:** 1 junio 2026  
**Elección:** Presidente y Vicepresidente — Mayo 31 de 2026  
**Resultado oficial PRECON:** DE LA ESPRIELLA 44.51% vs CEPEDA CASTRO 41.62% (diferencia: 673.138 votos)

---

## ESTADO ACTUAL (sesión 2 — entrenamiento de modelo)

**Decisión clave:** entrenar modelo IA (Donut) para leer las 121.041 actas, en vez de OCR Tesseract (precisión insuficiente con números manuscritos).

**Estrategia de etiquetado SIN trabajo manual:**
- El E-14 tiene redundancia matemática: `suma(votos) + blanco + nulo + no_marcadas = suma_total`
- Un VLM profesor (Qwen2.5-VL-7B) lee cada acta → si la ecuación CUADRA, la etiqueta es correcta automáticamente
- Las que NO cuadran → candidatas a fraude
- Esto da miles de etiquetas limpias gratis, luego se destila a Donut (rápido) para el run completo

**Confirmado:** PRECON NO tiene datos por mesa (URLs de 7/9/11 dígitos dan 404). Solo llega a municipio. El PDF E-14 es la única fuente por mesa.

**Progreso:**
- [x] Fase 1: descarga estratificada — 7.273 actas train (250/depto) + 400 holdout (Tolima 29 + Caldas 09). En `training/pdfs_train/` y `manifest_train.csv`. ZIP: `training/pdfs_train.zip` (1.4 GB)
- [x] Notebook Fase 2 generado: `training/fase2_autolabel.ipynb` (Qwen2.5-VL-7B + validación matemática, reanudable)
- [ ] Fase 2: subir ZIP a Drive `safevote/`, correr notebook en Colab Pro A100 (~2.7h) → `labels_clean.jsonl` + `labels_review.jsonl`
- [ ] Fase 3: notebook entrenamiento Donut (PENDIENTE crear)
- [ ] Fase 4: inferencia masiva 121.041 actas
- [ ] Fase 5: dashboard web Flask con evidencia + estadísticas

**Modelo profesor elegido:** Qwen2.5-VL-7B (no 72B — el filtro matemático corrige errores igual, y 7B no quema saldo de Colab Pro). 72B-4bit solo como reintento para actas difíciles que no cuadren.

**Procesamiento por PÁGINA** (no acta completa) por aspect ratio:
- Pág 1: nivelación (votantes_e11, votos_urna, incinerados) + candidatos 1-7
- Pág 2: candidatos 8-13 + blanco/nulo/no_marcadas/suma_total
- Pág 3: firmas + ¿recuento? + tachones

**Scripts nuevos sesión 2:**
- `training/download_training_sample.py` — descarga estratificada (SEED=42, HOLDOUT=["29","09"])
- `training/make_notebook_fase2.py` — generador notebook v1 (obsoleto)
- `training/make_notebook_autolabel_v2.py` — generador notebook v2 (CONFIG VALIDADA)
- `training/fase2_autolabel_v2.ipynb` — **notebook actual a usar**

### CONFIG VALIDADA (sesión de optimización) — lo que SÍ funciona
| Parámetro | Valor | Nota |
|---|---|---|
| Modelo | Qwen2.5-VL-7B | gratis, corre en A100 |
| Resolución | `max_pixels=2560*28*28` (~2M) | **bajarla mata la precisión** |
| Recorte | solo encabezado superior, ANCHO COMPLETO (TOP_P1=0.15, TOP_P2=0.10) | recortar la columna pierde contexto y baja precisión |
| Prompt | regla explícita de PUNTOS (`• • •`=0, nunca 3) | error sistemático arreglado |
| Lectura | **self-consistency: 3 lecturas + voto mayoría** (temp=0.3) | **yield 32% → 53%** |
| Validación | `suma(cand)+blanco+nulo+nomarc == suma_total` (o == votos_urna) | exacta = etiqueta limpia |

### Progresión del yield (50 actas, mismas)
```
v1 básico (1M, prompt simple):        24%
v2 alta-res + recorte encabezado:     ~32-36%
v3 + regla de puntos en prompt:       ~32% (45% en muestra de 20)
v6/v7 recorte columna + baja-res:     17%  ← PEOR (perdió contexto)
v8 self-consistency (3x + voto):      53%  ← GANADOR
```

### Lo que NO funcionó (no reintentar)
- **Recortar la columna de votos** → pierde nombres/contexto → 17% (vs 32% página completa)
- **Bajar resolución** (800k-1.5M) → dígitos muy chicos → 17%
- **Batching** → NO acelera (GPU saturada por imagen alta-res) Y baja yield (padding) + OOM en batch 6
- **max_new_tokens bajo** → no era el cuello de botella (el costo es procesar la imagen)

### Velocidad real (techo)
- 1 lectura: ~0.11 pág/s, yield 32%
- Self-consistency (3x): ~0.04 pág/s efectivo, ~74 actas/hora, yield 53%
- Labelar 121.041 con Qwen = días → POR ESO se necesita Donut al final

### INSIGHT ESTRATÉGICO CLAVE
Las actas que **NO cuadran tras self-consistency** = candidatas a FRAUDE REAL (el ruido de lectura de la IA ya fue removido por el voto). Esto ES el detector de fraude. → Usar el lector preciso directo sobre departamentos sospechosos + construir web, SIN esperar a Donut. Donut queda para escalar a las 121.041 después.

### Plan acordado con el usuario
1. Consolidar config en notebook v2 ✅
2. Seguir mejorando detección de la IA (iterar)
3. Procesar varios departamentos sospechosos (Cauca-11, Nariño-23, Boyacá-07, Cundinamarca-15, Valle-31)
4. Construir página web de auditoría (`resultado_sospechosas.jsonl` → dashboard)
5. Al final: entrenar Donut con `resultado_clean.jsonl` para las 121.041

### HERRAMIENTA DE ETIQUETADO COLABORATIVO (labeling_app/) — NUEVA
Decisión: en vez de seguir peleando con el yield de Qwen/GPT (~40-43% techo, ni pagando GPT-4o mejora — los errores son de visión), **etiquetar a mano con ayuda colaborativa**. Etiquetas humanas = perfectas → entrenan Donut bien.

**App web de etiquetado** (`labeling_app/`):
- Reparte actas sin repetir (cola con bloqueo 15 min)
- Visor con ZOOM por casilla: al enfocar un campo, la imagen hace zoom/pan a esa casilla (mapa calibrado en label.html DEFMAP)
- Enter = siguiente campo; en SUMA TOTAL si cuadra → siguiente acta; al pasar de acta foco va a votantes_e11 con zoom
- Validación: usa VOTOS EN URNA como referencia (NO suma_total, que los jurados escriben mal)
- Reglas de fraude automáticas: urna > votantes, o votos > votantes (relleno de urna)
- Botón "Marcar posible fraude" → guarda en BD (flagged=TRUE)
- Stats con gráficas (dona, barras, ranking), pantalla intro explicando el proyecto, tema Elecciones 2026
- Modo calibración: clic en cada casilla para fijar posiciones exactas

**Stack de PRODUCCIÓN — DOS versiones:**

*v1 Flask (labeling_app/)* — prototipo funcional, ya probado local:
- Flask + Gunicorn + PostgreSQL (psycopg2) + PyMuPDF render servidor + caché. `app.py` prod, `app_sqlite_local.py` backup. Render de imagen en el SERVIDOR.

*v2 MODERNA (safevote-web/)* — la que el usuario pidió (NestJS + framework):
- **Frontend: Next.js 14 + React + react-pdf** (renderiza el PDF en el NAVEGADOR, no el servidor)
- **Backend: NestJS 10 + Prisma** (ORM) — modular, tipado
- **DB: PostgreSQL 16** · cola con `FOR UPDATE SKIP LOCKED`
- **Infra: Docker Compose** (db + api + web) + nginx host + Certbot TLS
- Estructura: `api/` (NestJS: actas.service/controller/module, prisma, seed.ts, Dockerfile), `web/` (Next: app/page.tsx labeling UI, layout, Dockerfile), `docker-compose.yml`, `nginx/safevote.conf`, `README.md`
- Endpoints NestJS: GET /api/actas/next, GET /api/actas/:id/pdf, POST /api/actas/:id/{submit,flag,skip}, GET /api/stats, GET /api/flagged
- PROBADO: docker compose levanta db+api+web OK. API carga 7273 actas, todas las rutas mapeadas. Frontend corre en localhost:4500 (3000/3001 estaban ocupados por otros contenedores del usuario).
- Landing rediseñada: tema CLARO profesional (blanco, azul institucional, bandera CO), secciones (hero, "así va la verificación" con gráficas en vivo dona+tarjetas, cómo funciona, por qué importa), stats se refrescan cada 15s desde /api/stats.
- MAP de zoom CALIBRADO y baked en DEFMAP de page.tsx (el usuario calibró clic por clic con el modo 🎯 Calibrar). Modo calibración disponible (localStorage e14map_v2).
- Validación usa votos_urna (no suma_total). Reglas fraude: urna>votantes, votos>votantes.
- Reconstruir web (docker compose up --build web) es lento (~2-3 min); para iterar diseño rápido convendría modo dev (next dev + volumen) — no configurado aún.
- Plan: subir a VPS + dominio. Guía en README.md y labeling_app/DEPLOY.md

### Archivos de salida del notebook v2 (en Drive safevote/)
- `labels_sc.jsonl` — lecturas crudas con voto (reanudable, acumula entre deptos)
- `resultado_clean.jsonl` — actas CONSISTENTES (etiquetas para Donut)
- `resultado_sospechosas.jsonl` — actas que NO cuadran (candidatas fraude → web)

---

## RESULTADO DE LA ELECCION (PRECON FINAL)

| Candidato | Votos | % |
|---|---|---|
| ABELARDO DE LA ESPRIELLA (codcan=4) | 10.361.499 | 44.51% |
| IVÁN CEPEDA CASTRO (codcan=1) | 9.688.361 | 41.62% |
| PALOMA VALENCIA (codcan=11) | 1.639.685 | 7.04% |
| SERGIO FAJARDO (codcan=12) | 1.009.073 | 4.33% |
| CLAUDIA LÓPEZ (codcan=2) | 225.517 | 0.97% |
| BOTERO JARAMILLO (codcan=3) | 206.140 | 0.89% |
| + 7 candidatos menores | ... | ... |

**Total votantes:** 23.978.304 (57.89% del censo de 41.421.973)  
**Total mesas:** 122.020  
**Mesas publicadas:** 121.041 (99.2%)

---

## APIs DESCUBIERTAS

### 1. Visor E-14 (PDFs de actas escaneadas)
```
BASE: https://divulgacione14presidente.registraduria.gov.co/assets/temis/
```

#### JSONs estáticos (sin autenticación)
| Archivo | Descripción | Tamaño |
|---|---|---|
| `/divipol_json/allDepartments.json` | Lista 34 departamentos | pequeño |
| `/divipol_json/allCorporations.json` | Corporación PRESIDENTE | pequeño |
| `/divipol_json/departmentsTree.json` | Árbol completo dept→mun→zona→puesto→mesas | 299KB gz |
| `/divipol_json/allTransmissionCodes.json` | **CLAVE:** mapeo mesa→hash SHA256 del PDF | 5.9MB gz / 34.7MB raw |
| `/divipol_json/allMviewGetProgressByDepartmentAndCorporations.json` | Progreso por depto | 1KB |
| `/divipol_json/allMviewGetProgressByMunicipalityAndCorporations.json` | Progreso por municipio | 19KB |
| `/divipol_json/CorpIndexAndMap.json` | Corporaciones + mapa ganadores | 1KB |

#### URL de los PDFs E-14
```
GET /assets/temis/pdf/{dept}/{mun}/{zone_padded3}/{stand}/{table:03d}/PRE/{sha256}.pdf?uuid={uuid4_aleatorio}

Ejemplo real:
/assets/temis/pdf/05/001/021/03/004/PRE/93ce73e701b99b82fdd5e96c0a164b211ab039c175045459b5978117990f94b5.pdf

Donde:
  dept        = idDepartmentCode (ej: "05" = BOLIVAR)
  mun         = municipalityCode (ej: "001")
  zone_padded = idZoneCode con ceros a 3 dígitos (ej: "021") — en índice viene sin ceros "21"
  stand       = standCode (ej: "03")
  table       = numberStand del índice (ej: "004")
  sha256      = expectedName del allTransmissionCodes.json (sin ".pdf")
  uuid        = cualquier UUID v4 generado al azar (solo cache-busting, NO es auth)
```

#### Estructura del allTransmissionCodes.json
```json
{
  "data": {
    "status11": { "nodes": [ ... ] },  // 120.801 registros = E14 escaneados
    "status3":  { "nodes": [ ... ] }   // 240 registros = fotos especiales
  }
}
// Total: 121.041 = exactamente las actas publicadas

// Cada nodo:
{
  "idTransmissionCode": "3497118",
  "numberStand": "027",           // ← número de mesa con ceros "027"
  "expectedName": "bf247ca2...41.pdf",  // ← SHA256 del PDF
  "idTransmissionCodeStatus": 11,
  "idCorporationCode": "001",
  "idStand": "000011815",
  "standCode": "00",
  "idZoneCode": "00",             // ← SIN padding (usar .zfill(3) para la URL)
  "idDepartmentCode": "15",
  "municipalityCode": "118"
}

// Clave del índice:
key = f"{idDepartmentCode}/{municipalityCode}/{idZoneCode}/{standCode}/{numberStand}"
// Ejemplo: "05/001/21/03/004"  (zona SIN padding)
// URL usa: "05/001/021/03/004" (zona CON padding zfill(3))
```

### 2. PRECON — Resultados oficiales
```
BASE: https://resultados.registraduria.gov.co/json/ACT/PR/
```

| URL | Nivel |
|---|---|
| `/00.json` | Nacional |
| `/{DD}.json` | Departamento (2 dígitos, ej: "60") |
| `/{DD}{MMM}.json` | Municipio (5 dígitos, ej: "60001" = Leticia) |
| `/{DD}{MMM}{ZZ}.json` | Zona (7 dígitos) — pendiente confirmar |

**IMPORTANTE:** Requiere cookie de sesión del browser. Desde Python funciona sin problemas (no hay auth real).

#### Estructura del JSON PRECON
```json
{
  "elec": "1",
  "amb": "60001",        // código del ámbito
  "dept": "60",
  "totales": {
    "act": {
      "metota": "134",   // total mesas esperadas
      "mesesc": "134",   // mesas escrutadas
      "centota": "20991",// censo electoral
      "votant": "20991", // votantes que votaron
      "votnul": "203",   // nulos
      "votnma": "73",    // no marcadas
      "votblan": "401",  // en blanco
      "votval": "20715"  // votos válidos
    }
  },
  "camaras": [{
    "partotabla": [{
      "act": {
        "codpar": "10",
        "cantotabla": [{
          "codcan": "4",        // código candidato
          "nomcan": "ABELARDO",
          "apecan": "DE LA ESPRIELLA",
          "vot": "10415"        // votos en este ámbito
        }]
      }
    }]
  }],
  "mapagan": [...],    // ganador por sub-ámbito (municipios si es dept)
  "historico": [...]   // snapshots cada 5 minutos del conteo
}
```

#### Códigos de candidatos (codcan)
| codcan | Nombre |
|---|---|
| 1 | IVÁN CEPEDA CASTRO |
| 2 | CLAUDIA LÓPEZ |
| 3 | RAÚL SANTIAGO BOTERO JARAMILLO |
| 4 | ABELARDO DE LA ESPRIELLA |
| 5 | ÓSCAR MAURICIO LIZCANO ARANGO |
| 6 | MIGUEL URIBE LONDOÑO |
| 7 | SONDRA MACOLLINS GARVIN PINTO |
| 8 | ROY LEONARDO BARRERAS MONTEALEGRE |
| 9 | CARLOS EDUARDO CAICEDO OMAR |
| 10 | GUSTAVO MATAMOROS CAMACHO |
| 11 | PALOMA VALENCIA LASERNA |
| 12 | SERGIO FAJARDO VALDERRAMA |
| 13 | LUIS GILBERTO MURILLO URRUTIA |

---

## ESTRUCTURA DEL FORMULARIO E-14

El acta física tiene **3 páginas**:

**Página 1:** Cabecera + candidatos 1-7
- NIVELACIÓN DE LA MESA:
  - TOTAL VOTANTES FORMULARIO E-11 = votantes que llegaron a votar
  - TOTAL VOTOS EN LA URNA = votos contados
  - TOTAL VOTOS INCINERADOS = votos destruidos
- Tabla candidatos 1-7 con columna VOTACIÓN (3 celdas: [centenas][decenas][unidades])
- Celdas vacías = punto (•) = cero

**Página 2:** Candidatos 8-13 + SUMA TOTAL
- SUMA TOTAL (CANDIDATOS + EN BLANCO + NULOS + NO MARCADOS) = total sufragantes

**Página 3:** Firmas de jurados + ¿HUBO RECUENTO DE VOTOS?

**Formato de votos:** Las celdas de votación usan 3 cajitas donde:
- `[•][5][5]` = 055 = 55 votos
- `[•][•][2]` = 002 = 2 votos  
- `[•][•][•]` = 000 = 0 votos

**Dimensiones del PDF renderizado a 300 DPI:** ~3705 × 10842 px

---

## ANÁLISIS ESTADÍSTICO REALIZADO

### Ley de Benford — Anomalías detectadas (Chi2 > 15.5)
| Departamento | Candidato | Chi2 | Estado |
|---|---|---|---|
| NARIÑO | DE LA ESPRIELLA | 30.65 | *** ANOMALÍA (2x umbral) |
| BOYACÁ | DE LA ESPRIELLA | 23.61 | *** ANOMALÍA |
| CUNDINAMARCA | DE LA ESPRIELLA | 23.48 | *** ANOMALÍA |
| CAUCA | CEPEDA CASTRO | 22.11 | *** ANOMALÍA |
| NARIÑO | CEPEDA CASTRO | 20.12 | *** ANOMALÍA |
| VALLE | CEPEDA CASTRO | 18.58 | *** ANOMALÍA |
| NORTE SANTANDER | DE LA ESPRIELLA | 16.65 | *** ANOMALÍA |
| VALLE | DE LA ESPRIELLA | 15.88 | *** ANOMALÍA |

### Participación anormal
- **Municipio 11006 (ALMAGUER, Cauca):** 81.6% — 25 pts sobre promedio nacional
- **CONSULADOS 88815:** 12% — muy baja
- Promedio nacional: 57.89%

### Histórico del conteo
- 2 saltos anómalos detectados:
  - Snap 10 (~4:48pm): +18.002 mesas en 5 minutos
  - Snap 11 (~4:53pm): +17.326 mesas en 5 minutos
  - Total: 35.328 mesas (29%) cargadas en 10 minutos

### Actas sin E14 escaneado (fotos o faltantes)
| Departamento | Sin verificar | % |
|---|---|---|
| CONSULADOS | 2.644 | 72.0% |
| VAUPES | 41 | 46.6% |
| VICHADA | 75 | 38.1% |
| GUAINIA | 26 | 22.2% |
| AMAZONAS | 25 | 14.2% |
| GUAVIARE | 35 | 15.8% |

---

## ARCHIVOS DESCARGADOS

```
SafeVote/
├── cache/
│   ├── allMviewGetProgressByDepartmentAndCorporations.json
│   ├── allTransmissionCodes.json    (34.7 MB — índice de 121.041 PDFs)
│   └── departmentsTree.json         (árbol completo de mesas)
├── pdfs/
│   └── 60/                          (151 PDFs de AMAZONAS — 13.7 MB)
├── precon/
│   └── cache/
│       ├── 00.json                  (nacional)
│       ├── 01.json ... 88.json      (34 departamentos)
│       └── 01001.json ... 88xxx.json (1.189 municipios)
│       TOTAL: 1.224 JSONs descargados
└── resultados/
    └── ocr_dept_60.csv              (OCR de Amazonas — obsoleto, usar PRECON)
```

---

## ESTADO DEL CÓDIGO

### Scripts funcionales
| Script | Función |
|---|---|
| `scraper/registraduria_client.py` | Descarga PDFs usando índice de hashes |
| `pipeline/download_dept.py` | Descarga PDFs de un departamento |
| `pipeline/ocr_dept.py` | OCR de PDFs (Tesseract) — precisión ~60-70% |
| `pipeline/preprocess.py` | Preprocesamiento de imágenes para OCR |
| `precon/download_precon.py` | Descarga todos los JSONs PRECON |
| `precon/analyze_precon.py` | Análisis estadístico completo |
| `analyze_now.py` | Análisis rápido de progreso |
| `run_pipeline.py` | Orquestador (descarga + OCR) |

### Dependencias instaladas
```
httpx, pdf2image, pytesseract, Pillow, pandas, numpy, scipy, pymupdf, fitz
Tesseract v5.4.0 + spa.traineddata
```

---

## PRÓXIMOS PASOS (en orden de prioridad)

### 1. Analizador IA de formularios (PRIORIDAD ALTA)
Crear `ai_analyzer/form_analyzer.py` que por cada PDF:
- Extraiga votos con coordenadas fijas (el layout E-14 es siempre igual)
- Detecte tachones con OpenCV (líneas sobre celdas)
- Verifique coherencia matemática interna
- Compare contra PRECON del municipio
- Genere JSON de resultados con evidencia fotográfica

### 2. Dashboard web
Crear `web/app.py` (Flask) con:
- Mapa de Colombia con anomalías por color
- Tabla de formularios sospechosos con filtros
- Vista individual de cada acta con anotaciones
- Estadísticas generales

### 3. Departamentos prioritarios para análisis
Por orden de anomalías detectadas:
1. **NARIÑO** (3.840 actas) — Benford anómalo en AMBOS candidatos
2. **VALLE** (11.035 actas) — Benford anómalo en AMBOS candidatos  
3. **BOYACÁ** (3.126 actas) — Benford anómalo Espriella
4. **CUNDINAMARCA** (6.916 actas) — Benford anómalo Espriella
5. **CAUCA** (3.427 actas) — Benford + municipio 11006 con 81.6% participación

### 4. Coordenadas fijas del E-14 (pendiente calibrar)
Para extracción precisa de votos sin OCR complejo.
Necesita: coordenadas pixel de celda de votos candidato 1 en imagen 300 DPI.

---

## CONTEXTO TÉCNICO

- **Python 3.13** en Windows 11
- **Trabajar siempre desde:** `C:\Users\MANUEL\Desktop\SafeVote`
- **CMD** (no PowerShell) para comandos del usuario
- Siempre poner `set PYTHONIOENCODING=utf-8` antes de correr Python
- `set PATH=%PATH%;C:\Program Files\Tesseract-OCR` para OCR
- El sitio de la Registraduría bloquea peticiones Python directas (timeout) — usar browser para descargar JSONs grandes
- Los PDFs se pueden descargar con Python sin problema (no bloquea)
