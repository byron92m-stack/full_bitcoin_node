#!/usr/bin/env python3
"""
Mueve a su semana correcta los 2 bloques mal particionados en capa1
(timestamps de bloque no monotonos + particionado por semana ISO del timestamp):
    bloque   60788 : 2010-W23 -> 2010-W24
    bloque  293303 : 2014-W13 -> 2014-W14
Idempotente. Hace copia .bak_rep antes de reescribir. Indexer PARADO.
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
    print(f"\n=== bloque {height:,}: {wk_from} -> {wk_to} ===")
    for tabla in TABLAS:
        p_from, p_to = ruta(tabla, wk_from), ruta(tabla, wk_to)
        t_from, t_to = pq.read_table(p_from), pq.read_table(p_to)
        mask = pc.equal(t_from["height"], height)
        mover = t_from.filter(mask)
        if mover.num_rows == 0:
            print(f"  {tabla:8s}: ya re-particionado, nada que mover")
            continue
        if pc.any(pc.equal(t_to["height"], height)).as_py():
            print(f"  {tabla:8s}: ERROR: {height} ya existe en {wk_to}")
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
              f"{wk_to} {t_to.num_rows:,} -> {nuevo.num_rows:,}  (movidas {mover.num_rows:,})")

print("\n=== verificacion: monotonia por altura entre las 2 semanas ===")
for height, wk_from, wk_to in CASOS:
    for tabla in TABLAS:
        a = pq.read_table(ruta(tabla, wk_from), columns=["height"])["height"]
        b = pq.read_table(ruta(tabla, wk_to), columns=["height"])["height"]
        ma, mb = pc.max(a).as_py(), pc.min(b).as_py()
        ok = ma < mb
        print(f"  {tabla:8s} {wk_from} max={ma:,} < {wk_to} min={mb:,}: {'OK' if ok else 'FALLO'}")
        if not ok:
            fallos += 1
sys.exit(1 if fallos else 0)
