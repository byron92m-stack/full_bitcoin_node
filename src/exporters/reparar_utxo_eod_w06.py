#!/usr/bin/env python3
"""Corrige utxo_eod_count de los 7 dias de 2022-W06 sin repetir el escaneo global.

Por que existe: reparar_semana_2022W06.py calculaba n_creados con la condicion
`cb.txid IS NULL` (heredada del calculo de fees), que EXCLUYE las salidas coinbase.
El indexer (PASO B) si las inserta como UTXO vivas, asi que el conteo quedaba corto
en ~1 salida por bloque (~140-190/dia) y utxo_eod_count derivaba.

n_creados depende SOLO de los archivos de la semana (outputs + blocks), no del join
de prevouts, asi que aqui se recalcula en segundos y se reescribe unicamente la
columna utxo_eod_count de esos 7 dias. El script canonico queda corregido tambien.
"""
import os
import shutil
import sys

import duckdb
import pandas as pd

BASE = "/media/SSD4T/obm"
C1, C2 = f"{BASE}/capa1", f"{BASE}/capa2"
SEM, ANIO = "2022-W06", "2022"
RUTA = f"{C2}/daily_aggregates_{ANIO}.parquet"

con = duckdb.connect()
con.execute("SET TimeZone='UTC'")

DIAS = [r[0] for r in con.execute(
    f"SELECT DISTINCT strftime(to_timestamp(time),'%Y-%m-%d') d "
    f"FROM read_parquet('{C1}/blocks/blocks_{SEM}.parquet') ORDER BY 1").fetchall()]
print(f"  dias UTC: {DIAS[0]} .. {DIAS[-1]} ({len(DIAS)})")

# creaciones por dia con el MISMO criterio que el indexer (PASO B), coinbase incluida
crea = con.execute(f"""
SELECT strftime(to_timestamp(b.time),'%Y-%m-%d') date, COUNT(*) n_creados
FROM read_parquet('{C1}/outputs/outputs_{SEM}.parquet') o
JOIN read_parquet('{C1}/blocks/blocks_{SEM}.parquet') b ON b.height = o.height
WHERE COALESCE(o.script_type,'') <> 'nulldata'
  AND NOT COALESCE(o.script_hex,'') LIKE '6a%'
  AND length(COALESCE(o.script_hex,'')) <= 20000
GROUP BY 1 ORDER BY 1""").df()
print("  salidas creadas por dia (coinbase incluida):")
print("   ", dict(zip(crea["date"], crea["n_creados"])))

d = pd.read_parquet(RUTA)
d["date"] = d["date"].astype(str)
ant = d[d["date"] < DIAS[0]]
DIA0 = ant["date"].max()
acum = int(ant.loc[ant["date"] == DIA0, "utxo_eod_count"].iloc[0])
print(f"  base {DIA0} (intacto) = {acum:,}")

nuevos = {}
for dia in DIAS:
    creados = int(crea.loc[crea["date"] == dia, "n_creados"].iloc[0])
    gastados = int(d.loc[d["date"] == dia, "spent_output_count"].iloc[0])
    acum += creados - gastados
    nuevos[dia] = acum
print("  utxo_eod_count corregido:", nuevos)

shutil.copy2(RUTA, RUTA + ".bak_utxo")
d.loc[d["date"].isin(nuevos), "utxo_eod_count"] = d["date"].map(nuevos)
assert not d["utxo_eod_count"].isna().any()
d.to_parquet(RUTA + ".tmp", index=False, compression="zstd")
os.replace(RUTA + ".tmp", RUTA)
print(f"  {os.path.basename(RUTA)}: columna utxo_eod_count de W06 corregida (backup .bak_utxo)")
con.close()
print("\nLISTO")
