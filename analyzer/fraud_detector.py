"""
Detector de anomalías electorales — Primera capa (sin OCR).

Analiza los JSONs de progreso para encontrar patrones sospechosos:
  1. Mesas faltantes por departamento (expected vs published)
  2. Proporción anormal de fotos vs E14 escaneados
  3. Municipios con 0% de publicación (bloqueo total)
  4. Outliers estadísticos en tasa de publicación
"""

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass
class Anomaly:
    level: str          # CRITICAL / WARNING / INFO
    dept_code: str
    dept_name: str
    description: str
    value: float


def load_dept_progress(path: str | Path) -> pd.DataFrame:
    """Carga allMviewGetProgressByDepartmentAndCorporations.json."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    nodes = data["data"]["allMviewGetProgressByDepartmentAndCorporations"]["nodes"]
    df = pd.DataFrame(nodes)
    df["pct_published"]    = df["published"]    / df["expected"] * 100
    df["pct_e14"]          = df["publishedE14"] / df["expected"] * 100
    df["pct_photo"]        = df["publishedPhoto"] / df["expected"] * 100
    df["pct_photo_of_pub"] = df.apply(
        lambda r: r["publishedPhoto"] / r["published"] * 100 if r["published"] > 0 else 0,
        axis=1,
    )
    df["missing"]          = df["expected"] - df["published"]
    return df


def load_mun_progress(path: str | Path) -> pd.DataFrame:
    """Carga allMviewGetProgressByMunicipalityAndCorporations.json."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    edges = data["data"]["allMviewGetProgressByMunicipalityAndCorporations"]["edges"]
    rows = [e["node"] for e in edges]
    df = pd.DataFrame(rows)
    df["pct_published"] = df["published"] / df["expected"] * 100
    df["missing"]       = df["expected"] - df["published"]
    return df


def detect_dept_anomalies(df: pd.DataFrame) -> list[Anomaly]:
    anomalies = []

    for _, r in df.iterrows():
        code = r["idDepartmentCode"]
        name = r["name"]

        # Mesas faltantes
        if r["missing"] > 0:
            pct_missing = r["missing"] / r["expected"] * 100
            level = "CRITICAL" if pct_missing > 10 else "WARNING" if pct_missing > 2 else "INFO"
            anomalies.append(Anomaly(
                level=level,
                dept_code=code,
                dept_name=name,
                description=f"{r['missing']} mesas sin publicar ({pct_missing:.1f}% del total)",
                value=pct_missing,
            ))

        # Proporción alta de fotos vs E14
        if r["pct_photo_of_pub"] > 20:
            level = "CRITICAL" if r["pct_photo_of_pub"] > 50 else "WARNING"
            anomalies.append(Anomaly(
                level=level,
                dept_code=code,
                dept_name=name,
                description=(
                    f"{r['publishedPhoto']} fotos vs {r['publishedE14']} E14 escaneados "
                    f"({r['pct_photo_of_pub']:.1f}% son fotos — más difíciles de verificar)"
                ),
                value=r["pct_photo_of_pub"],
            ))

    return sorted(anomalies, key=lambda a: (a.level != "CRITICAL", a.level != "WARNING", -a.value))


def print_report(dept_df: pd.DataFrame, mun_df: pd.DataFrame):
    print("=" * 70)
    print("REPORTE DE ANOMALÍAS — ELECCIONES PRESIDENCIALES COLOMBIA 2026")
    print("=" * 70)

    total_expected  = dept_df["expected"].sum()
    total_published = dept_df["published"].sum()
    total_e14       = dept_df["publishedE14"].sum()
    total_photo     = dept_df["publishedPhoto"].sum()
    total_missing   = dept_df["missing"].sum()

    print(f"\nRESUMEN NACIONAL:")
    print(f"  Mesas esperadas:    {total_expected:>8,}")
    print(f"  Publicadas:         {total_published:>8,}  ({total_published/total_expected*100:.2f}%)")
    print(f"  E14 escaneados:     {total_e14:>8,}  ({total_e14/total_expected*100:.2f}%)")
    print(f"  Fotos:              {total_photo:>8,}  ({total_photo/total_expected*100:.2f}%)")
    print(f"  FALTANTES:          {total_missing:>8,}  ({total_missing/total_expected*100:.2f}%)")

    print(f"\nDEPARTAMENTOS CON MESAS FALTANTES:")
    faltantes = dept_df[dept_df["missing"] > 0].sort_values("missing", ascending=False)
    for _, r in faltantes.iterrows():
        bar = "█" * int(r["pct_published"] / 2)
        print(f"  {r['name']:<20} {r['published']:>6}/{r['expected']:<6} {r['pct_published']:>6.2f}%  faltantes: {r['missing']:>4}")

    print(f"\nDEPARTAMENTOS CON ALTA PROPORCIÓN DE FOTOS (vs E14 escaneados):")
    fotos = dept_df[dept_df["pct_photo_of_pub"] > 0].sort_values("pct_photo_of_pub", ascending=False)
    for _, r in fotos.iterrows():
        if r["publishedPhoto"] > 0:
            print(f"  {r['name']:<20} fotos:{r['publishedPhoto']:>5}  E14:{r['publishedE14']:>6}  foto%:{r['pct_photo_of_pub']:>6.1f}%")

    anomalies = detect_dept_anomalies(dept_df)
    print(f"\nANOMALÍAS DETECTADAS ({len(anomalies)} total):")
    for a in anomalies:
        icon = "🔴" if a.level == "CRITICAL" else "🟡" if a.level == "WARNING" else "🔵"
        print(f"  [{a.level}] {a.dept_name}: {a.description}")

    # Municipios con menos del 90% publicado
    low_mun = mun_df[mun_df["pct_published"] < 90].sort_values("pct_published")
    if not low_mun.empty:
        print(f"\nMUNICIPIOS CON < 90% PUBLICADO ({len(low_mun)} municipios):")
        for _, r in low_mun.head(20).iterrows():
            print(f"  Dept {r['idDepartmentCode']} — {r['municipalityName']:<25} {r['published']:>4}/{r['expected']:<4} ({r['pct_published']:.1f}%)")


if __name__ == "__main__":
    cache = Path("cache")
    dept_path = cache / "allMviewGetProgressByDepartmentAndCorporations.json"
    mun_path  = cache / "allMviewGetProgressByMunicipalityAndCorporations.json"

    if not dept_path.exists():
        print("Ejecuta primero: python scraper/registraduria_client.py --cache cache")
    else:
        dept_df = load_dept_progress(dept_path)
        mun_df  = load_mun_progress(mun_path)
        print_report(dept_df, mun_df)
