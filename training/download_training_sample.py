"""
FASE 1 — Descarga estratificada de actas E-14 para entrenamiento.

Objetivo: muestra geograficamente diversa (toda Colombia) para que el modelo
aprenda la variedad de caligrafia manuscrita region por region.

Estrategia:
  - N actas por departamento (configurable, default 250)
  - Departamentos pequenos: se toman todas las disponibles
  - 2 departamentos se reservan COMPLETOS para test de generalizacion (holdout)
  - Genera manifest.csv con metadata de cada PDF (para etiquetado posterior)

Uso:
  python training/download_training_sample.py --per-dept 250
"""
import argparse
import asyncio
import csv
import json
import logging
import random
import uuid
from collections import defaultdict
from pathlib import Path

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BASE = "https://divulgacione14presidente.registraduria.gov.co/assets/temis"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/pdf,*/*",
    "Referer": "https://divulgacione14presidente.registraduria.gov.co/",
}

DEPT_NAMES = {
    "01":"ANTIOQUIA","03":"ATLANTICO","05":"BOLIVAR","07":"BOYACA",
    "09":"CALDAS","11":"CAUCA","12":"CESAR","13":"CORDOBA",
    "15":"CUNDINAMARCA","16":"BOGOTA","17":"CHOCO","19":"HUILA",
    "21":"MAGDALENA","23":"NARINO","24":"RISARALDA","25":"NORTE_SANTANDER",
    "26":"QUINDIO","27":"SANTANDER","28":"SUCRE","29":"TOLIMA",
    "31":"VALLE","40":"ARAUCA","44":"CAQUETA","46":"CASANARE",
    "48":"LA_GUAJIRA","50":"GUAINIA","52":"META","54":"GUAVIARE",
    "56":"SAN_ANDRES","60":"AMAZONAS","64":"PUTUMAYO","68":"VAUPES",
    "72":"VICHADA","88":"CONSULADOS"
}

# Departamentos reservados ENTEROS para test de generalizacion (NO se entrenan)
HOLDOUT_DEPTS = ["29", "09"]   # TOLIMA y CALDAS (tamano medio, region andina)

SEED = 42


def build_index(cache_dir: Path) -> list[dict]:
    """Carga allTransmissionCodes.json -> lista de actas con metadata."""
    path = cache_dir / "allTransmissionCodes.json"
    logger.info("Cargando indice (%s MB)...", path.stat().st_size // 1_000_000)
    data = json.loads(path.read_text(encoding="utf-8"))
    actas = []
    for status_key in ("status11", "status3"):
        for n in data["data"].get(status_key, {}).get("nodes", []):
            actas.append({
                "dept":   n["idDepartmentCode"],
                "mun":    n["municipalityCode"],
                "zona":   n["idZoneCode"],
                "stand":  n["standCode"],
                "mesa":   n["numberStand"],
                "hash":   n["expectedName"],          # "sha256.pdf"
                "status": status_key,
            })
    logger.info("Indice: %d actas", len(actas))
    return actas


def stratified_sample(actas: list[dict], per_dept: int) -> tuple[list, list]:
    """Devuelve (muestra_entrenamiento, muestra_holdout)."""
    rng = random.Random(SEED)
    by_dept = defaultdict(list)
    for a in actas:
        by_dept[a["dept"]].append(a)

    train, holdout = [], []
    for dept, items in sorted(by_dept.items()):
        rng.shuffle(items)
        if dept in HOLDOUT_DEPTS:
            # holdout: tomar hasta 200 para test
            holdout.extend(items[:200])
        else:
            train.extend(items[:per_dept])
    return train, holdout


def acta_to_url_and_path(a: dict, root: str) -> tuple[str, Path, str]:
    zone_padded = a["zona"].zfill(3)
    fname = a["hash"].replace(".pdf", "")
    url = f"{BASE}/pdf/{a['dept']}/{a['mun']}/{zone_padded}/{a['stand']}/{a['mesa']}/PRE/{fname}.pdf?uuid={uuid.uuid4()}"
    # ID estable y unico por acta
    acta_id = f"{a['dept']}_{a['mun']}_{a['zona']}_{a['stand']}_{a['mesa']}"
    dest = Path(root) / a["dept"] / f"{acta_id}.pdf"
    return url, dest, acta_id


async def download_one(client, a, root, sem, manifest):
    url, dest, acta_id = acta_to_url_and_path(a, root)
    if dest.exists() and dest.stat().st_size > 500:
        manifest.append({**a, "acta_id": acta_id, "path": str(dest), "ok": True})
        return True
    async with sem:
        try:
            r = await client.get(url, headers=HEADERS, follow_redirects=True)
            r.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(r.content)
            manifest.append({**a, "acta_id": acta_id, "path": str(dest), "ok": True})
            return True
        except Exception as e:
            logger.debug("ERR %s: %s", acta_id, e)
            manifest.append({**a, "acta_id": acta_id, "path": str(dest), "ok": False})
            return False


async def download_set(actas, root, concurrency, label):
    sem = asyncio.Semaphore(concurrency)
    manifest = []
    done = 0
    async with httpx.AsyncClient(timeout=60) as client:
        tasks = [download_one(client, a, root, sem, manifest) for a in actas]
        for coro in asyncio.as_completed(tasks):
            await coro
            done += 1
            if done % 200 == 0:
                logger.info("  [%s] %d/%d descargadas", label, done, len(actas))
    ok = sum(1 for m in manifest if m["ok"])
    logger.info("[%s] %d OK / %d total", label, ok, len(actas))
    return manifest


def write_manifest(manifest: list[dict], path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["acta_id","dept","mun","zona","stand","mesa","hash","status","path","ok"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(manifest)
    logger.info("Manifest: %s (%d filas)", path, len(manifest))


async def main(per_dept: int, concurrency: int):
    cache = Path("cache")
    actas = build_index(cache)
    train, holdout = stratified_sample(actas, per_dept)

    logger.info("=" * 55)
    logger.info("Entrenamiento: %d actas (%d deptos)", len(train), len(DEPT_NAMES)-len(HOLDOUT_DEPTS))
    logger.info("Holdout (test): %d actas (%s)", len(holdout), HOLDOUT_DEPTS)
    logger.info("=" * 55)

    train_manifest = await download_set(train, "training/pdfs_train", concurrency, "TRAIN")
    write_manifest(train_manifest, Path("training/manifest_train.csv"))

    holdout_manifest = await download_set(holdout, "training/pdfs_holdout", concurrency, "HOLDOUT")
    write_manifest(holdout_manifest, Path("training/manifest_holdout.csv"))

    # Resumen por departamento
    by_dept = defaultdict(int)
    for m in train_manifest:
        if m["ok"]:
            by_dept[m["dept"]] += 1
    logger.info("\nActas descargadas por departamento:")
    for dept, n in sorted(by_dept.items()):
        logger.info("  %s %-18s %5d", dept, DEPT_NAMES.get(dept, "?"), n)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--per-dept", type=int, default=250, help="Actas por departamento")
    p.add_argument("--concurrency", type=int, default=20)
    args = p.parse_args()
    asyncio.run(main(args.per_dept, args.concurrency))
