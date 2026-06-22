"""Muestra el texto OCR completo de los primeros 3 PDFs para calibrar el parser."""
import fitz
import pytesseract
from PIL import Image
from pathlib import Path

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TESS_CONFIG = "--oem 3 --psm 6 -l spa"

pdfs = sorted(Path("pdfs/60").rglob("*.pdf"))[:2]

for pdf_path in pdfs:
    print(f"\n{'='*60}")
    print(f"ARCHIVO: {pdf_path}")
    print(f"{'='*60}")
    doc = fitz.open(str(pdf_path))
    print(f"Paginas: {len(doc)}")
    for i, page in enumerate(doc):
        mat = fitz.Matrix(250/72, 250/72)
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
        img = Image.frombytes("L", [pix.width, pix.height], pix.samples)
        text = pytesseract.image_to_string(img, config=TESS_CONFIG)
        print(f"\n--- PAGINA {i+1} ---")
        print(text)
    doc.close()
