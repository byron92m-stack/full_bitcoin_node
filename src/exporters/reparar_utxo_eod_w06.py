#!/usr/bin/env python3
"""Fixes utxo_eod_count of the 7 days of 2022-W06 without repeating the global scan.

Why it exists: reparar_semana_2022W06.py computed n_created with the condition
`cb.txid IS NULL` (inherited from the fees calculation), which EXCLUDES coinbase outputs.
The indexer (STEP B) does insert them as live UTXOs, so the count came up short
by ~1 output per block (~140-190/day) and utxo_eod_count drifted.

n_created depends ONLY on the files of the week (outputs + blocks), not on the join
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
WEEK, YEAR = "2022-W06", "2022"
PATH = f"{C2}/daily_aggregates_{YEAR}.parquet"

con = duckdb.connect()
con.execute("SET TimeZone='UTC'")

DAYS = [r[0] for r in con.execute(
    f"SELECT DISTINCT strftime(to_timestamp(time),'%Y-%m-%d') d "
    f"FROM read_parquet('{C1}/blocks/blocks_{WEEK}.parquet') ORDER BY 1").fetchall()]
print(f"  UTC days: {DAYS[0]} .. {DAYS[-1]} ({len(DAYS)})")

# creations per day with the SAME criterion as the indexer (STEP B), coinbase included
created_df = con.execute(f"""
SELECT strftime(to_timestamp(b.time),'%Y-%m-%d') date, COUNT(*) n_created
FROM read_parquet('{C1}/outputs/outputs_{WEEK}.parquet') o
JOIN read_parquet('{C1}/blocks/blocks_{WEEK}.parquet') b ON b.height = o.height
WHERE COALESCE(o.script_type,'') <> 'nulldata'
  AND NOT COALESCE(o.script_hex,'') LIKE '6a%'
  AND length(COALESCE(o.script_hex,'')) <= 20000
GROUP BY 1 ORDER BY 1""").df()
print("  outputs created per day (coinbase included):")
print("   ", dict(zip(created_df["date"], created_df["n_created"])))

d = pd.read_parquet(PATH)
d["date"] = d["date"].astype(str)
before_df = d[d["date"] < DAYS[0]]
BASE_DAY = before_df["date"].max()
accum = int(before_df.loc[before_df["date"] == BASE_DAY, "utxo_eod_count"].iloc[0])
print(f"  base {BASE_DAY} (intact) = {accum:,}")

corrected = {}
for day in DAYS:
    created = int(created_df.loc[created_df["date"] == day, "n_created"].iloc[0])
    spent = int(d.loc[d["date"] == day, "spent_output_count"].iloc[0])
    accum += created - spent
    corrected[day] = accum
print("  utxo_eod_count corrected:", corrected)

shutil.copy2(PATH, PATH + ".bak_utxo")
d.loc[d["date"].isin(corrected), "utxo_eod_count"] = d["date"].map(corrected)
assert not d["utxo_eod_count"].isna().any()
d.to_parquet(PATH + ".tmp", index=False, compression="zstd")
os.replace(PATH + ".tmp", PATH)
print(f"  {os.path.basename(PATH)}: utxo_eod_count column of W06 fixed (backup .bak_utxo)")
con.close()
print("\nDONE")
