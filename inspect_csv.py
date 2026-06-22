import pandas as pd

df = pd.read_csv("resultados/ocr_dept_60.csv")
print(f"Columnas: {list(df.columns)}\n")
print(f"Total filas: {len(df)}")
print(f"\nEjemplo fila 0 - texto OCR:")
print(df["texto_completo"].iloc[0])
print(f"\nEjemplo fila 0 - datos extraidos:")
for col in ["total_validos","votos_blanco","votos_nulos","tarjetas_no_marc","total_sufragantes","total_potencial"]:
    print(f"  {col}: {df[col].iloc[0]}")
print(f"\nCuantos tienen total_sufragantes detectado: {df['total_sufragantes'].notna().sum()}/{len(df)}")
print(f"Cuantos tienen total_validos detectado:    {df['total_validos'].notna().sum()}/{len(df)}")
print(f"Cuantos tienen votos_blanco detectado:     {df['votos_blanco'].notna().sum()}/{len(df)}")
print(f"\nRango numeros_detectados: {df['numeros_detectados'].min()} - {df['numeros_detectados'].max()}")
print(f"Media numeros_detectados: {df['numeros_detectados'].mean():.1f}")
