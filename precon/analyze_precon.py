"""
Analisis de fraude sobre datos PRECON.
Corre: python precon/analyze_precon.py
"""
import json
import math
from pathlib import Path

import pandas as pd
import numpy as np

CANDIDATES = {
    "1":  "CEPEDA CASTRO",
    "2":  "CLAUDIA LOPEZ",
    "3":  "BOTERO JARAMILLO",
    "4":  "DE LA ESPRIELLA",
    "5":  "LIZCANO ARANGO",
    "6":  "URIBE LONDONO",
    "7":  "SONDRA GARVIN",
    "8":  "BARRERAS MONTEALEGRE",
    "9":  "CAICEDO OMAR",
    "10": "MATAMOROS",
    "11": "PALOMA VALENCIA",
    "12": "FAJARDO VALDERRAMA",
    "13": "MURILLO URRUTIA",
}

DEPT_NAMES = {
    "01":"ANTIOQUIA","03":"ATLANTICO","05":"BOLIVAR","07":"BOYACA",
    "09":"CALDAS","11":"CAUCA","12":"CESAR","13":"CORDOBA",
    "15":"CUNDINAMARCA","16":"BOGOTA D.C.","17":"CHOCO","19":"HUILA",
    "21":"MAGDALENA","23":"NARINO","24":"RISARALDA","25":"NORTE SANTANDER",
    "26":"QUINDIO","27":"SANTANDER","28":"SUCRE","29":"TOLIMA",
    "31":"VALLE","40":"ARAUCA","44":"CAQUETA","46":"CASANARE",
    "48":"LA GUAJIRA","50":"GUAINIA","52":"META","54":"GUAVIARE",
    "56":"SAN ANDRES","60":"AMAZONAS","64":"PUTUMAYO","68":"VAUPES",
    "72":"VICHADA","88":"CONSULADOS"
}


def parse_precon(data: dict) -> dict:
    result = {"amb": data.get("amb",""), "dept": data.get("dept","")}
    totales = data.get("totales",{}).get("act",{})
    result["votant"]  = int(totales.get("votant",0) or 0)
    result["votnul"]  = int(totales.get("votnul",0) or 0)
    result["votnma"]  = int(totales.get("votnma",0) or 0)
    result["votblan"] = int(totales.get("votblan") or totales.get("votbla",0) or 0)
    result["votval"]  = int(totales.get("votval",0) or 0)
    result["mesesc"]  = int(totales.get("mesesc",0) or 0)
    result["metota"]  = int(totales.get("metota",0) or 0)
    result["centota"] = int(totales.get("centota",0) or 0)  # censo electoral

    camaras = data.get("camaras",[])
    if camaras:
        for partido in camaras[0].get("partotabla",[]):
            act = partido.get("act",{})
            for cand in act.get("cantotabla",[]):
                cod = str(cand.get("codcan",""))
                result[f"vot_{cod}"] = int(cand.get("vot",0) or 0)

    # Historico (solo en nivel nacional/dept)
    result["_historico"] = data.get("historico", [])
    # Mapagan (ganador por sub-ambito)
    result["_mapagan"] = data.get("camaras",[{}])[0].get("mapagan",[]) if data.get("camaras") else []

    return result


def load_all(cache_dir: Path):
    rows = []
    for f in sorted(cache_dir.glob("*.json")):
        if f.name == "departmentsTree_ref.json":
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if "elec" not in data:
                continue
            row = parse_precon(data)
            row["amb"] = f.stem
            n = len(f.stem)
            row["nivel"] = "nacional" if n==2 and f.stem=="00" else \
                           "dept"     if n==2 else \
                           "mun"      if n==5 else "otro"
            rows.append(row)
        except:
            pass
    return pd.DataFrame(rows)


def benford(numbers):
    nums = [n for n in numbers if n > 9]
    if len(nums) < 30:
        return None
    fd = [int(str(n)[0]) for n in nums]
    obs = {d: fd.count(d)/len(fd) for d in range(1,10)}
    exp = {d: math.log10(1+1/d) for d in range(1,10)}
    chi2 = sum(len(fd)*(obs[d]-exp[d])**2/exp[d] for d in range(1,10))
    return {"chi2": round(chi2,2), "n": len(fd), "obs": obs, "exp": exp,
            "alerta": chi2 > 15.5}


# ─────────────────────────────────────────────
#  A) BENFORD POR DEPARTAMENTO
# ─────────────────────────────────────────────
def analisis_benford_por_dept(df: pd.DataFrame):
    print("\n" + "="*60)
    print("A) LEY DE BENFORD POR DEPARTAMENTO")
    print("   (Chi2 > 15.5 = anomalia estadistica p<0.05)")
    print("="*60)

    mun = df[df["nivel"]=="mun"].copy()
    alertas = []

    for dept_code, dept_name in sorted(DEPT_NAMES.items()):
        subset = mun[mun["amb"].str.startswith(dept_code)]
        for cod, cname in [("4","DE LA ESPRIELLA"),("1","CEPEDA CASTRO")]:
            col = f"vot_{cod}"
            if col not in subset.columns:
                continue
            vals = subset[col].dropna().astype(int).tolist()
            bf = benford(vals)
            if bf is None:
                continue
            flag = " *** ALERTA" if bf["alerta"] else ""
            if bf["alerta"] or bf["chi2"] > 10:
                alertas.append({
                    "dept": dept_name, "candidato": cname,
                    "chi2": bf["chi2"], "n": bf["n"],
                    "alerta": bf["alerta"]
                })

    # Mostrar ordenado por chi2
    alertas_df = pd.DataFrame(alertas).sort_values("chi2", ascending=False)
    print(f"\n{'Departamento':<22} {'Candidato':<22} {'Chi2':>7}  {'n':>5}  Estado")
    print("-"*72)
    for _, r in alertas_df.iterrows():
        estado = "*** ANOMALIA ***" if r["alerta"] else "vigilar"
        print(f"  {r['dept']:<20} {r['candidato']:<22} {r['chi2']:>7.2f}  {r['n']:>5}  {estado}")


# ─────────────────────────────────────────────
#  B) PARTICIPACION ANORMAL (>80% o <20%)
# ─────────────────────────────────────────────
def analisis_participacion(df: pd.DataFrame):
    print("\n" + "="*60)
    print("B) MUNICIPIOS CON PARTICIPACION ANOMALA")
    print("   (Promedio nacional: 57.88%)")
    print("="*60)

    mun = df[(df["nivel"]=="mun") & (df["centota"]>100)].copy()
    if mun.empty:
        # sin censo electoral, usar votant vs promedio
        mun = df[(df["nivel"]=="mun") & (df["votant"]>0)].copy()
        avg = mun["votant"].mean()
        std = mun["votant"].std()
        outliers = mun[abs(mun["votant"]-avg) > 3*std].copy()
        outliers["razon"] = "outlier_votos"
    else:
        mun["pct_part"] = mun["votant"] / mun["centota"] * 100
        outliers = mun[(mun["pct_part"] > 80) | (mun["pct_part"] < 15)].copy()
        outliers["razon"] = outliers["pct_part"].apply(
            lambda x: "PARTICIPACION >80%" if x > 80 else "PARTICIPACION <15%"
        )

    if "pct_part" in outliers.columns:
        outliers = outliers.sort_values("pct_part", ascending=False)
        print(f"\n  {'Municipio':<10} {'Votantes':>10} {'Censo':>10} {'Part%':>8}  Razon")
        print("  " + "-"*55)
        for _, r in outliers.head(30).iterrows():
            dept = r["amb"][:2]
            dname = DEPT_NAMES.get(dept, dept)
            print(f"  {r['amb']:<10} {r['votant']:>10,} {r['centota']:>10,} {r['pct_part']:>7.1f}%  {r['razon']}  [{dname}]")
    else:
        print(f"\n  Municipios con votos > media+3sigma:")
        for _, r in outliers.head(20).iterrows():
            print(f"  {r['amb']}: {r['votant']:,} votantes")

    # Participacion por departamento
    dept_df = df[df["nivel"]=="dept"].copy()
    if not dept_df.empty and "centota" in dept_df.columns:
        dept_df2 = dept_df[dept_df["centota"]>0].copy()
        if not dept_df2.empty:
            dept_df2["pct"] = dept_df2["votant"]/dept_df2["centota"]*100
            print(f"\n  PARTICIPACION POR DEPARTAMENTO:")
            for _, r in dept_df2.sort_values("pct", ascending=False).iterrows():
                name = DEPT_NAMES.get(r["amb"], r["amb"])
                flag = " <-- ALTA" if r["pct"]>75 else (" <-- BAJA" if r["pct"]<35 else "")
                print(f"  {name:<22} {r['pct']:>6.1f}%  ({r['votant']:,} / {r['centota']:,}){flag}")


# ─────────────────────────────────────────────
#  C) ANALISIS DEL HISTORICO (saltos sospechosos)
# ─────────────────────────────────────────────
def analisis_historico(cache_dir: Path):
    print("\n" + "="*60)
    print("C) HISTORICO DEL CONTEO — SALTOS SOSPECHOSOS")
    print("   (Cada entrada = snapshot cada ~5 minutos)")
    print("="*60)

    # Cargar historico nacional
    nac_path = cache_dir / "00.json"
    if not nac_path.exists():
        print("  00.json no encontrado")
        return

    data = json.loads(nac_path.read_text(encoding="utf-8"))
    hist = data.get("historico", [])
    if not hist:
        print("  Sin historico")
        return

    # Convertir a DataFrame
    rows = []
    for h in hist:
        mdhm = str(h.get("mdhm",""))
        if len(mdhm) == 8:
            hora = f"{mdhm[2:4]}:{mdhm[4:6]}"
        else:
            hora = mdhm
        rows.append({
            "numact":   int(h.get("numact",0)),
            "mesesc":   int(h.get("mesesc",0)),
            "mesfalt":  int(h.get("mesfalt",0)),
            "hora":     hora,
        })
    hdf = pd.DataFrame(rows).sort_values("numact")

    # Calcular mesas nuevas por intervalo
    hdf["mesas_nuevas"] = hdf["mesesc"].diff().fillna(0)
    avg = hdf["mesas_nuevas"][hdf["mesas_nuevas"]>0].mean()
    std = hdf["mesas_nuevas"][hdf["mesas_nuevas"]>0].std()

    print(f"\n  Total snapshots: {len(hdf)}")
    print(f"  Promedio mesas por intervalo: {avg:.0f}")
    print(f"  Desviacion estandar: {std:.0f}")
    print(f"\n  {'Snap':>5} {'Hora':>6} {'Mesas acum':>12} {'Nuevas':>8}  Estado")
    print("  " + "-"*50)

    alertas_hist = []
    for _, r in hdf.iterrows():
        nuevas = r["mesas_nuevas"]
        if nuevas > avg + 3*std and nuevas > 100:
            estado = f"*** SALTO ANOMALO ({nuevas:.0f} mesas de golpe)"
            alertas_hist.append(r)
        elif nuevas > avg + 2*std:
            estado = f"** pico alto ({nuevas:.0f})"
        else:
            estado = ""
        if estado or r["numact"] % 5 == 0:
            print(f"  {r['numact']:>5} {r['hora']:>6} {r['mesesc']:>12,} {nuevas:>8.0f}  {estado}")

    if not alertas_hist:
        print("\n  No se detectaron saltos anomalos en el historico nacional.")
    else:
        print(f"\n  *** {len(alertas_hist)} SALTOS ANOMALOS DETECTADOS ***")

    # Analizar historicos por departamento
    print(f"\n  SALTOS EN DEPARTAMENTOS:")
    dept_alertas = []
    for dept_code in DEPT_NAMES:
        dp = cache_dir / f"{dept_code}.json"
        if not dp.exists():
            continue
        try:
            d2 = json.loads(dp.read_text(encoding="utf-8"))
            h2 = d2.get("historico",[])
            if len(h2) < 5:
                continue
            mesas = [int(x.get("mesesc",0)) for x in sorted(h2, key=lambda x: int(x.get("numact",0)))]
            diffs = [mesas[i]-mesas[i-1] for i in range(1,len(mesas))]
            if not diffs:
                continue
            avg2 = sum(diffs)/len(diffs)
            std2 = (sum((d-avg2)**2 for d in diffs)/len(diffs))**0.5
            max_salto = max(diffs)
            if std2 > 0 and max_salto > avg2 + 3*std2 and max_salto > 50:
                dept_alertas.append({
                    "dept": DEPT_NAMES[dept_code],
                    "max_salto": max_salto,
                    "avg": round(avg2,1),
                    "std": round(std2,1),
                    "ratio": round(max_salto/std2,1) if std2>0 else 0
                })
        except:
            pass

    dept_alertas.sort(key=lambda x: -x["ratio"])
    if dept_alertas:
        print(f"\n  {'Departamento':<22} {'Max salto':>10} {'Promedio':>9} {'Std':>7} {'Ratio':>7}")
        print("  " + "-"*58)
        for a in dept_alertas:
            flag = " ***" if a["ratio"] > 5 else ""
            print(f"  {a['dept']:<22} {a['max_salto']:>10,} {a['avg']:>9.1f} {a['std']:>7.1f} {a['ratio']:>7.1f}{flag}")
    else:
        print("  Sin saltos anomalos detectados por departamento.")


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
def main():
    cache_dir = Path("precon/cache")
    df = load_all(cache_dir)

    print("="*60)
    print("ANALISIS PRECON — ELECCIONES PRESIDENCIALES COLOMBIA 2026")
    print("="*60)

    nac = df[df["nivel"]=="nacional"]
    if not nac.empty:
        r = nac.iloc[0]
        print(f"\nRESUMEN NACIONAL:")
        print(f"  Votantes:    {r['votant']:>12,}  ({r['votant']/41421973*100:.2f}% del censo)")
        print(f"  Validos:     {r['votval']:>12,}")
        print(f"  Nulos:       {r['votnul']:>12,}  ({r['votnul']/r['votant']*100:.2f}%)")
        print(f"  No marcadas: {r['votnma']:>12,}  ({r['votnma']/r['votant']*100:.2f}%)")
        print(f"  Blancos:     {r['votblan']:>12,}  ({r['votblan']/r['votval']*100:.2f}%)")

        cand_cols = sorted([c for c in df.columns if c.startswith("vot_")],
                          key=lambda c: -r.get(c,0))
        total_can = sum(r.get(c,0) for c in cand_cols)
        print(f"\nVOTOS POR CANDIDATO:")
        for col in cand_cols:
            cod = col.replace("vot_","")
            vot = int(r.get(col,0) or 0)
            if vot > 0:
                name = CANDIDATES.get(cod, f"Candidato {cod}")
                print(f"  {name:<35} {vot:>12,}  ({vot/total_can*100:.2f}%)")
        diff = abs(int(r.get("vot_4",0)) - int(r.get("vot_1",0)))
        print(f"\n  Diferencia 1er-2do lugar: {diff:,} votos ({diff/total_can*100:.2f}%)")

    analisis_benford_por_dept(df)
    analisis_participacion(df)
    analisis_historico(cache_dir)

    print("\n" + "="*60)
    print("FIN DEL ANALISIS")
    print("="*60)


if __name__ == "__main__":
    main()
