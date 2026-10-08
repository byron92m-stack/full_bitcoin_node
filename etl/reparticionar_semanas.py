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
CASOS = [(60788, "2010-W23", "2010-W24"),
         (293303, "2014-W13", "2014-W14")]
TABLAS = ["blocks", "txs", "inputs", "outputs"]

def ruta(tabla, week):
    return os.path.join(CAPA1, tabla, f"{tabla}_{week}.parquet")

fallos = 0
for height, wk_from, wk_to in CASOS:
    print(f"\n=== block {height:,}: {wk_from} -> {wk_to} ===")
    for tabla in TABLAS:
        p_from, p_to = ruta(tabla, wk_from), ruta(tabla, wk_to)
        t_from, t_to = pq.read_table(p_from), pq.read_table(p_to)
        mask = pc.equal(t_from["height"], height)
        mover = t_from.filter(mask)
        if mover.num_rows == 0:
            print(f"  {tabla:8s}: already re-partitioned, nothing to move")
            continue
        if pc.any(pc.equal(t_to["height"], height)).as_py():
            print(f"  {tabla:8s}: ERROR: {height} already exists in {wk_to}")
            fallos += 1
            continue
        queda = t_from.filter(pc.invert(mask))
        nuevo = pa.concat_tables([t_to, mover])
        nuevo = nuevo.take(pc.sort_indices(nuevo, sort_keys=[("height", "ascending")]))
        for p, t in ((p_from, queda), (p_to, nuevo)):
            shutil.copy2(p, p + ".bak_rep")
            tmp = p + ".tmp"
            pq.write_table(t, tmp, compression="zstd")
            os.replace(tmp, p)
        print(f"  {tabla:8s}: {wk_from} {t_from.num_rows:,} -> {queda.num_rows:,} | "
              f"{wk_to} {t_to.num_rows:,} -> {nuevo.num_rows:,}  (moved {mover.num_rows:,})")

print("\n=== verification: monotonicity by height between the 2 weeks ===")
for height, wk_from, wk_to in CASOS:
    for tabla in TABLAS:
        a = pq.read_table(ruta(tabla, wk_from), columns=["height"])["height"]
        b = pq.read_table(ruta(tabla, wk_to), columns=["height"])["height"]
        ma, mb = pc.max(a).as_py(), pc.min(b).as_py()
        ok = ma < mb
        print(f"  {tabla:8s} {wk_from} max={ma:,} < {wk_to} min={mb:,}: {'OK' if ok else 'FAIL'}")
        if not ok:
            fallos += 1
sys.exit(1 if fallos else 0)
