#!/usr/bin/env python3
"""Repara los agregados de 2022-W06 en capa2 (perdidos por la ventana de crash F7).

Recomputa EXACTAMENTE desde capa1 (no necesita el estado del UTXO):
  * resuelve cada prevout de la semana contra capa1/outputs (un escaneo global),
  * agrega por dia UTC: spent_value, count, cdd (exacto: entero + resto/86400),
    umbrales 155d/365d, fees, coinbase, issuance y las 12 bandas de edad,
  * utxo_eod_count(d) = eod(2022-02-06) + SUM(creados - gastados) hasta d.

Escribe en capa2/daily_aggregates_2022.parquet y age_band_aggregates_2022.parquet
(con backup .bak_w06). Idempotente: borra las fechas de la semana antes de insertar.
"""
import os
import shutil
import sys

import duckdb
import pandas as pd

BASE = "/media/SSD4T/obm"
C1, C2 = f"{BASE}/capa1", f"{BASE}/capa2"
SEM, ANIO = "2022-W06", "2022"
DIA0 = "2022-02-06"                      # ultimo dia con datos de W05 (baseline)
BANDAS = [("0d_1d", 0, 1), ("1d_1w", 1, 7), ("1w_1m", 7, 30), ("1m_3m", 30, 90),
          ("3m_6m", 90, 180), ("6m_1y", 180, 365), ("1y_2y", 365, 730),
          ("2y_3y", 730, 1095), ("3y_5y", 1095, 1825), ("5y_7y", 1825, 2555),
          ("7y_10y", 2555, 3650), ("10y_plus", 3650, 10**9)]
os.makedirs(f"{BASE}/tmp/repair", exist_ok=True)
con = duckdb.connect()
con.execute("SET threads=4")
con.execute("SET memory_limit='10GB'")
con.execute(f"SET temp_directory='{BASE}/tmp/repair'")
try:                                     # respetar el orden escrito -> hash sobre `inp` (6,5 M)
    con.execute("SET disabled_optimizers='join_order'")
except Exception as e:
    print(f"  aviso: no se pudo fijar el orden de join ({e})")

for t, sql in (
    ("inp", f"SELECT height,txid,prev_txid,prev_vout FROM read_parquet('{C1}/inputs/inputs_{SEM}.parquet') WHERE is_coinbase=false"),
    ("inp_cb", f"SELECT DISTINCT height,txid FROM read_parquet('{C1}/inputs/inputs_{SEM}.parquet') WHERE is_coinbase=true"),
    ("outw", f"SELECT height,txid,vout,value_sats,script_type,script_hex FROM read_parquet('{C1}/outputs/outputs_{SEM}.parquet')"),
    ("blk", f"SELECT height,time FROM read_parquet('{C1}/blocks/blocks_*.parquet')"),
):
    con.execute(f"CREATE TABLE {t} AS {sql}")
print("  tablas de la semana cargadas")

JOIN = f"""
FROM read_parquet('{C1}/outputs/outputs_*.parquet') o
JOIN inp i  ON o.txid = i.prev_txid AND o.vout = i.prev_vout
JOIN blk bs ON bs.height = i.height
JOIN blk bc ON bc.height = o.height
"""
print("  plan del join (debe construir hash sobre 'inp', NO escanear+hashear 3.900 M filas):")
for r in con.execute("EXPLAIN SELECT count(*) " + JOIN).fetchall():
    for ln in str(r[-1]).splitlines():
        if any(k in ln for k in ("JOIN", "SCAN", "HASH", "inp", "read_parquet")):
            print("    " + ln.strip()[:110])

con.execute(f"""CREATE TABLE res AS SELECT
    i.height h_spend, i.txid tx_spend, o.value_sats, o.height h_create,
    i.prev_txid, i.prev_vout, bs.time t_spend, bc.time t_create,
    GREATEST(0, bs.time - bc.time) age {JOIN}""")
n = con.execute("SELECT count(*) FROM res").fetchone()[0]
tot = con.execute("SELECT count(*) FROM inp").fetchone()[0]
print(f"  prevouts resueltos: {n:,} / {tot:,}  ({'OK' if n==tot else 'FALTAN ' + format(tot-n, ',')})")
if n != tot:
    sys.exit("ABORTADO: no se resolvieron todos los inputs; no se escribe nada")

# ---- agregado diario ----
dia = con.execute(f"""
SELECT strftime(to_timestamp(t_spend),'%Y-%m-%d') date,
       CAST(SUM(CAST(value_sats AS HUGEINT)*age/86400) AS BIGINT) cdd_sat_days,
       CAST(SUM(CAST(value_sats AS HUGEINT)*age % 86400) AS BIGINT) cdd_rem_86400,
       CAST(SUM(value_sats) AS BIGINT) spent_value_sats,
       COUNT(*) spent_output_count,
       CAST(SUM(CASE WHEN age>=155*86400 THEN value_sats ELSE 0 END) AS BIGINT) ge155_v,
       CAST(SUM(CASE WHEN age>=155*86400 THEN CAST(value_sats AS HUGEINT)*age/86400 ELSE 0 END) AS BIGINT) ge155_c,
       CAST(SUM(CASE WHEN age>=155*86400 THEN CAST(value_sats AS HUGEINT)*age % 86400 ELSE 0 END) AS BIGINT) ge155_r,
       CAST(SUM(CASE WHEN age>=365*86400 THEN value_sats ELSE 0 END) AS BIGINT) ge365_v,
       CAST(SUM(CASE WHEN age>=365*86400 THEN CAST(value_sats AS HUGEINT)*age/86400 ELSE 0 END) AS BIGINT) ge365_c,
       CAST(SUM(CASE WHEN age>=365*86400 THEN CAST(value_sats AS HUGEINT)*age % 86400 ELSE 0 END) AS BIGINT) ge365_r
FROM res GROUP BY 1 ORDER BY 1""").df()
b = con.execute("""
SELECT strftime(to_timestamp(b.time),'%Y-%m-%d') date,
       CAST(SUM(o.value_sats) AS BIGINT) out_all,
       CAST(SUM(CASE WHEN cb.txid IS NOT NULL THEN o.value_sats ELSE 0 END) AS BIGINT) cb_sats,
       CAST(SUM(CASE WHEN cb.txid IS NULL AND COALESCE(o.script_type,'')<>'nulldata'
                      AND NOT COALESCE(o.script_hex,'') LIKE '6a%'
                      AND length(COALESCE(o.script_hex,''))<=20000 THEN 1 ELSE 0 END) AS BIGINT) n_creados
FROM outw o JOIN blk b ON b.height=o.height
LEFT JOIN inp_cb cb ON cb.height=o.height AND cb.txid=o.txid
GROUP BY 1 ORDER BY 1""").df()
m = dia.merge(b, on="date", how="left")
base = int(pd.read_parquet(f"{C2}/daily_aggregates_{ANIO}.parquet")
           .query("date == @DIA0")["utxo_eod_count"].iloc[0])
m["fees_sats"] = m.spent_value_sats - (m.out_all - m.cb_sats)
m["coinbase_output_sats"] = m.cb_sats
m["issuance_sats"] = m.cb_sats - m.fees_sats
acum = base
eod = []
for _, r in m.iterrows():
    acum += int(r.n_creados) - int(r.spent_output_count)
    eod.append(acum)
m["utxo_eod_count"] = eod
m["last_height"] = [con.execute("SELECT max(h_spend) FROM res WHERE strftime(to_timestamp(t_spend),'%Y-%m-%d')=?",
                                [d]).fetchone()[0] for d in m.date]
COLS = ["date","last_height","spent_value_sats","spent_output_count","cdd_sat_days","cdd_rem_86400",
        "fees_sats","coinbase_output_sats","issuance_sats","utxo_eod_count","spent_value_ge155d_sats",
        "spent_value_ge365d_sats","cdd_ge155d_sat_days","cdd_ge155d_rem_86400",
        "cdd_ge365d_sat_days","cdd_ge365d_rem_86400"]
m = m.rename(columns={"ge155_v":"spent_value_ge155d_sats","ge155_c":"cdd_ge155d_sat_days",
                      "ge155_r":"cdd_ge155d_rem_86400","ge365_v":"spent_value_ge365d_sats",
                      "ge365_c":"cdd_ge365d_sat_days","ge365_r":"cdd_ge365d_rem_86400"})[COLS]
print("\n  filas recomputadas:"); print(m.to_string(index=False))

# ---- bandas ----
band = con.execute(f"""
SELECT strftime(to_timestamp(t_spend),'%Y-%m-%d') date,
       CAST(FLOOR(age/86400.0) AS INT) edad_dias,
       CAST(SUM(value_sats) AS BIGINT) sv, COUNT(*) n,
       CAST(SUM(CAST(value_sats AS HUGEINT)*age/86400) AS BIGINT) cq,
       CAST(SUM(CAST(value_sats AS HUGEINT)*age % 86400) AS BIGINT) cr
FROM res GROUP BY 1,2""").df()
filas = []
for _, r in band.iterrows():
    for nom, lo, hi in BANDAS:
        if lo <= r.edad_dias < hi:
            filas.append({"date": r.date, "age_band": nom, "spent_value_sats": r.sv,
                          "spent_output_count": r.n, "cdd_sat_days": r.cq, "cdd_rem_86400": r.cr})
            break
bd = pd.DataFrame(filas)
print(f"\n  filas de bandas: {len(bd)}")

# ---- escribir con backup ----
for ruta, nuevo, clave in ((f"{C2}/daily_aggregates_{ANIO}.parquet", m, ["date"]),
                           (f"{C2}/age_band_aggregates_{ANIO}.parquet", bd, ["date", "age_band"])):
    viejo = pd.read_parquet(ruta)
    viejo["date"] = viejo["date"].astype(str)
    shutil.copy2(ruta, ruta + ".bak_w06")
    limpio = viejo[~viejo["date"].isin(nuevo["date"])]
    out = pd.concat([limpio, nuevo], ignore_index=True).sort_values(clave).reset_index(drop=True)
    for c in viejo.columns:
        if c in out.columns:
            out[c] = out[c].astype(viejo[c].dtype)
    out.to_parquet(ruta + ".tmp", index=False, compression="zstd")
    os.replace(ruta + ".tmp", ruta)
    print(f"  {os.path.basename(ruta)}: {len(viejo)} -> {len(out)} filas (backup .bak_w06)")
con.close()
print("\nREPARADO")
