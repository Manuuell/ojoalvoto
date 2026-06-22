"""Prueba el OCR mejorado en 3 PDFs y muestra resultados."""
import sys
sys.path.insert(0, ".")
from pathlib import Path
from pipeline.ocr_dept import pdf_to_text_all_pages, parse_e14_text, extract_all_votes

pdfs = sorted(Path("pdfs/60").rglob("*.pdf"))[:3]

for pdf_path in pdfs:
    print(f"\n{'='*55}")
    print(f"PDF: {pdf_path.name}  ({'/'.join(pdf_path.parts[-4:])})")

    # Extraccion posicional de votos
    pos = extract_all_votes(pdf_path)
    print(f"  Votos por posicion (_votes_raw): {pos.get('_votes_raw')}")

    # OCR completo + parse
    text = pdf_to_text_all_pages(pdf_path)
    row = parse_e14_text(text, pdf_path)

    print(f"  Potencial mesa:        {row.get('potencial_mesa')}")
    print(f"  Total sufragantes:     {row.get('total_sufragantes')}")
    print(f"  Candidatos detectados: {row.get('candidatos_detectados')}/13")
    print(f"  Hubo reconteo:         {row.get('hubo_recuento')}")
    votos = {k.replace('votos_',''):v for k,v in row.items()
             if k.startswith('votos_') and v is not None}
    print(f"  Votos candidatos: {votos}")

    # Mostrar texto OCR pag1 para ver como lee los nombres
    pag1 = text.split("===PAGINA===")[0] if "===PAGINA===" in text else text
    print(f"\n  --- TEXTO OCR PAG 1 (primeras 40 lineas) ---")
    for line in pag1.split("\n")[:40]:
        if line.strip():
            print(f"    {line}")
