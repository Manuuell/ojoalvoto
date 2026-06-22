"""
SafeVote 2026 — Backend de etiquetado colaborativo (PRODUCCIÓN).

Stack:
  - Flask + Gunicorn (servidor WSGI multi-worker)
  - PostgreSQL (persistente, concurrente) vía psycopg2 + pool
  - Reparto de actas sin colisión con FOR UPDATE SKIP LOCKED (cola de trabajo)
  - Render de PDF con PyMuPDF + caché en disco
  - nginx (reverse proxy + TLS) por delante

Config por variables de entorno (.env):
  DATABASE_URL=postgresql://user:pass@db:5432/safevote
  PDFS_DIR=/data/pdfs            (PDFs locales; si no están, se bajan de la Registraduría)
  MANIFEST=/data/manifest.csv    (catálogo de actas)
  CACHE_DIR=/data/cache          (imágenes renderizadas)
  PREFILL=/data/prefills.jsonl   (opcional, lecturas IA para pre-llenado)
"""
import csv
import io
import json
import os
import uuid
from contextlib import contextmanager
from pathlib import Path

import fitz
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from psycopg2.pool import ThreadedConnectionPool
from flask import Flask, jsonify, request, send_file, render_template

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://safevote:safevote@localhost:5432/safevote")
PDFS_DIR  = Path(os.environ.get("PDFS_DIR", "/data/pdfs"))
MANIFEST  = Path(os.environ.get("MANIFEST", "/data/manifest.csv"))
CACHE_DIR = Path(os.environ.get("CACHE_DIR", "/data/cache"))
PREFILL   = Path(os.environ.get("PREFILL", "/data/prefills.jsonl"))
REG_BASE  = "https://divulgacione14presidente.registraduria.gov.co/assets/temis/pdf"
LOCK_TTL_MIN = 15
RENDER_DPI = 150
TOP_CROP = {0: 0.13, 1: 0.06}

CACHE_DIR.mkdir(parents=True, exist_ok=True)
app = Flask(__name__)
pool = ThreadedConnectionPool(1, 16, dsn=DATABASE_URL)
PREFILLS = {}


@contextmanager
def db(commit=False):
    conn = pool.getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def init_db():
    with db(commit=True) as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS actas(
                acta_id TEXT PRIMARY KEY, dept TEXT, mun TEXT, zona TEXT, stand TEXT, mesa TEXT, hash TEXT,
                status TEXT DEFAULT 'pending', assigned_at TIMESTAMPTZ, labeler TEXT, flagged BOOLEAN DEFAULT FALSE);
            CREATE TABLE IF NOT EXISTS labels(
                acta_id TEXT PRIMARY KEY, data JSONB, labeler TEXT, created_at TIMESTAMPTZ DEFAULT now());
            CREATE INDEX IF NOT EXISTS idx_status ON actas(status);
        """)
        cur.execute("SELECT COUNT(*) c FROM actas")
        n = cur.fetchone()["c"]
    if n == 0 and MANIFEST.exists():
        rows = []
        with open(MANIFEST, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if str(r.get("ok", "True")).lower() in ("true", "1", ""):
                    rows.append((r["acta_id"], r["dept"], r["mun"], r["zona"], r["stand"], r["mesa"], r.get("hash", "")))
        with db(commit=True) as cur:
            execute_values(cur,
                "INSERT INTO actas(acta_id,dept,mun,zona,stand,mesa,hash) VALUES %s ON CONFLICT DO NOTHING", rows)
        print(f"[init] Cargadas {len(rows)} actas en Postgres")


def load_prefills():
    global PREFILLS
    if PREFILL.exists():
        from collections import defaultdict
        tmp = defaultdict(dict)
        for line in open(PREFILL, encoding="utf-8"):
            try:
                r = json.loads(line)
                if r.get("parsed"):
                    tmp[r["acta_id"]][r["page"]] = r["parsed"]
            except Exception:
                pass
        PREFILLS = dict(tmp)
    print(f"[init] Pre-llenados: {len(PREFILLS)} actas")


# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("label.html")


@app.route("/api/next")
def api_next():
    labeler = request.args.get("labeler", "anon")[:40]
    with db(commit=True) as cur:
        cur.execute(f"UPDATE actas SET status='pending' WHERE status='in_progress' "
                    f"AND assigned_at < now() - interval '{LOCK_TTL_MIN} minutes'")
        cur.execute("""
            UPDATE actas SET status='in_progress', assigned_at=now(), labeler=%s
            WHERE acta_id = (SELECT acta_id FROM actas WHERE status='pending'
                             ORDER BY random() LIMIT 1 FOR UPDATE SKIP LOCKED)
            RETURNING acta_id,dept,mun,zona,stand,mesa,hash""", (labeler,))
        row = cur.fetchone()
    if not row:
        return jsonify({"done": True})
    pf = PREFILLS.get(row["acta_id"], {})
    prefill = {}
    if pf:
        p1, p2 = pf.get("p1", {}), pf.get("p2", {})
        v = {**p1.get("votos", {}), **p2.get("votos", {})}
        for k in ["votantes_e11", "votos_urna", "incinerados"]:
            if k in p1: prefill[k] = p1[k]
        prefill.update(v)
        for k in ["blanco", "nulo", "no_marcadas", "suma_total"]:
            if k in p2: prefill[k] = p2[k]
    return jsonify({"done": False, "acta_id": row["acta_id"],
                    "info": {k: row[k] for k in ("dept", "mun", "zona", "stand", "mesa")},
                    "prefill": prefill})


def _render_page(row, page):
    """Devuelve PNG (bytes) de la página, con caché en disco."""
    cache = CACHE_DIR / f"{row['acta_id']}_{page}.png"
    if cache.exists():
        return cache.read_bytes()
    # Buscar PDF local o bajar de la Registraduría
    aid, dept = row["acta_id"], row["dept"]
    local = None
    for c in (PDFS_DIR / dept / f"{aid}.pdf", PDFS_DIR / f"{aid}.pdf"):
        if c.exists():
            local = c; break
    if local:
        doc = fitz.open(str(local))
    else:
        import httpx
        zone = row["zona"].zfill(3)
        url = f"{REG_BASE}/{dept}/{row['mun']}/{zone}/{row['stand']}/{row['mesa']}/PRE/{row['hash']}?uuid={uuid.uuid4()}"
        data = httpx.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"}).content
        doc = fitz.open(stream=data, filetype="pdf")
    if page >= len(doc):
        doc.close(); raise IndexError("pagina")
    pix = doc[page].get_pixmap(matrix=fitz.Matrix(RENDER_DPI/72, RENDER_DPI/72))
    png = pix.tobytes("png"); doc.close()
    from PIL import Image
    im = Image.open(io.BytesIO(png)); w, h = im.size
    im = im.crop((0, int(h*TOP_CROP.get(page, 0.1)), w, h))
    out = io.BytesIO(); im.save(out, "PNG")
    cache.write_bytes(out.getvalue())
    return out.getvalue()


@app.route("/api/image/<acta_id>/<int:page>")
def api_image(acta_id, page):
    with db() as cur:
        cur.execute("SELECT * FROM actas WHERE acta_id=%s", (acta_id,))
        row = cur.fetchone()
    if not row:
        return "no encontrada", 404
    try:
        return send_file(io.BytesIO(_render_page(row, page)), mimetype="image/png")
    except Exception as e:
        return f"error: {e}", 500


@app.route("/api/submit", methods=["POST"])
def api_submit():
    d = request.get_json(force=True)
    aid = d.get("acta_id")
    with db(commit=True) as cur:
        cur.execute("""INSERT INTO labels(acta_id,data,labeler,created_at) VALUES(%s,%s,%s,now())
                       ON CONFLICT(acta_id) DO UPDATE SET data=EXCLUDED.data,labeler=EXCLUDED.labeler,created_at=now()""",
                    (aid, json.dumps(d.get("votes", {}), ensure_ascii=False), d.get("labeler", "anon")[:40]))
        cur.execute("UPDATE actas SET status='done' WHERE acta_id=%s", (aid,))
    return jsonify({"ok": True})


@app.route("/api/flag", methods=["POST"])
def api_flag():
    d = request.get_json(force=True)
    aid = d.get("acta_id")
    payload = {"votes": d.get("votes", {}), "nota": d.get("nota", "")[:300]}
    with db(commit=True) as cur:
        cur.execute("""INSERT INTO labels(acta_id,data,labeler,created_at) VALUES(%s,%s,%s,now())
                       ON CONFLICT(acta_id) DO UPDATE SET data=EXCLUDED.data,labeler=EXCLUDED.labeler,created_at=now()""",
                    (aid, json.dumps(payload, ensure_ascii=False), d.get("labeler", "anon")[:40]))
        cur.execute("UPDATE actas SET status='done', flagged=TRUE WHERE acta_id=%s", (aid,))
    return jsonify({"ok": True})


@app.route("/api/skip", methods=["POST"])
def api_skip():
    aid = request.get_json(force=True).get("acta_id")
    with db(commit=True) as cur:
        cur.execute("UPDATE actas SET status='skipped' WHERE acta_id=%s", (aid,))
    return jsonify({"ok": True})


@app.route("/api/stats")
def api_stats():
    with db() as cur:
        cur.execute("SELECT status, COUNT(*) c FROM actas GROUP BY status")
        st = {r["status"]: r["c"] for r in cur.fetchall()}
        cur.execute("SELECT COUNT(*) c FROM actas")
        total = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) c FROM actas WHERE flagged")
        flagged = cur.fetchone()["c"]
        cur.execute("SELECT labeler, COUNT(*) c FROM labels GROUP BY labeler ORDER BY c DESC LIMIT 10")
        rank = cur.fetchall()
    return jsonify({"total": total, "done": st.get("done", 0), "pending": st.get("pending", 0),
                    "in_progress": st.get("in_progress", 0), "skipped": st.get("skipped", 0),
                    "flagged": flagged, "ranking": [{"labeler": r["labeler"], "n": r["c"]} for r in rank]})


@app.route("/api/flagged")
def api_flagged():
    with db() as cur:
        cur.execute("""SELECT a.acta_id,a.dept,a.mun,a.zona,a.stand,a.mesa,a.hash,l.data,l.labeler
                       FROM actas a LEFT JOIN labels l ON l.acta_id=a.acta_id
                       WHERE a.flagged ORDER BY a.acta_id""")
        out = cur.fetchall()
    return app.response_class(json.dumps(out, ensure_ascii=False, indent=2, default=str),
                              mimetype="application/json",
                              headers={"Content-Disposition": "attachment; filename=fraude_candidatos.json"})


@app.route("/api/export")
def api_export():
    with db() as cur:
        cur.execute("""SELECT l.acta_id,a.dept,l.data,l.labeler,a.flagged
                       FROM labels l JOIN actas a ON a.acta_id=l.acta_id""")
        out = cur.fetchall()
    return app.response_class(json.dumps(out, ensure_ascii=False, indent=2, default=str),
                              mimetype="application/json",
                              headers={"Content-Disposition": "attachment; filename=etiquetas.json"})


@app.route("/health")
def health():
    return jsonify({"ok": True})


# Inicializar al importar (gunicorn no llama __main__)
try:
    init_db()
    load_prefills()
except Exception as e:
    print(f"[init] aviso: {e}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
