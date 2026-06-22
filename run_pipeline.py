"""
Pipeline completo: descarga PDFs + OCR + analisis basico.
Uso: python run_pipeline.py --dept 60
"""
import asyncio
import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DEPT_NAMES = {
    "60": "AMAZONAS", "01": "ANTIOQUIA", "40": "ARAUCA", "03": "ATLANTICO",
    "16": "BOGOTA D.C.", "05": "BOLIVAR", "07": "BOYACA", "09": "CALDAS",
    "44": "CAQUETA", "46": "CASANARE", "11": "CAUCA", "12": "CESAR",
    "17": "CHOCO", "88": "CONSULADOS", "13": "CORDOBA", "15": "CUNDINAMARCA",
    "50": "GUAINIA", "54": "GUAVIARE", "19": "HUILA", "48": "LA GUAJIRA",
    "21": "MAGDALENA", "52": "META", "23": "NARINO", "25": "NORTE DE SAN",
    "64": "PUTUMAYO", "26": "QUINDIO", "24": "RISARALDA", "56": "SAN ANDRES",
    "27": "SANTANDER", "28": "SUCRE", "29": "TOLIMA", "31": "VALLE",
    "68": "VAUPES", "72": "VICHADA",
}


async def run(dept: str, skip_download: bool, skip_ocr: bool):
    name = DEPT_NAMES.get(dept, dept)
    logger.info("=" * 55)
    logger.info("PIPELINE: %s (%s)", name, dept)
    logger.info("=" * 55)

    # --- PASO 1: DESCARGA ---
    if not skip_download:
        from pipeline.download_dept import download_dept
        entries = await download_dept(dept, Path("cache"), concurrency=15)
        if not entries:
            logger.error("Sin entradas para dept=%s", dept)
            sys.exit(1)
    else:
        logger.info("Paso 1 omitido (--skip-download)")

    # --- PASO 2: OCR ---
    out_csv = Path(f"resultados/ocr_dept_{dept}.csv")
    if not skip_ocr:
        from pipeline.ocr_dept import ocr_dept
        rows = ocr_dept(dept, out_csv)
    else:
        logger.info("Paso 2 omitido (--skip-ocr)")
        rows = None

    # --- PASO 3: ANALISIS BASICO ---
    if out_csv.exists():
        import pandas as pd
        df = pd.read_csv(out_csv)
        logger.info("\nRESULTADOS BASICOS — %s", name)
        logger.info("  Actas procesadas:  %d", len(df))
        logger.info("  OCR exitoso:       %d (%.1f%%)", df["ocr_ok"].sum(), df["ocr_ok"].mean()*100)

        if "total_sufragantes" in df.columns:
            valid = df["total_sufragantes"].dropna()
            if len(valid) > 0:
                logger.info("  Total sufragantes detectados: %d actas con dato", len(valid))
                logger.info("    Min: %d  Max: %d  Media: %.1f", valid.min(), valid.max(), valid.mean())

        if "total_validos" in df.columns and "votos_blanco" in df.columns:
            # Verificacion basica de coherencia
            coherentes = df.apply(
                lambda r: (
                    r.get("total_validos") is not None and
                    r.get("votos_blanco") is not None and
                    r.get("votos_blanco", 0) <= r.get("total_validos", 0)
                ),
                axis=1,
            ).sum()
            logger.info("  Actas coherentes (blanco<=validos): %d", coherentes)

        logger.info("  CSV guardado en: %s", out_csv)

    logger.info("Pipeline completo.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dept", default="60", help="Codigo depto (default: 60=AMAZONAS)")
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--skip-ocr", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args.dept, args.skip_download, args.skip_ocr))
