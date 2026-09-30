#!/usr/bin/env python3
"""capa3 — Las 23 series de OBM v0.1.0.

Fuentes : capa1/blocks  +  capa2/daily_aggregates  +  capa2/age_band_aggregates
Salida  : capa3/obm_<serie>_daily.csv   (esquema OBM exacto)

Esquema : date,series_id,value,unit,frequency,release_version
Las 2 tablas de bandas de edad son ANCHAS: date,series_id + 12 columnas + unit,frequency,release_version.

Decisiones (validadas contra la referencia oficial):
  * issuance = coinbase - fees  (emision REALIZADA, no subsidio de protocolo) -> capa2
  * raw_output_value = spent_value - fees   (identidad exacta del indexer)
  * difficulty = float64 de Core derivada de bits -> Decimal(repr(...)) con 12 decimales
  * Decimal (prec 60) en todo; 8 decimales BTC/BTC-days, 12 ratios/difficulty/hashrate, enteros en conteos
  * 1 fila por dia UTC desde 2009-01-01, sin huecos; NaN (vacio) donde OBM no publica valor

Uso:  python3 /media/SSD4T/obm/src/exporters/capa3_series.py [--no-bip30]
      --no-bip30 -> publica el UTXO set "real" (sin el ajuste de compatibilidad)
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
SEG_DIA = Decimal(86400)
DOS32 = Decimal(2) ** 32
E18 = Decimal(10) ** 18
INICIO = datetime.date(2009, 1, 1)
BANDAS = ["0d_1d", "1d_1w", "1w_1m", "1m_3m", "3m_6m", "6m_1y",
          "1y_2y", "2y_3y", "3y_5y", "5y_7y", "7y_10y", "10y_plus"]

# --- Ajuste de compatibilidad OBM por BIP30 ----------------------------------
# OBM cuenta las DOS copias de los dos coinbases duplicados de 2010 (txid
# d5d27987...:0 en las alturas 91812/91842 y e3bf3d07...:0 en 91722/91880),
# mientras que live_outputs deduplica por (txid, vout) igual que Bitcoin Core.
# Efecto medido: la serie oficial va +1 desde 2010-11-14 y +2 desde 2010-11-15.
# Se aplica SOLO en capa3 (capa2 conserva el UTXO set real). --no-bip30 lo desactiva.
BIP30_D1 = datetime.date(2010, 11, 14)
BIP30_D2 = datetime.date(2010, 11, 15)


def ajuste_bip30(f, activo=True):
    if not activo:
        return 0
    if f >= BIP30_D2:
        return 2
    if f >= BIP30_D1:
        return 1
    return 0


# ------------------------- formateadores OBM -------------------------
def ent(x):
    return "NaN" if x is None else str(int(x))


def _q(x, dec):
    if x is None:
        return "NaN"
    return f"{Decimal(x).quantize(Decimal(1).scaleb(-dec), rounding=ROUND_HALF_EVEN):.{dec}f}"


def btc(sats, dec=8):                      # satoshis -> BTC
    return "NaN" if sats is None else _q(Decimal(int(sats)) / SATS, dec)


def btc_dias(sat_dias, dec=8):             # SATOSHI-DIAS (capa2) -> BTC-dias
    return "NaN" if sat_dias is None else _q(Decimal(int(sat_dias)) / SATS, dec)


def ratio(a, b, dec=12):
    if a is None or b is None or Decimal(b) == 0:
        return "NaN"
    return _q(Decimal(a) / Decimal(b), dec)


def escribir(serie, filas, unidad):
    with open(f"{CAPA3}/{serie}.csv", "w", newline="") as fh:
        fh.write("date,series_id,value,unit,frequency,release_version\n")
        for f, v in filas:
            fh.write(f"{f},{serie},{v},{unidad},daily,{VERSION}\n")
    print(f"  {serie:<44} {len(filas):>6} filas  [{unidad}]")


def escribir_ancha(serie, filas, cols, unidad):
    with open(f"{CAPA3}/{serie}.csv", "w", newline="") as fh:
        fh.write(",".join(["date", "series_id"] + cols + ["unit", "frequency", "release_version"]) + "\n")
        for f, vals in filas:
            fh.write(",".join([str(f), serie] + vals + [unidad, "daily", VERSION]) + "\n")
    print(f"  {serie:<44} {len(filas):>6} filas  [{unidad}] ancha {len(cols)} col")


# ------------------------------ lecturas ------------------------------
def cargar_capa2_diario():
    dias = {}
    for f in sorted(glob.glob(f"{CAPA2}/daily_aggregates_*.parquet")):
        t = pq.read_table(f).to_pydict()
        for i, d in enumerate(t["date"]):
            dias[datetime.date.fromisoformat(str(d))] = {k: t[k][i] for k in t}
    return dias


def cargar_capa2_bandas():
    out = {}
    for f in sorted(glob.glob(f"{CAPA2}/age_band_aggregates_*.parquet")):
        t = pq.read_table(f).to_pydict()
        rem = t.get("cdd_rem_86400") or [0] * len(t["date"])
        for i in range(len(t["date"])):
            out.setdefault(datetime.date.fromisoformat(str(t["date"][i])), {})[t["age_band"][i]] = (
                int(t["spent_value_sats"][i]), int(t["cdd_sat_days"][i]), int(rem[i] or 0))
    return out


def cargar_difficulty_epochs():
    """Dificultad EXACTA de Core por epoca de 2016 bloques, leida del campo del RPC.

    OBM lee 'difficulty' de getblock (Apéndice A.6); recalcularla desde 'bits' difiere
    en 1 ULP de float64 en ~40% de los dias. Ver src/exporters/fix_difficulty_rpc.py.
    """
    p = f"{CAPA1}/difficulty_epochs.parquet"
    if not os.path.exists(p):
        return {}
    t = pq.read_table(p, columns=["epoch", "difficulty"]).to_pydict()
    return {int(k): Decimal(repr(v)) for k, v in zip(t["epoch"], t["difficulty"])}


def cargar_capa1_bloques():
    """Por dia UTC: n, Sum(nTx), Sum(weight), Sum(difficulty), tmin/tmax,
    y difficulty del bloque de MAYOR ALTURA (difficulty_eod)."""
    por_dia = {}
    dif_ep = cargar_difficulty_epochs()
    for f in sorted(glob.glob(f"{CAPA1}/blocks/blocks_*.parquet")):
        t = pq.read_table(f, columns=["height", "time", "nTx", "weight", "bits"]).to_pydict()
        for h, ts, ntx, w, bits in zip(t["height"], t["time"], t["nTx"], t["weight"], t["bits"]):
            ts = int(ts)
            d = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).date()
            r = por_dia.get(d)
            _e = int(h) // 2016
            df = dif_ep[_e] if _e in dif_ep else Decimal(repr(difficulty_core(bits)))
            if r is None:
                por_dia[d] = {"n": 1, "ntx": int(ntx or 0), "w": int(w or 0), "diff": df,
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
    return por_dia


# -------------------------------- main --------------------------------
def main():
    BIP30 = "--no-bip30" not in sys.argv
    os.makedirs(CAPA3, exist_ok=True)
    print(f"=== capa3 — 23 series OBM v0.1.0 ===  (ajuste BIP30: {'ON' if BIP30 else 'OFF'})")
    d2 = cargar_capa2_diario()
    bandas = cargar_capa2_bandas()
    b1 = cargar_capa1_bloques()
    if not d2:
        sys.exit("ERROR: capa2/daily_aggregates_*.parquet vacio")
    if not b1:
        sys.exit("ERROR: capa1/blocks vacio")
    primer = min(b1)
    ultimo = max(list(d2) + list(b1))
    cal, f = [], INICIO
    while f <= ultimo:
        cal.append(f)
        f += datetime.timedelta(days=1)
    desde = [f for f in cal if f >= primer]
    idx = {f: i for i, f in enumerate(cal)}
    print(f"capa2: {len(d2)} dias | capa1: {len(b1)} dias con bloque | "
          f"calendario {cal[0]}..{cal[-1]} ({len(cal)} dias) | primer bloque {primer}\n")

    def V(f, k):
        r = d2.get(f)
        return None if r is None else int(r[k])

    def CDD_SAT(f):
        """CDD EXACTO en sat-dias (Decimal) = cdd_sat_days + cdd_rem_86400/86400."""
        r = d2.get(f)
        if r is None:
            return None
        return (Decimal(int(r.get("cdd_sat_days") or 0))
                + Decimal(int(r.get("cdd_rem_86400") or 0)) / SEG_DIA)

    def CDD_BTC(f):
        x = CDD_SAT(f)
        return None if x is None else x / SATS

    # ---- 1-5: de capa1/blocks ----
    escribir("obm_block_count_daily", [(f, ent(b1[f]["n"] if f in b1 else 0)) for f in cal], "blocks")
    escribir("obm_tx_count_daily", [(f, ent(b1[f]["ntx"] if f in b1 else 0)) for f in cal], "transactions")
    escribir("obm_block_weight_wu_daily", [(f, ent(b1[f]["w"] if f in b1 else 0)) for f in desde], "WU")
    escribir("obm_difficulty_eod_daily",
             [(f, _q(b1[f]["deod"], 12) if f in b1 else "NaN") for f in desde], "difficulty")
    hr = []
    for f in desde:
        i = idx[f]
        ventana = [cal[j] for j in range(max(0, i - 6), i + 1) if cal[j] in b1]
        if not ventana:
            hr.append((f, "NaN")); continue
        dsum = sum((b1[x]["diff"] for x in ventana), Decimal(0))
        tmin = min(b1[x]["tmin"] for x in ventana)
        tmax = max(b1[x]["tmax"] for x in ventana)
        if tmax - tmin <= 0:
            hr.append((f, "NaN")); continue
        hr.append((f, _q((dsum * DOS32) / Decimal(tmax - tmin) / E18, 12)))
    escribir("obm_est7d_hashrate_ehs_daily", hr, "EH/s")

    # ---- 6-10: emision / comisiones / revenue / fee share / oferta ----
    escribir("obm_issuance_btc_daily", [(f, btc(V(f, "issuance_sats")) if f in d2 else btc(0)) for f in cal], "BTC")
    escribir("obm_fees_btc_daily", [(f, btc(V(f, "fees_sats")) if f in d2 else btc(0)) for f in cal], "BTC")
    escribir("obm_miner_revenue_btc_daily",
             [(f, btc(V(f, "coinbase_output_sats")) if f in d2 else btc(0)) for f in cal], "BTC")
    # fee_share = fees/coinbase; sin coinbase (dia sin bloque) el campo va VACIO
    escribir("obm_fee_share_revenue_ratio_daily",
             [(f, "" if (not f in d2 or not V(f, "coinbase_output_sats"))
               else ratio(V(f, "fees_sats"), V(f, "coinbase_output_sats"))) for f in cal], "ratio")
    acum, filas = Decimal(0), []
    for f in cal:
        acum += Decimal(btc(V(f, "issuance_sats")) if f in d2 else "0")
        filas.append((f, _q(acum, 8)))
    escribir("obm_supply_btc_daily", filas, "BTC")
    sup_dia = dict(filas)                      # date -> oferta en BTC (str, 8 dec)

    # ---- 11-21: UTXO y coin-age ----
    escribir("obm_raw_output_value_btc_daily",
             [(f, btc(V(f, "spent_value_sats") - V(f, "fees_sats")) if f in d2 else btc(0)) for f in desde], "BTC")
    escribir("obm_spent_output_count_daily",
             [(f, ent(V(f, "spent_output_count")) if f in d2 else "0") for f in cal], "outputs")
    escribir("obm_spent_value_btc_daily",
             [(f, btc(V(f, "spent_value_sats")) if f in d2 else btc(0)) for f in cal], "BTC")
    escribir("obm_cdd_btcxdays_daily",
             [(f, _q(CDD_BTC(f), 8) if f in d2 else btc_dias(0)) for f in desde], "BTC-days")
    # dormancy = CDD/spent_value en DIAS -> sat-dias / satoshis (mismas unidades)
    escribir("obm_dormancy_days_daily",
             [(f, ratio(CDD_SAT(f), V(f, "spent_value_sats")) if f in d2 else "NaN")
              for f in cal], "days")
    escribir("obm_cdd_per_supply_days_daily",
             [(f, ratio(CDD_BTC(f) if f in d2 else Decimal(0), sup_dia[f])
               if Decimal(sup_dia[f]) != 0 else "NaN") for f in desde], "days")
    escribir("obm_spent_value_ge155d_btc_daily",
             [(f, btc(V(f, "spent_value_ge155d_sats")) if f in d2 else btc(0)) for f in cal], "BTC")
    escribir("obm_spent_value_ge365d_btc_daily",
             [(f, btc(V(f, "spent_value_ge365d_sats")) if f in d2 else btc(0)) for f in cal], "BTC")
    filas = []
    for f in cal:
        if f in d2:
            dif = V(f, "spent_value_sats") - V(f, "spent_value_ge155d_sats")
            filas.append((f, "0" if abs(dif) < 1000 else btc(dif)))
        else:
            filas.append((f, "0"))
    escribir("obm_spent_value_lt155d_btc_daily", filas, "BTC")
    # OBM publica NaN en los dias sin bloque, no forward-fill
    escribir("obm_utxo_eod_count_daily",
             [(f, ent(V(f, "utxo_eod_count") + ajuste_bip30(f, BIP30)) if f in d2 else "NaN")
              for f in desde], "outputs")
    # liveliness = cumsum(CDD) / cumsum(oferta), acumulado desde el primer bloque
    acum_cdd, acum_sup, filas = Decimal(0), Decimal(0), []
    for f in desde:
        if f in d2:
            acum_cdd += CDD_BTC(f)
        acum_sup += Decimal(sup_dia[f])
        filas.append((f, ratio(acum_cdd, acum_sup)))
    escribir("obm_liveliness_ratio_daily", filas, "ratio")

    # ---- 22-23: tablas anchas de bandas de edad ----
    escribir_ancha("obm_spent_value_age_band_btc_daily",
                   [(f, [btc(bandas[f][b][0]) if (f in bandas and b in bandas[f]) else btc(0) for b in BANDAS])
                    for f in cal], [f"spent_value_{b}_btc" for b in BANDAS], "BTC")
    escribir_ancha("obm_cdd_age_band_btcxdays_daily",
                   [(f, [_q((Decimal(bandas[f][b][1]) + Decimal(bandas[f][b][2]) / SEG_DIA) / SATS, 12)
                         if (f in bandas and b in bandas[f]) else btc_dias(0, 12)
                         for b in BANDAS]) for f in cal],
                   [f"cdd_{b}_btcxdays" for b in BANDAS], "BTC-days")


if __name__ == "__main__":
    main()
