"""
Genera fase2_autolabel_v2.ipynb — notebook consolidado con TODA la config validada.

Hallazgos incorporados (sesion de optimizacion 1 jun 2026):
  - Modelo: Qwen2.5-VL-7B
  - Resolucion ALTA (max_pixels=2560*28*28 ~2M) → dígitos legibles  [clave: bajar res mata precisión]
  - Recorte SOLO del encabezado superior (full width) → recortar la columna pierde contexto y BAJA precisión
  - Prompt con regla explícita de PUNTOS (• • • = 0, nunca 3)
  - SELF-CONSISTENCY: 3 lecturas + voto por mayoría → yield 32% → 53%
  - Validación matemática: suma candidatos + blanco+nulo+no_marcadas == suma_total (o == votos_urna)
  - Las actas que NO cuadran tras self-consistency = candidatas a FRAUDE real (ruido de IA ya removido)

Correr: python training/make_notebook_autolabel_v2.py
Resultado: training/fase2_autolabel_v2.ipynb  (subir a Colab)
"""
import json
from pathlib import Path

CELLS = []

CELLS.append(("md", r"""# SafeVote — Auto-etiquetado E-14 v2 (config validada)

**Lector preciso:** Qwen2.5-VL-7B + alta resolución + self-consistency (3 lecturas + voto).

### Resumen de la config (lo que funciona)
| Parámetro | Valor | Por qué |
|---|---|---|
| Resolución | max_pixels ~2M | bajarla mata la precisión |
| Recorte | solo encabezado superior (ancho completo) | recortar la columna pierde el contexto de candidatos |
| Prompt | regla explícita de puntos | "• • •" = 0, nunca 3 |
| Lectura | 3x + voto por mayoría | yield 32% → 53% |
| Validación | suma interna == total | exacta = etiqueta limpia |

### Resultado esperado
- ~53% de actas **cuadran** → etiquetas limpias (consistentes)
- ~47% **no cuadran** → candidatas a inconsistencia / fraude real

### Antes de empezar
1. Runtime → GPU **A100**
2. `pdfs_train.zip` en tu Drive en `safevote/`
3. Ejecuta en orden. El bucle es **reanudable**.
"""))

CELLS.append(("code", "# 1) GPU\n!nvidia-smi"))

CELLS.append(("code", '# 2) Dependencias\n!pip install -q transformers==4.49.0 accelerate qwen-vl-utils pymupdf\nprint("OK")'))

CELLS.append(("code", r"""# 3) Montar Drive
from google.colab import drive
drive.mount('/content/drive')
import os
DRIVE = '/content/drive/MyDrive/safevote'
os.makedirs(DRIVE, exist_ok=True)
print("Drive:", DRIVE, "->", os.listdir(DRIVE) if os.path.exists(DRIVE) else "vacia")"""))

CELLS.append(("code", r"""# 4) Descomprimir PDFs (reanudable: si ya estan, no hace nada)
import zipfile, os, time
WORK = '/content/data'
os.makedirs(WORK, exist_ok=True)
if not os.path.exists(f'{WORK}/manifest_train.csv') and not os.path.exists(f'{WORK}/pdfs_train'):
    t0=time.time()
    with zipfile.ZipFile(f'{DRIVE}/pdfs_train.zip') as z: z.extractall(WORK)
    print(f"Descomprimido en {time.time()-t0:.0f}s")
else:
    print("Ya descomprimido")
print(os.listdir(WORK))"""))

CELLS.append(("code", r"""# 5) Cargar manifest -> df (rapido)
import pandas as pd, os, glob
manifest_path = glob.glob(f'{WORK}/**/manifest_train.csv', recursive=True)[0]
df = pd.read_csv(manifest_path, dtype=str)
df = df[df['ok']=='True'].reset_index(drop=True)
df['colab_path'] = df.apply(lambda r: f"{WORK}/pdfs_train/{r['dept']}/{r['acta_id']}.pdf", axis=1)
df = df[df['colab_path'].apply(os.path.exists)].reset_index(drop=True)
print(f"Actas disponibles: {len(df)}")
print("Por departamento:"); print(df['dept'].value_counts().sort_index())"""))

CELLS.append(("code", r"""# 6) Cargar Qwen2.5-VL-7B
import torch
from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor
from qwen_vl_utils import process_vision_info
MODEL_ID = "Qwen/Qwen2.5-VL-7B-Instruct"
model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
    MODEL_ID, torch_dtype=torch.bfloat16, device_map="auto")
# Procesador de ALTA resolucion (clave para leer digitos manuscritos)
proc = AutoProcessor.from_pretrained(MODEL_ID, min_pixels=256*28*28, max_pixels=2560*28*28)
print("Modelo cargado.")"""))

CELLS.append(("code", r'''# 7) Render + recorte de encabezado (ancho completo)
import fitz
from PIL import Image

def render_crop(pdf_path, page_num, top_frac, dpi=200):
    """Renderiza una pagina y recorta SOLO el encabezado superior (mantiene ancho completo)."""
    doc = fitz.open(pdf_path)
    if page_num >= len(doc):
        doc.close(); return None
    page = doc[page_num]
    pix = page.get_pixmap(matrix=fitz.Matrix(dpi/72, dpi/72))
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    doc.close()
    w,h = img.size
    return img.crop((0, int(h*top_frac), w, h))

# Recortes por pagina (solo quitan el encabezado de barcode/QR/titulo)
TOP_P1 = 0.15   # pagina 1: nivelacion + candidatos 1-7
TOP_P2 = 0.10   # pagina 2: candidatos 8-13 + totales'''))

CELLS.append(("code", r'''# 8) Prompts E-14 (con regla explicita de PUNTOS)
PROMPT_P1 = """Eres experto en leer actas electorales colombianas E-14 (presidenciales 2026). Esta es la PAGINA 1.

COMO LEER LA COLUMNA "VOTACION" (lo MAS importante):
- Cada candidato tiene 3 casillas: [centenas][decenas][unidades].
- Un PUNTO (.) = casilla VACIA, ahi NO hay digito. Los puntos NUNCA son numeros.
- Si las 3 casillas son puntos => el candidato saco CERO (0). JAMAS escribas 3.
- Ejemplos:  "punto punto punto"=0  |  "punto punto 8"=8  |  "punto 4 2"=42  |  "1 4 9"=149

DIGITOS MANUSCRITOS - confusiones comunes (lee con cuidado):
- 1 vs 7: un 7 puede NO tener rayita horizontal y parecer un 1. El 1 es un trazo
  vertical simple; el 7 tiene un trazo diagonal/horizontal en la parte de ARRIBA.
- 8 puede verse como dos circulos o una bola.
- 4 puede parecer una A.

NIVELACION DE LA MESA (3 numeros manuscritos arriba):
TOTAL VOTANTES FORMULARIO E-11, TOTAL VOTOS EN LA URNA, TOTAL VOTOS INCINERADOS

Candidatos de esta pagina, EN ORDEN (arriba a abajo):
1 CEPEDA, 2 CLAUDIA LOPEZ, 3 BOTERO, 4 DE LA ESPRIELLA, 5 LIZCANO, 6 URIBE, 7 SONDRA

Responde SOLO este JSON (sin texto, sin formato extra):
{"votantes_e11":0,"votos_urna":0,"incinerados":0,"votos":{"cepeda":0,"claudia":0,"botero":0,"espriella":0,"lizcano":0,"uribe":0,"sondra":0}}"""

PROMPT_P2 = """Eres experto en leer actas electorales colombianas E-14 (presidenciales 2026). Esta es la PAGINA 2.

COMO LEER LA COLUMNA "VOTACION" (lo MAS importante):
- Cada renglon tiene 3 casillas: [centenas][decenas][unidades].
- Un PUNTO (.) = casilla VACIA, NO hay digito. Los puntos NUNCA son numeros.
- Si las 3 casillas son puntos => CERO (0). JAMAS escribas 3.
- Ejemplos: "punto punto punto"=0 | "punto punto 8"=8 | "punto 1 9"=19

DIGITOS MANUSCRITOS - confusiones comunes (lee con cuidado):
- 1 vs 7: un 7 puede NO tener rayita y parecer un 1. El 1 es trazo vertical simple;
  el 7 tiene un trazo diagonal/horizontal ARRIBA.
- 8 puede verse como dos circulos.

Candidatos de esta pagina, EN ORDEN:
8 BARRERAS, 9 CAICEDO, 10 MATAMOROS, 11 PALOMA VALENCIA, 12 FAJARDO, 13 MURILLO
Luego: VOTOS EN BLANCO, VOTOS NULOS, TARJETAS NO MARCADAS, y SUMA TOTAL.

Responde SOLO este JSON (sin texto extra):
{"votos":{"barreras":0,"caicedo":0,"matamoros":0,"paloma":0,"fajardo":0,"murillo":0},"blanco":0,"nulo":0,"no_marcadas":0,"suma_total":0}"""
print("Prompts listos")'''))

CELLS.append(("code", r'''# 9) Parseo robusto del JSON
import json, re
def parse_json(text):
    text = re.sub(r'^```(json)?', '', text.strip()).strip()
    text = re.sub(r'```$', '', text).strip()
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if not m: return None
    try: return json.loads(m.group(0))
    except: return None'''))

CELLS.append(("code", r'''# 10) SELF-CONSISTENCY: k lecturas + voto por mayoria
import torch
from collections import Counter

def query_sc(img, prompt, k=3, temperature=0.3):
    """k lecturas con sampling. Devuelve lista de textos."""
    m=[{"role":"user","content":[{"type":"image","image":img},{"type":"text","text":prompt}]}]
    t=proc.apply_chat_template(m,tokenize=False,add_generation_prompt=True)
    ii,_=process_vision_info(m)
    inp=proc(text=[t],images=ii,padding=True,return_tensors="pt").to(model.device)
    outs=[]
    for _ in range(k):
        with torch.no_grad():
            g=model.generate(**inp,max_new_tokens=200,do_sample=True,temperature=temperature,top_p=0.9)
        outs.append(proc.batch_decode(g[:,inp.input_ids.shape[1]:],skip_special_tokens=True)[0])
    return outs

def vote(texts):
    """Vota cada campo entre las k lecturas (mayoria)."""
    ps=[parse_json(t) for t in texts]; ps=[p for p in ps if isinstance(p,dict)]
    if not ps: return None
    out={}; keys=set().union(*[p.keys() for p in ps])
    for k in keys:
        if k=="votos":
            vk=set().union(*[set(p["votos"].keys()) for p in ps if isinstance(p.get("votos"),dict)])
            out["votos"]={}
            for c in vk:
                vals=[p["votos"].get(c) for p in ps if isinstance(p.get("votos"),dict) and p["votos"].get(c) is not None]
                if vals: out["votos"][c]=Counter(map(str,vals)).most_common(1)[0][0]
        else:
            vals=[p.get(k) for p in ps if p.get(k) is not None and not isinstance(p.get(k),dict)]
            if vals: out[k]=Counter(map(str,vals)).most_common(1)[0][0]
    return out'''))

CELLS.append(("code", r'''# 11) CONFIG del run  (ajusta aqui)
# ---------------------------------------------------------
DEPT_FILTRO = "11"      # codigo departamento a procesar (11=CAUCA). None = todos
N_ACTAS     = 100       # cuantas actas procesar (None = todas las del filtro)
K_LECTURAS  = 3         # self-consistency: numero de lecturas por pagina
OUT_FILE    = f'{DRIVE}/labels_sc.jsonl'   # salida (reanudable)
# ---------------------------------------------------------

sub = df.copy()
if DEPT_FILTRO: sub = sub[sub['dept']==DEPT_FILTRO]
if N_ACTAS:     sub = sub.head(N_ACTAS)
print(f"A procesar: {len(sub)} actas (dept={DEPT_FILTRO})")'''))

CELLS.append(("code", r'''# 12) BUCLE PRINCIPAL (self-consistency, reanudable)
import json, time, os

done=set()
if os.path.exists(OUT_FILE):
    for line in open(OUT_FILE):
        try:
            r=json.loads(line); done.add((r['acta_id'],r['page']))
        except: pass
print(f"Ya procesadas: {len(done)} (acta,pagina)")

t0=time.time(); n=0
with open(OUT_FILE,'a') as f:
    for _,row in sub.iterrows():
        aid=row['acta_id']; pdf=row['colab_path']
        for pg,prompt,top in [(0,PROMPT_P1,TOP_P1),(1,PROMPT_P2,TOP_P2)]:
            tag='p1' if pg==0 else 'p2'
            if (aid,tag) in done: continue
            try:
                img=render_crop(pdf,pg,top)
                parsed=vote(query_sc(img,prompt,k=K_LECTURAS))
                rec={"acta_id":aid,"dept":row['dept'],"page":tag,"parsed":parsed}
            except Exception as e:
                rec={"acta_id":aid,"dept":row['dept'],"page":tag,"parsed":None,"error":str(e)[:150]}
            f.write(json.dumps(rec,ensure_ascii=False)+"\n"); f.flush(); n+=1
        if n%10==0: print(f"  {n} pag | {(time.time()-t0)/60:.1f} min")
print(f"LISTO {n} paginas nuevas en {(time.time()-t0)/60:.1f} min")'''))

CELLS.append(("code", r'''# 13) VALIDACION + clasificacion (limpia vs sospechosa)
import json
from collections import defaultdict

C=['cepeda','claudia','botero','espriella','lizcano','uribe','sondra',
   'barreras','caicedo','matamoros','paloma','fajardo','murillo']

raw=defaultdict(dict)
for line in open(OUT_FILE):
    r=json.loads(line)
    if r.get('parsed'): raw[r['acta_id']][r['page']]=(r['parsed'], r.get('dept',''))

clean,review=[],[]
for aid,pgs in raw.items():
    if 'p1' not in pgs or 'p2' not in pgs: continue
    p1,dept=pgs['p1']; p2,_=pgs['p2']
    v={**p1.get('votos',{}),**p2.get('votos',{})}
    cs=sum(int(v.get(k,0) or 0) for k in C)
    bl=int(p2.get('blanco',0) or 0);nu=int(p2.get('nulo',0) or 0)
    nm=int(p2.get('no_marcadas',0) or 0);su=int(p2.get('suma_total',0) or 0)
    ur=int(p1.get('votos_urna',0) or 0);e11=int(p1.get('votantes_e11',0) or 0)
    tot=cs+bl+nu+nm
    rec={"acta_id":aid,"dept":dept,"votos":{k:int(v.get(k,0) or 0) for k in C},
         "blanco":bl,"nulo":nu,"no_marcadas":nm,"suma_total":su,"votos_urna":ur,
         "votantes_e11":e11,"total_calculado":tot,"dif":tot-su if su else tot-ur}
    if (tot==su and su>0) or (tot==ur and ur>0):
        rec["estado"]="CONSISTENTE"; clean.append(rec)
    else:
        rec["estado"]="SOSPECHOSA"; review.append(rec)

with open(f'{DRIVE}/resultado_clean.jsonl','w') as f:
    for r in clean: f.write(json.dumps(r,ensure_ascii=False)+"\n")
with open(f'{DRIVE}/resultado_sospechosas.jsonl','w') as f:
    for r in review: f.write(json.dumps(r,ensure_ascii=False)+"\n")

tot_n=len(clean)+len(review)
print(f"CONSISTENTES: {len(clean)}")
print(f"SOSPECHOSAS:  {len(review)}")
print(f"Yield: {len(clean)/tot_n*100:.0f}%" if tot_n else "sin datos")'''))

CELLS.append(("code", r'''# 14) VER actas sospechosas (imagen + numeros leidos)
import json, matplotlib.pyplot as plt
path_map=dict(zip(df['acta_id'],df['colab_path']))
susp=[json.loads(l) for l in open(f'{DRIVE}/resultado_sospechosas.jsonl')]
print(f"{len(susp)} sospechosas. Mostrando primeras 5:")
for r in susp[:5]:
    aid=r['acta_id']
    img=render_crop(path_map[aid],0,TOP_P1)
    plt.figure(figsize=(6,9)); plt.imshow(img); plt.axis('off'); plt.title(f"{aid}  ({r['estado']})"); plt.show()
    print(f"Votos: {r['votos']}")
    print(f"suma_calc={r['total_calculado']}  suma_total={r['suma_total']}  urna={r['votos_urna']}  dif={r['dif']}")
    print("="*60)'''))

CELLS.append(("md", r"""## Próximos pasos
1. **Mejorar detección** — iterar prompt / k de lecturas si hace falta.
2. **Procesar más departamentos** — cambia `DEPT_FILTRO` y vuelve a correr (es reanudable, acumula en `labels_sc.jsonl`).
3. **Página web** — `resultado_sospechosas.jsonl` alimenta el dashboard de auditoría.
4. **Entrenar Donut** — cuando tengamos suficientes etiquetas limpias (`resultado_clean.jsonl`), destilamos a un modelo rápido para las 121.041 actas.
"""))


def build_notebook(cells):
    nb_cells=[]
    for kind,src in cells:
        lines=src.split("\n")
        source=[l+"\n" for l in lines[:-1]]+[lines[-1]]
        if kind=="md":
            nb_cells.append({"cell_type":"markdown","metadata":{},"source":source})
        else:
            nb_cells.append({"cell_type":"code","metadata":{},"execution_count":None,"outputs":[],"source":source})
    return {"cells":nb_cells,
            "metadata":{"accelerator":"GPU","colab":{"provenance":[],"gpuType":"A100"},
                        "kernelspec":{"display_name":"Python 3","name":"python3"},
                        "language_info":{"name":"python"}},
            "nbformat":4,"nbformat_minor":0}

if __name__=="__main__":
    nb=build_notebook(CELLS)
    out=Path("training/fase2_autolabel_v2.ipynb")
    out.write_text(json.dumps(nb,ensure_ascii=False,indent=1),encoding="utf-8")
    print(f"Notebook generado: {out}  ({len(CELLS)} celdas)")
