#!/usr/bin/env python3
"""Repara los agregados de 2022-W06 en capa2 (perdidos por la ventana de crash F7).

Recomputa EXACTAMENTE desde capa1 (no necesita el estado del UTXO):
  * resuelve cada prevout de la semana contra capa1/outputs (un escaneo global),
  * agrega por dia UTC: spent_value, count, cdd (exacto: entero + resto/86400),
    umbrales 155d/365d, fees, coinbase, issuance y las 12 bandas de edad,
  * utxo_eod_count(d) = eod(dia anterior) + SUM(creados - gastados) hasta d.

Tres precauciones, cada una por un bug real medido el 30-Sep-2026:
  1. SET TimeZone='UTC'. strftime(to_timestamp(t),'%Y-%m-%d') usa la zona de la
     sesion: con America/Guayaquil (UTC-5) cada dia UTC se corria 5 h y aparecia un
     dia fantasma al inicio de la semana (aqui: 2022-02-06 con 127.914 gastos).
  2. Solo se escriben los dias UTC que pertenecen a la semana, nunca el dia vecino.
  3. Las bandas se agregan por banda (GROUP BY date, age_band): 7 dias = 84 filas
     como maximo, no una fila por edad entera (17.069).

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
BANDAS = [("0d_1d", 0, 1), ("1d_1w", 1, 7), ("1w_1m", 7, 30), ("1m_3m", 30, 90),
          ("3m_6m", 90, 180), ("6m_1y", 180, 365), ("1y_2y", 365, 730),
          ("2y_3y", 730, 1095), ("3y_5y", 1095, 1825), ("5y_7y", 1825, 2555),
          ("7y_10y", 2555, 3650), ("10y_plus", 3650, 10**9)]
CASO_BANDA = "CASE " + " ".join(
    f"WHEN edad_dias >= {lo} AND edad_dias < {hi} THEN '{nom}'"
    for nom, lo, hi in BANDAS) + " END"

os.makedirs(f"{BASE}/tmp/repair", exist_ok=True)
con = duckdb.connect()
con.execute("SET threads=4")
con.execute("SET memory_limit='10GB'")
con.execute(f"SET temp_directory='{BASE}/tmp/repair'")
con.execute("SET TimeZone='UTC'")            # (1) fechas en UTC, como OBM
try:                                         # hash sobre `inp` (6,5 M), no 3.900 M
    con.execute("SET disabled_optimizers='join_order'")
except Exception as e:
    print(f"  aviso: no se pudo fijar el orden de join ({e})")

# (2) dias UTC de la semana, segun los propios bloques de capa1
DIAS = [r[0] for r in con.execute(
    f"SELECT DISTINCT strftime(to_timestamp(time),'%Y-%m-%d') d "
    f"FROM read_parquet('{C1}/blocks/blocks_{SEM}.parquet') ORDER BY 1").fetchall()]
FILTRO = "(" + ",".join(f"'{d}'" for d in DIAS) + ")"
print(f"  dias UTC de {SEM}: {DIAS[0]} .. {DIAS[-1]}  ({len(DIAS)} dias)")
if len(DIAS) != 7:
    sys.exit(f"ABORTADO: {SEM} deberia tener 7 dias UTC y tiene {len(DIAS)}")
EN_DIAS = f"strftime(to_timestamp(t_spend),'%Y-%m-%d') IN {FILTRO}"

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

# ---- agregado diario (solo los 7 dias UTC de la semana) ----
dia = con.execute(f"""
SELECT strftime(to_timestamp(t_spend),'%Y-%m-%d') date,
       CAST(SUM((CAST(value_sats AS HUGEINT)*age) // 86400) AS BIGINT) cdd_sat_days,
       CAST(SUM((CAST(value_sats AS HUGEINT)*age) % 86400) AS BIGINT) cdd_rem_86400,
       CAST(SUM(value_sats) AS BIGINT) spent_value_sats,
       COUNT(*) spent_output_count,
       CAST(SUM(CASE WHEN age>=155*86400 THEN value_sats ELSE 0 END) AS BIGINT) ge155_v,
       CAST(SUM(CASE WHEN age>=155*86400 THEN (CAST(value_sats AS HUGEINT)*age) // 86400 ELSE 0 END) AS BIGINT) ge155_c,
       CAST(SUM(CASE WHEN age>=155*86400 THEN (CAST(value_sats AS HUGEINT)*age) % 86400 ELSE 0 END) AS BIGINT) ge155_r,
       CAST(SUM(CASE WHEN age>=365*86400 THEN value_sats ELSE 0 END) AS BIGINT) ge365_v,
       CAST(SUM(CASE WHEN age>=365*86400 THEN (CAST(value_sats AS HUGEINT)*age) // 86400 ELSE 0 END) AS BIGINT) ge365_c,
       CAST(SUM(CASE WHEN age>=365*86400 THEN (CAST(value_sats AS HUGEINT)*age) % 86400 ELSE 0 END) AS BIGINT) ge365_r
FROM res WHERE {EN_DIAS} GROUP BY 1 ORDER BY 1""").df()
b = con.execute(f"""
SELECT strftime(to_timestamp(b.time),'%Y-%m-%d') date,
       CAST(SUM(o.value_sats) AS BIGINT) out_all,
       CAST(SUM(CASE WHEN cb.txid IS NOT NULL THEN o.value_sats ELSE 0 END) AS BIGINT) cb_sats,
       CAST(SUM(CASE WHEN COALESCE(o.script_type,'')<>'nulldata'
                      AND NOT COALESCE(o.script_hex,'') LIKE '6a%'
                      AND length(COALESCE(o.script_hex,''))<=20000 THEN 1 ELSE 0 END) AS BIGINT) n_creados
FROM outw o JOIN blk b ON b.height=o.height
LEFT JOIN inp_cb cb ON cb.height=o.height AND cb.txid=o.txid
WHERE strftime(to_timestamp(b.time),'%Y-%m-%d') IN {FILTRO}
GROUP BY 1 ORDER BY 1""").df()
m = dia.merge(b, on="date", how="left")
if set(m["date"]) != set(DIAS):
    sys.exit(f"ABORTADO: dias recomputados {sorted(m['date'])} != dias UTC {DIAS}")

# base utxo_eod_count: ultimo dia con datos ANTES de la semana
prev = pd.read_parquet(f"{C2}/daily_aggregates_{ANIO}.parquet")
prev["date"] = prev["date"].astype(str)
ant = prev[prev["date"] < DIAS[0]]
DIA0 = ant["date"].max()
base = int(ant.loc[ant["date"] == DIA0, "utxo_eod_count"].iloc[0])
print(f"  base utxo_eod_count: {DIA0} = {base:,}")
m["fees_sats"] = m.spent_value_sats - (m.out_all - m.cb_sats)
m["coinbase_output_sats"] = m.cb_sats
m["issuance_sats"] = m.cb_sats - m.fees_sats
acum = base
eod = []
for _, r in m.iterrows():
    acum += int(r.n_creados) - int(r.spent_output_count)
    eod.append(acum)
m["utxo_eod_count"] = eod
m["last_height"] = [con.execute(f"SELECT max(h_spend) FROM res WHERE {EN_DIAS} AND strftime(to_timestamp(t_spend),'%Y-%m-%d')=?",
                                [d]).fetchone()[0] for d in m.date]
COLS = ["date","last_height","spent_value_sats","spent_output_count","cdd_sat_days","cdd_rem_86400",
        "fees_sats","coinbase_output_sats","issuance_sats","utxo_eod_count","spent_value_ge155d_sats",
        "spent_value_ge365d_sats","cdd_ge155d_sat_days","cdd_ge155d_rem_86400",
        "cdd_ge365d_sat_days","cdd_ge365d_rem_86400"]
m = m.rename(columns={"ge155_v":"spent_value_ge155d_sats","ge155_c":"cdd_ge155d_sat_days",
                      "ge155_r":"cdd_ge155d_rem_86400","ge365_v":"spent_value_ge365d_sats",
                      "ge365_c":"cdd_ge365d_sat_days","ge365_r":"cdd_ge365d_rem_86400"})[COLS]
print("\n  filas recomputadas:"); print(m.to_string(index=False))

# ---- bandas de edad (3) agregadas por banda, no por edad entera ----
bd = con.execute(f"""
WITH r AS (
  SELECT strftime(to_timestamp(t_spend),'%Y-%m-%d') date, value_sats, age,
         CAST(age // 86400 AS INT) edad_dias
  FROM res WHERE {EN_DIAS}
)
SELECT date, {CASO_BANDA} age_band,
       CAST(SUM(value_sats) AS BIGINT) spent_value_sats,
       COUNT(*) spent_output_count,
       CAST(SUM((CAST(value_sats AS HUGEINT)*age) // 86400) AS BIGINT) cdd_sat_days,
       CAST(SUM((CAST(value_sats AS HUGEINT)*age) % 86400) AS BIGINT) cdd_rem_86400
FROM r GROUP BY 1,2 ORDER BY 1,2""").df()
print(f"\n  filas de bandas: {len(bd)} (maximo esperado {7*12})")

# ---- verificacion: la suma de bandas debe dar el agregado diario ----
for d in DIAS:
    s = bd[bd["date"] == d][["spent_value_sats","spent_output_count","cdd_sat_days","cdd_rem_86400"]].sum()
    r0 = m[m["date"] == d].iloc[0]
    for c in ("spent_value_sats","spent_output_count","cdd_sat_days","cdd_rem_86400"):
        if int(s[c]) != int(r0[c]):
            sys.exit(f"ABORTADO: {d}: bandas {c}={int(s[c])} != diario {int(r0[c])}")
print("  verificacion OK: las bandas suman igual que el agregado diario en los 7 dias")

# ---- verificacion en SQL (HUGEINT: exacto; pandas convierte HUGEINT a float64) ----
con.register("dia_df", m[["date","spent_value_sats","spent_output_count","cdd_sat_days","cdd_rem_86400"]])
con.register("bd_df", bd[["date","age_band","spent_value_sats","spent_output_count","cdd_sat_days","cdd_rem_86400"]])
CHK = """
SELECT count(*) FROM (SELECT date, CAST(SUM(spent_value_sats) AS HUGEINT) sv,
                             CAST(SUM(spent_output_count) AS HUGEINT) n,
                             CAST(SUM(cdd_sat_days) AS HUGEINT) cdd,
                             CAST(SUM(cdd_rem_86400) AS HUGEINT) rem
                      FROM bd_df GROUP BY 1) x
JOIN dia_df d USING (date)
WHERE x.sv<>d.spent_value_sats OR x.n<>d.spent_output_count
   OR x.cdd<>d.cdd_sat_days OR x.rem<>d.cdd_rem_86400"""
mal = con.execute(CHK).fetchone()[0]
print(f"  verificacion SQL (suma de bandas == agregado diario): {mal} discrepancias")
if mal:
    sys.exit("ABORTADO: el agregado diario no coincide con la suma de sus bandas")

# ---- escribir con backup ----
for ruta, nuevo, clave in ((f"{C2}/daily_aggregates_{ANIO}.parquet", m, ["date"]),
                           (f"{C2}/age_band_aggregates_{ANIO}.parquet", bd, ["date","age_band"])):
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
