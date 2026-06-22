# SafeVote — Herramienta de etiquetado colaborativo E-14

App web para etiquetar actas E-14 entre varias personas, sin repetir trabajo.

## Características
- Reparte una acta pendiente por usuario (sin duplicados)
- Bloqueo temporal: si no la terminas en 15 min, se libera para otro
- Pre-llenado opcional con lecturas de IA (corriges en vez de teclear todo)
- Verificación en vivo: muestra si la suma cuadra (ayuda a evitar typos)
- Guarda en SQLite, exporta JSON para entrenar Donut
- Ranking de colaboradores

## Preparar los datos
1. Copia el manifest de actas:
   ```
   copy ..\training\manifest_train.csv manifest.csv
   ```
2. Apunta a la carpeta de PDFs (o déjalos en `pdfs/`):
   - Windows: `set PDFS_DIR=C:\Users\MANUEL\Desktop\SafeVote\training\pdfs_train`
   - Si no hay PDF local, la app lo descarga de la Registraduría usando el hash.
3. (Opcional) pre-llenado de IA: copia `labels_sc.jsonl` como `prefills.jsonl`.

## Correr local
```
pip install -r requirements.txt
set PDFS_DIR=C:\Users\MANUEL\Desktop\SafeVote\training\pdfs_train
python app.py
```
Abrir http://localhost:5000

## Exponer online (rápido) — túnel
Con la app corriendo local, en otra terminal:
```
# opción 1: cloudflared (gratis, sin cuenta)
cloudflared tunnel --url http://localhost:5000
# opción 2: ngrok
ngrok http 5000
```
Comparte el link que te dan. Varias personas etiquetan a la vez.

## Desplegar en la nube (Render / Railway, capa gratis)
- Sube esta carpeta a un repo de GitHub
- Crea un "Web Service", comando de inicio:
  ```
  gunicorn app:app
  ```
- Sube `manifest.csv`. Los PDFs se descargan on-demand de la Registraduría
  (no necesitas subir 1.4 GB), o súbelos si prefieres.

## Exportar etiquetas (para entrenar Donut)
Abrir: `http://localhost:5000/api/export` → descarga `etiquetas.json`

## Endpoints
| Ruta | Qué hace |
|---|---|
| `/` | interfaz de etiquetado |
| `/api/next` | siguiente acta sin asignar |
| `/api/submit` | guarda etiqueta |
| `/api/skip` | marca acta ilegible |
| `/api/stats` | progreso + ranking |
| `/api/export` | descarga todas las etiquetas |
