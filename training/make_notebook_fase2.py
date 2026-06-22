"""
Genera fase2_autolabel.ipynb — notebook de Colab para auto-etiquetar actas E-14
con Qwen2.5-VL-7B + filtro de validacion matematica.

Correr: python training/make_notebook_fase2.py
Resultado: training/fase2_autolabel.ipynb  (subir a Google Colab)
"""
import json
from pathlib import Path

# ─────────────────────────────────────────────────────────────
# Cada elemento = una celda. ("md", texto) o ("code", texto)
# ─────────────────────────────────────────────────────────────
CELLS = []

CELLS.append(("md", r"""# SafeVote — Fase 2: Auto-etiquetado de actas E-14
**Modelo profesor:** Qwen2.5-VL-7B-Instruct
**Objetivo:** leer cada acta y producir JSON de votos, validado con la matemática interna del formulario.

### Antes de empezar
1. Runtime → Change runtime type → **GPU (A100 recomendado)**
2. Sube `pdfs_train.zip` a tu Google Drive en la carpeta `safevote/`
3. Ejecuta las celdas en orden.

El proceso es **reanudable**: si Colab se desconecta, vuelve a correr la celda del bucle y continúa donde quedó.
"""))

CELLS.append(("code", r"""# 1) Verificar GPU
!nvidia-smi"""))

CELLS.append(("code", r"""# 2) Instalar dependencias
!pip install -q transformers==4.49.0 accelerate qwen-vl-utils pymupdf
print("OK")"""))

CELLS.append(("code", r"""# 3) Montar Google Drive
from google.colab import drive
drive.mount('/content/drive')

import os
DRIVE = '/content/drive/MyDrive/safevote'
os.makedirs(DRIVE, exist_ok=True)
print("Drive montado. Carpeta de trabajo:", DRIVE)
print("Contenido:", os.listdir(DRIVE) if os.path.exists(DRIVE) else "vacia")"""))

CELLS.append(("code", r"""# 4) Descomprimir los PDFs (subidos a Drive como pdfs_train.zip)
import zipfile, os, time

ZIP_PATH = f'{DRIVE}/pdfs_train.zip'
WORK = '/content/data'
os.makedirs(WORK, exist_ok=True)

if not os.path.exists(f'{WORK}/manifest_train.csv'):
    t0 = time.time()
    with zipfile.ZipFile(ZIP_PATH) as z:
        z.extractall(WORK)
    print(f"Descomprimido en {time.time()-t0:.0f}s")
else:
    print("Ya descomprimido")

# Localizar manifest y carpeta de pdfs
for root, dirs, files in os.walk(WORK):
    if 'manifest_train.csv' in files:
        print("manifest:", os.path.join(root, 'manifest_train.csv'))
    break
print(os.listdir(WORK))"""))

CELLS.append(("code", r"""# 5) Cargar manifest
import pandas as pd, glob

manifest_path = glob.glob(f'{WORK}/**/manifest_train.csv', recursive=True)[0]
df = pd.read_csv(manifest_path, dtype=str)
df = df[df['ok'] == 'True'].reset_index(drop=True)

# Corregir rutas: el manifest tiene rutas Windows; reconstruir a la ruta de Colab
def fix_path(p):
    # p ejemplo: training/pdfs_train/01/01_001_..._.pdf
    name = p.replace('\\','/').split('/')[-1]
    dept = p.replace('\\','/').split('/')[-2]
    cands = glob.glob(f'{WORK}/**/{dept}/{name}', recursive=True)
    return cands[0] if cands else None

df['colab_path'] = df['path'].apply(fix_path)
df = df[df['colab_path'].notna()].reset_index(drop=True)
print(f"Actas con PDF localizado: {len(df)}")
df.head(3)"""))

CELLS.append(("code", r"""# 6) Cargar modelo Qwen2.5-VL-7B
import torch
from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor
from qwen_vl_utils import process_vision_info

MODEL_ID = "Qwen/Qwen2.5-VL-7B-Instruct"
model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
    MODEL_ID, torch_dtype=torch.bfloat16, device_map="auto"
)
# Limitar resolucion para velocidad (suficiente para digitos manuscritos)
processor = AutoProcessor.from_pretrained(
    MODEL_ID, min_pixels=256*28*28, max_pixels=1280*28*28
)
print("Modelo cargado.")"""))

CELLS.append(("code", r'''# 7) Renderizar paginas del PDF a imagen
import fitz
from PIL import Image

def render_page(pdf_path, page_num, dpi=200):
    doc = fitz.open(pdf_path)
    if page_num >= len(doc):
        doc.close()
        return None
    page = doc[page_num]
    mat = fitz.Matrix(dpi/72, dpi/72)
    pix = page.get_pixmap(matrix=mat)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    doc.close()
    return img'''))

CELLS.append(("code", r'''# 8) Prompts E-14 (pagina 1 y pagina 2)
PROMPT_P1 = """Eres experto en leer actas electorales colombianas E-14 (elecciones presidenciales 2026).
Esta es la PAGINA 1. Contiene:
A) Seccion "NIVELACION DE LA MESA" con 3 numeros manuscritos:
   - TOTAL VOTANTES FORMULARIO E-11
   - TOTAL VOTOS EN LA URNA
   - TOTAL VOTOS INCINERADOS
B) Tabla de candidatos 1 a 7 con su votacion.

REGLAS DE LECTURA:
- Los votos estan en casillas de 3 digitos: [centena][decena][unidad].
- Una casilla con un punto (.) o vacia = CERO.
- Ejemplos: ". 6 4" = 64 ; ". . 2" = 2 ; ". . ." = 0 ; "1 4 9" = 149.
- Lee con cuidado los numeros MANUSCRITOS.

Candidatos pagina 1, EN ORDEN:
1 IVAN CEPEDA CASTRO
2 CLAUDIA LOPEZ
3 RAUL SANTIAGO BOTERO JARAMILLO
4 ABELARDO DE LA ESPRIELLA
5 OSCAR MAURICIO LIZCANO ARANGO
6 MIGUEL URIBE LONDONO
7 SONDRA MACOLLINS GARVIN PINTO

Responde SOLO con este JSON (sin texto extra, sin ```):
{"votantes_e11": 0, "votos_urna": 0, "incinerados": 0, "votos": {"cepeda": 0, "claudia": 0, "botero": 0, "espriella": 0, "lizcano": 0, "uribe": 0, "sondra": 0}}"""

PROMPT_P2 = """Eres experto en leer actas electorales colombianas E-14 (elecciones presidenciales 2026).
Esta es la PAGINA 2. Contiene:
A) Tabla de candidatos 8 a 13 con su votacion.
B) VOTOS EN BLANCO, VOTOS NULOS, TARJETAS NO MARCADAS.
C) SUMA TOTAL (candidatos + blanco + nulos + no marcadas).

REGLAS DE LECTURA:
- Votos en casillas de 3 digitos [centena][decena][unidad].
- Punto (.) o casilla vacia = CERO. Ejemplos: ". 6 4"=64 ; ". . 2"=2 ; ". . ."=0.
- Lee con cuidado los numeros MANUSCRITOS.

Candidatos pagina 2, EN ORDEN:
8 ROY LEONARDO BARRERAS MONTEALEGRE
9 CARLOS EDUARDO CAICEDO OMAR
10 GUSTAVO MATAMOROS CAMACHO
11 PALOMA VALENCIA LASERNA
12 SERGIO FAJARDO VALDERRAMA
13 LUIS GILBERTO MURILLO URRUTIA

Responde SOLO con este JSON (sin texto extra, sin ```):
{"votos": {"barreras": 0, "caicedo": 0, "matamoros": 0, "paloma": 0, "fajardo": 0, "murillo": 0}, "blanco": 0, "nulo": 0, "no_marcadas": 0, "suma_total": 0}"""

def query_model(img, prompt, max_new_tokens=400):
    messages = [{"role":"user","content":[
        {"type":"image","image": img},
        {"type":"text","text": prompt},
    ]}]
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    image_inputs, _ = process_vision_info(messages)
    inputs = processor(text=[text], images=image_inputs, padding=True, return_tensors="pt").to(model.device)
    with torch.no_grad():
        gen = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
    trimmed = [o[len(i):] for i,o in zip(inputs.input_ids, gen)]
    return processor.batch_decode(trimmed, skip_special_tokens=True)[0]'''))

CELLS.append(("code", r'''# 9) Parseo robusto del JSON que devuelve el modelo
import json, re

def parse_json(text):
    text = text.strip()
    # quitar fences si los hay
    text = re.sub(r'^```(json)?', '', text).strip()
    text = re.sub(r'```$', '', text).strip()
    # tomar del primer { al ultimo }
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None'''))

CELLS.append(("code", r'''# 10) Bucle principal REANUDABLE
import json, os, time

OUT = f'{DRIVE}/labels_raw.jsonl'

# Cargar ya procesados (reanudacion)
done = set()
if os.path.exists(OUT):
    with open(OUT) as f:
        for line in f:
            try:
                r = json.loads(line)
                done.add((r['acta_id'], r['page']))
            except: pass
print(f"Ya procesados: {len(done)} (acta,pagina)")

t0 = time.time()
n = 0
with open(OUT, 'a') as fout:
    for _, row in df.iterrows():
        acta_id = row['acta_id']
        pdf = row['colab_path']
        for page_num, prompt, tag in [(0, PROMPT_P1, 'p1'), (1, PROMPT_P2, 'p2')]:
            if (acta_id, tag) in done:
                continue
            try:
                img = render_page(pdf, page_num)
                if img is None:
                    continue
                raw = query_model(img, prompt)
                parsed = parse_json(raw)
                rec = {"acta_id": acta_id, "dept": row['dept'], "page": tag,
                       "parsed": parsed, "raw": raw[:300]}
            except Exception as e:
                rec = {"acta_id": acta_id, "dept": row['dept'], "page": tag,
                       "parsed": None, "error": str(e)[:200]}
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fout.flush()
            n += 1
            if n % 50 == 0:
                rate = n/(time.time()-t0)
                print(f"  {n} paginas | {rate:.2f} pag/s | acta {acta_id}")
print(f"LISTO. {n} paginas nuevas en {(time.time()-t0)/60:.1f} min")'''))

CELLS.append(("code", r'''# 11) Merge pagina1+pagina2 + VALIDACION MATEMATICA
import json
from collections import defaultdict

raw = defaultdict(dict)
with open(OUT) as f:
    for line in f:
        r = json.loads(line)
        if r.get('parsed'):
            raw[r['acta_id']][r['page']] = (r['parsed'], r['dept'])

clean, review = [], []
for acta_id, pages in raw.items():
    if 'p1' not in pages or 'p2' not in pages:
        continue
    p1, dept = pages['p1']
    p2, _ = pages['p2']
    try:
        v = {**p1.get('votos',{}), **p2.get('votos',{})}
        cand_sum = sum(int(v.get(k,0) or 0) for k in
            ['cepeda','claudia','botero','espriella','lizcano','uribe','sondra',
             'barreras','caicedo','matamoros','paloma','fajardo','murillo'])
        blanco = int(p2.get('blanco',0) or 0)
        nulo   = int(p2.get('nulo',0) or 0)
        nomarc = int(p2.get('no_marcadas',0) or 0)
        suma   = int(p2.get('suma_total',0) or 0)
        urna   = int(p1.get('votos_urna',0) or 0)

        total_calc = cand_sum + blanco + nulo + nomarc
        # VALIDACION: la ecuacion interna debe cuadrar exacto
        cuadra_suma = (total_calc == suma and suma > 0)
        cuadra_urna = (total_calc == urna and urna > 0)

        rec = {"acta_id": acta_id, "dept": dept, "votos": v,
               "blanco": blanco, "nulo": nulo, "no_marcadas": nomarc,
               "suma_total": suma, "votos_urna": urna,
               "votantes_e11": int(p1.get('votantes_e11',0) or 0),
               "incinerados": int(p1.get('incinerados',0) or 0),
               "total_calculado": total_calc}

        if cuadra_suma or cuadra_urna:
            rec["validacion"] = "OK"
            clean.append(rec)
        else:
            rec["validacion"] = "NO_CUADRA"
            rec["diferencia"] = total_calc - suma
            review.append(rec)
    except Exception as e:
        review.append({"acta_id": acta_id, "error": str(e)})

# Guardar
with open(f'{DRIVE}/labels_clean.jsonl','w') as f:
    for r in clean: f.write(json.dumps(r, ensure_ascii=False)+"\n")
with open(f'{DRIVE}/labels_review.jsonl','w') as f:
    for r in review: f.write(json.dumps(r, ensure_ascii=False)+"\n")

print(f"Actas validadas (CLEAN): {len(clean)}")
print(f"Actas en revision (NO cuadra / fraude?): {len(review)}")
print(f"Yield: {len(clean)/(len(clean)+len(review))*100:.1f}%")'''))

CELLS.append(("code", r'''# 12) Estadisticas del etiquetado
import pandas as pd
cdf = pd.DataFrame(clean)
print("=== ETIQUETAS LIMPIAS POR DEPARTAMENTO ===")
print(cdf['dept'].value_counts().sort_index())
print(f"\nTotal limpias: {len(cdf)}")
print("\nEstas son las etiquetas validadas para entrenar Donut (Fase 3).")
print("Las de labels_review.jsonl son candidatas a inconsistencia/fraude.")'''))


def build_notebook(cells):
    nb_cells = []
    for kind, src in cells:
        lines = src.split("\n")
        source = [l + "\n" for l in lines[:-1]] + [lines[-1]]
        if kind == "md":
            nb_cells.append({"cell_type":"markdown","metadata":{},"source":source})
        else:
            nb_cells.append({"cell_type":"code","metadata":{},
                             "execution_count":None,"outputs":[],"source":source})
    return {
        "cells": nb_cells,
        "metadata": {
            "accelerator":"GPU",
            "colab":{"provenance":[],"gpuType":"A100"},
            "kernelspec":{"display_name":"Python 3","name":"python3"},
            "language_info":{"name":"python"}
        },
        "nbformat":4,"nbformat_minor":0
    }


if __name__ == "__main__":
    nb = build_notebook(CELLS)
    out = Path("training/fase2_autolabel.ipynb")
    out.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Notebook generado: {out}")
    print(f"Celdas: {len(CELLS)}")
