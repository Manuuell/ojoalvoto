"""
Descarga todos los PDFs de actas E-14 de un departamento.
Uso: python pipeline/download_dept.py --dept 60   (60 = AMAZONAS)
"""
import asyncio
import json
import logging
import uuid
from pathlib import Path
from collections import Counter

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BASE = "https://divulgacione14presidente.registraduria.gov.co/assets/temis"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://divulgacione14presidente.registraduria.gov.co/",
}


def build_index(cache_dir: Path) -> dict[str, str]:
    """Carga allTransmissionCodes.json y construye indice key->filename."""
    path = cache_dir / "allTransmissionCodes.json"
    logger.info("Cargando indice de hashes (%s MB)...", path.stat().st_size // 1_000_000)
    data = json.loads(path.read_text(encoding="utf-8"))
    index = {}
    for status_key in ("status11", "status3"):
        for node in data["data"].get(status_key, {}).get("nodes", []):
            key = "{}/{}/{}/{}/{}".format(
                node["idDepartmentCode"],
                node["municipalityCode"],
                node["idZoneCode"],
                node["standCode"],
                node["numberStand"],
            )
            index[key] = node["expectedName"]
    logger.info("Indice listo: %d entradas", len(index))
    return index


def get_dept_entries(index: dict[str, str], dept_code: str) -> list[tuple[str, str, str]]:
    """Retorna lista de (key, pdf_url, local_path) para el departamento."""
    entries = []
    for key, fname in index.items():
        parts = key.split("/")
        if parts[0] != dept_code:
            continue
        dept, mun, zone_raw, stand, table = parts
        zone_padded = zone_raw.zfill(3)
        pdf_path = f"{dept}/{mun}/{zone_padded}/{stand}/{table}"
        url = f"{BASE}/pdf/{pdf_path}/PRE/{fname}?uuid={uuid.uuid4()}"
        local = f"pdfs/{dept}/{mun}/{zone_raw}/{stand}/{table}.pdf"
        entries.append((key, url, local))
    return entries


async def download_one(
    client: httpx.AsyncClient,
    url: str,
    dest: Path,
    sem: asyncio.Semaphore,
) -> bool:
    if dest.exists() and dest.stat().st_size > 500:
        return True
    async with sem:
        try:
            resp = await client.get(url, headers=HEADERS, follow_redirects=True)
            resp.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(resp.content)
            return True
        except Exception as e:
            logger.warning("ERROR %s: %s", dest.name, e)
            return False


async def download_dept(dept_code: str, cache_dir: Path, concurrency: int = 15):
    index = build_index(cache_dir)
    entries = get_dept_entries(index, dept_code)

    if not entries:
        logger.error("No hay entradas para dept=%s", dept_code)
        return

    logger.info("Dept %s: %d actas a descargar", dept_code, len(entries))
    sem = asyncio.Semaphore(concurrency)
    stats = Counter()

    async with httpx.AsyncClient(timeout=60) as client:
        tasks = [
            download_one(client, url, Path(local), sem)
            for _, url, local in entries
        ]
        results = await asyncio.gather(*tasks)

    for ok in results:
        stats["ok" if ok else "err"] += 1

    logger.info("Descarga completa: %d OK / %d ERROR de %d total", stats["ok"], stats["err"], len(entries))
    return entries


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dept", required=True, help="Codigo departamento (ej: 60)")
    parser.add_argument("--cache", default="cache")
    parser.add_argument("--concurrency", type=int, default=15)
    args = parser.parse_args()
    asyncio.run(download_dept(args.dept, Path(args.cache), args.concurrency))
