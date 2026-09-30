#!/usr/bin/env python3
"""capa1/difficulty_epochs.parquet — dificultad EXACTA del nodo por epoca de 2016 bloques.

Por que: OBM lee el campo 'difficulty' del RPC de Bitcoin Core (Apéndice A.6), no lo
recalcula desde 'bits'. Nuestra reconstruccion desde bits difiere en 1 ULP de float64 en
~40% de los dias (probadas 15 variantes equivalentes). La dificultad es CONSTANTE dentro
de cada epoca de 2016 bloques, asi que con ~481 llamadas (getblockhash + getblockheader)
obtenemos el valor bit-exacto de Core para las 968.458 alturas.

Uso: python3 fix_difficulty_rpc.py [--datadir DIR]
"""
import json
import subprocess
import sys

import pyarrow as pa
import pyarrow.parquet as pq

DATADIR = "/media/SSD4T/bitcoin/.bitcoin"
SALIDA = "/media/SSD4T/obm/capa1/difficulty_epochs.parquet"
EPOCA = 2016


def cli(*args):
    r = subprocess.run(["bitcoin-cli", f"-datadir={DATADIR}", *args],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"bitcoin-cli {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout.strip()


def main():
    if "--datadir" in sys.argv:
        globals()["DATADIR"] = sys.argv[sys.argv.index("--datadir") + 1]
    tip = int(cli("getblockcount"))
    n_ep = tip // EPOCA + 1
    print(f"tip={tip:,}  epocas={n_ep}")
    filas = []
    for k in range(n_ep):
        h = k * EPOCA
        j = json.loads(cli("getblockheader", cli("getblockhash", str(h))))
        filas.append({"epoch": k, "h_start": h, "h_end": min(h + EPOCA - 1, tip),
                      "difficulty": float(j["difficulty"]), "bits": j["bits"]})
        if k % 60 == 0:
            print(f"  epoca {k:>4}/{n_ep}  h={h:>7,}  difficulty={j['difficulty']}", flush=True)
    t = pa.Table.from_pylist(filas, schema=pa.schema([
        ("epoch", pa.int32()), ("h_start", pa.int32()), ("h_end", pa.int32()),
        ("difficulty", pa.float64()), ("bits", pa.string())]))
    pq.write_table(t, SALIDA, compression="zstd")
    print(f"escrito: {SALIDA}  ({len(filas)} epocas)")
    return filas


if __name__ == "__main__":
    main()
