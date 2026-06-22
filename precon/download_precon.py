"""
Descarga todos los JSONs de resultados PRECON desde resultados.registraduria.gov.co

Patron de URLs descubierto (1 junio 2026):
  /json/ACT/PR/00.json          → nacional
  /json/ACT/PR/{DD}.json        → departamento (DD = 2 digitos)
  /json/ACT/PR/{DD}{MMM}.json   → municipio (5 digitos)
  /json/ACT/PR/{DD}{MMM}{ZZ}.json  → zona? (7 digitos) — pendiente confirmar
"""
import asyncio
import json
import logging
from pathlib import Path
from collections import defaultdict

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BASE = "https://resultados.registraduria.gov.co/json/ACT/PR"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "*/*",
    "Referer": "https://resultados.registraduria.gov.co/resultados/0/00",
}

# Departamentos del sistema electoral colombiano
DEPT_CODES = [
    "01","03","05","07","09","11","12","13","15","16",
    "17","19","21","23","24","25","26","27","28","29",
    "31","40","44","46","48","50","52","54","56","60",
    "64","68","72","88"
]


async def fetch_json(client: httpx.AsyncClient, amb: str, cache_dir: Path) -> dict | None:
    dest = cache_dir / f"{amb}.json"
    if dest.exists() and dest.stat().st_size > 50:
        return json.loads(dest.read_text(encoding="utf-8"))

    url = f"{BASE}/{amb}.json"
    try:
        resp = await client.get(url, headers=HEADERS)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data
    except Exception as e:
        logger.debug("ERR %s: %s", amb, e)
        return None


def get_mun_codes_from_tree(tree_path: Path) -> list[str]:
    """Extrae todos los codigos de municipio del arbol DIVIPOL."""
    tree = json.loads(tree_path.read_text(encoding="utf-8"))
    codes = []
    for edge in tree["data"]["departmentsTree"]["edges"]:
        dept = edge["node"]["idDepartmentCode"]
        for mun in edge["node"].get("municipalities", []):
            mun_code = mun["municipalityCode"]
            codes.append(f"{dept}{mun_code}")
    return codes


async def download_all(cache_dir: Path, concurrency: int = 20):
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Cargar municipios del arbol
    tree_path = Path("cache/departmentsTree.json")
    if tree_path.exists():
        mun_codes = get_mun_codes_from_tree(tree_path)
        logger.info("Municipios a descargar: %d", len(mun_codes))
    else:
        mun_codes = []
        logger.warning("departmentsTree.json no encontrado, solo descargando dept")

    all_codes = ["00"] + DEPT_CODES + mun_codes
    logger.info("Total JSONs a descargar: %d", len(all_codes))

    sem = asyncio.Semaphore(concurrency)
    results = {}

    async def worker(amb: str):
        async with sem:
            data = await fetch_json(client, amb, cache_dir)
            results[amb] = data is not None

    async with httpx.AsyncClient(timeout=30) as client:
        await asyncio.gather(*[worker(c) for c in all_codes])

    ok  = sum(1 for v in results.values() if v)
    err = sum(1 for v in results.values() if not v)
    logger.info("Descarga completa: %d OK / %d no encontrados", ok, err)
    return results


if __name__ == "__main__":
    asyncio.run(download_all(Path("precon/cache")))
