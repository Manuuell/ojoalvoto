"""
Genera el manifest COMPLETO (121.041 actas) desde cache/allTransmissionCodes.json
y lo escribe en safevote-web/data/manifest.csv

Correr desde la raíz del proyecto:
    python gen_full_manifest.py
"""
import csv
import json
from pathlib import Path

SRC = Path("cache/allTransmissionCodes.json")
OUT = Path("safevote-web/data/manifest.csv")

def main():
    data = json.loads(SRC.read_text(encoding="utf-8"))
    rows = []
    for status_key in ("status11", "status3"):
        for n in data["data"].get(status_key, {}).get("nodes", []):
            dept = n["idDepartmentCode"]; mun = n["municipalityCode"]
            zona = n["idZoneCode"]; stand = n["standCode"]; mesa = n["numberStand"]
            acta_id = f"{dept}_{mun}_{zona}_{stand}_{mesa}"
            rows.append({
                "acta_id": acta_id, "dept": dept, "mun": mun, "zona": zona,
                "stand": stand, "mesa": mesa, "hash": n["expectedName"], "ok": "True",
            })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["acta_id","dept","mun","zona","stand","mesa","hash","ok"])
        w.writeheader(); w.writerows(rows)
    print(f"{len(rows):,} actas escritas en {OUT}")

if __name__ == "__main__":
    main()
