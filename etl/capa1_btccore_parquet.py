#!/usr/bin/env python3
# ============================================================
# BTC ETL — LAYER 1 (Bitcoin Core → weekly Parquet)
# UTXO-safe, compact, reproducible
# One file per ISO week: blocks_YYYY-Www.parquet, ...
# Writes to /media/SSD4T/obm/capa1/
#
# Usage:
#   python3 capa1_btccore_parquet.py                  # menu (1 = reset, 2 = continue)
#   python3 capa1_btccore_parquet.py --repair H1 H2   # repair range (CLI)
#   python3 capa1_btccore_parquet.py --validate       # validate layer 1 (CLI)
#
# v3.3 — patches applied:
#   F1-F7 (v3.2).
#   M1. Accumulator with pa.Table instead of lists of dicts (~10x less RAM).
#   M2. write_week uses pa.concat_tables (no pandas).
#   M3. process_block returns pa.Table directly.
# ============================================================

import os
import sys
import json
import math
import time
import shutil
import logging
import argparse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from decimal import Decimal, InvalidOperation, ROUND_DOWN

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import duckdb
import requests
from tqdm import tqdm
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from requests.exceptions import ConnectionError as ReqConnectionError, ReadTimeout
from urllib3.exceptions import ProtocolError
from http.client import RemoteDisconnected

# Shared canonical module: src/bitcoin_math.py (single source of truth).
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
from bitcoin_math import bits_to_difficulty

# ============================================================
# CONFIG
# ============================================================

RPC_USER = "bitcoinrpc"
RPC_PASSWORD = "superseguro123"
RPC_URL = "http://127.0.0.1:8332"

OBM_ROOT = "/media/SSD4T/obm"
FAST_BASE = os.path.join(OBM_ROOT, "capa1")
STATE_FILE = os.path.join(OBM_ROOT, "state_capa1.json")
LOG_DIR = os.path.join(OBM_ROOT, "logs")
LOG_FILE = os.path.join(LOG_DIR, "etl_capa1.log")
TMP_DIR = os.path.join(OBM_ROOT, "tmp", "capa1_etl")

DIRS = {
    "blocks": os.path.join(FAST_BASE, "blocks"),
    "txs": os.path.join(FAST_BASE, "txs"),
    "inputs": os.path.join(FAST_BASE, "inputs"),
    "outputs": os.path.join(FAST_BASE, "outputs"),
}

SAVE_EVERY = 1000
WEEK_FLUSH_MARGIN = 1

RPC_TIMEOUT = 120
RPC_RETRIES_TOTAL = 8
RPC_RETRY_BACKOFF = 0.6

SATOSHI = 100_000_000

# BIP30: 2 historical duplicate txids (blocks 91,812/91,842 and 91,722/91,880)
BIP30_TXIDS = {
    "d5d27987d2a3dfc724e359870c6644b40e497bdc0589a033220fe15429d88599",
    "e3bf3d07d4b0375638d5f1db5255fe07ba2c4cb067cd81b84ee974b6585fb468",
}

# ============================================================
# EXPLICIT SCHEMAS
# ============================================================

BLOCKS_SCHEMA = pa.schema([
    ("height", pa.int32()),
    ("hash", pa.string()),
    ("time", pa.int64()),
    ("mediantime", pa.int64()),
    ("version", pa.int64()),
    ("bits", pa.string()),
    # WARNING: this is NOT the node's 'difficulty' field, it is bits_to_difficulty(bits). The
    # exact Core value (the one OBM uses, Appendix A.6) is in difficulty_epochs.parquet. See F3.
    ("difficulty_from_bits", pa.float64()),
    ("chainwork", pa.string()),
    ("size", pa.int32()),
    ("weight", pa.int32()),
    ("strippedsize", pa.int32()),
    ("nTx", pa.int32()),
    ("previousblockhash", pa.string()),
    ("nextblockhash", pa.string()),
])

TXS_SCHEMA = pa.schema([
    ("height", pa.int32()),
    ("block_hash", pa.string()),
    ("txid", pa.string()),
    ("wtxid", pa.string()),
    ("version", pa.int64()),
    ("size", pa.int32()),
    ("vsize", pa.int32()),
    ("weight", pa.int32()),
    ("locktime", pa.int64()),
    ("vin_count", pa.int32()),
    ("vout_count", pa.int32()),
])

INPUTS_SCHEMA = pa.schema([
    ("height", pa.int32()),
    ("block_hash", pa.string()),
    ("txid", pa.string()),
    ("vin_index", pa.int32()),
    ("is_coinbase", pa.bool_()),
    ("sequence", pa.int64()),
    ("prev_txid", pa.string()),
    ("prev_vout", pa.int64()),
])

OUTPUTS_SCHEMA = pa.schema([
    ("height", pa.int32()),
    ("block_hash", pa.string()),
    ("txid", pa.string()),
    ("vout", pa.int32()),
    ("value_sats", pa.int64()),
    ("script_type", pa.string()),
    ("script_hex", pa.string()),
])

SCHEMAS = {
    "blocks": BLOCKS_SCHEMA,
    "txs": TXS_SCHEMA,
    "inputs": INPUTS_SCHEMA,
    "outputs": OUTPUTS_SCHEMA,
}

PRIMARY_KEY = {
    "blocks": ["height"],
    "txs": ["height", "txid"],
    "inputs": ["height", "txid", "vin_index"],
    "outputs": ["height", "txid", "vout"],
}

# ============================================================
# LOGGING
# ============================================================

def setup_logger() -> logging.Logger:
    os.makedirs(LOG_DIR, exist_ok=True)
    logger = logging.getLogger("capa1_btccore_parquet")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    if not logger.handlers:
        logger.addHandler(fh)
        logger.addHandler(sh)
    return logger

logger = setup_logger()

# ============================================================
# HTTP SESSION
# ============================================================

def build_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=RPC_RETRIES_TOTAL, connect=RPC_RETRIES_TOTAL,
        read=RPC_RETRIES_TOTAL, status=RPC_RETRIES_TOTAL,
        backoff_factor=RPC_RETRY_BACKOFF,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST"], raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
    s.mount("http://", adapter)
    return s

SESSION = build_session()

# ============================================================
# STATE
# ============================================================

def load_state() -> Dict[str, Any]:
    if not os.path.exists(STATE_FILE):
        return {
            "last_processed_height": -1,
            "last_processed_hash": None,
            "last_processed_week": None,
            "written_through_height": -1,
            "last_written_week": None,
        }
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        state = json.load(f)
    state.setdefault("last_processed_week", None)
    state.setdefault("written_through_height", -1)
    state.setdefault("last_written_week", None)
    return state

def save_state(state: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_FILE)

# ============================================================
# RPC
# ============================================================

_rpc_id = 0

def rpc_call(method: str, params: Optional[List[Any]] = None) -> Any:
    global _rpc_id
    _rpc_id += 1
    payload = {"jsonrpc": "1.0", "id": _rpc_id, "method": method, "params": params or []}
    auth = (RPC_USER, RPC_PASSWORD)
    for attempt in range(1, RPC_RETRIES_TOTAL + 1):
        try:
            r = SESSION.post(RPC_URL, json=payload, auth=auth, timeout=RPC_TIMEOUT)
            data = r.json()
            if data.get("error"):
                raise RuntimeError(data["error"])
            return data["result"]
        except (ReqConnectionError, ReadTimeout, RemoteDisconnected, ProtocolError):
            time.sleep(min(10.0, RPC_RETRY_BACKOFF * (2 ** (attempt - 1))))
    raise RuntimeError(f"RPC failed: {method}")

def get_block_count() -> int:
    return int(rpc_call("getblockcount"))

def get_block_hash(height: int) -> str:
    return rpc_call("getblockhash", [height])

def get_block(block_hash: str) -> Dict[str, Any]:
    return rpc_call("getblock", [block_hash, 2])

# ============================================================
# HELPERS
# ============================================================

def safe_int(x: Any) -> Optional[int]:
    try:
        return int(x) if x is not None else None
    except Exception:
        return None

def btc_to_sats(x: Any) -> Optional[int]:
    if x is None:
        return None
    try:
        d = Decimal(str(x)).quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)
        return int(d * SATOSHI)
    except (InvalidOperation, ValueError, TypeError):
        return None

def vin_is_coinbase(vin: Dict[str, Any]) -> bool:
    return "coinbase" in vin

def _normalize_none(col_list, arrow_type):
    if (pa.types.is_string(arrow_type)
            or pa.types.is_boolean(arrow_type)
            or pa.types.is_integer(arrow_type)):
        return [
            None if (isinstance(v, float) and math.isnan(v)) else v
            for v in col_list
        ]
    return col_list

def _dicts_to_arrow(filas: List[Dict], table: str) -> pa.Table:
    """Converts a list of dicts into a pa.Table with an explicit schema.
    Much more compact in memory than a pandas DataFrame."""
    schema = SCHEMAS[table]
    arrays = {}
    for field in schema:
        col = _normalize_none([r.get(field.name) for r in filas], field.type)
        arrays[field.name] = pa.array(col, type=field.type)
    return pa.table(arrays, schema=schema)

def timestamp_to_week(ts: int) -> str:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    iso_year, iso_week, _ = dt.isocalendar()
    return f"{iso_year:04d}-W{iso_week:02d}"

def week_to_int(week: str) -> int:
    y, w = week.split("-W")
    return int(y) * 100 + int(w)

# ============================================================
# PROCESS BLOCK (M3: returns pa.Table)
# ============================================================

def process_block(blk: Dict[str, Any]):
    height = safe_int(blk.get("height"))
    bh = blk.get("hash")
    blocks, txs, inputs, outputs = [], [], [], []

    bits = blk.get("bits")
    if bits is None:
        raise ValueError(f"block {height} without 'bits' field")
    # F3: the node's 'difficulty' field differs from this in ~47% of the blocks (1 ULP). It is
    # stored under a name that states its origin so nobody confuses it with Core's.
    difficulty_from_bits = bits_to_difficulty(bits)

    blocks.append({
        "height": height, "hash": bh,
        "time": safe_int(blk.get("time")),
        "mediantime": safe_int(blk.get("mediantime")),
        "version": safe_int(blk.get("version")),
        "bits": bits, "difficulty_from_bits": difficulty_from_bits,
        "chainwork": blk.get("chainwork"),
        "size": safe_int(blk.get("size")),
        "weight": safe_int(blk.get("weight")),
        "strippedsize": safe_int(blk.get("strippedsize")),
        "nTx": safe_int(blk.get("nTx")),
        "previousblockhash": blk.get("previousblockhash"),
        "nextblockhash": blk.get("nextblockhash"),
    })

    n_tx_field = blk.get("nTx")
    n_tx_real = len(blk.get("tx", []))
    if n_tx_field is not None and n_tx_field != n_tx_real:
        raise ValueError(f"nTx mismatch at height {height}: {n_tx_field} != {n_tx_real}")

    w = blk.get("weight"); ss = blk.get("strippedsize"); s = blk.get("size")
    if w is not None and ss is not None and s is not None:
        if w != 3 * ss + s:
            raise ValueError(f"weight mismatch at height {height}: {w} != 3*{ss}+{s}")

    for tx in blk.get("tx", []):
        txid = tx.get("txid")
        txs.append({
            "height": height, "block_hash": bh,
            "txid": txid, "wtxid": tx.get("hash"),
            "version": safe_int(tx.get("version")),
            "size": safe_int(tx.get("size")),
            "vsize": safe_int(tx.get("vsize")),
            "weight": safe_int(tx.get("weight")),
            "locktime": safe_int(tx.get("locktime")),
            "vin_count": len(tx.get("vin", [])),
            "vout_count": len(tx.get("vout", [])),
        })

        for idx, vin in enumerate(tx.get("vin", [])):
            if vin_is_coinbase(vin):
                inputs.append({
                    "height": height, "block_hash": bh,
                    "txid": txid, "vin_index": idx,
                    "is_coinbase": True,
                    "sequence": safe_int(vin.get("sequence")),
                    "prev_txid": None, "prev_vout": None,
                })
            else:
                inputs.append({
                    "height": height, "block_hash": bh,
                    "txid": txid, "vin_index": idx,
                    "is_coinbase": False,
                    "sequence": safe_int(vin.get("sequence")),
                    "prev_txid": vin.get("txid"),
                    "prev_vout": safe_int(vin.get("vout")),
                })

        for vout in tx.get("vout", []):
            spk = vout.get("scriptPubKey", {}) or {}
            outputs.append({
                "height": height, "block_hash": bh,
                "txid": txid, "vout": safe_int(vout.get("n")),
                "value_sats": btc_to_sats(vout.get("value")),
                "script_type": spk.get("type"),
                "script_hex": spk.get("hex"),
            })

    return (
        _dicts_to_arrow(blocks, "blocks"),
        _dicts_to_arrow(txs, "txs"),
        _dicts_to_arrow(inputs, "inputs"),
        _dicts_to_arrow(outputs, "outputs"),
    )

# ============================================================
# POST-WRITE VALIDATION
# ============================================================

def _validate_written_file(path: str, table: str):
    t = pq.read_table(path)
    if table == "blocks":
        bits_col = t["bits"].to_pylist()
        diff_col = t["difficulty_from_bits"].to_pylist()
        height_col = t["height"].to_pylist()
        for h, b, d in zip(height_col, bits_col, diff_col):
            if b is None:
                continue
            expected = bits_to_difficulty(b)
            if expected > 0 and abs(d - expected) / expected > 1e-12:
                raise ValueError(
                    f"difficulty_from_bits mismatch at height {h}: {d} vs {expected}")
    elif table == "inputs":
        for v in t["prev_vout"].to_pylist():
            if v is not None and not isinstance(v, int):
                raise ValueError(f"prev_vout not an integer: {v!r}")

# ============================================================
# WEEKLY WRITE WITH FUSION (DuckDB)
# ============================================================

def _fuse_with_duckdb(existing_path: str, new_path: str, table: str) -> Tuple[str, int]:
    """F1: does NOT replace. Returns (tmp_out_path, n_combined)."""
    pk = PRIMARY_KEY[table]
    pk_join = " AND ".join([f"e.{k} = n.{k}" for k in pk])

    con = duckdb.connect()
    con.execute("SET threads=4")
    con.execute("SET memory_limit='8GB'")
    con.execute(f"SET temp_directory='{TMP_DIR}'")
    con.execute("SET preserve_insertion_order=false")

    tmp_out = existing_path + ".fused"

    try:
        con.execute(f"""
            COPY (
                SELECT e.* FROM read_parquet('{existing_path}') e
                WHERE NOT EXISTS (
                    SELECT 1 FROM read_parquet('{new_path}') n
                    WHERE {pk_join}
                )
                UNION ALL BY NAME
                SELECT * FROM read_parquet('{new_path}')
            ) TO '{tmp_out}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """)
        n_combined = con.execute(f"SELECT COUNT(*) FROM read_parquet('{tmp_out}')").fetchone()[0]
    except Exception:
        if os.path.exists(tmp_out):
            os.remove(tmp_out)
        raise
    finally:
        con.close()

    return (tmp_out, n_combined)


def write_week(week: str, accum: Dict[str, List[pa.Table]]) -> Tuple[int, str]:
    """M2: uses pa.concat_tables (no pandas)."""
    if not accum["blocks"]:
        logger.info(f"Week {week} empty, nothing to write")
        return (-1, None)

    logger.info(f"Writing week {week}: "
                f"blocks={len(accum['blocks'])}, "
                f"txs={len(accum['txs'])}, "
                f"inputs={len(accum['inputs'])}, "
                f"outputs={len(accum['outputs'])}")

    os.makedirs(TMP_DIR, exist_ok=True)

    for table in ["blocks", "txs", "inputs", "outputs"]:
        tablas = accum[table]
        if not tablas:
            continue

        # Concatenate Arrow tables (no pandas, no intra-week duplicates)
        nueva = tablas[0] if len(tablas) == 1 else pa.concat_tables(tablas)

        path = DIRS[table]
        os.makedirs(path, exist_ok=True)
        final = os.path.join(path, f"{table}_{week}.parquet")

        tmp_new = os.path.join(TMP_DIR, f"{table}_{week}_new.parquet")
        tmp_tmp = tmp_new + ".tmp"
        pq.write_table(nueva, tmp_tmp, compression="zstd", compression_level=6)
        os.replace(tmp_tmp, tmp_new)

        n_new = nueva.num_rows

        if os.path.exists(final):
            con = duckdb.connect()
            n_existing_distinct = con.execute(
                f"SELECT COUNT(*) FROM (SELECT DISTINCT {', '.join(PRIMARY_KEY[table])} FROM read_parquet('{final}'))"
            ).fetchone()[0]
            con.close()

            tmp_out, n_combined = _fuse_with_duckdb(final, tmp_new, table)

            if n_combined < n_existing_distinct:
                if os.path.exists(tmp_out):
                    os.remove(tmp_out)
                raise RuntimeError(
                    f"FUSION ABORTED for {table}_{week}: "
                    f"n_combined={n_combined} < n_existing_distinct={n_existing_distinct}."
                )

            os.replace(tmp_out, final)
            logger.info(f"  {table}_{week}: fusion {n_existing_distinct:,} + {n_new:,} "
                        f"→ {n_combined:,} rows (+{n_combined - n_existing_distinct:,})")
        else:
            os.replace(tmp_new, final)
            logger.info(f"  {table}_{week}: new ({n_new:,} rows)")

        if os.path.exists(tmp_new):
            os.remove(tmp_new)

        _validate_written_file(final, table)

        size_mb = os.path.getsize(final) / 1024 / 1024
        logger.info(f"  {table}_{week}.parquet: {size_mb:.1f} MB")

    # M2: last_h from the Arrow tables
    tbl_blocks = accum["blocks"][0] if len(accum["blocks"]) == 1 else pa.concat_tables(accum["blocks"])
    heights = tbl_blocks.column("height").to_pylist()
    hashes = tbl_blocks.column("hash").to_pylist()
    last_h = max(heights)
    last_hash = hashes[heights.index(last_h)]
    return (last_h, last_hash)


def new_accumulator() -> Dict[str, List[pa.Table]]:
    """M1: accumulator of Arrow tables (not lists of dicts)."""
    return {"blocks": [], "txs": [], "inputs": [], "outputs": []}

# ============================================================
# INCREMENTAL FLUSH OF WEEKS
# ============================================================

def flush_ready_weeks(accums: Dict[str, Dict[str, List[pa.Table]]],
                      current_week: str,
                      state: Dict[str, Any]) -> int:
    current_int = week_to_int(current_week)
    ready = []

    for w in sorted(accums.keys()):
        if week_to_int(w) + WEEK_FLUSH_MARGIN < current_int:
            ready.append(w)

    for w in ready:
        last_h, _ = write_week(w, accums[w])
        if last_h >= 0:
            state["written_through_height"] = max(
                state.get("written_through_height", -1),
                last_h
            )
            state["last_written_week"] = w
            save_state(state)
        del accums[w]

    return len(ready)

# ============================================================
# VALIDATION (F3 + F4 + F7)
# ============================================================

def _validate_one_year(year: str) -> Dict[str, Any]:
    import glob
    results = {"year": year, "heights_ok": None, "cross": {}, "unique_ok": None}

    files = sorted(glob.glob(os.path.join(DIRS["blocks"], f"blocks_{year}-*.parquet")))
    if not files:
        return results

    heights = set()
    for f in files:
        t = pq.read_table(f, columns=["height"])
        for h in t["height"].to_pylist():
            heights.add(h)
    if heights:
        expected = max(heights) - min(heights) + 1
        results["heights_ok"] = (len(heights) == expected)

    con = duckdb.connect()
    con.execute("SET threads=4")
    con.execute("SET memory_limit='6GB'")
    con.execute(f"SET temp_directory='{TMP_DIR}'")

    pat_b = f"{DIRS['blocks']}/blocks_{year}-*.parquet"
    pat_t = f"{DIRS['txs']}/txs_{year}-*.parquet"
    pat_i = f"{DIRS['inputs']}/inputs_{year}-*.parquet"
    pat_o = f"{DIRS['outputs']}/outputs_{year}-*.parquet"

    n_txs = con.execute(f"SELECT COUNT(*) FROM read_parquet('{pat_t}')").fetchone()[0]
    n_inputs = con.execute(f"SELECT COUNT(*) FROM read_parquet('{pat_i}')").fetchone()[0]
    n_outputs = con.execute(f"SELECT COUNT(*) FROM read_parquet('{pat_o}')").fetchone()[0]
    sum_nTx = con.execute(f"SELECT SUM(nTx) FROM read_parquet('{pat_b}')").fetchone()[0]
    sum_vin = con.execute(f"SELECT SUM(vin_count) FROM read_parquet('{pat_t}')").fetchone()[0]
    sum_vout = con.execute(f"SELECT SUM(vout_count) FROM read_parquet('{pat_t}')").fetchone()[0]

    results["cross"] = {
        "txs": (n_txs, sum_nTx, n_txs == sum_nTx),
        "inputs": (n_inputs, sum_vin, n_inputs == sum_vin),
        "outputs": (n_outputs, sum_vout, n_outputs == sum_vout),
    }

    bip30_list = ",".join([repr(t) for t in BIP30_TXIDS])
    n_outputs_distinct = con.execute(f"""
        SELECT COUNT(*) FROM (
            SELECT DISTINCT txid, vout FROM read_parquet('{pat_o}')
            WHERE txid NOT IN ({bip30_list})
        )
    """).fetchone()[0]
    n_outputs_non_bip30 = con.execute(f"""
        SELECT COUNT(*) FROM read_parquet('{pat_o}')
        WHERE txid NOT IN ({bip30_list})
    """).fetchone()[0]
    results["unique_ok"] = (n_outputs_non_bip30 == n_outputs_distinct)
    con.close()

    return results


def validate_capa1_continuity() -> bool:
    import glob
    os.makedirs(TMP_DIR, exist_ok=True)

    print("\n=== Validating layer 1 continuity (by year) ===")
    logger.info("Validating layer 1 continuity...")

    years = sorted(set(
        f.split("_")[-1].split("-")[0]
        for f in glob.glob(os.path.join(DIRS["blocks"], "blocks_*.parquet"))
    ))

    all_ok = True
    for year in years:
        r = _validate_one_year(year)
        status_h = "✓" if r.get("heights_ok") else "✗"
        cross = r.get("cross", {})
        cross_ok = all(v[2] for v in cross.values())
        status_c = "✓" if cross_ok else "✗"
        status_u = "✓" if r.get("unique_ok") else "✗"
        print(f"  {year}: heights {status_h}  cross {status_c}  unique {status_u}")
        if not (r.get("heights_ok") and cross_ok and r.get("unique_ok")):
            all_ok = False

    if all_ok:
        print("\n  ✓ layer 1 complete and consistent.")
        logger.info("✓ layer 1 complete and consistent.")
        return True
    else:
        print("\n  ⚠  layer 1 has problems.")
        logger.warning("layer 1 has validation problems.")
        return False

# ============================================================
# REPAIR RANGE (F2: does not touch the checkpoint)
# ============================================================

def repair_range(start_h: int, end_h: int):
    print(f"\n=== Repairing range {start_h:,} – {end_h:,} ===")
    logger.info(f"Repairing range {start_h}-{end_h}")

    ensure_dirs()
    accums: Dict[str, Dict[str, List[pa.Table]]] = {}
    week_actual = None
    if start_h > 0:                      # week of the block before the range
        try:
            _prev = get_block(get_block_hash(start_h - 1))
            week_actual = timestamp_to_week(int(_prev["time"]))
        except Exception:
            week_actual = None

    for h in tqdm(range(start_h, end_h + 1), desc=f"Repairing {start_h}-{end_h}"):
        try:
            bh = get_block_hash(h)
            blk = get_block(bh)
            ts = blk.get("time")
            if ts is None:
                raise ValueError(f"block {h} without timestamp")
            own_week = timestamp_to_week(int(ts))
            if week_actual is None or week_to_int(own_week) > week_to_int(week_actual):
                week_actual = own_week
            week = week_actual

            if week not in accums:
                accums[week] = new_accumulator()

            b, t, i, o = process_block(blk)
            accums[week]["blocks"].append(b)
            accums[week]["txs"].append(t)
            accums[week]["inputs"].append(i)
            accums[week]["outputs"].append(o)
        except Exception as e:
            logger.error(f"Error processing block {h}: {e}")
            print(f"Error processing block {h}: {e}")
            raise

    for week in sorted(accums.keys()):
        print(f"\n  Week {week}: {len(accums[week]['blocks'])} blocks")
        write_week(week, accums[week])

    print(f"\n✓ Repair completed. {len(accums)} weeks affected.")
    logger.info(f"Repair completed: {len(accums)} weeks")
    print("NOTE: the ingestion checkpoint has NOT been modified (F2).")

# ============================================================
# NORMAL INGESTION (F7: no automatic validation)
# ============================================================

def ingest_normal():
    ensure_dirs()
    state = load_state()
    tip = get_block_count()

    written_through = state.get("written_through_height", -1)

    if written_through >= 0:
        start_height = written_through + 1
        print(f"Resuming from block {start_height} (written through {written_through})")
        logger.info(f"Resuming from {start_height} (written_through={written_through})")
    else:
        start_height = 0
        print("Starting from the beginning.")
        logger.info("Starting from block 0")

    if start_height > tip:
        print("There are no new blocks to process.")
        logger.info("There are no new blocks to process.")
        return

    print(f"\nProcessing blocks {start_height} → {tip}")
    logger.info(f"Processing blocks {start_height} → {tip}")

    accums: Dict[str, Dict[str, List[pa.Table]]] = {}

    # FIX week monotonicity: the week assigned to a block can NEVER go
    # backwards with respect to the previous block's. Block timestamps are not
    # increasing (allowed by consensus) and partitioning by the ISO week of the
    # timestamp made a block land in a file for an EARLIER week,
    # being processed out of height order (=> phantom UTXOs and lost spends).
    week_actual = state.get("last_processed_week") if start_height > 0 else None

    for h in tqdm(range(start_height, tip + 1), desc="Blocks", unit="blk"):
        try:
            bh = get_block_hash(h)
            blk = get_block(bh)

            ts = blk.get("time")
            if ts is None:
                raise ValueError(f"block {h} without timestamp")
            own_week = timestamp_to_week(int(ts))
            if week_actual is None or week_to_int(own_week) > week_to_int(week_actual):
                week_actual = own_week
            week = week_actual

            if week not in accums:
                accums[week] = new_accumulator()

            b, t, i, o = process_block(blk)
            accums[week]["blocks"].append(b)
            accums[week]["txs"].append(t)
            accums[week]["inputs"].append(i)
            accums[week]["outputs"].append(o)

            flush_ready_weeks(accums, week, state)

            if h % SAVE_EVERY == 0 or h == tip:
                state["last_processed_height"] = h
                state["last_processed_hash"] = bh
                state["last_processed_week"] = week
                save_state(state)

        except Exception as e:
            logger.error(f"Error processing block {h}: {e}")
            print(f"Error processing block {h}: {e}")
            save_state(state)
            return

    print(f"\n=== Writing remaining weeks ({len(accums)}) ===")
    for week in sorted(accums.keys()):
        print(f"  {week}: {len(accums[week]['blocks'])} blocks")
        last_h, _ = write_week(week, accums[week])
        if last_h >= 0:
            state["written_through_height"] = max(
                state.get("written_through_height", -1), last_h
            )
            state["last_written_week"] = week
            save_state(state)

    print("\nLayer 1 completed successfully.")
    logger.info("Layer 1 completed successfully.")

# ============================================================
# MAIN
# ============================================================

def ensure_dirs():
    os.makedirs(FAST_BASE, exist_ok=True)
    os.makedirs(TMP_DIR, exist_ok=True)
    for d in DIRS.values():
        os.makedirs(d, exist_ok=True)

def main():
    parser = argparse.ArgumentParser(description="Layer 1 — Bitcoin Core → weekly Parquet")
    parser.add_argument("--repair", nargs=2, type=int, metavar=("H1", "H2"))
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()

    if args.repair:
        start_h, end_h = args.repair
        if start_h > end_h:
            print("Error: H1 must be <= H2"); return
        tip = get_block_count()
        if end_h > tip:
            print(f"Error: H2={end_h} > tip={tip}"); return
        repair_range(start_h, end_h)
        return

    if args.validate:
        validate_capa1_continuity()
        return

    print("\n=== LAYER 1 — Bitcoin Core → weekly Parquet ===")
    print(f"Write path: {FAST_BASE}")
    print("1) Full reset (delete parquet + state)")
    print("2) Continue from the last complete week")
    print("==================================================")

    choice = input("Select an option [1-2]: ").strip()

    if choice == "1":
        print("Full reset requested.")
        logger.info("Full reset requested.")
        if os.path.exists(FAST_BASE):
            shutil.rmtree(FAST_BASE)
        ensure_dirs()
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
        print("Full reset executed. Starting from block 0.")
        logger.info("Full reset executed.")
        ingest_normal()
    elif choice == "2":
        print("Continuing from the last state.")
        logger.info("Continuation requested.")
        ingest_normal()
    else:
        print("Invalid option.")


if __name__ == "__main__":
    main()