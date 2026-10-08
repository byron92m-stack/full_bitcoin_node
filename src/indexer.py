#!/usr/bin/env python3
# ============================================================
# OBM — Indexer (Layer 1 → Layer 2)
#
# Replica of the spent-output indexer described in OBM §3.4:
#   - live_outputs.sqlite       current UTXO set (mutable state)
#   - daily_aggregates_YYYY.parquet    daily aggregates per year
#   - age_band_aggregates_YYYY.parquet aggregates per (day, band) per year
#   - state_indexer.json        progress: last_processed_week + journal + utxo_count
#
# Usage:
#   python3 indexer.py    # menu (1 = reset, 2 = continue)
#
# Processes WEEK BY WEEK, aligned with capa1.
# Only processes COMPLETE weeks (not the last one in progress).
# Commit per week.
# No rollback (only moves forward).
#
# Output: capa2/ (EVERYTHING the indexer produces).
# CDD in SATOSHI-DAYS (int64). They fit comfortably in int64 (max 9.2e18).
# To convert to BTC-days: cdd_btc_days = cdd_sat_days / 100_000_000.
#
# v5 — patches from the review:
#   P1b. Never processes the ETL's current week (the final drain leaves it half-done):
#        it requires that the ETL has already written a LATER week.
#   P2c. inserted via cursor.rowcount. NEVER con.total_changes: sqlite3_total_changes()
#        truncates to 32 bits and wraps around (real bug F5, corrupted utxo_count from 2017-W13).
#   P4b. CROSS JOIN to pin the plan: a normal JOIN is reversed if ANALYZE is present
#        (full SCAN of live_outputs per block).
#   P5.  weeks_done: progress in the SAME transaction as the data; the DB is the
#        source of truth for progress and utxo_count is derived from it.
#
# v4 — applied patches:
#   P1. Complete-week guard (does not process capa1's last week in progress).
#   P2. inserted = max(cursor.rowcount, 0) (does not inflate utxo_count).
#   P3. Abort if last_week is None with a non-empty DB.
#   P4. SQLite batching per block (bulk SELECT + DELETE).
# ============================================================

import os
import sys
import json
import math
import time
import shutil
import sqlite3
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple
from decimal import Decimal

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ============================================================
# CONFIG
# ============================================================

OBM_ROOT = "/media/SSD4T/obm"
CAPA1 = os.path.join(OBM_ROOT, "capa1")
CAPA2 = os.path.join(OBM_ROOT, "capa2")
STATE_FILE = os.path.join(OBM_ROOT, "state_indexer.json")
STATE_CAPA1_FILE = os.path.join(OBM_ROOT, "state_capa1.json")
LOG_DIR = os.path.join(OBM_ROOT, "logs")
LOG_FILE = os.path.join(LOG_DIR, "indexer.log")
TMP_DIR = os.path.join(OBM_ROOT, "tmp", "indexer")
DB_PATH = os.path.join(CAPA2, "live_outputs.sqlite")

SATOSHI = 100_000_000
SEGUNDOS_DIA = 86400

# Age bands (paper §3.4)
BANDAS = [
    (0, 1, "0d_1d"),
    (1, 7, "1d_1w"),
    (7, 30, "1w_1m"),
    (30, 90, "1m_3m"),
    (90, 180, "3m_6m"),
    (180, 365, "6m_1y"),
    (365, 730, "1y_2y"),
    (730, 1095, "2y_3y"),
    (1095, 1825, "3y_5y"),
    (1825, 2555, "5y_7y"),
    (2555, 3650, "7y_10y"),
    (3650, float("inf"), "10y_plus"),
]

THRESHOLD_155D = 155 * SEGUNDOS_DIA
THRESHOLD_365D = 365 * SEGUNDOS_DIA

# ============================================================
# EXPLICIT DTYPES
# ============================================================

DAILY_DTYPES = {
    "date": "string",
    "last_height": "int64",
    "spent_value_sats": "int64",
    "spent_output_count": "int64",
    # EXACT CDD = cdd_sat_days + cdd_rem_86400/86400  (sat-days, Decimal)
    "cdd_sat_days": "int64",
    "cdd_rem_86400": "int64",
    "fees_sats": "int64",
    "coinbase_output_sats": "int64",
    "issuance_sats": "int64",
    "utxo_eod_count": "int64",
    "spent_value_ge155d_sats": "int64",
    "spent_value_ge365d_sats": "int64",
    "cdd_ge155d_sat_days": "int64",
    "cdd_ge155d_rem_86400": "int64",
    "cdd_ge365d_sat_days": "int64",
    "cdd_ge365d_rem_86400": "int64",
}

AGE_BAND_DTYPES = {
    "date": "string",
    "age_band": "string",
    "spent_value_sats": "int64",
    "spent_output_count": "int64",
    "cdd_sat_days": "int64",
    "cdd_rem_86400": "int64",
}

# ============================================================
# LOGGING
# ============================================================

def setup_logger() -> logging.Logger:
    os.makedirs(LOG_DIR, exist_ok=True)
    logger = logging.getLogger("indexer")
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
# STATE
# ============================================================

def load_state() -> Dict[str, Any]:
    if not os.path.exists(STATE_FILE):
        return {
            "last_processed_week": None,
            "last_processed_height": -1,
            "last_processed_hash": None,
            "utxo_count": 0,
            "week_journal": {},
        }
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        state = json.load(f)
    state.setdefault("week_journal", {})
    state.setdefault("utxo_count", 0)
    return state

def save_state(state: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_FILE)

def load_state_capa1() -> Dict[str, Any]:
    """ETL state (to know how far capa1 has been written)."""
    if not os.path.exists(STATE_CAPA1_FILE):
        return {"written_through_height": -1, "last_written_week": None}
    with open(STATE_CAPA1_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

# ============================================================
# SQLITE
# ============================================================

def open_db() -> sqlite3.Connection:
    os.makedirs(CAPA2, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA synchronous = NORMAL")
    con.execute("PRAGMA cache_size = -2000000")   # KiB -> ~1.9 GB
    con.execute("PRAGMA temp_store = MEMORY")
    con.execute("PRAGMA mmap_size = 6000000000")   # bytes -> ~5.6 GB
    con.execute("""
        CREATE TABLE IF NOT EXISTS live_outputs (
            txid TEXT NOT NULL,
            vout INTEGER NOT NULL,
            value_sats INTEGER NOT NULL,
            created_height INTEGER NOT NULL,
            created_time INTEGER NOT NULL,
            script_type TEXT,
            PRIMARY KEY (txid, vout)
        ) WITHOUT ROWID
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS weeks_done (
            week TEXT PRIMARY KEY,
            last_height INTEGER NOT NULL,
            last_hash TEXT,
            n_spent INTEGER NOT NULL DEFAULT 0,
            n_inserted INTEGER NOT NULL DEFAULT 0,
            finished_at TEXT
        )
    """)
    # F7: the daily and per-band aggregates live in the DB, written in the SAME
    # transaction as the data. The yearly parquet files are a DERIVED artifact rebuildable with
    # rebuild_year_from_db(), so a cut between the commit and the parquet write
    # can no longer leave days lost (it was the case of 2022-W06).
    con.execute("""
        CREATE TABLE IF NOT EXISTS daily_agg (
            date TEXT PRIMARY KEY,
            last_height INTEGER NOT NULL DEFAULT -1,
            spent_value_sats INTEGER NOT NULL DEFAULT 0,
            spent_output_count INTEGER NOT NULL DEFAULT 0,
            cdd_sat_days INTEGER NOT NULL DEFAULT 0,
            cdd_rem_86400 INTEGER NOT NULL DEFAULT 0,
            fees_sats INTEGER NOT NULL DEFAULT 0,
            coinbase_output_sats INTEGER NOT NULL DEFAULT 0,
            issuance_sats INTEGER NOT NULL DEFAULT 0,
            utxo_eod_count INTEGER NOT NULL DEFAULT 0,
            spent_value_ge155d_sats INTEGER NOT NULL DEFAULT 0,
            spent_value_ge365d_sats INTEGER NOT NULL DEFAULT 0,
            cdd_ge155d_sat_days INTEGER NOT NULL DEFAULT 0,
            cdd_ge155d_rem_86400 INTEGER NOT NULL DEFAULT 0,
            cdd_ge365d_sat_days INTEGER NOT NULL DEFAULT 0,
            cdd_ge365d_rem_86400 INTEGER NOT NULL DEFAULT 0
        ) WITHOUT ROWID
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS age_band_agg (
            date TEXT NOT NULL,
            age_band TEXT NOT NULL,
            spent_value_sats INTEGER NOT NULL DEFAULT 0,
            spent_output_count INTEGER NOT NULL DEFAULT 0,
            cdd_sat_days INTEGER NOT NULL DEFAULT 0,
            cdd_rem_86400 INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (date, age_band)
        ) WITHOUT ROWID
    """)
    con.execute("""
        CREATE TEMP TABLE IF NOT EXISTS input_keys (
            txid TEXT NOT NULL,
            vout INTEGER NOT NULL
        )
    """)
    con.commit()
    return con

def db_count(con: sqlite3.Connection) -> int:
    return con.execute("SELECT COUNT(*) FROM live_outputs").fetchone()[0]

# ============================================================
# READING CAPA1 (per week)
# ============================================================

def list_available_weeks() -> List[str]:
    blocks_dir = os.path.join(CAPA1, "blocks")
    if not os.path.exists(blocks_dir):
        return []
    semanas = []
    for fname in os.listdir(blocks_dir):
        if fname.startswith("blocks_") and fname.endswith(".parquet"):
            week = fname[len("blocks_"):-len(".parquet")]
            semanas.append(week)
    return sorted(semanas)

def check_capa1_monotonic(weeks: List[str]) -> bool:
    """Checks that the capa1 week files are ordered by height.
    Uses the parquet statistics (min/max of 'height'): cost ~milliseconds."""
    prev_max, prev_week, malas = -1, None, []
    for w in weeks:
        p = os.path.join(CAPA1, "blocks", f"blocks_{w}.parquet")
        pf = pq.ParquetFile(p)
        i = pf.schema.names.index("height")
        mn = mx = None
        for rg in range(pf.metadata.num_row_groups):
            st = pf.metadata.row_group(rg).column(i).statistics
            if st is None or not st.has_min_max:
                mn = None
                break
            mn = st.min if mn is None else min(mn, st.min)
            mx = st.max if mx is None else max(mx, st.max)
        if mn is None:                      # no statistics: read the column
            col = pq.read_table(p, columns=["height"])["height"].to_pylist()
            mn, mx = min(col), max(col)
        if mn <= prev_max:
            malas.append((prev_week, w, mn, prev_max))
        prev_max, prev_week = mx, w
    if malas:
        for pw, w, mn, pm in malas:
            logger.error(f"capa1 NOT monotonic in height: {w} starts at {mn:,} "
                         f"but {pw} reaches {pm:,}")
        print("\nERROR: capa1 has weeks out of order by height "
              "(non-monotonic block timestamps badly partitioned).")
        print("The indexer would process blocks out of order -> ghost UTXOs.")
        print("Fix the ETL (week = max(own, previous)) and re-partition")
        print("with etl/reparticionar_semanas.py")
        return False
    return True

def check_parquet_cobertura(done_weeks) -> List[Tuple[str, List[str]]]:
    """Detects weeks in weeks_done whose days are NOT in the yearly aggregates parquet.

    Known cause (finding F7): the parquet write is AFTER the commit, so
    a cut between both leaves the week committed and registered but without aggregates, and on
    resume it is skipped. Here it is detected and we abort instead of losing it silently.

    Since the F7 fix the parquet files are a DERIVED artifact of the DB that is rebuilt entirely at
    startup (rebuild_all_from_db), so this cut can no longer happen: this guard is
    the check that the rebuild has covered all the weeks in weeks_done.
    """
    por_anio = {}

    def dias_del_anio(y):
        if y not in por_anio:
            p = os.path.join(CAPA2, f"daily_aggregates_{y}.parquet")
            por_anio[y] = (set(pd.read_parquet(p, columns=["date"])["date"].astype(str))
                           if os.path.exists(p) else None)
        return por_anio[y]

    faltan = []
    for w in sorted(done_weeks):
        try:
            t = pq.read_table(os.path.join(CAPA1, "blocks", f"blocks_{w}.parquet"),
                              columns=["time"])
            esperados = {utc_date_from_timestamp(int(x)) for x in t["time"].to_pylist()}
        except Exception:
            continue
        # F8.6: each day is written to the parquet of ITS year, not to that of the week. A
        # week can start or end in the adjacent year (2009-W53 -> 2010-01-01..03
        # lives in daily_aggregates_2010.parquet), so it must be looked up by the year of
        # the day itself. Looking it up in the one for w[:4] caused 13 false aborts at year boundaries.
        f = sorted(d for d in esperados
                   if dias_del_anio(d[:4]) is None or d not in dias_del_anio(d[:4]))
        if f:
            faltan.append((w, f))
    return faltan


def week_to_int(week: str) -> int:
    """'2026-W39' -> 202639 (comparable as an integer)."""
    y, w = week.split("-W")
    return int(y) * 100 + int(w)

def read_week(week: str) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    blocks = pq.read_table(os.path.join(CAPA1, "blocks", f"blocks_{week}.parquet")).to_pandas()
    txs = pq.read_table(os.path.join(CAPA1, "txs", f"txs_{week}.parquet")).to_pandas()
    inputs = pq.read_table(os.path.join(CAPA1, "inputs", f"inputs_{week}.parquet")).to_pandas()
    outputs = pq.read_table(os.path.join(CAPA1, "outputs", f"outputs_{week}.parquet")).to_pandas()
    return blocks, txs, inputs, outputs

# ============================================================
# HELPERS
# ============================================================

def utc_date_from_timestamp(ts: int) -> str:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d")

def get_age_band(age_days: float) -> Optional[str]:
    """Paper's age band (SS3.4). The BANDAS boundaries are in DAYS."""
    for lo, hi, name in BANDAS:
        if lo <= age_days < hi:
            return name
    return None

def empty_daily_row(date: str) -> Dict[str, int]:
    return {
        "date": date, "last_height": -1,
        "spent_value_sats": 0, "spent_output_count": 0,
        "cdd_sat_days": 0, "cdd_rem_86400": 0,
        "fees_sats": 0, "coinbase_output_sats": 0, "issuance_sats": 0,
        "utxo_eod_count": 0,
        "spent_value_ge155d_sats": 0, "spent_value_ge365d_sats": 0,
        "cdd_ge155d_sat_days": 0, "cdd_ge155d_rem_86400": 0,
        "cdd_ge365d_sat_days": 0, "cdd_ge365d_rem_86400": 0,
    }

def empty_age_band_row(date: str, band: str) -> Dict[str, int]:
    return {
        "date": date, "age_band": band,
        "spent_value_sats": 0, "spent_output_count": 0,
        "cdd_sat_days": 0, "cdd_rem_86400": 0,
    }

# ============================================================
# PROCESSING ONE WEEK (with P4: batching)
# ============================================================

def process_week(con: sqlite3.Connection, week: str, utxo_count: int) -> Optional[Dict[str, Any]]:
    logger.info(f"Reading week {week} from capa1...")
    blocks, txs, inputs, outputs = read_week(week)

    if blocks.empty:
        logger.warning(f"  Week {week} has no blocks, skipping")
        return None

    # Index by height
    blocks_by_height = {int(r.height): r for r in blocks.itertuples(index=False)}
    txs_by_height: Dict[int, List[Any]] = {}
    for r in txs.itertuples(index=False):
        txs_by_height.setdefault(int(r.height), []).append(r)
    inputs_by_height_txid: Dict[Tuple[int, str], List[Any]] = {}
    for r in inputs.itertuples(index=False):
        inputs_by_height_txid.setdefault((int(r.height), r.txid), []).append(r)
    outputs_by_height_txid: Dict[Tuple[int, str], List[Any]] = {}
    for r in outputs.itertuples(index=False):
        outputs_by_height_txid.setdefault((int(r.height), r.txid), []).append(r)

    daily: Dict[str, Dict[str, int]] = {}
    age_bands: Dict[Tuple[str, str], Dict[str, int]] = {}
    utxo_count_by_date: Dict[str, int] = {}
    n_spent_total = 0
    n_inserted_total = 0

    logger.info(f"  UTXO count at the start of the week: {utxo_count:,}")

    alturas = sorted(blocks_by_height.keys())
    for h in alturas:
        block = blocks_by_height[h]
        block_time = int(block.time)
        date = utc_date_from_timestamp(block_time)
        if date not in daily:
            daily[date] = empty_daily_row(date)
        daily[date]["last_height"] = h

        block_txs = txs_by_height.get(h, [])
        coinbase_output_sats = 0
        total_input_sats = 0
        total_output_sats_no_coinbase = 0

        # ---- P4: STEP A: collect the block's input_keys ----
        input_keys_batch = []
        input_to_tx = {}

        for tx in block_txs:
            txid = tx.txid
            key = (h, txid)
            tx_inputs = inputs_by_height_txid.get(key, [])
            tx_outputs = outputs_by_height_txid.get(key, [])

            if not tx_inputs:
                logger.warning(f"  TX {txid} has no inputs (block {h}), skipping")
                continue
            is_coinbase = bool(tx_inputs[0].is_coinbase)

            if is_coinbase:
                for vout in tx_outputs:
                    coinbase_output_sats += int(vout.value_sats)
                continue

            for vout in tx_outputs:
                total_output_sats_no_coinbase += int(vout.value_sats)

            for vin in tx_inputs:
                pk = (vin.prev_txid, int(vin.prev_vout))
                input_keys_batch.append(pk)
                input_to_tx[pk] = txid

        # ---- P4: STEP B: resolve with ONE SELECT ----
        con.execute("DELETE FROM input_keys")
        if input_keys_batch:
            con.executemany(
                "INSERT OR IGNORE INTO input_keys (txid, vout) VALUES (?, ?)",
                input_keys_batch,
            )

        # CROSS JOIN pins the join order: it scans input_keys (small) and looks up
        # live_outputs by PRIMARY KEY. With a normal "JOIN", if statistics exist
        # (ANALYZE) the planner reverses it -> full SCAN of live_outputs per
        # block (hundreds of millions of rows) and the job never finishes.
        rows = con.execute("""
            SELECT ik.txid, ik.vout, lo.value_sats, lo.created_time
            FROM input_keys ik CROSS JOIN live_outputs lo
            WHERE lo.txid = ik.txid AND lo.vout = ik.vout
        """).fetchall()
        utxo_map = {(r[0], r[1]): (int(r[2]), int(r[3])) for r in rows}

        # ---- P4: STEP C: process resolved inputs ----
        resolved_keys = []
        for pk in input_keys_batch:
            row = utxo_map.get(pk)
            if row is None:
                prev_txid, prev_vout = pk
                other_key = (h, prev_txid)
                for other_vout in outputs_by_height_txid.get(other_key, []):
                    if int(other_vout.vout) == prev_vout:
                        row = (int(other_vout.value_sats), block_time)
                        break

            if row is None:
                logger.warning(
                    f"  UTXO not found: {pk[0]}:{pk[1]} "
                    f"spent by {input_to_tx[pk]} (block {h})"
                )
                continue

            value_sats, created_time = row
            age_seconds = max(0, block_time - created_time)
            # EXACT CDD: integer part and remainder numerator separately.
            # Truncating per input (//86400) introduced up to 1 sat-day of error per input
            # (~1e-9 relative in the daily aggregate).
            cdd_sat_days, cdd_rem = divmod(value_sats * age_seconds, SEGUNDOS_DIA)

            daily[date]["spent_value_sats"] += value_sats
            daily[date]["spent_output_count"] += 1
            daily[date]["cdd_sat_days"] += cdd_sat_days
            daily[date]["cdd_rem_86400"] += cdd_rem
            total_input_sats += value_sats

            if age_seconds >= THRESHOLD_155D:
                daily[date]["spent_value_ge155d_sats"] += value_sats
                daily[date]["cdd_ge155d_sat_days"] += cdd_sat_days
                daily[date]["cdd_ge155d_rem_86400"] += cdd_rem
            if age_seconds >= THRESHOLD_365D:
                daily[date]["spent_value_ge365d_sats"] += value_sats
                daily[date]["cdd_ge365d_sat_days"] += cdd_sat_days
                daily[date]["cdd_ge365d_rem_86400"] += cdd_rem

            # NOTE: the BANDAS boundaries are in DAYS -> the age must be passed
            # in days. It used to be passed in SECONDS and almost everything fell into '10y_plus'.
            band = get_age_band(age_seconds / SEGUNDOS_DIA)
            if band is not None:
                key_band = (date, band)
                if key_band not in age_bands:
                    age_bands[key_band] = empty_age_band_row(date, band)
                age_bands[key_band]["spent_value_sats"] += value_sats
                age_bands[key_band]["spent_output_count"] += 1
                age_bands[key_band]["cdd_sat_days"] += cdd_sat_days
                age_bands[key_band]["cdd_rem_86400"] += cdd_rem

            resolved_keys.append(pk)
            utxo_count -= 1

        # ---- Fees and issuance ----
        fees_sats = total_input_sats - total_output_sats_no_coinbase
        if fees_sats < 0:
            logger.warning(f"  Block {h}: negative fees ({fees_sats}), clamping to 0")
            fees_sats = 0
        issuance_sats = coinbase_output_sats - fees_sats
        if issuance_sats < 0:
            logger.warning(f"  Block {h}: negative issuance ({issuance_sats}), clamping to 0")
            issuance_sats = 0

        daily[date]["fees_sats"] += fees_sats
        daily[date]["coinbase_output_sats"] += coinbase_output_sats
        daily[date]["issuance_sats"] += issuance_sats

        # ---- Process outputs ----
        output_rows = []
        for tx in block_txs:
            txid = tx.txid
            key = (h, txid)
            tx_outputs = outputs_by_height_txid.get(key, [])
            for vout in tx_outputs:
                st = vout.script_type
                if st == "nulldata":
                    continue
                sh = vout.script_hex or ""
                if sh.startswith("6a") or len(sh) > 20000:
                    continue
                output_rows.append((txid, int(vout.vout), int(vout.value_sats), h, block_time, st))

        if output_rows:
            cur = con.executemany(
                "INSERT OR IGNORE INTO live_outputs VALUES (?, ?, ?, ?, ?, ?)",
                output_rows,
            )
            # ---- P2c: INSERT accounting ----
            # Do NOT use con.total_changes: the C API sqlite3_total_changes() truncates to
            # 32 bits and wraps around after 2^32 changes (real bug that corrupted
            # utxo_count from 2017-W13). cursor.rowcount accumulates in
            # executemany and is bounded by the batch size (thousands), with no risk.
            inserted = cur.rowcount if (cur.rowcount is not None and cur.rowcount > 0) else 0
            if not (0 <= inserted <= len(output_rows)):
                logger.error(f"  Block {h}: inserted={inserted} out of range "
                             f"(batch of {len(output_rows)}); clamping")
                inserted = max(0, min(inserted, len(output_rows)))
            utxo_count += inserted
            n_inserted_total += inserted

        # ---- P4: STEP D: delete ALL spent outputs at once ----
        # CRITICAL: the DELETE goes AFTER the INSERT of outputs.
        # If it goes before, an output created and spent in the same block
        # is not deleted (it does not exist yet) and remains as a ghost row.
        if resolved_keys:
            con.executemany(
                "DELETE FROM live_outputs WHERE txid = ? AND vout = ?",
                resolved_keys,
            )
            n_spent_total += len(resolved_keys)

        utxo_count_by_date[date] = utxo_count

    # Assign utxo_eod_count
    for date in daily:
        daily[date]["utxo_eod_count"] = utxo_count_by_date.get(date, utxo_count)

    last_height = max(blocks_by_height.keys())
    last_hash = blocks_by_height[last_height].hash

    # ---- F7: the aggregates go in the SAME transaction as the data ----
    # The yearly parquet becomes a derived artifact rebuildable from here.
    _sql_d = (f"INSERT OR REPLACE INTO daily_agg ({', '.join(DAILY_DTYPES)}) "
              f"VALUES ({', '.join(['?'] * len(DAILY_DTYPES))})")
    con.executemany(_sql_d, [tuple(r[c] for c in DAILY_DTYPES) for r in daily.values()])
    _sql_b = (f"INSERT OR REPLACE INTO age_band_agg ({', '.join(AGE_BAND_DTYPES)}) "
              f"VALUES ({', '.join(['?'] * len(AGE_BAND_DTYPES))})")
    con.executemany(_sql_b, [tuple(r[c] for c in AGE_BAND_DTYPES) for r in age_bands.values()])

    # ---- P5: progress is recorded in the SAME transaction as the data ----
    # A cut between the commit and the JSON save can no longer reprocess the
    # week (its inputs would be deleted and the aggregates would come out zero,
    # overwriting the correct values with drop_duplicates(keep="last")).
    con.execute(
        "INSERT OR REPLACE INTO weeks_done "
        "(week, last_height, last_hash, n_spent, n_inserted, finished_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (week, last_height, last_hash, n_spent_total, n_inserted_total,
         datetime.now(timezone.utc).isoformat(timespec="seconds")),
    )
    con.commit()
    logger.info(
        f"  Week {week} processed: {len(daily)} days, "
        f"{len(age_bands)} band rows, UTXOs at end: {utxo_count:,}"
    )

    last_height = max(blocks_by_height.keys())
    last_hash = blocks_by_height[last_height].hash
    return {
        "daily": daily, "age_bands": age_bands,
        "last_height": last_height, "last_hash": last_hash,
        "utxo_count": utxo_count,
    }

# ============================================================
# WRITING AGGREGATES (per year) in capa2
# ============================================================

def _write_year_parquet(con: sqlite3.Connection, table: str, dtypes: Dict[str, str],
                        filename: str, year: str, order: str) -> None:
    cols = list(dtypes)
    df = pd.read_sql_query(
        f"SELECT {', '.join(cols)} FROM {table} WHERE date LIKE ? ORDER BY {order}",
        con, params=(year + "-%",),
    )
    for col, dt in dtypes.items():
        if col in df.columns:
            df[col] = df[col].astype(dt)
    path = os.path.join(CAPA2, filename)
    tmp = path + ".tmp"
    df.to_parquet(tmp, index=False, compression="zstd")
    os.replace(tmp, path)
    logger.info(f"  {filename}: {len(df)} rows (from the DB)")

def rebuild_year_from_db(con: sqlite3.Connection, year: str) -> None:
    """Rewrites COMPLETELY the two yearly parquet files of `year` from the DB.

    Does not merge with whatever was on disk: the DB —written in the SAME transaction as
    the data— is the single source, so this is idempotent and repairs by itself
    any earlier cut between the commit and the parquet write (F7). Also,
    since there is a single row per date, the double-counting risk that the
    merge-by SUM had when a date was split between two weeks disappears (F4).
    """
    _write_year_parquet(con, "daily_agg", DAILY_DTYPES,
                        f"daily_aggregates_{year}.parquet", year, "date")
    _write_year_parquet(con, "age_band_agg", AGE_BAND_DTYPES,
                        f"age_band_aggregates_{year}.parquet", year, "date, age_band")

def rebuild_all_from_db(con: sqlite3.Connection) -> int:
    """Rebuilds the yearly files for all the years present in the DB."""
    anios = [r[0] for r in con.execute(
        "SELECT DISTINCT substr(date, 1, 4) FROM daily_agg ORDER BY 1")]
    for y in anios:
        rebuild_year_from_db(con, y)
    return len(anios)

# ============================================================
# MAIN
# ============================================================

def ensure_dirs():
    os.makedirs(CAPA2, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(TMP_DIR, exist_ok=True)

def main():
    print("\n=== OBM Indexer — Layer 1 → Layer 2 ===")
    print(f"capa1 (read):  {CAPA1}")
    print(f"capa2 (write): {CAPA2}")
    print("1) Full reset (delete capa2 + state)")
    print("2) Continue from the last processed week")
    print("================================================")

    choice = input("Select an option [1-2]: ").strip()
    ensure_dirs()

    if choice == "1":
        print("Full reset requested.")
        logger.info("Full reset requested.")
        if os.path.exists(CAPA2):
            shutil.rmtree(CAPA2)
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
        ensure_dirs()
        print("Full reset executed.")
        logger.info("Full reset executed.")

    # Load state
    state = load_state()
    last_week = state.get("last_processed_week")
    journal = state.get("week_journal", {})
    utxo_count = state.get("utxo_count", 0)

    # ---- P1: load written_through from the ETL ----
    state_capa1 = load_state_capa1()
    written_through = state_capa1.get("written_through_height", -1)
    print(f"\nwritten_through (ETL): {written_through:,}")

    # Filter COMPLETE weeks
    available = list_available_weeks()
    if not available:
        print("No weeks in capa1.")
        return

    if not check_capa1_monotonic(available):
        return

    # A week is COMPLETE only if the ETL has already moved on to a LATER week.
    # The ETL does a final "drain" that writes the current week HALF-DONE, so
    # (max(height) <= written_through) is NOT enough: it would be true for that partial week
    # and the indexer would process it incomplete and then skip it forever.
    capa1_week = state_capa1.get("last_written_week")
    capa1_week_int = week_to_int(capa1_week) if capa1_week else None
    if capa1_week:
        print(f"ETL's current week: {capa1_week} (excluded)")

    def week_is_complete(week):
        try:
            t = pq.read_table(
                os.path.join(CAPA1, "blocks", f"blocks_{week}.parquet"),
                columns=["height"],
            )
            if max(t["height"].to_pylist()) > written_through:
                return False          # file truncated relative to the ETL state
            if capa1_week_int is not None and week_to_int(week) >= capa1_week_int:
                return False          # ETL's current week (possibly partial)
            return True
        except Exception:
            return False

    available_complete = [w for w in available if week_is_complete(w)]
    print(f"Available weeks: {len(available)}")
    print(f"Complete weeks:  {len(available_complete)}")

    # The real progress lives in the DB's weeks_done table (filtered further below,
    # after opening it). last_week / state_indexer.json remains as information.
    to_process = available_complete

    if not to_process:
        print("No new weeks to process.")
        return

    print(f"Weeks to process: {len(to_process)} (from {to_process[0]} to {to_process[-1]})")
    logger.info(f"Processing {len(to_process)} weeks")

    con = open_db()

    # ---- P3: abort if last_week is None with a non-empty DB ----
    done_weeks = {r[0] for r in con.execute("SELECT week FROM weeks_done")}
    if done_weeks:
        # F7: the yearly parquet files are DERIVED from the DB, so they are rebuilt entirely
        # at startup. That repairs by itself an earlier cut between the commit and the
        # parquet write; the guard that follows checks that the rebuild
        # has covered all the weeks in weeks_done.
        n_anios = rebuild_all_from_db(con)
        logger.info(f"yearly parquet rebuilt from the DB ({n_anios} years)")
        faltan = check_parquet_cobertura(done_weeks)
        if faltan:
            for w, ds in faltan[:5]:
                logger.error(f"aggregates missing for {w}: {len(ds)} days (e.g. {ds[:3]})")
            print("\nERROR: there are weeks in weeks_done WITHOUT their aggregates in the yearly parquet.")
            print("Known cause (F7): cut between the commit and the parquet write.")
            print("Do NOT continue with those days without repairing. See AUDITORIA_HALLAZGOS.md (F7).")
            con.close()
            return
    if not done_weeks:
        real_count = db_count(con)
        if real_count > 0:
            logger.error(f"DB has {real_count:,} UTXOs but the state says last_week=None.")
            print(f"\nERROR: DB has {real_count:,} UTXOs but the state does not.")
            print("Aborting to avoid corruption.")
            print("To start from scratch:")
            print("  python3 indexer.py  # option 1 (reset)")
            return
        utxo_count = 0
    else:
        utxo_count = con.execute(
            "SELECT COALESCE(SUM(n_inserted),0) - COALESCE(SUM(n_spent),0) FROM weeks_done"
        ).fetchone()[0]
        print(f"Weeks already indexed: {len(done_weeks)} (last: {max(done_weeks)}) | "
              f"Live UTXOs: {utxo_count:,}")
        to_process = [w for w in to_process if w not in done_weeks]
        if not to_process:
            print("No new weeks to process.")
            con.close()
            return

    t0 = time.time()
    for i, week in enumerate(to_process):
        t_start = time.time()
        try:
            result = process_week(con, week, utxo_count)
        except Exception as e:
            logger.error(f"Error processing {week}: {e}", exc_info=True)
            print(f"\nError processing {week}: {e}")
            save_state(state)
            con.close()
            return

        if result is None:
            logger.warning(f"  Week {week} has no data, skipping")
            state["last_processed_week"] = week
            save_state(state)
            continue

        utxo_count = result["utxo_count"]

        # The aggregates are already in the DB (same transaction); here only the
        # yearly files of the years touched by this week are rewritten entirely.
        for y in set(d.split("-")[0] for d in result["daily"]):
            rebuild_year_from_db(con, y)

        state["last_processed_week"] = week
        state["last_processed_height"] = result["last_height"]
        state["last_processed_hash"] = result["last_hash"]
        state["utxo_count"] = utxo_count
        journal[week] = {"last_height": result["last_height"], "last_hash": result["last_hash"]}
        state["week_journal"] = journal
        save_state(state)

        elapsed = time.time() - t_start
        total_elapsed = time.time() - t0
        avg = total_elapsed / (i + 1)
        remaining = avg * (len(to_process) - i - 1)

        print(f"[{i+1:>4}/{len(to_process)}] {week}: "
              f"{elapsed:>5.1f}s | ETA: {remaining/3600:>5.1f}h | "
              f"UTXOs: {utxo_count:>12,}")

    con.close()
    print("\nIndexer completed successfully.")
    logger.info("Indexer completed successfully.")

if __name__ == "__main__":
    main()