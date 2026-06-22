"""Verifica la estructura del indice de hashes."""
import json, uuid
from pathlib import Path
from collections import Counter

print("Cargando allTransmissionCodes.json...")
data = json.loads(Path("cache/allTransmissionCodes.json").read_text(encoding="utf-8"))

index = {}
for status_key in ("status11", "status3"):
    for node in data["data"].get(status_key, {}).get("nodes", []):
        dept  = node["idDepartmentCode"]
        mun   = node["municipalityCode"]
        zone  = node["idZoneCode"]
        stand = node["standCode"]
        table = node["numberStand"]
        fname = node["expectedName"]
        key   = f"{dept}/{mun}/{zone}/{stand}/{table}"
        index[key] = fname

print(f"Indice: {len(index):,} entradas")

# Buscar claves del departamento 05 (BOLIVAR) para ver el patron real
print("\nEjemplos de claves dept=05:")
dept05 = [(k,v) for k,v in index.items() if k.startswith("05/")]
for k, v in dept05[:5]:
    print(f"  '{k}'  ->  '{v[:20]}...'")

# Verificar con el PDF real conocido:
# URL: /pdf/05/001/021/03/004/PRE/93ce73e7...pdf
test_key = "05/001/021/03/004"
print(f"\nBuscar '{test_key}': {'ENCONTRADO' if test_key in index else 'NO ENCONTRADO'}")

# Ver un nodo raw para entender campos exactos
node0 = data["data"]["status11"]["nodes"][0]
print(f"\nNodo ejemplo status11[0]:")
for k, v in node0.items():
    print(f"  {k}: {repr(v)}")

# Buscar el hash conocido directamente
known_hash = "93ce73e701b99b82fdd5e96c0a164b211ab039c175045459b5978117990f94b5.pdf"
found_key = next((k for k, v in index.items() if v == known_hash), None)
print(f"\nBuscar por hash conocido: '{found_key}'")

# Reconstruir URL con la logica correcta:
# index_key  -> zona SIN padding: '05/001/21/03/004'
# pdf_path   -> zona CON padding: '05/001/021/03/004'
if found_key:
    parts = found_key.split("/")
    dept, mun, zone_raw, stand, table = parts
    zone_padded = zone_raw.zfill(3)
    pdf_path = f"{dept}/{mun}/{zone_padded}/{stand}/{table}"
    BASE = "https://divulgacione14presidente.registraduria.gov.co/assets/temis"
    fname = index[found_key].replace(".pdf", "")
    url = f"{BASE}/pdf/{pdf_path}/PRE/{fname}.pdf?uuid={uuid.uuid4()}"
    print(f"\nURL generada:")
    print(f"  {url}")
    print(f"\nURL real conocida:")
    print(f"  {BASE}/pdf/05/001/021/03/004/PRE/93ce73e701b99b82fdd5e96c0a164b211ab039c175045459b5978117990f94b5.pdf")
    match = "MATCH" if pdf_path == "05/001/021/03/004" else "DIFERENTE"
    print(f"\nPath: {match}")
