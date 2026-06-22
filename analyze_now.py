import json
import pandas as pd
from pathlib import Path

data = json.loads(Path("cache/allMviewGetProgressByDepartmentAndCorporations.json").read_text())
nodes = data["data"]["allMviewGetProgressByDepartmentAndCorporations"]["nodes"]
df = pd.DataFrame(nodes)
df["missing"] = df["expected"] - df["published"]
df["pct_pub"] = df["published"] / df["expected"] * 100
df["pct_photo"] = df.apply(
    lambda r: r["publishedPhoto"] / r["published"] * 100 if r["published"] > 0 else 0, axis=1
)

total_exp   = df["expected"].sum()
total_pub   = df["published"].sum()
total_e14   = df["publishedE14"].sum()
total_photo = df["publishedPhoto"].sum()
total_miss  = df["missing"].sum()

print("=" * 60)
print("RESUMEN NACIONAL — 1 junio 2026")
print("=" * 60)
print(f"Mesas esperadas:   {total_exp:>8,}")
print(f"Publicadas:        {total_pub:>8,}  ({total_pub/total_exp*100:.2f}%)")
print(f"E14 escaneados:    {total_e14:>8,}  ({total_e14/total_exp*100:.2f}%)")
print(f"Fotos:             {total_photo:>8,}  ({total_photo/total_exp*100:.2f}%)")
print(f"FALTANTES:         {total_miss:>8,}  ({total_miss/total_exp*100:.2f}%)")

print()
print("DEPARTAMENTOS CON MESAS FALTANTES (ordenado por cantidad):")
falt = df[df["missing"] > 0].sort_values("missing", ascending=False)
for _, r in falt.iterrows():
    pct_miss = 100 - r["pct_pub"]
    flag = " *** CRITICO" if pct_miss > 10 else " ** ALERTA" if pct_miss > 2 else ""
    print(f"  {r['name']:<22} {r['published']:>6}/{r['expected']:<6}  faltantes:{r['missing']:>5}  ({pct_miss:.2f}%){flag}")

print()
print("FOTOS vs E14 ESCANEADOS (fotos son mas dificiles de verificar):")
fotos = df[df["publishedPhoto"] > 0].sort_values("pct_photo", ascending=False)
for _, r in fotos.iterrows():
    flag = " *** CRITICO" if r["pct_photo"] > 50 else " ** ALERTA" if r["pct_photo"] > 20 else ""
    print(f"  {r['name']:<22} fotos:{r['publishedPhoto']:>5}  E14:{r['publishedE14']:>6}  foto%:{r['pct_photo']:>6.1f}%{flag}")

print()
print("TOTAL ACTAS SIN VERIFICAR (fotos + faltantes):")
df["sin_verificar"] = df["publishedPhoto"] + df["missing"]
sv = df[df["sin_verificar"] > 0].sort_values("sin_verificar", ascending=False)
for _, r in sv.iterrows():
    print(f"  {r['name']:<22} {r['sin_verificar']:>6} actas sin E14 escaneado ({r['sin_verificar']/r['expected']*100:.1f}%)")
