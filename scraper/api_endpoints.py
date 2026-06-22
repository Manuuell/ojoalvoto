"""
Mapa completo de endpoints descubiertos — Visor Ciudadano E-14 Presidencial 2026.
Todos son GET públicos sin autenticación, servidos via CDN Akamai desde S3 (CloudFront BOG51-P3).
Se actualizan cada 60 segundos (cache-control: max-age=60).
"""

BASE = "https://divulgacione14presidente.registraduria.gov.co/assets/temis"

ENDPOINTS = {
    # Catálogos estáticos
    "departments":      f"{BASE}/divipol_json/allDepartments.json",
    "corporations":     f"{BASE}/divipol_json/allCorporations.json",
    "tree":             f"{BASE}/divipol_json/departmentsTree.json",         # 299KB gz — árbol completo
    "transmission":     f"{BASE}/divipol_json/allTransmissionCodes.json",    # 5.9MB gz — hash→PDF
    "corp_index_map":   f"{BASE}/divipol_json/CorpIndexAndMap.json",

    # Progreso de publicación (se actualizan en tiempo real)
    "progress_dept":    f"{BASE}/divipol_json/allMviewGetProgressByDepartmentAndCorporations.json",
    "progress_mun":     f"{BASE}/divipol_json/allMviewGetProgressByMunicipalityAndCorporations.json",

    # PDFs de actas E-14 (patrón, no URL directa):
    # GET {BASE}/pdf/{dept}/{mun}/{zone}/{stand}/{table:03d}/PRE/{sha256}.pdf?uuid={uuid4}
    # El sha256 viene de allTransmissionCodes.json
}

# Tipos de acta que pueden publicarse:
#   publishedE14    → PDF escaneado del formulario físico E-14
#   publishedPhoto  → Fotografía del acta (consulados exterior y zonas remotas)
#
# Departamentos con mayor proporción de FOTOS (sospechosos de difícil verificación):
#   CONSULADOS: 2333 fotos / 1026 E14 de 3670 esperadas  ← 63.6% son fotos
#   CAQUETA:      81 fotos /  898 E14 de  983 esperadas
#   CHOCO:        14 fotos / 1129 E14 de 1252 esperadas  + 109 faltantes
#   VAUPES:        9 fotos /   47 E14 de   88 esperadas  + 32 faltantes (36%)
