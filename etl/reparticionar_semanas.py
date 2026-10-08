#!/usr/bin/env python3
"""
Moves the 2 mis-partitioned blocks in capa1 to their correct week
(non-monotonic block timestamps + partitioning by ISO week of the timestamp):
    block    60788 : 2010-W23 -> 2010-W24
    block   293303 : 2014-W13 -> 2014-W14
Idempotent. It makes a .bak_rep copy before rewriting. Indexer STOPPED.
"""
import os, shutil, sys
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

CAPA1 = "/media/SSD4T/obm/capa1"
CASES = [(60788, "2010-W23", "2010-W24"),
         (293303, "2014-W13", "2014-W14")]
TABLES = ["blocks", "txs", "inputs", "outputs"]

def path(table, week):
    return os.path.join(CAPA1, table, f"{table}_{week}.parquet")

failures = 0
for height, wk_from, wk_to in CASES:
    print(f"\n=== block {height:,}: {wk_from} -> {wk_to} ===")
    for table in TABLES:
        p_from, p_to = path(table, wk_from), path(table, wk_to)
        t_from, t_to = pq.read_table(p_from), pq.read_table(p_to)
        mask = pc.equal(t_from["height"], height)
        to_move = t_from.filter(mask)
        if to_move.num_rows == 0:
            print(f"  {table:8s}: already re-partitioned, nothing to move")
            continue
        if pc.any(pc.equal(t_to["height"], height)).as_py():
            print(f"  {table:8s}: ERROR: {height} already exists in {wk_to}")
            failures += 1
            continue
        remaining = t_from.filter(pc.invert(mask))
        new_table = pa.concat_tables([t_to, to_move])
        new_table = new_table.take(pc.sort_indices(new_table, sort_keys=[("height", "ascending")]))
        for p, t in ((p_from, remaining), (p_to, new_table)):
            shutil.copy2(p, p + ".bak_rep")
            tmp = p + ".tmp"
            pq.write_table(t, tmp, compression="zstd")
            os.replace(tmp, p)
        print(f"  {table:8s}: {wk_from} {t_from.num_rows:,} -> {remaining.num_rows:,} | "
              f"{wk_to} {t_to.num_rows:,} -> {new_table.num_rows:,}  (moved {to_move.num_rows:,})")

print("\n=== verification: monotonicity by height between the 2 weeks ===")
for height, wk_from, wk_to in CASES:
    for table in TABLES:
        a = pq.read_table(path(table, wk_from), columns=["height"])["height"]
        b = pq.read_table(path(table, wk_to), columns=["height"])["height"]
        ma, mb = pc.max(a).as_py(), pc.min(b).as_py()
        ok = ma < mb
        print(f"  {table:8s} {wk_from} max={ma:,} < {wk_to} min={mb:,}: {'OK' if ok else 'FAIL'}")
        if not ok:
            failures += 1
sys.exit(1 if failures else 0)
