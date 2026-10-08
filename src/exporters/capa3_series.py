#!/usr/bin/env python3
"""capa3 — The 23 OBM v0.1.0 series.

Sources : capa1/blocks  +  capa2/daily_aggregates  +  capa2/age_band_aggregates
Output  : capa3/obm_<serie>_daily.csv   (exact OBM schema)

Schema : date,series_id,value,unit,frequency,release_version
The 2 age-band tables are WIDE: date,series_id + 12 columns + unit,frequency,release_version.

Decisions (validated against the official reference):
  * issuance = coinbase - fees  (REALIZED issuance, not the protocol subsidy) -> capa2
  * raw_output_value = spent_value - fees   (exact indexer identity)
  * difficulty = Core float64 derived from bits -> Decimal(repr(...)) with 12 decimals
  * Decimal (prec 60) everywhere; 8 decimals for BTC/BTC-days, 12 for ratios/difficulty/hashrate, integers for counts
  * 1 row per UTC day since 2009-01-01, no gaps; NaN (empty) where OBM publishes no value

Usage:  python3 /media/SSD4T/obm/src/exporters/capa3_series.py [--no-bip30]
      --no-bip30 -> publishes the "real" UTXO set (without the compatibility adjustment)
"""
import datetime
import glob
import os
import sys
from decimal import Decimal, getcontext, ROUND_HALF_EVEN

import pyarrow.parquet as pq

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bitcoin_math import difficulty_core

getcontext().prec = 60

OBM = "/media/SSD4T/obm"
CAPA1 = os.path.join(OBM, "capa1")
CAPA2 = os.path.join(OBM, "capa2")
CAPA3 = os.path.join(OBM, "capa3")
VERSION = "OBM v0.1.0"
SATS = Decimal(10 ** 8)
SECONDS_PER_DAY = Decimal(86400)
TWO32 = Decimal(2) ** 32
E18 = Decimal(10) ** 18
START = datetime.date(2009, 1, 1)
BANDS = ["0d_1d", "1d_1w", "1w_1m", "1m_3m", "3m_6m", "6m_1y",
          "1y_2y", "2y_3y", "3y_5y", "5y_7y", "7y_10y", "10y_plus"]

# --- OBM compatibility adjustment for BIP30 -----------------------------------
# OBM counts BOTH copies of the two duplicated 2010 coinbases (txid
# d5d27987...:0 at heights 91812/91842 and e3bf3d07...:0 at 91722/91880),
# while live_outputs deduplicates by (txid, vout) just like Bitcoin Core.
# Measured effect: the official series is +1 from 2010-11-14 and +2 from 2010-11-15.
# It is applied ONLY in capa3 (capa2 keeps the real UTXO set). --no-bip30 disables it.
BIP30_D1 = datetime.date(2010, 11, 14)
BIP30_D2 = datetime.date(2010, 11, 15)


def bip30_adjustment(f, enabled=True):
    if not enabled:
        return 0
    if f >= BIP30_D2:
        return 2
    if f >= BIP30_D1:
        return 1
    return 0


# ------------------------- OBM formatters -------------------------
def fmt_int(x):
    return "NaN" if x is None else str(int(x))


def _q(x, dec):
    if x is None:
        return "NaN"
    return f"{Decimal(x).quantize(Decimal(1).scaleb(-dec), rounding=ROUND_HALF_EVEN):.{dec}f}"


def btc(sats, dec=8):                      # satoshis -> BTC
    return "NaN" if sats is None else _q(Decimal(int(sats)) / SATS, dec)


def btc_days(sat_days, dec=8):             # SATOSHI-DAYS (capa2) -> BTC-days
    return "NaN" if sat_days is None else _q(Decimal(int(sat_days)) / SATS, dec)


def ratio(a, b, dec=12):
    if a is None or b is None or Decimal(b) == 0:
        return "NaN"
    return _q(Decimal(a) / Decimal(b), dec)


def write_series(series_id, rows, unit):
    with open(f"{CAPA3}/{series_id}.csv", "w", newline="") as fh:
        fh.write("date,series_id,value,unit,frequency,release_version\n")
        for f, v in rows:
            fh.write(f"{f},{series_id},{v},{unit},daily,{VERSION}\n")
    print(f"  {series_id:<44} {len(rows):>6} rows  [{unit}]")


def write_wide(series_id, rows, cols, unit):
    with open(f"{CAPA3}/{series_id}.csv", "w", newline="") as fh:
        fh.write(",".join(["date", "series_id"] + cols + ["unit", "frequency", "release_version"]) + "\n")
        for f, vals in rows:
            fh.write(",".join([str(f), series_id] + vals + [unit, "daily", VERSION]) + "\n")
    print(f"  {series_id:<44} {len(rows):>6} rows  [{unit}] wide {len(cols)} col")


# ------------------------------ reads ------------------------------
def load_capa2_daily():
    days = {}
    for f in sorted(glob.glob(f"{CAPA2}/daily_aggregates_*.parquet")):
        t = pq.read_table(f).to_pydict()
        for i, d in enumerate(t["date"]):
            days[datetime.date.fromisoformat(str(d))] = {k: t[k][i] for k in t}
    return days


def load_capa2_bands():
    out = {}
    for f in sorted(glob.glob(f"{CAPA2}/age_band_aggregates_*.parquet")):
        t = pq.read_table(f).to_pydict()
        rem = t.get("cdd_rem_86400") or [0] * len(t["date"])
        for i in range(len(t["date"])):
            out.setdefault(datetime.date.fromisoformat(str(t["date"][i])), {})[t["age_band"][i]] = (
                int(t["spent_value_sats"][i]), int(t["cdd_sat_days"][i]), int(rem[i] or 0))
    return out


def load_difficulty_epochs():
    """EXACT Core difficulty per 2016-block epoch, read from the RPC field.

    OBM reads 'difficulty' from getblock (Appendix A.6); recomputing it from 'bits' differs
    by 1 float64 ULP on ~40% of the days. See src/exporters/fix_difficulty_rpc.py.
    """
    p = f"{CAPA1}/difficulty_epochs.parquet"
    if not os.path.exists(p):
        return {}
    t = pq.read_table(p, columns=["epoch", "difficulty"]).to_pydict()
    return {int(k): Decimal(repr(v)) for k, v in zip(t["epoch"], t["difficulty"])}


def load_capa1_blocks():
    """Per UTC day: n, Sum(nTx), Sum(weight), Sum(difficulty), tmin/tmax,
    and difficulty of the HIGHEST block (difficulty_eod)."""
    by_day = {}
    dif_ep = load_difficulty_epochs()
    missing_epochs = set()
    for f in sorted(glob.glob(f"{CAPA1}/blocks/blocks_*.parquet")):
        t = pq.read_table(f, columns=["height", "time", "nTx", "weight", "bits"]).to_pydict()
        for h, ts, ntx, w, bits in zip(t["height"], t["time"], t["nTx"], t["weight"], t["bits"]):
            ts = int(ts)
            d = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).date()
            r = by_day.get(d)
            _e = int(h) // 2016
            if _e in dif_ep:
                df = dif_ep[_e]
            else:
                # F3: difficulty is READ from the node; recomputing it from bits differs by 1 ULP.
                # A missing epoch means difficulty_epochs.parquet fell behind.
                df = Decimal(repr(difficulty_core(bits)))
                if _e not in missing_epochs:
                    missing_epochs.add(_e)
                    print(f"WARNING: missing difficulty epoch {_e} in difficulty_epochs.parquet "
                          f"(height {int(h)}); difficulty_core(bits) is used, which F3 forbids. "
                          f"Rerun src/exporters/fix_difficulty_rpc.py with the node running.")
            if r is None:
                by_day[d] = {"n": 1, "ntx": int(ntx or 0), "w": int(w or 0), "diff": df,
                              "tmin": ts, "tmax": ts, "hmax": int(h), "deod": df}
            else:
                r["n"] += 1
                r["ntx"] += int(ntx or 0)
                r["w"] += int(w or 0)
                r["diff"] += df
                r["tmin"] = min(r["tmin"], ts)
                r["tmax"] = max(r["tmax"], ts)
                if int(h) > r["hmax"]:
                    r["hmax"] = int(h)
                    r["deod"] = df
    return by_day


# -------------------------------- main --------------------------------
def main():
    BIP30 = "--no-bip30" not in sys.argv
    os.makedirs(CAPA3, exist_ok=True)
    print(f"=== capa3 — 23 OBM v0.1.0 series ===  (BIP30 adjustment: {'ON' if BIP30 else 'OFF'})")
    d2 = load_capa2_daily()
    bands = load_capa2_bands()
    b1 = load_capa1_blocks()
    if not d2:
        sys.exit("ERROR: capa2/daily_aggregates_*.parquet is empty")
    if not b1:
        sys.exit("ERROR: capa1/blocks is empty")
    first_day = min(b1)
    last_day = max(list(d2) + list(b1))
    cal, f = [], START
    while f <= last_day:
        cal.append(f)
        f += datetime.timedelta(days=1)
    since = [f for f in cal if f >= first_day]
    idx = {f: i for i, f in enumerate(cal)}
    print(f"capa2: {len(d2)} days | capa1: {len(b1)} days with blocks | "
          f"calendar {cal[0]}..{cal[-1]} ({len(cal)} days) | first block {first_day}\n")

    def V(f, k):
        r = d2.get(f)
        return None if r is None else int(r[k])

    def CDD_SAT(f):
        """EXACT CDD in sat-days (Decimal) = cdd_sat_days + cdd_rem_86400/86400."""
        r = d2.get(f)
        if r is None:
            return None
        return (Decimal(int(r.get("cdd_sat_days") or 0))
                + Decimal(int(r.get("cdd_rem_86400") or 0)) / SECONDS_PER_DAY)

    def CDD_BTC(f):
        x = CDD_SAT(f)
        return None if x is None else x / SATS

    # ---- 1-5: from capa1/blocks ----
    write_series("obm_block_count_daily", [(f, fmt_int(b1[f]["n"] if f in b1 else 0)) for f in cal], "blocks")
    write_series("obm_tx_count_daily", [(f, fmt_int(b1[f]["ntx"] if f in b1 else 0)) for f in cal], "transactions")
    write_series("obm_block_weight_wu_daily", [(f, fmt_int(b1[f]["w"] if f in b1 else 0)) for f in since], "WU")
    write_series("obm_difficulty_eod_daily",
             [(f, _q(b1[f]["deod"], 12) if f in b1 else "NaN") for f in since], "difficulty")
    hr = []
    for f in since:
        i = idx[f]
        window = [cal[j] for j in range(max(0, i - 6), i + 1) if cal[j] in b1]
        if not window:
            hr.append((f, "NaN")); continue
        dsum = sum((b1[x]["diff"] for x in window), Decimal(0))
        tmin = min(b1[x]["tmin"] for x in window)
        tmax = max(b1[x]["tmax"] for x in window)
        if tmax - tmin <= 0:
            hr.append((f, "NaN")); continue
        hr.append((f, _q((dsum * TWO32) / Decimal(tmax - tmin) / E18, 12)))
    write_series("obm_est7d_hashrate_ehs_daily", hr, "EH/s")

    # ---- 6-10: issuance / fees / revenue / fee share / supply ----
    write_series("obm_issuance_btc_daily", [(f, btc(V(f, "issuance_sats")) if f in d2 else btc(0)) for f in cal], "BTC")
    write_series("obm_fees_btc_daily", [(f, btc(V(f, "fees_sats")) if f in d2 else btc(0)) for f in cal], "BTC")
    write_series("obm_miner_revenue_btc_daily",
             [(f, btc(V(f, "coinbase_output_sats")) if f in d2 else btc(0)) for f in cal], "BTC")
    # fee_share = fees/coinbase; with no coinbase (day without blocks) the field is EMPTY
    write_series("obm_fee_share_revenue_ratio_daily",
             [(f, "" if (not f in d2 or not V(f, "coinbase_output_sats"))
               else ratio(V(f, "fees_sats"), V(f, "coinbase_output_sats"))) for f in cal], "ratio")
    accum, rows = Decimal(0), []
    for f in cal:
        accum += Decimal(btc(V(f, "issuance_sats")) if f in d2 else "0")
        rows.append((f, _q(accum, 8)))
    write_series("obm_supply_btc_daily", rows, "BTC")
    supply_by_day = dict(rows)                      # date -> supply in BTC (str, 8 dec)

    # ---- 11-21: UTXO and coin-age ----
    write_series("obm_raw_output_value_btc_daily",
             [(f, btc(V(f, "spent_value_sats") - V(f, "fees_sats")) if f in d2 else btc(0)) for f in since], "BTC")
    write_series("obm_spent_output_count_daily",
             [(f, fmt_int(V(f, "spent_output_count")) if f in d2 else "0") for f in cal], "outputs")
    write_series("obm_spent_value_btc_daily",
             [(f, btc(V(f, "spent_value_sats")) if f in d2 else btc(0)) for f in cal], "BTC")
    write_series("obm_cdd_btcxdays_daily",
             [(f, _q(CDD_BTC(f), 8) if f in d2 else btc_days(0)) for f in since], "BTC-days")
    # dormancy = CDD/spent_value in DAYS -> sat-days / satoshis (same units)
    write_series("obm_dormancy_days_daily",
             [(f, ratio(CDD_SAT(f), V(f, "spent_value_sats")) if f in d2 else "NaN")
              for f in cal], "days")
    write_series("obm_cdd_per_supply_days_daily",
             [(f, ratio(CDD_BTC(f) if f in d2 else Decimal(0), supply_by_day[f])
               if Decimal(supply_by_day[f]) != 0 else "NaN") for f in since], "days")
    write_series("obm_spent_value_ge155d_btc_daily",
             [(f, btc(V(f, "spent_value_ge155d_sats")) if f in d2 else btc(0)) for f in cal], "BTC")
    write_series("obm_spent_value_ge365d_btc_daily",
             [(f, btc(V(f, "spent_value_ge365d_sats")) if f in d2 else btc(0)) for f in cal], "BTC")
    rows = []
    for f in cal:
        if f in d2:
            dif = V(f, "spent_value_sats") - V(f, "spent_value_ge155d_sats")
            rows.append((f, "0" if abs(dif) < 1000 else btc(dif)))
        else:
            rows.append((f, "0"))
    write_series("obm_spent_value_lt155d_btc_daily", rows, "BTC")
    # OBM publishes NaN on days without blocks, no forward-fill
    write_series("obm_utxo_eod_count_daily",
             [(f, fmt_int(V(f, "utxo_eod_count") + bip30_adjustment(f, BIP30)) if f in d2 else "NaN")
              for f in since], "outputs")
    # liveliness = cumsum(CDD) / cumsum(supply), accumulated since the first block
    accum_cdd, accum_supply, rows = Decimal(0), Decimal(0), []
    for f in since:
        if f in d2:
            accum_cdd += CDD_BTC(f)
        accum_supply += Decimal(supply_by_day[f])
        rows.append((f, ratio(accum_cdd, accum_supply)))
    write_series("obm_liveliness_ratio_daily", rows, "ratio")

    # ---- 22-23: wide age-band tables ----
    write_wide("obm_spent_value_age_band_btc_daily",
                   [(f, [btc(bands[f][b][0]) if (f in bands and b in bands[f]) else btc(0) for b in BANDS])
                    for f in cal], [f"spent_value_{b}_btc" for b in BANDS], "BTC")
    write_wide("obm_cdd_age_band_btcxdays_daily",
                   [(f, [_q((Decimal(bands[f][b][1]) + Decimal(bands[f][b][2]) / SECONDS_PER_DAY) / SATS, 12)
                         if (f in bands and b in bands[f]) else btc_days(0, 12)
                         for b in BANDS]) for f in cal],
                   [f"cdd_{b}_btcxdays" for b in BANDS], "BTC-days")


if __name__ == "__main__":
    main()
