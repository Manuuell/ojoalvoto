"""
OCR sobre los PDFs de un departamento ya descargados.
Extrae los datos del formulario E-14 y genera un CSV.

Uso: python pipeline/ocr_dept.py --dept 60
"""
import csv
import logging
import re
import sys
from pathlib import Path

import fitz
import pytesseract
from PIL import Image
from pipeline.preprocess import preprocess, binarize, crop_vote_column, crop_header, crop_nivelacion

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Ruta de Tesseract en Windows
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Configuracion OCR: modo pagina = bloque uniforme, solo numeros+letras espanol
TESS_CONFIG = "--oem 3 --psm 6 -l spa"


def render_page(pdf_path: Path, page_num: int = 0, dpi: int = 300) -> Image.Image:
    """Renderiza una pagina del PDF a imagen PIL en escala de grises."""
    doc = fitz.open(str(pdf_path))
    page = doc[page_num]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
    img = Image.frombytes("L", [pix.width, pix.height], pix.samples)
    doc.close()
    return img


def ocr_image(img: Image.Image, config: str = TESS_CONFIG) -> str:
    return pytesseract.image_to_string(img, config=config)


def extract_positioned_numbers(img: Image.Image) -> list[tuple[int, int, int]]:
    """
    Extrae numeros con sus coordenadas (x_centro, y_centro, valor).
    Usa image_to_data de Tesseract que devuelve bounding boxes por palabra.
    """
    import pandas as pd
    data = pytesseract.image_to_data(
        img, config="--oem 3 --psm 6 -l spa",
        output_type=pytesseract.Output.DATAFRAME
    )
    data = data[data["conf"] > 30]  # solo detecciones con >30% confianza
    results = []
    for _, row in data.iterrows():
        text = str(row["text"]).strip()
        if re.fullmatch(r"\d{1,4}", text):
            val = int(text)
            if val > 2000:  # filtrar barcodes y numeros de serie
                continue
            x_center = int(row["left"] + row["width"] / 2)
            y_center = int(row["top"] + row["height"] / 2)
            results.append((x_center, y_center, val))
    return results


def ocr_vote_cell(cell_img: Image.Image) -> int:
    """
    OCR de una celda de votos del E-14.
    Formato: 3 cajas [centenas][decenas][unidades], puntos (.) = cero.
    Retorna el valor numerico (0-999).
    """
    # Ampliar y binarizar la celda
    w, h = cell_img.size
    cell_img = cell_img.resize((w * 3, h * 3), Image.LANCZOS)
    cell_img = binarize(cell_img)

    # OCR caracter por caracter (PSM 8 = una sola palabra)
    text = pytesseract.image_to_string(
        cell_img,
        config="--oem 3 --psm 8 -c tessedit_char_whitelist=0123456789. "
    ).strip()

    # Limpiar: reemplazar puntos/espacios por ceros, tomar solo digitos
    digits = ""
    for ch in text:
        if ch.isdigit():
            digits += ch
        elif ch in (".", "•", " ", "o", "O"):
            digits += "0"

    if not digits:
        return 0
    # Tomar los ultimos 3 digitos (el formato siempre es de 3 celdas)
    return int(digits[-3:]) if len(digits) >= 3 else int(digits) if digits else 0


def extract_votes_by_position(img: Image.Image) -> list[int]:
    """
    Extrae los votos usando posicion espacial + OCR por celda.

    Layout real del E-14 (confirmado en imagen):
      - Columna VOTACION: ~80-98% del ancho de la pagina
      - Cada candidato ocupa ~12% del alto de la zona de tabla
      - Zona de candidatos: pag1 ~48%-95%, pag2 ~28%-82%
      - Las 3 celdas de votos estan en la franja horizontal de cada candidato
    """
    w, h = img.size

    # Zona de la columna de votos:
    #   X: ultimo 20% de la pagina (las 3 celdas de votos)
    #   Y: desde 42% hasta 97% — excluye header (0-12%), info mesa (12-28%),
    #      seccion NIVELACION (28-42%) y el footer con KIT/barcode
    x_start = int(w * 0.80)
    y_start = int(h * 0.42)
    y_end   = int(h * 0.97)

    import pandas as pd
    data = pytesseract.image_to_data(
        img, config="--oem 3 --psm 6 -l spa",
        output_type=pytesseract.Output.DATAFRAME
    )
    data = data[(data["conf"] > 20) & (data["text"].str.strip() != "")]

    # Filtrar tokens en la columna de votos Y debajo del header/nivelacion
    vote_tokens = data[
        (data["left"] >= x_start) &
        (data["top"]  >= y_start) &
        (data["top"]  <= y_end)
    ].copy()
    if vote_tokens.empty:
        return []

    # Agrupar por fila de candidato: clusterizar por coordenada Y
    vote_tokens = vote_tokens.sort_values("top")
    vote_tokens["y_center"] = vote_tokens["top"] + vote_tokens["height"] // 2

    # Detectar filas de candidato agrupando tokens con Y cercano (tolerancia 20px)
    rows: list[list] = []
    current_row: list = []
    prev_y = -100
    for _, tok in vote_tokens.iterrows():
        if tok["y_center"] - prev_y > 25:  # nueva fila
            if current_row:
                rows.append(current_row)
            current_row = [tok]
        else:
            current_row.append(tok)
        prev_y = tok["y_center"]
    if current_row:
        rows.append(current_row)

    # Por cada fila, concatenar los caracteres y parsear como numero
    votes = []
    for row_tokens in rows:
        chars = "".join(str(t["text"]).strip() for t in sorted(row_tokens, key=lambda t: t["left"]))
        # Interpretar puntos como ceros
        digits = ""
        for ch in chars:
            if ch.isdigit():
                digits += ch
            elif ch in (".", "•", "o", "O"):
                digits += "0"
        if digits:
            try:
                val = int(digits[-3:]) if len(digits) >= 3 else int(digits)
                if 0 <= val <= 600:
                    votes.append(val)
            except ValueError:
                pass

    return votes


def pdf_to_text_all_pages(pdf_path: Path, dpi: int = 300) -> str:
    """Renderiza todas las paginas y concatena el texto OCR."""
    doc = fitz.open(str(pdf_path))
    n_pages = len(doc)
    doc.close()
    texts = []
    for i in range(n_pages):
        raw = render_page(pdf_path, i, dpi)
        processed = preprocess(raw)
        texts.append(ocr_image(processed))
    return "\n\n===PAGINA===\n\n".join(texts)


def extract_all_votes(pdf_path: Path, dpi: int = 300) -> dict:
    """
    Extrae votos por posicion espacial de paginas 1 y 2.
    Retorna dict con votos por candidato y totales.
    """
    # Candidatos en orden del formulario E-14 presidencial 2026
    candidate_order = [
        "cepeda", "claudia", "botero", "espriella", "lizcano",
        "uribe_l", "sondra", "barreras", "caicedo", "matamoros",
        "paloma", "fajardo", "murillo"
    ]

    all_votes = []
    for page_num in range(2):  # paginas 1 y 2 tienen candidatos
        try:
            raw = render_page(pdf_path, page_num, dpi)
            processed = preprocess(raw)
            page_votes = extract_votes_by_position(processed)
            all_votes.extend(page_votes)
        except Exception:
            pass

    result = {}
    # Asignar votos a candidatos por posicion (los primeros 7 son pag1, los siguientes pag2)
    for i, cand in enumerate(candidate_order):
        result[f"votos_{cand}"] = all_votes[i] if i < len(all_votes) else None

    result["votos_blanco"]       = all_votes[13] if len(all_votes) > 13 else None
    result["votos_nulos"]        = all_votes[14] if len(all_votes) > 14 else None
    result["tarjetas_no_marc"]   = all_votes[15] if len(all_votes) > 15 else None
    result["total_sufragantes_pos"] = all_votes[16] if len(all_votes) > 16 else None
    result["_votes_raw"]         = str(all_votes[:20])
    return result


def extract_numbers(text: str) -> list[int]:
    """Extrae todos los números del texto OCR."""
    return [int(n) for n in re.findall(r"\b\d+\b", text)]


def parse_e14_text(text: str, pdf_path: Path, use_positional: bool = True) -> dict:
    """
    Parsea texto OCR del acta E-14 presidencial Colombia 2026.

    Estructura real del formulario (3 paginas):
      Pag 1: cabecera + candidatos 1-7 + sus votos en tabla
      Pag 2: candidatos 8-13 + SUMA TOTAL al final
      Pag 3: firmas de jurados

    Campos clave:
      NIVELACION DE LA MESA = potencial de votantes habilitados
      Numero junto a cada candidato = votos obtenidos
      SUMA TOTAL (CANDIDATOS + EN BLANCO + NULOS + NO MARCADOS) = total sufragantes
    """
    parts = pdf_path.parts
    result = {
        "archivo":   pdf_path.name,
        "dept":      parts[-5] if len(parts) >= 5 else "",
        "mun":       parts[-4] if len(parts) >= 4 else "",
        "zona":      parts[-3] if len(parts) >= 3 else "",
        "stand":     parts[-2] if len(parts) >= 2 else "",
        "mesa":      pdf_path.stem,
        "texto_p1":  text.split("===PAGINA===")[0][:400].replace("\n", " ") if "===PAGINA===" in text else text[:400].replace("\n", " "),
        "ocr_ok":    True,
    }

    text_upper = text.upper()
    numbers = extract_numbers(text)
    result["numeros_detectados"] = len(numbers)

    # --- Potencial de votantes (seccion NIVELACION DE LA MESA) ---
    # El formulario tiene 3 filas en esa seccion:
    #   TOTAL VOTANTES FORMULARIO E-11  →  XXX  (= votantes habilitados)
    #   TOTAL VOTOS EN LA URNA          →  XXX
    #   TOTAL VOTOS INCINERADOS         →  XXX
    # Intentamos varias variantes porque el OCR garble esta seccion
    potencial = None
    for pattern in [
        r"TOTAL\s+VOTANTES[^\d]{0,40}(\d{2,4})",
        r"FORMULARIO\s+E.?11[^\d]{0,20}(\d{2,4})",
        r"NIVEL[AÁ]CI[OÓ]N[^\d]{0,40}(\d{2,4})",
        r"VOTOS\s+EN\s+LA\s+URNA[^\d]{0,20}(\d{2,4})",
    ]:
        m = re.search(pattern, text_upper)
        if m:
            val = int(m.group(1))
            if 10 <= val <= 600:
                potencial = val
                break
    result["potencial_mesa"] = potencial

    # --- SUMA TOTAL de sufragantes (final pag 2) ---
    # "SUMA TOTAL (CANDIDATOS + EN BLANCO + NULOS + NO MARCADOS)" seguido del numero
    # El OCR lo lee con variaciones: "SUMA TOTAL", "TOTAL CANDIDATOS"
    result["total_sufragantes"] = None
    for m in re.finditer(r"SUMA\s+TOTAL[^\d]{0,80}(\d{1,3})", text_upper):
        val = int(m.group(1))
        if 5 <= val <= 600:   # rango razonable, excluye KIT numbers (9330+)
            result["total_sufragantes"] = val
            break

    # --- Extraccion posicional de votos (mas precisa que regex) ---
    if use_positional:
        pos_data = extract_all_votes(pdf_path)
        result.update(pos_data)

    # --- Candidatos y votos por regex (fallback / verificacion cruzada) ---
    # Limite de votos por candidato: max 500 (evita capturar año, barcodes, KIT)
    candidates = {
        "cepeda":       r"(?:IV[AÁ]N\s+)?CEPEDA[^\d]{0,30}(\d{1,3})",
        "claudia":      r"CLAUDIA\s+L[OÓ]PEZ[^\d]{0,30}(\d{1,3})",
        "botero":       r"BOTERO\s+JARAMILLO[^\d]{0,30}(\d{1,3})",
        "espriella":    r"ESPRIELLA[^\d]{0,30}(\d{1,3})",
        "lizcano":      r"LIZCANO[^\d]{0,30}(\d{1,3})",
        "uribe_l":      r"MIGUEL\s+URIBE\s+LONDONO[^\d]{0,30}(\d{1,3})",
        "sondra":       r"SONDRA[^\d]{0,30}(\d{1,3})",
        "barreras":     r"BARRERAS[^\d]{0,30}(\d{1,3})",
        "caicedo":      r"CAICEDO[^\d]{0,30}(\d{1,3})",
        "matamoros":    r"MATAMOROS[^\d]{0,30}(\d{1,3})",
        "paloma":       r"PALOMA\s+VALENCIA[^\d]{0,30}(\d{1,3})",
        "fajardo":      r"FAJARDO[^\d]{0,30}(\d{1,3})",
        "murillo":      r"MURILLO\s+URRUTIA[^\d]{0,30}(\d{1,3})",
    }
    for cand, pattern in candidates.items():
        if result.get(f"votos_{cand}") is None:   # solo si posicional no lo encontro
            m = re.search(pattern, text_upper)
            result[f"votos_{cand}"] = int(m.group(1)) if m else None

    # --- Verificacion interna de coherencia ---
    votos_cands = [result[f"votos_{c}"] for c in candidates if result.get(f"votos_{c}") is not None]
    result["suma_candidatos_detectados"] = sum(votos_cands) if votos_cands else None
    result["candidatos_detectados"] = len(votos_cands)
    # Reconteo: buscar en pagina 3 (firmas), no en el encabezado
    pag3 = text.split("===PAGINA===")[-1].upper() if "===PAGINA===" in text else ""
    result["hubo_recuento"] = "S" if re.search(r"RECUENTO[^\n]{0,30}S[IÍ]\b", pag3) else "N"

    return result


def ocr_dept(dept_code: str, output_csv: Path):
    pdf_dir = Path("pdfs") / dept_code
    if not pdf_dir.exists():
        logger.error("No existe directorio %s — ejecuta download_dept.py primero", pdf_dir)
        sys.exit(1)

    pdfs = sorted(pdf_dir.rglob("*.pdf"))
    logger.info("Procesando %d PDFs de dept=%s...", len(pdfs), dept_code)

    rows = []
    for i, pdf_path in enumerate(pdfs, 1):
        try:
            text = pdf_to_text_all_pages(pdf_path)
            row = parse_e14_text(text, pdf_path)
            rows.append(row)
            if i % 10 == 0:
                logger.info("  %d/%d procesados...", i, len(pdfs))
        except Exception as e:
            logger.warning("  ERROR en %s: %s", pdf_path.name, e)
            rows.append({"archivo": pdf_path.name, "ocr_ok": False, "error": str(e)})

    if not rows:
        logger.error("Sin resultados")
        return

    # Guardar CSV
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    ok = sum(1 for r in rows if r.get("ocr_ok"))
    logger.info("OCR completo: %d/%d exitosos -> %s", ok, len(rows), output_csv)
    return rows


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dept", required=True)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    out = Path(args.output) if args.output else Path(f"resultados/ocr_dept_{args.dept}.csv")
    ocr_dept(args.dept, out)
