#!/usr/bin/env python3
"""capa1/difficulty_epochs.parquet — EXACT node difficulty per 2016-block epoch.

Why: OBM reads the 'difficulty' field from the Bitcoin Core RPC (Appendix A.6), it does not
recompute it from 'bits'. Our reconstruction from bits differs by 1 ULP of float64 in ~40% of
the days (15 equivalent variants were tested). Difficulty is CONSTANT within each 2016-block
epoch, so ~481 calls (getblockhash + getblockheader) give us Core's bit-exact value for the
whole chain.

Usage: python3 fix_difficulty_rpc.py [--datadir DIR]
"""
import json
import subprocess
import sys

import pyarrow as pa
import pyarrow.parquet as pq

DATADIR = "/media/SSD4T/bitcoin/.bitcoin"
OUTPUT = "/media/SSD4T/obm/capa1/difficulty_epochs.parquet"
EPOCH = 2016


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
    n_ep = tip // EPOCH + 1
    print(f"tip={tip:,}  epochs={n_ep}")
    rows = []
    for k in range(n_ep):
        h = k * EPOCH
        j = json.loads(cli("getblockheader", cli("getblockhash", str(h))))
        rows.append({"epoch": k, "h_start": h, "h_end": min(h + EPOCH - 1, tip),
                     "difficulty": float(j["difficulty"]), "bits": j["bits"]})
        if k % 60 == 0:
            print(f"  epoch {k:>4}/{n_ep}  h={h:>7,}  difficulty={j['difficulty']}", flush=True)
    t = pa.Table.from_pylist(rows, schema=pa.schema([
        ("epoch", pa.int32()), ("h_start", pa.int32()), ("h_end", pa.int32()),
        ("difficulty", pa.float64()), ("bits", pa.string())]))
    pq.write_table(t, OUTPUT, compression="zstd")
    print(f"written: {OUTPUT}  ({len(rows)} epochs)")
    return rows


if __name__ == "__main__":
    main()
