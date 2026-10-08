# OBM v0.1.0 reproducibility audit — findings

Raw material for Package A (`AUDITORIA.md`). **All the numbers are measured**; the
"reproduce" column indicates the script or command that regenerates them. Zero numbers by hand.

**Context**: independent reimplementation (our own node, our own code, zero lines from the
OBM authors) of the dataset described in *"Open Bitcoin Metrics: Verifiable Full-Node-Derived
Bitcoin Time Series for Economic Research"* (arXiv:2607.03124v1, Jul-2026). Comparison
reference: `obm_reference/metrics/` (the 23 official CSVs, v0.1.0).

## Overall result

`python3 src/exporters/validar_capa3.py` (day-by-day comparison, tolerance = published decimals)

| Series block | Result |
|---|---|
| 5 block series (`block_count`, `block_weight_wu`, `tx_count`, `difficulty_eod`, `est7d_hashrate`) | **bit-exact on the 6,461 dates** of the reference |
| UTXO and coin-age series | exact over the processed span; `utxo_eod_count` exact with the BIP30 adjustment |
| `cdd_btcxdays` | **1 day** with a 1 sat-day difference (1E-8) |
| `cdd_age_band` | **111 days / 113 cells** with 1 ulp (1E-12) of the last published decimal |

**Obtained on 2026-10-08: 21/23 bit-exact.** The two differences are in the CDD and are worth one unit
of the last published decimal. The tolerance is **derived from the reference file** (column by
column); it used to be written by hand, it said 8 decimals where the reference publishes 12 and let
113 cells through (finding A1 of the adversarial review).

---

## F1 — BIP30: the reference counts BOTH copies (convention documented in OBM)

**Fact.** OBM §3.4: *"when the indexer encounters such a duplicate live outpoint, it overwrites
the earlier entry with the later one and records the event in metadata. The overwritten output is
not counted as spent and therefore does not generate spent value or CDD."*

**Our implementation** uses `INSERT OR IGNORE` (*first-write-wins*), so `live_outputs`
keeps the `(txid,vout)` uniqueness as Bitcoin Core.

**Measurement.** The official series is **+1 on 2010-11-14** and **+2 from 2010-11-15** (5,780 days with
diff=+2 over the whole coverage of the reference, 1,508 of them in 2009-2014). It matches exactly
the two duplicated coinbases:
`d5d27987…:0` at heights 91,812/91,842 and `e3bf3d07…:0` at 91,722/91,880.

**Bounded impact.** Neither of those two outputs is **ever** spent (verified by searching for inputs
that reference them) → the only consequence is the **count**; no other metric is affected.

**Fix.** Explicit and reversible adjustment in layer 3 (`capa3_series.py`, flag `--no-bip30`) →
`utxo_eod_count` becomes **exact on the 6,456 compared dates** (4,715 in the first measurement,
with the coverage at that time).
*Reproduce*: `python3 src/exporters/validar_capa3.py` (days with diff≠0).

## F2 — CDD precision: truncating per input costs 1.8e-9

**Fact.** OBM: `CDD_i = V_i·A_i` with `A_i = (t_spend−t_create)/86400` **fractional**, stored
"as satoshi-days" (A.4). Truncating per input (`(V·Δt)//86400`) loses up to 1 sat-day per input.

**Measurement (2,622 days, 2009-01-03 → 2016-03-13):**

| | days with difference | max. error (BTC-days) | max. rel. error |
|---|---|---|---|
| truncated per input | 2,320 | 3.33e-3 | 1.77e-9 |
| **exact** (2 accumulators) | **70** | **1.49e-8** | **8.9e-11** |

→ ≈20× less relative error and ≈223,490× less absolute error. Even so it is **not bit-exact**: with the
tolerance of the last published decimal there remain **1 day** in `cdd_btcxdays` (1E-8 = 1 sat-day) and
**111 days / 113 cells** in `cdd_age_band` (1E-12). The 113 cells were checked one by one: they are
**exact ties at decimal 13**, our figure is the **half-even** rounding of the exact value in
**113/113** and OBM's is one ulp below — the disagreement is their rounding convention, not
generic "floating point".

**Fix.** Columns `cdd_rem_86400` (+ `cdd_ge155d_rem_86400`, `cdd_ge365d_rem_86400` in daily,
and `cdd_rem_86400` in bands): exact = `cdd_sat_days + cdd_rem_86400/86400`.

**int64 bound verified with real data**: daily maximum of CDD = 518,269,161.94 BTC-days
(2024-05-28) = 5.18e16 sat-days → **178× of headroom**; the remainder column ≤2.16e11 → **4.3e7×**.
*Reproduce*: compare `cdd_sat_days` vs `cdd_sat_days + cdd_rem_86400/86400` against the reference.

## F3 — Difficulty: NOT reproducible from `bits`, yes from the node (fixed)

**Fact.** OBM A.6: *"The mining difficulty is read from the block-level difficulty field returned
by Bitcoin Core"*.

**Measurement.** Reconstructing it from `bits` with **15 variants** (including Core's `GetDifficulty`
loop) differs from the reference by **1 float64 ULP on 2,825 of 6,461 days** (max 0.05).
Checked against the node: `getblock <h> 1` → `27428630902.25787` = **the reference**; my calculation
from bits → `27428630902.257874` ✗.

**Fix.** The difficulty is **constant within each 2016-block epoch** → **481 RPC calls**
(`getblockhash`+`getblockheader`) instead of one per block → `capa1/difficulty_epochs.parquet`
(today it covers epochs 0..480; epoch 481, of `2026-W40`, is missing, and `capa3_series.py` **warns**
when it finds it instead of silently recalculating: see A3 in the adversarial review).
(`src/exporters/fix_difficulty_rpc.py`).
**Result**: `difficulty_eod` **and** `est7d_hashrate` become **bit-exact on the 6,461 dates**.

**Lesson**: for protocol state variables, **read them from the node; do not recalculate them**.

## F4 — The height/time order (bug in OUR ETL, not in OBM)

**Fact.** OBM §3.3 warns that the timestamps are not monotonic and §3.4 says that the index
**scans in height order** → OBM does not have this problem. Our ETL partitioned by ISO week
**of the timestamp** and the indexer processed those weeks in order.

**Measurement.** Scanning the **970,447 heights** there are **16,119 raw inversions**, of which
**exactly 2 cross a week boundary**:
`h=60,787` (2010-06-14 00:00, W24) vs `h=60,788` (2010-06-13 23:59, W23), and
`h=293,302` (2014-03-31 00:00, W14) vs `h=293,303` (2014-03-30 23:55, W13).

**Measured impact** (block 293,303): 5 unresolvable inputs → `spent_value` for that day short by
**8,711,850,115 sats (87.12 BTC)** and `spent_output_count` −5 out of 152,195, with `fees`/`issuance`
deviated; **5 phantom UTXOs** (+5 permanent in the count); a one-day snapshot error (+19 on
2014-03-30) and a transient one (+1 on 2010-06-13).

**Fix (3 pieces).** (a) ETL: week = `max(own, previous)` → monotonic partition in height;
(b) re-partitioning of the 2 blocks (`etl/reparticionar_semanas.py`); (c) multi-file merge
**summing** flows (see F6). Added a **guard** in `src/indexer.py` that aborts if layer 1 is not
monotonic in height.

## F5 — 32-bit overflow in the progress counter

**Fact.** `sqlite3_total_changes()` returns a 32-bit `int` (it truncates). After passing 2³² accumulated
changes, the counter **wrapped around**.

**Measurement.** In **2017-W13** `weeks_done.n_inserted` ended up at **−4,290,243,423** (the real value
was 4,723,873) and `utxo_eod_count` was shifted by **exactly 2³²** for **1,713 days**
(2017-03-29 → 2021-12-05). It was detected with the invariant
`COUNT(live_outputs) == SUM(n_inserted) − SUM(n_spent)`.

**Exact repair** (`src/exporters/reparar_wrap_2017.py`): +2³² to week 2017-W13 and to the dates
≥ 2017-03-29 → verified `COUNT == derivado == 77,000,836` and `FANTASMAS=0`.

**Root fix.** `inserted = max(cursor.rowcount, 0)` (bounded by the batch size) + a
range check that logs an error if `inserted` falls outside `[0, len(batch)]`.

## F6 — Aggregation semantics when a date falls into two files

**Fact.** Consequence of F4: the date 2010-06-13 was split between `..._2010-W23` and
`..._2010-W24`. The original merge used `drop_duplicates(keep="last")` → the partial row from W24
**overwrote** the complete one from W23.

**Measurement**: that day lost **148 outputs and 14,232 BTC** of `spent_value` (measured against the
reference).

**Correct rule**: for a split date, **sum** the flows (`spent_value`,
`spent_output_count`, `cdd`, `fees`, `coinbase`, `issuance`, `ge155/ge365` and their CDD) and keep
the **last** `utxo_eod_count` and the **maximum** `last_height`. It was implemented in
`append_daily_to_year` / `append_age_bands_to_year`; since the F7 fix (8-Oct) that merge no
longer exists: the date is the primary key of `daily_agg` in the DB, so a split date
converges on its own with `INSERT OR REPLACE` and the annual parquet files are rebuilt from there.

---

## What is NOT an OBM bug (important for attribution)

| Finding | Whose is it? |
|---|---|
| F1 BIP30 | **Documented in OBM** §3.4 (last-write-wins). Our difference is one of implementation |
| F2 CDD precision | **OBM implementation choice** (float); our exact value is more precise and differs in the last digit |
| F3 difficulty | **OBM method** (reading from the node); our reconstruction from `bits` was the one that failed |
| F4 height/time order | **Our ETL** ✗ — OBM does it right (it scans in height order) |
| F5 32-bit overflow | **Our progress instrumentation** ✗ |
| F6 multi-file merge | **Our splitting into files** ✗ (consequence of F4) |

## Reproducing all the evidence

```bash
cd /media/SSD4T/obm
python3 src/exporters/fix_difficulty_rpc.py     # F3 (needs the node; already generated)
python3 src/exporters/capa3_series.py           # 23 series
python3 src/exporters/validar_capa3.py          # global validation + figures
# F4: inversions crossing a week boundary in the 970,447 heights (~1 s scan)
# F5: reparacion ya aplicada (src/exporters/reparar_wrap_2017.py, idempotente)
```

## F7 — The crash window between the commit and the parquet write (OUR bug)

**Fact.** In `main()` the per-week order is: (1) `process_week()` which **commits** to the DB
(including the `weeks_done` row), (2) writing of the aggregate parquet files, (3) saving of the
state JSON. A cut between (1) and (2) leaves the week **committed and recorded** but **without its
aggregates in parquet**, and on resume it is skipped (it is in `weeks_done`) → **silent and
permanent loss** of those days.

**It actually happened.** On 28-Sep the indexer was interrupted with Ctrl-C, landing exactly on
`con.commit()` of week **2022-W06**. Measured result: `weeks_done[2022-W06]` exists (the
commit completed) but `daily_aggregates_2022.parquet` **has none of its 7 days**.

**Measured impact** (validated against the reference): 7 days with flows at zero (`spent_value` of
2022-02-08 short by 11,956,176 BTC) **plus a permanent shift of the supply** of
**6,650 BTC** from 2022-02-13 (that week's issuance) that contaminates `supply`,
`cdd_per_supply` and `liveliness` for **686 days**.

**Root fix (applied on 8-Oct).** The order was NOT reversed to parquet→commit: the annual
merge by SUM would make a week reprocessed after a rollback be counted twice (the annual
layout does not distinguish a date shared between weeks —F4— from a rewritten one). The
definitive solution is the inverse: the daily and band aggregates come to **live in the DB**
(`daily_agg`, `age_band_agg`), written in the **same transaction** as the data and `weeks_done`, and
the annual parquet files remain as a **derived** artifact that is rebuilt in full from the DB on startup
(`rebuild_all_from_db`) and when closing each week (`rebuild_year_from_db`). A cut between commit and
parquet no longer loses anything: it heals itself on the next startup. Implemented in `src/indexer.py`,
migrated with `src/exporters/migrar_agregados_a_db.py` (36/36 files rebuilt without differences)
and verified with `src/exporters/verificar_f7_autocuracion.py` (5/5).

**Fix for the data already lost (done on 30-Sep).** The 2022-W06 aggregates were
**recomputable from layer 1 alone** (without the UTXO state): `spent_value` = Σ values of the
resolved prevouts (join of the week's `capa1/inputs` against `capa1/outputs`), `cdd` with
`age = t_spend − t_create` from the respective heights, and `utxo_eod_count(d) = utxo_eod_count(fin de
2022-W05) + Σ(created − spent) up to d`. Done with `src/exporters/reparar_semana_2022W06.py`
(plus `reparar_utxo_eod_w06.py` for `utxo_eod_count`): the 7 days match the reference and
left layer 3 complete.

## F8 — Six silent traps in the repair script (OUR bug, corrected)

Context: `src/exporters/reparar_semana_2022W06.py` (repair of the F7 crash window)
failed three times before producing valid data. The six causes belong to OUR
implementation; none involves OBM. They remain documented because they are silent and the
four would have propagated to layer 3.

### F8.1 — `strftime(to_timestamp(t))` uses the SESSION time zone
DuckDB formats in the session zone, not in UTC. With `America/Guayaquil` (UTC-5) each
day was shifted by 5 h and a phantom day appeared at the start of the week (2022-02-06 with
127,914 spends, which are the blocks of 02-07 between 00:00 and 04:59 UTC), also overwriting the
correct 02-06 (826,967 spends / 304,532,860,918,303 sats).
Fix: `SET TimeZone='UTC'` when opening the connection.
Repro: `SELECT strftime(to_timestamp(1644192614),'%Y-%m-%d')` → `2022-02-06` without the SET,
`2022-02-07` with it (and `datetime.fromtimestamp(ts, timezone.utc)` in Python agrees).

### F8.2 — Age bands without aggregation
The Python loop iterated over every whole age (0…4.500 days) and wrote one row per age:
17,069 rows where 84 correspond (7 days × 12 bands).
Fix: aggregate in SQL with `CASE` + `GROUP BY date, age_band`.

### F8.3 — In DuckDB `/` is REAL division, not integer
`CAST(value_sats AS HUGEINT)*age/86400` executes as `CAST(... AS DOUBLE)/86400` (DuckDB's own
plan gives it away), so the CDD was computed in floating point and stopped
being exact: 950,272 sat-days of error in a test of 2 M rows, with sums that depend on the
grouping order. Fix: `(CAST(value_sats AS HUGEINT)*age) // 86400`, the same
semantics as the indexer's `divmod(value_sats*age_seconds, 86400)`.
The script's own assert caught it: the per-band sum and the daily aggregate differed
by 14 sat-days; with `//` they match exactly.

### F8.4 — pandas converts HUGEINT to float64
Verifying the totals by summing in pandas loses precision (dtype `float64`). Fix:
verify in SQL (HUGEINT against HUGEINT) over the DataFrames registered in DuckDB.

### F8.5 — `n_creados` excluded the coinbase outputs
The condition `cb.txid IS NULL` (inherited from the fee calculation) removed the coinbase
outputs from the count, which the indexer DOES insert as live UTXOs (STEP B). Result:
`utxo_eod_count` short by ~1 output per block (140-190/day, cumulative). It was detected
by comparing against the reference: the daily offset was exactly the number of blocks of the
day. Fix: count every output that passes the spendability filter, coinbase included.
`src/exporters/reparar_utxo_eod_w06.py` applies only that column without repeating the
386 GB scan (idempotent).

### Final verification of 2022-W06 (7 days, against `obm_reference/metrics`)
```
obm_spent_output_count_daily   0 diferencias
obm_spent_value_btc_daily      0 diferencias
obm_fees_btc_daily             0 diferencias
obm_issuance_btc_daily         0 diferencias
obm_utxo_eod_count_daily       -2 constant (F1: BIP30, compensated in layer 3)
obm_cdd_btcxdays_daily         max 3.7e-09 BTC-days (float residual, rel. 1.9e-16)
```
Integrity check: the −2 offset stays constant from 2010-11-15 throughout
all of 2022, with no step → the repair introduced no discontinuity. The 7 days
are in the parquet (verified with the corrected F8.6 guard).

### F8.6 — The coverage guard looked for the day in the week's year
`check_parquet_cobertura()` (guard added for F7) resolved each expected day against
`daily_aggregates_<week-year>.parquet`. But each day is written to the parquet of **its**
year, and an ISO week can start or end in the adjacent year (F4): the days
2010-01-01..03 of `2009-W53` live in `daily_aggregates_2010.parquet`. Effect: 13 false
aborts due to the year boundary (2009-W53, 2010-W52, 2011-W52, 2013-W01, 2014-W01, 2015-W01,
2015-W53, 2016-W52, 2019-W01, 2020-W01, 2020-W53, 2021-W52, 2022-W52), which would have
blocked the resumption of layer 2 with no real gap existing.
No previous startup had exercised it because it was added to the code with the indexer already
running (the process went on with the old module already imported); it was detected while reviewing the
state just before resuming.
Fix: resolve each day against the parquet of its own year. Verification: 0 gaps over
the **927** weeks of `weeks_done` (it was checked first with the 792 that existed then and
later with 886, 904, 925 and 927, always 0), and a negative test with a truncated parquet
(without 2012-06-15) → the guard detects it.
