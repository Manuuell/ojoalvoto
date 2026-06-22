"""
SafeVote — Herramienta de etiquetado colaborativo de actas E-14.

- Reparte actas sin repetir (cada usuario recibe una pendiente).
- Bloqueo temporal: si alguien abre un acta y no la termina en 15 min, se libera.
- Guarda etiquetas en SQLite.
- Lista para desplegar online (Render/Railway) o local + túnel (ngrok/cloudflared).
- Pre-llenado opcional con lecturas de IA (labels_sc.jsonl) si existe.

Ejecutar local:
    pip install -r requirements.txt
    python app.py
    abrir http://localhost:5000
"""
import csv
import io
import json
import os
import sqlite3
import time
import uuid
from pathlib import Path

import fitz  # pymupdf
from flask import Flask, g, jsonify, request, send_file, render_template

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_DIR    = Path(__file__).parent
DB_PATH     = BASE_DIR / "labels.db"
MANIFEST    = BASE_DIR / "manifest.csv"                 # actas a etiquetar
PDFS_DIR    = Path(os.environ.get("PDFS_DIR", BASE_DIR.parent / "training" / "pdfs_train"))  # PDFs locales
PREFILL     = BASE_DIR / "prefills.jsonl"               # opcional (lecturas IA)
LOCK_TTL    = 15 * 60                                   # 15 min para liberar un acta abierta
RENDER_DPI  = 150
TOP_CROP    = {0: 0.13, 1: 0.06}                        # recorte de encabezado por pagina

# URL publica de la Registraduria (fallback si no hay PDF local)
REG_BASE = "https://divulgacione14presidente.registraduria.gov.co/assets/temis/pdf"

# Campos del formulario E-14
FIELDS_P1 = ["votantes_e11", "votos_urna", "incinerados",
             "cepeda", "claudia", "botero", "espriella", "lizcano", "uribe", "sondra"]
FIELDS_P2 = ["barreras", "caicedo", "matamoros", "paloma", "fajardo", "murillo",
             "blanco", "nulo", "no_marcadas", "suma_total"]
CANDIDATOS = ["cepeda","claudia","botero","espriella","lizcano","uribe","sondra",
              "barreras","caicedo","matamoros","paloma","fajardo","murillo"]

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Base de datos
# ---------------------------------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")  # mejor concurrencia
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS actas (
            acta_id TEXT PRIMARY KEY,
            dept TEXT, mun TEXT, zona TEXT, stand TEXT, mesa TEXT, hash TEXT,
            status TEXT DEFAULT 'pending',
            assigned_at REAL DEFAULT 0,
            labeler TEXT,
            flagged INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS labels (
            acta_id TEXT PRIMARY KEY,
            data TEXT, labeler TEXT, created_at REAL
        );
        CREATE INDEX IF NOT EXISTS idx_status ON actas(status);
    """)
    # Cargar manifest si la tabla esta vacia
    n = db.execute("SELECT COUNT(*) FROM actas").fetchone()[0]
    if n == 0 and MANIFEST.exists():
        with open(MANIFEST, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            if r.get("ok", "True") not in ("True", "true", "1", ""):
                continue
            db.execute(
                "INSERT OR IGNORE INTO actas(acta_id,dept,mun,zona,stand,mesa,hash) VALUES(?,?,?,?,?,?,?)",
                (r["acta_id"], r["dept"], r["mun"], r["zona"], r["stand"], r["mesa"], r.get("hash","")))
        db.commit()
        print(f"Cargadas {len(rows)} actas en la base de datos.")
    db.close()


def load_prefills():
    """Carga lecturas de IA por acta_id -> {p1:{...}, p2:{...}} si existe el archivo."""
    pf = {}
    if PREFILL.exists():
        from collections import defaultdict
        tmp = defaultdict(dict)
        for line in open(PREFILL, encoding="utf-8"):
            try:
                r = json.loads(line)
                if r.get("parsed"):
                    tmp[r["acta_id"]][r["page"]] = r["parsed"]
            except: pass
        pf = dict(tmp)
    print(f"Pre-llenados disponibles: {len(pf)} actas")
    return pf

PREFILLS = {}

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("label.html", candidatos=CANDIDATOS)


@app.route("/api/next")
def api_next():
    """Asigna la siguiente acta pendiente al usuario (sin repetir)."""
    labeler = request.args.get("labeler", "anon")[:40]
    db = get_db()
    now = time.time()
    # liberar bloqueos vencidos
    db.execute("UPDATE actas SET status='pending' WHERE status='in_progress' AND assigned_at < ?",
               (now - LOCK_TTL,))
    db.commit()
    # tomar una pendiente
    row = db.execute("SELECT * FROM actas WHERE status='pending' ORDER BY RANDOM() LIMIT 1").fetchone()
    if row is None:
        return jsonify({"done": True})
    db.execute("UPDATE actas SET status='in_progress', assigned_at=?, labeler=? WHERE acta_id=?",
               (now, labeler, row["acta_id"]))
    db.commit()

    aid = row["acta_id"]
    pf = PREFILLS.get(aid, {})
    prefill = {}
    if pf:
        p1 = pf.get("p1", {}); p2 = pf.get("p2", {})
        v = {**p1.get("votos", {}), **p2.get("votos", {})}
        for k in FIELDS_P1 + FIELDS_P2:
            if k in CANDIDATOS:
                prefill[k] = v.get(k, "")
            elif k in p1:
                prefill[k] = p1.get(k, "")
            elif k in p2:
                prefill[k] = p2.get(k, "")
    return jsonify({
        "done": False,
        "acta_id": aid,
        "info": {"dept": row["dept"], "mun": row["mun"], "zona": row["zona"],
                 "stand": row["stand"], "mesa": row["mesa"]},
        "prefill": prefill,
    })


def _find_pdf(row):
    """Ruta local del PDF, o None."""
    aid = row["acta_id"]; dept = row["dept"]
    cands = [PDFS_DIR / dept / f"{aid}.pdf", PDFS_DIR / f"{aid}.pdf"]
    for c in cands:
        if c.exists():
            return c
    return None


@app.route("/api/image/<acta_id>/<int:page>")
def api_image(acta_id, page):
    db = get_db()
    row = db.execute("SELECT * FROM actas WHERE acta_id=?", (acta_id,)).fetchone()
    if row is None:
        return "no encontrada", 404
    pdf_path = _find_pdf(row)
    try:
        if pdf_path:
            doc = fitz.open(str(pdf_path))
        else:
            # fallback: descargar de la Registraduria usando el hash
            import httpx
            zone = row["zona"].zfill(3)
            url = f"{REG_BASE}/{row['dept']}/{row['mun']}/{zone}/{row['stand']}/{row['mesa']}/PRE/{row['hash']}?uuid={uuid.uuid4()}"
            data = httpx.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"}).content
            doc = fitz.open(stream=data, filetype="pdf")
        if page >= len(doc):
            doc.close(); return "pagina inexistente", 404
        pg = doc[page]
        pix = pg.get_pixmap(matrix=fitz.Matrix(RENDER_DPI/72, RENDER_DPI/72))
        img_bytes = pix.tobytes("png")
        doc.close()
        # recortar encabezado
        from PIL import Image
        im = Image.open(io.BytesIO(img_bytes))
        w, h = im.size
        im = im.crop((0, int(h*TOP_CROP.get(page, 0.1)), w, h))
        out = io.BytesIO(); im.save(out, "PNG"); out.seek(0)
        return send_file(out, mimetype="image/png")
    except Exception as e:
        return f"error: {e}", 500


@app.route("/api/submit", methods=["POST"])
def api_submit():
    data = request.get_json(force=True)
    aid = data.get("acta_id")
    labeler = data.get("labeler", "anon")[:40]
    votes = data.get("votes", {})
    if not aid:
        return jsonify({"error": "falta acta_id"}), 400
    db = get_db()
    db.execute("INSERT OR REPLACE INTO labels(acta_id,data,labeler,created_at) VALUES(?,?,?,?)",
               (aid, json.dumps(votes, ensure_ascii=False), labeler, time.time()))
    db.execute("UPDATE actas SET status='done' WHERE acta_id=?", (aid,))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/skip", methods=["POST"])
def api_skip():
    """Marca un acta como ilegible/saltada (la libera y la marca para revision)."""
    data = request.get_json(force=True)
    aid = data.get("acta_id")
    db = get_db()
    db.execute("UPDATE actas SET status='skipped' WHERE acta_id=?", (aid,))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/flag", methods=["POST"])
def api_flag():
    """Guarda la etiqueta Y marca el acta como POSIBLE FRAUDE en la base de datos."""
    data = request.get_json(force=True)
    aid = data.get("acta_id")
    labeler = data.get("labeler", "anon")[:40]
    votes = data.get("votes", {})
    nota = data.get("nota", "")[:300]
    db = get_db()
    db.execute("INSERT OR REPLACE INTO labels(acta_id,data,labeler,created_at) VALUES(?,?,?,?)",
               (aid, json.dumps({"votes": votes, "nota": nota}, ensure_ascii=False), labeler, time.time()))
    db.execute("UPDATE actas SET status='done', flagged=1 WHERE acta_id=?", (aid,))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/flagged")
def api_flagged():
    """Lista los PDFs marcados como posible fraude (para revisar)."""
    db = get_db()
    rows = db.execute("""SELECT a.acta_id,a.dept,a.mun,a.zona,a.stand,a.mesa,a.hash,l.data,l.labeler
                         FROM actas a LEFT JOIN labels l ON l.acta_id=a.acta_id
                         WHERE a.flagged=1 ORDER BY a.acta_id""").fetchall()
    out = [dict(r) for r in rows]
    return app.response_class(json.dumps(out, ensure_ascii=False, indent=2),
                              mimetype="application/json",
                              headers={"Content-Disposition": "attachment; filename=fraude_candidatos.json"})


@app.route("/api/stats")
def api_stats():
    db = get_db()
    rows = db.execute("SELECT status, COUNT(*) c FROM actas GROUP BY status").fetchall()
    stats = {r["status"]: r["c"] for r in rows}
    total = db.execute("SELECT COUNT(*) FROM actas").fetchone()[0]
    done = stats.get("done", 0)
    flagged = db.execute("SELECT COUNT(*) FROM actas WHERE flagged=1").fetchone()[0]
    # top etiquetadores
    top = db.execute("SELECT labeler, COUNT(*) c FROM labels GROUP BY labeler ORDER BY c DESC LIMIT 10").fetchall()
    return jsonify({"total": total, "done": done, "pending": stats.get("pending", 0),
                    "in_progress": stats.get("in_progress", 0), "skipped": stats.get("skipped", 0),
                    "flagged": flagged,
                    "ranking": [{"labeler": r["labeler"], "n": r["c"]} for r in top]})


@app.route("/api/export")
def api_export():
    """Exporta todas las etiquetas como JSON (para entrenar Donut)."""
    db = get_db()
    rows = db.execute("""SELECT l.acta_id, a.dept, l.data, l.labeler
                         FROM labels l JOIN actas a ON a.acta_id=l.acta_id""").fetchall()
    out = [{"acta_id": r["acta_id"], "dept": r["dept"],
            "votes": json.loads(r["data"]), "labeler": r["labeler"]} for r in rows]
    return app.response_class(json.dumps(out, ensure_ascii=False, indent=2),
                              mimetype="application/json",
                              headers={"Content-Disposition": "attachment; filename=etiquetas.json"})


if __name__ == "__main__":
    init_db()
    PREFILLS = load_prefills()
    # Verificar que la carpeta de PDFs existe y tiene archivos
    print(f"PDFS_DIR = {PDFS_DIR}")
    if PDFS_DIR.exists():
        n_pdf = sum(1 for _ in PDFS_DIR.rglob("*.pdf"))
        print(f"  PDFs encontrados: {n_pdf}")
        if n_pdf == 0:
            print("  AVISO: no hay PDFs ahi. Define PDFS_DIR o revisa la ruta.")
    else:
        print(f"  AVISO: la carpeta NO existe. Los PDFs se intentaran descargar de la Registraduria.")
    port = int(os.environ.get("PORT", 5000))
    print(f"\n  Abre http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=False)
