#!/usr/bin/env python3
"""Fixes utxo_eod_count of the 7 days of 2022-W06 without repeating the global scan.

Why it exists: reparar_semana_2022W06.py computed n_creados with the condition
`cb.txid IS NULL` (inherited from the fees calculation), which EXCLUDES coinbase outputs.
The indexer (STEP B) does insert them as live UTXOs, so the count came up short
by ~1 output per block (~140-190/day) and utxo_eod_count drifted.

n_creados depends ONLY on the files of the week (outputs + blocks), not on the join
of prevouts, so here it is recomputed in seconds and only the utxo_eod_count column
of those 7 days is rewritten. The canonical script is fixed as well.
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
print(f"  UTC days: {DIAS[0]} .. {DIAS[-1]} ({len(DIAS)})")

# creations per day with the SAME criterion as the indexer (STEP B), coinbase included
crea = con.execute(f"""
SELECT strftime(to_timestamp(b.time),'%Y-%m-%d') date, COUNT(*) n_creados
FROM read_parquet('{C1}/outputs/outputs_{SEM}.parquet') o
JOIN read_parquet('{C1}/blocks/blocks_{SEM}.parquet') b ON b.height = o.height
WHERE COALESCE(o.script_type,'') <> 'nulldata'
  AND NOT COALESCE(o.script_hex,'') LIKE '6a%'
  AND length(COALESCE(o.script_hex,'')) <= 20000
GROUP BY 1 ORDER BY 1""").df()
print("  outputs created per day (coinbase included):")
print("   ", dict(zip(crea["date"], crea["n_creados"])))

d = pd.read_parquet(RUTA)
d["date"] = d["date"].astype(str)
ant = d[d["date"] < DIAS[0]]
DIA0 = ant["date"].max()
acum = int(ant.loc[ant["date"] == DIA0, "utxo_eod_count"].iloc[0])
print(f"  base {DIA0} (intact) = {acum:,}")

nuevos = {}
for dia in DIAS:
    creados = int(crea.loc[crea["date"] == dia, "n_creados"].iloc[0])
    gastados = int(d.loc[d["date"] == dia, "spent_output_count"].iloc[0])
    acum += creados - gastados
    nuevos[dia] = acum
print("  utxo_eod_count corrected:", nuevos)

shutil.copy2(RUTA, RUTA + ".bak_utxo")
d.loc[d["date"].isin(nuevos), "utxo_eod_count"] = d["date"].map(nuevos)
assert not d["utxo_eod_count"].isna().any()
d.to_parquet(RUTA + ".tmp", index=False, compression="zstd")
os.replace(RUTA + ".tmp", RUTA)
print(f"  {os.path.basename(RUTA)}: utxo_eod_count column of W06 fixed (backup .bak_utxo)")
con.close()
print("\nDONE")
