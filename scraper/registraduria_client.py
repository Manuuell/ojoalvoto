"""
Cliente para la API del Visor Ciudadano E-14 — Registraduría Nacional de Colombia.

Endpoints descubiertos (1 junio 2026):
  Base: https://divulgacione14presidente.registraduria.gov.co/assets/temis/

  JSON estáticos (sin auth):
    /divipol_json/allDepartments.json         → lista de departamentos
    /divipol_json/allCorporations.json        → corporaciones (PRESIDENTE)
    /divipol_json/departmentsTree.json        → árbol completo dept→mun→zona→puesto→mesas
    /divipol_json/allTransmissionCodes.json   → mapeo mesa_id → hash SHA256 del PDF

  PDFs de actas E-14 (sin auth, uuid es solo cache-buster del cliente):
    /pdf/{dept}/{mun}/{zone}/{stand}/{table}/PRE/{sha256}.pdf?uuid={random-uuid}

  Ejemplo real:
    /pdf/05/001/021/03/004/PRE/93ce73e701b99b82fdd5e96c0a164b211ab039c175045459b5978117990f94b5.pdf

  Segmentos:
    dept  = idDepartmentCode   (ej: "05" = BOLIVAR)
    mun   = municipalityCode   (ej: "001")
    zone  = idZoneCode         (ej: "021")
    stand = standCode          (ej: "03")
    table = número de mesa     (ej: "004")
    PRE   = acronym corporación
    sha256= hash del archivo (viene de allTransmissionCodes.json)
"""

import asyncio
import json
import logging
import uuid
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import httpx

logger = logging.getLogger(__name__)

BASE = "https://divulgacione14presidente.registraduria.gov.co/assets/temis"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://divulgacione14presidente.registraduria.gov.co/departamento/05",
    "Accept-Language": "es-CO,es;q=0.9",
}


# ---------------------------------------------------------------------------
# Modelos de datos
# ---------------------------------------------------------------------------

@dataclass
class Mesa:
    dept_code: str
    dept_name: str
    mun_code: str
    mun_name: str
    zone_code: str
    zone_name: str
    stand_code: str
    stand_name: str
    table_number: int
    pdf_hash: str = ""   # se rellena desde allTransmissionCodes.json

    @property
    def index_key(self) -> str:
        """
        Clave para buscar en el índice de allTransmissionCodes.
        Usa los valores RAW del JSON (zone_code sin padding, table con padding de 3).
        Ejemplo: '05/001/21/03/004'
        """
        return f"{self.dept_code}/{self.mun_code}/{self.zone_code}/{self.stand_code}/{self.table_number:03d}"

    @property
    def pdf_path_segments(self) -> str:
        """
        Segmentos para la URL del PDF (zone_code con padding a 3 dígitos).
        Ejemplo: '05/001/021/03/004'
        La URL usa zone_code con ceros: '021', pero el índice lo guarda sin: '21'.
        """
        return f"{self.dept_code}/{self.mun_code}/{self.zone_code.zfill(3)}/{self.stand_code}/{self.table_number:03d}"

    @property
    def pdf_url(self) -> str:
        if not self.pdf_hash:
            raise ValueError(f"pdf_hash no cargado para mesa {self}")
        uid = uuid.uuid4()
        return f"{BASE}/pdf/{self.pdf_path_segments}/PRE/{self.pdf_hash}.pdf?uuid={uid}"

    @property
    def local_path(self) -> Path:
        return Path("pdfs") / self.dept_code / self.mun_code / self.zone_code / self.stand_code / f"{self.table_number:03d}.pdf"

    def __str__(self):
        return (
            f"{self.dept_name}/{self.mun_name}/{self.stand_name}/Mesa {self.table_number}"
            f" → {self.pdf_path_segments}"
        )


# ---------------------------------------------------------------------------
# Carga de JSONs estáticos
# ---------------------------------------------------------------------------

async def _fetch_json(client: httpx.AsyncClient, url: str, cache: Path) -> dict:
    if cache.exists():
        logger.debug("Cache hit: %s", cache)
        return json.loads(cache.read_text(encoding="utf-8"))
    logger.info("GET %s", url)
    resp = await client.get(url, headers=HEADERS)
    resp.raise_for_status()
    data = resp.json()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


async def fetch_departments_tree(client: httpx.AsyncClient, cache_dir: Path) -> dict:
    return await _fetch_json(
        client,
        f"{BASE}/divipol_json/departmentsTree.json",
        cache_dir / "departmentsTree.json",
    )


async def fetch_transmission_codes(client: httpx.AsyncClient, cache_dir: Path) -> dict:
    """5.9MB gzip — mapeo de códigos de mesa a hashes SHA-256 de los PDFs."""
    return await _fetch_json(
        client,
        f"{BASE}/divipol_json/allTransmissionCodes.json",
        cache_dir / "allTransmissionCodes.json",
    )


# ---------------------------------------------------------------------------
# Enumeración de mesas
# ---------------------------------------------------------------------------

def iter_all_mesas(tree: dict) -> Iterator[Mesa]:
    """Genera todas las mesas a partir de departmentsTree.json."""
    for edge in tree["data"]["departmentsTree"]["edges"]:
        node = edge["node"]
        dept_code = node["idDepartmentCode"]
        dept_name = node["departmentName"]

        for mun in node.get("municipalities", []):
            mun_code = mun["municipalityCode"]
            mun_name = mun["municipalityName"]

            for zone in mun.get("zones", []):
                zone_code = zone["idZoneCode"]
                zone_name = zone["zoneName"]

                for stand in zone.get("stands", []):
                    stand_code = stand["standCode"]
                    stand_name = stand["standName"]
                    count = stand["countTable"]

                    for t in range(1, count + 1):
                        yield Mesa(
                            dept_code=dept_code,
                            dept_name=dept_name,
                            mun_code=mun_code,
                            mun_name=mun_name,
                            zone_code=zone_code,
                            zone_name=zone_name,
                            stand_code=stand_code,
                            stand_name=stand_name,
                            table_number=t,
                        )


def build_hash_index(transmission_codes: dict) -> dict[str, str]:
    """
    Construye índice: '{dept}/{mun}/{zone}/{stand}/{table}' → 'sha256hash.pdf'

    Estructura real de allTransmissionCodes.json (descubierta 1 jun 2026):
      data.status3  →  240 registros  (fotos / tipo especial)
      data.status11 → 120801 registros (E14 escaneados)
      Total: 121.041 = exactamente todas las actas publicadas

    Campos por nodo:
      idDepartmentCode, municipalityCode, idZoneCode, standCode,
      numberStand (= número de mesa con ceros, ej "004"),
      expectedName (= "sha256hash.pdf")
    """
    index: dict[str, str] = {}
    data = transmission_codes.get("data", {})
    for status_key in ("status11", "status3"):
        for node in data.get(status_key, {}).get("nodes", []):
            dept  = node["idDepartmentCode"]
            mun   = node["municipalityCode"]
            zone  = node["idZoneCode"]
            stand = node["standCode"]
            table = node["numberStand"]          # ya viene con ceros: "004"
            fname = node["expectedName"]         # "sha256....pdf"
            key   = f"{dept}/{mun}/{zone}/{stand}/{table}"
            index[key] = fname
    return index


def attach_hashes(mesas: list[Mesa], index: dict[str, str]) -> tuple[list[Mesa], int]:
    """Añade el hash PDF a cada mesa. Retorna (mesas_con_hash, sin_hash)."""
    missing = 0
    for m in mesas:
        h = index.get(m.pdf_path_segments)
        if h:
            m.pdf_hash = h
        else:
            missing += 1
    return mesas, missing


# ---------------------------------------------------------------------------
# Descarga de PDFs
# ---------------------------------------------------------------------------

async def download_pdf(client: httpx.AsyncClient, mesa: Mesa, base_dir: Path) -> Path | None:
    dest = base_dir / mesa.local_path
    if dest.exists() and dest.stat().st_size > 1000:
        return dest

    try:
        url = mesa.pdf_url
    except ValueError:
        return None

    try:
        resp = await client.get(url, headers=HEADERS, follow_redirects=True)
        resp.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(resp.content)
        logger.debug("OK  %s (%d KB)", mesa, len(resp.content) // 1024)
        return dest
    except httpx.HTTPStatusError as e:
        logger.warning("HTTP %s — %s", e.response.status_code, mesa)
        return None
    except Exception as e:
        logger.warning("ERR %s — %s", mesa, e)
        return None


async def download_batch(
    mesas: list[Mesa],
    base_dir: Path,
    concurrency: int = 20,
) -> dict[str, int]:
    """Descarga PDFs en paralelo. Retorna estadísticas {ok, error, skip}."""
    stats = Counter()
    sem = asyncio.Semaphore(concurrency)

    async def worker(m: Mesa):
        async with sem:
            result = await download_pdf(client, m, base_dir)
            stats["ok" if result else "error"] += 1
            if (stats["ok"] + stats["error"]) % 100 == 0:
                logger.info("Progreso: %d OK / %d ERR / %d total", stats["ok"], stats["error"], len(mesas))

    async with httpx.AsyncClient(timeout=60, http2=True) as client:
        await asyncio.gather(*[worker(m) for m in mesas])

    return dict(stats)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

async def fetch_progress_jsons(cache_dir: Path):
    """Descarga solo los JSONs de progreso (rápido, ~20KB total)."""
    urls = {
        "allMviewGetProgressByDepartmentAndCorporations.json":
            f"{BASE}/divipol_json/allMviewGetProgressByDepartmentAndCorporations.json",
        "allMviewGetProgressByMunicipalityAndCorporations.json":
            f"{BASE}/divipol_json/allMviewGetProgressByMunicipalityAndCorporations.json",
        "CorpIndexAndMap.json":
            f"{BASE}/divipol_json/CorpIndexAndMap.json",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        for filename, url in urls.items():
            await _fetch_json(client, url, cache_dir / filename)
    logger.info("JSONs de progreso descargados en %s", cache_dir)


async def main(cache_dir: str = "cache", pdf_dir: str = "pdfs", dept_filter: str | None = None):
    cache = Path(cache_dir)
    async with httpx.AsyncClient(timeout=60) as client:
        tree = await fetch_departments_tree(client, cache)
        codes = await fetch_transmission_codes(client, cache)

    mesas = list(iter_all_mesas(tree))
    if dept_filter:
        mesas = [m for m in mesas if m.dept_code == dept_filter]

    index = build_hash_index(codes)
    mesas, missing = attach_hashes(mesas, index)

    print(f"\nTotal mesas:        {len(mesas):>8,}")
    print(f"Con hash PDF:       {len(mesas) - missing:>8,}")
    print(f"Sin hash (pending): {missing:>8,}")

    por_dept = Counter(m.dept_name for m in mesas if m.pdf_hash)
    print("\nTop 10 departamentos con actas publicadas:")
    for dept, n in sorted(por_dept.items(), key=lambda x: -x[1])[:10]:
        print(f"  {dept:<30} {n:>6,}")

    listas = [m for m in mesas if m.pdf_hash]
    if not listas:
        print("\nNo hay mesas con hash. Revisar estructura de allTransmissionCodes.json")
        return

    print(f"\nEjemplo URL: {listas[0].pdf_url}")
    print(f"\nIniciando descarga de {len(listas):,} PDFs con concurrencia=20...")
    stats = await download_batch(listas, Path(pdf_dir))
    print(f"\nDescarga completa: {stats}")


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--dept", help="Filtrar por código de departamento (ej: 05)")
    parser.add_argument("--cache", default="cache")
    parser.add_argument("--pdfs", default="pdfs")
    args = parser.parse_args()
    asyncio.run(main(cache_dir=args.cache, pdf_dir=args.pdfs, dept_filter=args.dept))
