#!/usr/bin/env python3
"""Repara el desbordamiento de 32 bits de total_changes (2017-W13).

El contador dio la vuelta exactamente una vez al pasar 2^32 cambios, lo que
- dejo la semana 2017-W13 de weeks_done con n_inserted negativo, y
- desplazo utxo_eod_count en exactamente 2^32 desde 2017-03-29.

Ambas cosas se reparan SUMANDO 2^32. Idempotente: comprueba antes de tocar.
REQUIERE EL INDEXER PARADO.
"""
import glob, os, sqlite3, sys, shutil
import pandas as pd

WRAP = 2 ** 32
DIA = "2017-03-29"          # primer dia afectado (el wrap ocurre dentro de 2017-W13)
SEMANA = "2017-W13"
DB = "/media/SSD4T/obm/capa2/live_outputs.sqlite"

# 1) weeks_done ------------------------------------------------------------
con = sqlite3.connect(DB, timeout=60)
con.execute("PRAGMA busy_timeout=60000")
ins, sp = con.execute("SELECT n_inserted, n_spent FROM weeks_done WHERE week=?", (SEMANA,)).fetchone()
print(f"weeks_done[{SEMANA}]: n_inserted={ins:,}  n_spent={sp:,}")
if ins < 0:
    con.execute("UPDATE weeks_done SET n_inserted = n_inserted + ? WHERE week = ?", (WRAP, SEMANA))
    con.commit()
    print(f"  -> reparado a n_inserted={ins+WRAP:,}")
else:
    print("  -> ya estaba reparado (n_inserted>=0)")
n, i, s = con.execute("SELECT COUNT(*), SUM(n_inserted), SUM(n_spent) FROM weeks_done").fetchone()
print(f"weeks_done: semanas={n}  SUM(ins)={i:,}  SUM(spent)={s:,}  -> utxo_count derivado={i-s:,}")
con.close()

# 2) parquet ---------------------------------------------------------------
print(f"\nutxo_eod_count: sumando {WRAP:,} a las fechas >= {DIA}")
for f in sorted(glob.glob("/media/SSD4T/obm/capa2/daily_aggregates_*.parquet")):
    d = pd.read_parquet(f)
    d["date"] = d["date"].astype(str)
    m = d["date"] >= DIA
    if not m.any():
        continue
    neg = int((d.loc[m, "utxo_eod_count"] < 0).sum())
    if neg == 0:
        print(f"  {os.path.basename(f)}: ya reparado ({int(m.sum())} dias >= {DIA})")
        continue
    shutil.copy2(f, f + ".bak_wrap")
    d.loc[m, "utxo_eod_count"] = d.loc[m, "utxo_eod_count"].astype("int64") + WRAP
    d.to_parquet(f + ".tmp", index=False, compression="zstd")
    os.replace(f + ".tmp", f)
    print(f"  {os.path.basename(f)}: {neg} dias negativos reparados (de {int(m.sum())} afectados)")

# 3) verificacion ----------------------------------------------------------
print("\nverificacion:")
for f in sorted(glob.glob("/media/SSD4T/obm/capa2/daily_aggregates_*.parquet")):
    d = pd.read_parquet(f, columns=["date", "utxo_eod_count"])
    neg = int((d["utxo_eod_count"] < 0).sum())
    if neg:
        print(f"  {os.path.basename(f)}: AUN HAY {neg} NEGATIVOS  <== REVISAR")
        sys.exit(1)
print("  0 valores negativos en utxo_eod_count  -> OK")
