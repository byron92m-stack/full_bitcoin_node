#!/usr/bin/env python3
"""Repairs the 32-bit overflow of total_changes (2017-W13).

The counter wrapped around exactly once when passing 2^32 changes, which
- left the 2017-W13 week of weeks_done with a negative n_inserted, and
- shifted utxo_eod_count by exactly 2^32 since 2017-03-29.

Both things are repaired by ADDING 2^32. Idempotent: it checks before touching.
REQUIRES THE INDEXER STOPPED.
"""
import glob, os, sqlite3, sys, shutil
import pandas as pd

WRAP = 2 ** 32
FIRST_AFFECTED_DAY = "2017-03-29"          # first affected day (the wrap occurs inside 2017-W13)
WEEK = "2017-W13"
DB = "/media/SSD4T/obm/capa2/live_outputs.sqlite"

# 1) weeks_done ------------------------------------------------------------
con = sqlite3.connect(DB, timeout=60)
con.execute("PRAGMA busy_timeout=60000")
ins, sp = con.execute("SELECT n_inserted, n_spent FROM weeks_done WHERE week=?", (WEEK,)).fetchone()
print(f"weeks_done[{WEEK}]: n_inserted={ins:,}  n_spent={sp:,}")
if ins < 0:
    con.execute("UPDATE weeks_done SET n_inserted = n_inserted + ? WHERE week = ?", (WRAP, WEEK))
    con.commit()
    print(f"  -> repaired to n_inserted={ins+WRAP:,}")
else:
    print("  -> it was already repaired (n_inserted>=0)")
n, i, s = con.execute("SELECT COUNT(*), SUM(n_inserted), SUM(n_spent) FROM weeks_done").fetchone()
print(f"weeks_done: weeks={n}  SUM(ins)={i:,}  SUM(spent)={s:,}  -> derived utxo_count={i-s:,}")
con.close()

# 2) parquet ---------------------------------------------------------------
print(f"\nutxo_eod_count: adding {WRAP:,} to the dates >= {FIRST_AFFECTED_DAY}")
for f in sorted(glob.glob("/media/SSD4T/obm/capa2/daily_aggregates_*.parquet")):
    d = pd.read_parquet(f)
    d["date"] = d["date"].astype(str)
    m = d["date"] >= FIRST_AFFECTED_DAY
    if not m.any():
        continue
    neg = int((d.loc[m, "utxo_eod_count"] < 0).sum())
    if neg == 0:
        print(f"  {os.path.basename(f)}: already repaired ({int(m.sum())} days >= {FIRST_AFFECTED_DAY})")
        continue
    shutil.copy2(f, f + ".bak_wrap")
    d.loc[m, "utxo_eod_count"] = d.loc[m, "utxo_eod_count"].astype("int64") + WRAP
    d.to_parquet(f + ".tmp", index=False, compression="zstd")
    os.replace(f + ".tmp", f)
    print(f"  {os.path.basename(f)}: {neg} negative days repaired (of {int(m.sum())} affected)")

# 3) verification ----------------------------------------------------------
print("\nverification:")
for f in sorted(glob.glob("/media/SSD4T/obm/capa2/daily_aggregates_*.parquet")):
    d = pd.read_parquet(f, columns=["date", "utxo_eod_count"])
    neg = int((d["utxo_eod_count"] < 0).sum())
    if neg:
        print(f"  {os.path.basename(f)}: THERE ARE STILL {neg} NEGATIVES  <== CHECK")
        sys.exit(1)
print("  0 negative values in utxo_eod_count  -> OK")
