#!/usr/bin/env python3
# ============================================================
# OBM — Indexer (Capa 1 → Capa 2)
#
# Replica del spent-output indexer descrito en OBM §3.4:
#   - live_outputs.sqlite       UTXO set actual (estado mutable)
#   - daily_aggregates_YYYY.parquet    agregados diarios por año
#   - age_band_aggregates_YYYY.parquet agregados por (día, banda) por año
#   - state_indexer.json        progreso: last_processed_week + journal + utxo_count
#
# Uso:
#   python3 indexer.py    # menú (1 = reset, 2 = continuar)
#
# Procesa SEMANA A SEMANA, alineado con capa1.
# Solo procesa semanas COMPLETAS (no la última en curso).
# Commit por semana.
# Sin rollback (solo avanza hacia adelante).
#
# Salida: capa2/ (TODO lo que produce el indexer).
# CDD en SATOSHI-DÍAS (int64). Caben holgadamente en int64 (max 9.2e18).
# Para convertir a BTC-días: cdd_btc_days = cdd_sat_days / 100_000_000.
#
# v5 — parches de la revision:
#   P1b. Nunca procesa la semana en curso del ETL (el drain final la deja a medias):
#        exige que el ETL ya haya escrito una semana POSTERIOR.
#   P2c. inserted via cursor.rowcount. NUNCA con.total_changes: sqlite3_total_changes()
#        trunca a 32 bits y da la vuelta (bug real F5, corrompio utxo_count desde 2017-W13).
#   P4b. CROSS JOIN para fijar el plan: un JOIN normal se invierte si hay ANALYZE
#        (SCAN completo de live_outputs por bloque).
#   P5.  weeks_done: progreso en la MISMA transaccion que los datos; la DB es la
#        fuente de verdad del avance y utxo_count se deriva de ella.
#
# v4 — parches aplicados:
#   P1. Guard de semana completa (no procesa la última en curso de capa1).
#   P2. inserted = max(cursor.rowcount, 0) (no infla utxo_count).
#   P3. Abortar si last_week is None con DB no vacía.
#   P4. Batching SQLite por bloque (SELECT + DELETE masivos).
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

# Bandas de edad (paper §3.4)
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
# DTYPES EXPLÍCITOS
# ============================================================

DAILY_DTYPES = {
    "date": "string",
    "last_height": "int64",
    "spent_value_sats": "int64",
    "spent_output_count": "int64",
    # CDD EXACTO = cdd_sat_days + cdd_rem_86400/86400  (sat-dias, Decimal)
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
    """State del ETL (para saber hasta dónde está escrito capa1)."""
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
    con.execute("PRAGMA cache_size = -2000000")   # KiB -> ~1,9 GB
    con.execute("PRAGMA temp_store = MEMORY")
    con.execute("PRAGMA mmap_size = 6000000000")   # bytes -> ~5,6 GB
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
    # F7: los agregados diarios y por banda viven en la DB, escritos en la MISMA
    # transaccion que los datos. Los parquet anuales son un DERIVADO reconstruible con
    # rebuild_year_from_db(), asi que un corte entre el commit y la escritura del parquet
    # ya no puede dejar dias perdidos (fue el caso de 2022-W06).
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
# LECTURA DE CAPA1 (por semana)
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
    """Comprueba que los ficheros de semana de capa1 esten ordenados por altura.
    Usa las estadisticas de parquet (min/max de 'height'): coste ~milisegundos."""
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
        if mn is None:                      # sin estadisticas: leer la columna
            col = pq.read_table(p, columns=["height"])["height"].to_pylist()
            mn, mx = min(col), max(col)
        if mn <= prev_max:
            malas.append((prev_week, w, mn, prev_max))
        prev_max, prev_week = mx, w
    if malas:
        for pw, w, mn, pm in malas:
            logger.error(f"capa1 NO monotona en altura: {w} empieza en {mn:,} "
                         f"pero {pw} llega a {pm:,}")
        print("\nERROR: capa1 tiene semanas desordenadas por altura "
              "(timestamps de bloque no monotonos mal particionados).")
        print("El indexer procesaria bloques fuera de orden -> UTXOs fantasma.")
        print("Arregla el ETL (semana = max(propia, anterior)) y re-particiona")
        print("con etl/reparticionar_semanas.py")
        return False
    return True

def check_parquet_cobertura(done_weeks) -> List[Tuple[str, List[str]]]:
    """Detecta semanas de weeks_done cuyos dias NO estan en el parquet anual de agregados.

    Causa conocida (hallazgo F7): la escritura de los parquet es POSTERIOR al commit, asi que
    un corte entre ambos deja la semana commiteada y registrada pero sin agregados, y al
    reanudar se salta. Aqui se detecta y se aborta en vez de perderlo en silencio.

    Desde el arreglo de F7 los parquet son un DERIVADO de la DB que se reconstruye entero al
    arrancar (rebuild_all_from_db), asi que este corte ya no puede producirse: esta guarda es
    la comprobacion de que la reconstruccion ha cubierto todas las semanas de weeks_done.
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
        # F8.6: cada dia se escribe en el parquet de SU anio, no en el de la semana. Una
        # semana puede empezar o terminar en el anio contiguo (2009-W53 -> 2010-01-01..03
        # vive en daily_aggregates_2010.parquet), asi que hay que buscar por el anio del
        # propio dia. Buscarlo en el de w[:4] daba 13 abortos falsos por frontera de anio.
        f = sorted(d for d in esperados
                   if dias_del_anio(d[:4]) is None or d not in dias_del_anio(d[:4]))
        if f:
            faltan.append((w, f))
    return faltan


def week_to_int(week: str) -> int:
    """'2026-W39' -> 202639 (comparable como entero)."""
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
    """Banda de edad del paper (SS3.4). Las fronteras de BANDAS estan en DIAS."""
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
# PROCESAMIENTO DE UNA SEMANA (con P4: batching)
# ============================================================

def process_week(con: sqlite3.Connection, week: str, utxo_count: int) -> Optional[Dict[str, Any]]:
    logger.info(f"Leyendo semana {week} de capa1...")
    blocks, txs, inputs, outputs = read_week(week)

    if blocks.empty:
        logger.warning(f"  Semana {week} sin bloques, saltando")
        return None

    # Indexar por altura
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

    logger.info(f"  UTXO count al inicio de la semana: {utxo_count:,}")

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

        # ---- P4: PASO A: recolectar input_keys del bloque ----
        input_keys_batch = []
        input_to_tx = {}

        for tx in block_txs:
            txid = tx.txid
            key = (h, txid)
            tx_inputs = inputs_by_height_txid.get(key, [])
            tx_outputs = outputs_by_height_txid.get(key, [])

            if not tx_inputs:
                logger.warning(f"  TX {txid} sin inputs (bloque {h}), saltando")
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

        # ---- P4: PASO B: resolver con UN SELECT ----
        con.execute("DELETE FROM input_keys")
        if input_keys_batch:
            con.executemany(
                "INSERT OR IGNORE INTO input_keys (txid, vout) VALUES (?, ?)",
                input_keys_batch,
            )

        # CROSS JOIN fija el orden del join: recorre input_keys (pequena) y busca en
        # live_outputs por PRIMARY KEY. Con "JOIN" normal, si existen estadisticas
        # (ANALYZE) el planificador lo invierte -> SCAN completo de live_outputs por
        # bloque (cientos de millones de filas) y el job no termina nunca.
        rows = con.execute("""
            SELECT ik.txid, ik.vout, lo.value_sats, lo.created_time
            FROM input_keys ik CROSS JOIN live_outputs lo
            WHERE lo.txid = ik.txid AND lo.vout = ik.vout
        """).fetchall()
        utxo_map = {(r[0], r[1]): (int(r[2]), int(r[3])) for r in rows}

        # ---- P4: PASO C: procesar inputs resueltos ----
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
                    f"  UTXO no encontrado: {pk[0]}:{pk[1]} "
                    f"gastado por {input_to_tx[pk]} (bloque {h})"
                )
                continue

            value_sats, created_time = row
            age_seconds = max(0, block_time - created_time)
            # CDD EXACTO: parte entera y numerador del resto por separado.
            # Truncar por input (//86400) metia hasta 1 sat-dia de error por input
            # (~1e-9 relativo en el agregado diario).
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

            # OJO: las fronteras de BANDAS estan en DIAS -> hay que pasar la edad
            # en dias. Antes se pasaba en SEGUNDOS y casi todo caia en '10y_plus'.
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

        # ---- Fees e issuance ----
        fees_sats = total_input_sats - total_output_sats_no_coinbase
        if fees_sats < 0:
            logger.warning(f"  Bloque {h}: fees negativas ({fees_sats}), ajustando a 0")
            fees_sats = 0
        issuance_sats = coinbase_output_sats - fees_sats
        if issuance_sats < 0:
            logger.warning(f"  Bloque {h}: issuance negativa ({issuance_sats}), ajustando a 0")
            issuance_sats = 0

        daily[date]["fees_sats"] += fees_sats
        daily[date]["coinbase_output_sats"] += coinbase_output_sats
        daily[date]["issuance_sats"] += issuance_sats

        # ---- Procesar outputs ----
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
            # ---- P2c: contabilidad del INSERT ----
            # NO usar con.total_changes: la API C sqlite3_total_changes() trunca a
            # 32 bits y da la vuelta pasado 2^32 cambios (bug real que corrompio
            # utxo_count a partir de 2017-W13). cursor.rowcount acumula en
            # executemany y esta acotado por el tamano del lote (miles), sin riesgo.
            inserted = cur.rowcount if (cur.rowcount is not None and cur.rowcount > 0) else 0
            if not (0 <= inserted <= len(output_rows)):
                logger.error(f"  Bloque {h}: inserted={inserted} fuera de rango "
                             f"(lote de {len(output_rows)}); acotando")
                inserted = max(0, min(inserted, len(output_rows)))
            utxo_count += inserted
            n_inserted_total += inserted

        # ---- P4: PASO D: borrar TODOS los gastados de una vez ----
        # CRITICO: el DELETE va DESPUES del INSERT de outputs.
        # Si va antes, un output creado y gastado en el mismo bloque
        # no se borra (aun no existe) y queda como fila fantasma.
        if resolved_keys:
            con.executemany(
                "DELETE FROM live_outputs WHERE txid = ? AND vout = ?",
                resolved_keys,
            )
            n_spent_total += len(resolved_keys)

        utxo_count_by_date[date] = utxo_count

    # Asignar utxo_eod_count
    for date in daily:
        daily[date]["utxo_eod_count"] = utxo_count_by_date.get(date, utxo_count)

    last_height = max(blocks_by_height.keys())
    last_hash = blocks_by_height[last_height].hash

    # ---- F7: los agregados van en la MISMA transaccion que los datos ----
    # El parquet anual pasa a ser un derivado reconstruible desde aqui.
    _sql_d = (f"INSERT OR REPLACE INTO daily_agg ({', '.join(DAILY_DTYPES)}) "
              f"VALUES ({', '.join(['?'] * len(DAILY_DTYPES))})")
    con.executemany(_sql_d, [tuple(r[c] for c in DAILY_DTYPES) for r in daily.values()])
    _sql_b = (f"INSERT OR REPLACE INTO age_band_agg ({', '.join(AGE_BAND_DTYPES)}) "
              f"VALUES ({', '.join(['?'] * len(AGE_BAND_DTYPES))})")
    con.executemany(_sql_b, [tuple(r[c] for c in AGE_BAND_DTYPES) for r in age_bands.values()])

    # ---- P5: el progreso se registra en la MISMA transaccion que los datos ----
    # Un corte entre el commit y el guardado del JSON ya no puede reprocesar la
    # semana (sus inputs estarian borrados y los agregados saldrian a cero,
    # sobrescribiendo con drop_duplicates(keep="last") los valores correctos).
    con.execute(
        "INSERT OR REPLACE INTO weeks_done "
        "(week, last_height, last_hash, n_spent, n_inserted, finished_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (week, last_height, last_hash, n_spent_total, n_inserted_total,
         datetime.now(timezone.utc).isoformat(timespec="seconds")),
    )
    con.commit()
    logger.info(
        f"  Semana {week} procesada: {len(daily)} días, "
        f"{len(age_bands)} filas de bandas, UTXOs al final: {utxo_count:,}"
    )

    last_height = max(blocks_by_height.keys())
    last_hash = blocks_by_height[last_height].hash
    return {
        "daily": daily, "age_bands": age_bands,
        "last_height": last_height, "last_hash": last_hash,
        "utxo_count": utxo_count,
    }

# ============================================================
# ESCRITURA DE AGREGADOS (por año) en capa2
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
    logger.info(f"  {filename}: {len(df)} filas (desde la DB)")

def rebuild_year_from_db(con: sqlite3.Connection, year: str) -> None:
    """Reescribe COMPLETOS los dos parquet anuales de `year` a partir de la DB.

    No fusiona con lo que hubiera en disco: la DB —escrita en la MISMA transaccion que
    los datos— es la fuente unica, asi que esto es idempotente y repara por si solo
    cualquier corte anterior entre el commit y la escritura del parquet (F7). Ademas,
    al haber una sola fila por fecha, desaparece el riesgo de doble conteo que tenia la
    fusion por SUMA cuando una fecha quedaba repartida entre dos semanas (F4).
    """
    _write_year_parquet(con, "daily_agg", DAILY_DTYPES,
                        f"daily_aggregates_{year}.parquet", year, "date")
    _write_year_parquet(con, "age_band_agg", AGE_BAND_DTYPES,
                        f"age_band_aggregates_{year}.parquet", year, "date, age_band")

def rebuild_all_from_db(con: sqlite3.Connection) -> int:
    """Reconstruye los ficheros anuales de todos los años presentes en la DB."""
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
    print("\n=== OBM Indexer — Capa 1 → Capa 2 ===")
    print(f"capa1 (lectura):  {CAPA1}")
    print(f"capa2 (escritura): {CAPA2}")
    print("1) Reset completo (borrar capa2 + state)")
    print("2) Continuar desde la última semana procesada")
    print("================================================")

    choice = input("Selecciona una opción [1-2]: ").strip()
    ensure_dirs()

    if choice == "1":
        print("Reset completo solicitado.")
        logger.info("Reset completo solicitado.")
        if os.path.exists(CAPA2):
            shutil.rmtree(CAPA2)
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
        ensure_dirs()
        print("Reset completo ejecutado.")
        logger.info("Reset completo ejecutado.")

    # Cargar state
    state = load_state()
    last_week = state.get("last_processed_week")
    journal = state.get("week_journal", {})
    utxo_count = state.get("utxo_count", 0)

    # ---- P1: cargar written_through del ETL ----
    state_capa1 = load_state_capa1()
    written_through = state_capa1.get("written_through_height", -1)
    print(f"\nwritten_through (ETL): {written_through:,}")

    # Filtrar semanas COMPLETAS
    available = list_available_weeks()
    if not available:
        print("No hay semanas en capa1.")
        return

    if not check_capa1_monotonic(available):
        return

    # Una semana esta COMPLETA solo si el ETL ya avanzo a una semana POSTERIOR.
    # El ETL hace un "drain" final que escribe la semana en curso A MEDIAS, asi que
    # (max(height) <= written_through) NO basta: seria cierto para esa semana parcial
    # y el indexer la procesaria incompleta y luego la saltaria para siempre.
    capa1_week = state_capa1.get("last_written_week")
    capa1_week_int = week_to_int(capa1_week) if capa1_week else None
    if capa1_week:
        print(f"semana en curso del ETL: {capa1_week} (se excluye)")

    def week_is_complete(week):
        try:
            t = pq.read_table(
                os.path.join(CAPA1, "blocks", f"blocks_{week}.parquet"),
                columns=["height"],
            )
            if max(t["height"].to_pylist()) > written_through:
                return False          # fichero truncado respecto al state del ETL
            if capa1_week_int is not None and week_to_int(week) >= capa1_week_int:
                return False          # semana en curso del ETL (posiblemente parcial)
            return True
        except Exception:
            return False

    available_complete = [w for w in available if week_is_complete(w)]
    print(f"Semanas disponibles: {len(available)}")
    print(f"Semanas completas:   {len(available_complete)}")

    # El progreso real vive en la tabla weeks_done de la DB (se filtra mas abajo,
    # tras abrirla). last_week / state_indexer.json queda como informacion.
    to_process = available_complete

    if not to_process:
        print("No hay semanas nuevas para procesar.")
        return

    print(f"Semanas a procesar: {len(to_process)} (de {to_process[0]} a {to_process[-1]})")
    logger.info(f"Procesando {len(to_process)} semanas")

    con = open_db()

    # ---- P3: abortar si last_week is None con DB no vacía ----
    done_weeks = {r[0] for r in con.execute("SELECT week FROM weeks_done")}
    if done_weeks:
        # F7: los parquet anuales son DERIVADOS de la DB, asi que se reconstruyen enteros
        # al arrancar. Eso repara por si solo un corte anterior entre el commit y la
        # escritura del parquet; la guarda que va despues comprueba que la reconstruccion
        # ha cubierto todas las semanas de weeks_done.
        n_anios = rebuild_all_from_db(con)
        logger.info(f"parquet anual reconstruido desde la DB ({n_anios} anios)")
        faltan = check_parquet_cobertura(done_weeks)
        if faltan:
            for w, ds in faltan[:5]:
                logger.error(f"agregados ausentes para {w}: {len(ds)} dias (p.ej. {ds[:3]})")
            print("\nERROR: hay semanas en weeks_done SIN sus agregados en el parquet anual.")
            print("Causa conocida (F7): corte entre el commit y la escritura del parquet.")
            print("NO continuar con esos dias sin reparar. Ver AUDITORIA_HALLAZGOS.md (F7).")
            con.close()
            return
    if not done_weeks:
        real_count = db_count(con)
        if real_count > 0:
            logger.error(f"DB tiene {real_count:,} UTXOs pero el state dice last_week=None.")
            print(f"\nERROR: DB tiene {real_count:,} UTXOs pero el state no.")
            print("Abortando para evitar corrupción.")
            print("Para empezar de cero:")
            print("  python3 indexer.py  # opción 1 (reset)")
            return
        utxo_count = 0
    else:
        utxo_count = con.execute(
            "SELECT COALESCE(SUM(n_inserted),0) - COALESCE(SUM(n_spent),0) FROM weeks_done"
        ).fetchone()[0]
        print(f"Semanas ya indexadas: {len(done_weeks)} (ultima: {max(done_weeks)}) | "
              f"UTXOs vivos: {utxo_count:,}")
        to_process = [w for w in to_process if w not in done_weeks]
        if not to_process:
            print("No hay semanas nuevas para procesar.")
            con.close()
            return

    t0 = time.time()
    for i, week in enumerate(to_process):
        t_start = time.time()
        try:
            result = process_week(con, week, utxo_count)
        except Exception as e:
            logger.error(f"Error procesando {week}: {e}", exc_info=True)
            print(f"\nError procesando {week}: {e}")
            save_state(state)
            con.close()
            return

        if result is None:
            logger.warning(f"  Semana {week} sin datos, saltando")
            state["last_processed_week"] = week
            save_state(state)
            continue

        utxo_count = result["utxo_count"]

        # Los agregados ya estan en la DB (misma transaccion); aqui solo se reescriben
        # enteros los ficheros anuales de los años que toca esta semana.
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
    print("\nIndexer completado correctamente.")
    logger.info("Indexer completado correctamente.")

if __name__ == "__main__":
    main()