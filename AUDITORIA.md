# Reproducibility audit of OBM v0.1.0

**What this is.** An independent reimplementation of the *Open Bitcoin Metrics* dataset
(arXiv:2607.03124v1) starting **from our own full node alone, Bitcoin Core v26.0.0**
(`txindex=1`, no pruning). The goal is not to publish new metrics, but to check whether OBM's can be
**re-derived from the chain** and to document with numbers **where and why** they differ.

**Scope.** The 23 daily series published in `obm_reference/metrics/` (v0.1.0,
the snapshot delivered with the paper) are audited against the output of this pipeline. OBM's code
is not audited (no line of it was used): this is a **black-box audit of the data**
and a **white-box audit of the published methodology** (paper + `APPENDIX A` + `METODOLOGIA.md`).

---

## Method

1. **Own pipeline in 4 layers.** `layer 1` extracts the chain from the node into weekly parquet
   (`blocks`, `txs`, `inputs`, `outputs`); `layer 2` is the *spent-output indexer* of §3.4 of the paper
   (live UTXO in SQLite + daily and age-band aggregates); `layer 3` produces the 23 series;
   `layer 4` (market) is out by design. Hard rules: **zero hand-written numbers in the pipeline** (every number it produces
   comes out of a re-runnable script) and `layer 1`–`layer 3` reproducible with the node.

2. **Day-by-day comparison** against the official CSVs (`src/exporters/validar_capa3.py`), with the
   tolerance fixed by the **published decimals** of each series (half the last digit) so as not to
   mistake presentation rounding for a real discrepancy.

3. **Bilateral verification** of guards and validators: each one is tested with the real input
   (positive case) and with an input deliberately truncated (negative case) that proves it still
   detects the failure.

4. **Health invariants** that are checked after every stretch (see below).

---

## Result

`python3 src/exporters/validar_capa3.py` — day-by-day comparison with the tolerance of each series:

| Group of series | Result |
|---|---|
| 5 block series (`block_count`, `block_weight_wu`, `tx_count`, `difficulty_eod`, `est7d_hashrate`) | **bit-exact** on the dates of the reference (6,461–6,463 depending on the series) |
| 12 flow and UTXO series (`spent_output_count`, `spent_value` and their 155d/365d thresholds, `fees`, `issuance`, `miner_revenue`, `raw_output_value`, `supply`, `utxo_eod_count`, `fee_share`) | **bit-exact** |
| `spent_value_age_band` (12-column wide table) | **bit-exact** |
| `cdd_btcxdays` | **1 day** off (2010-05-22, 1E-8 BTC-days = 1 sat-day) |
| `cdd_age_band` (12-column wide table) | **111 days / 113 cells** off by 1E-12 = 1 ulp of the last published decimal |
| ratios derived from the CDD (`dormancy`, `cdd_per_supply`, `liveliness`) | **bit-exact** |

**21 of 23 series bit-exact**; the two that differ are the CDD ones, and they do so by **one unit
of the last published decimal** (1 sat-day on a day in 2010; 1 ulp on 111 days of the wide table),
where our value is verified to be the exact *half-even* rounding and OBM's differs by one unit of the last decimal, in either direction (F2). **The whole reference** is compared (its 23 series have between 6,459 and 6,463 dates), and
layer 3 extends 27 days beyond its end (up to 2026-10-08).

---

## Findings A — OBM conventions that have to be replicated

### F1 · BIP30: the reference counts BOTH copies
OBM §3.4 documents *last-write-wins* over the two duplicate historical coinbases. Our
implementation uses `INSERT OR IGNORE` (uniqueness `(txid,vout)` as in Core) → the official series is
**+1 on 2010-11-14** and **+2 from 2010-11-15**. The two affected outputs **are never spent**,
so the only consequence is the **count**; it is compensated by an explicit adjustment in layer 3
(`--no-bip30` flag) and `utxo_eod_count` becomes exact.

### F2 · The CDD is not bit-exact: rounding ties in the last decimal
OBM defines `CDD_i = V_i·A_i` with `A_i` **fractional**. These are two different effects, both measured:

- **Truncating per input** loses up to 1 sat-day per output. The *discarded* variant was measured
  then (historical, not re-run): 2,320 days with error, maximum **3.33e-3 BTC-days** (rel. 1.77e-9).
  With **two accumulators** (integer part + remainder; columns `cdd_rem_86400`) the residual against
  the reference is **1 day**, maximum **1e-8 BTC-days** (rel. **2.33e-14**) over the 2,627 days.
- **Even so it cannot be bit-exact.** With the tolerance derived from the last published decimal
  there remain **1 day** in `cdd_btcxdays` (1E-8 = 1 sat-day) and **111 days / 113 cells** in the wide
  table `cdd_age_band` (1E-12). The 113 cells were checked one by one: they are **exact ties in
  decimal 13**, our figure is the **half-even** rounding of the exact value in **113/113** and
  OBM's differs by one unit of the last decimal, in either direction. The disagreement is on OBM's side and is not generic "floating
  point": it is its rounding convention. The ratios derived from the CDD do come out exact.

### F3 · Difficulty is READ from the node, not recomputed
OBM A.6 reads it from the block's `difficulty` field. Reconstructing it from `bits` (15 variants tested)
differs by **1 ULP of float64 on 2,965 of 6,456 days**. As it is constant within each 2016-block
epoch, **482 RPC calls** (`getblockheader`) suffice instead of one per block (≈970,000) →
`capa1/difficulty_epochs.parquet`. **Lesson**: protocol state variables are read, not
recomputed.

*(Resolved on 2026-10-08: the file had got stuck at **epoch 480** and the blocks of
`2026-W40` fell in **481**, which was missing; `capa3_series.py` detected it and **warned** on screen
instead of recomputing silently —that `AVISO` was added precisely for this (A3 of the adversarial
review)— and the file was regenerated with the node running: today it covers **482 epochs (0..481)**,
with the tip at 970,449, and the warning no longer appears. Those dates still lie beyond the end of
the reference, so they do not enter the validation.)*

### F6 · Merge when a date falls into two weekly files
A consequence of partitioning by ISO week: a date can appear in two weeks (F4). The correct
merge **adds** the flows and keeps the **last** `utxo_eod_count` and the **maximum**
`last_height`.

---

## Findings B — bugs in **our** implementation

These are not discrepancies with OBM: they are our own faults, found and fixed during
construction, and they are documented because **none of them is detectable by looking at a single
series** (all four propagate to layer 3).

### F4 · The height/time order (ETL)
Block timestamps **are not monotonic** (16,119 raw inversions in the 970,447 blocks);
OBM's index scans **by height** (§3.4) and we partitioned by the timestamp's week.
Of those inversions, **exactly 2 cross a week boundary** and they are the ones that broke the
partitioning: h=60,787 vs 60,788 (2010-06) and h=293,302 vs 293,303 (2014-03). Impact measured on that
second block: 5 unresolvable inputs, that day's `spent_value` short by **8,711,850,115 sats
(87.12 BTC)**, 5 permanent phantom UTXOs and a snapshot error (+19 on 2014-03-30). Fixed in
3 pieces: week = `max(own, previous)`, re-partitioning of the 2 blocks and a merge adding flows
(F6), plus a **guard** that aborts if `layer 1` is not monotonic in height.

### F5 · 32-bit overflow in the progress counter
`sqlite3_total_changes()` returns a 32-bit `int` and wraps around. In **2017-W13**
`n_inserted` became **−4,290,243,423** (actual 4,723,873) and `utxo_eod_count` was shifted **exactly
2³²** for **1,713 days** (2017-03-29 → 2021-12-05). **It was caught by the count invariant**.
Exact repair (`src/exporters/reparar_wrap_2017.py`) and a permanent fix: counting with `cursor.rowcount`
capped at the batch size. *(The values in this paragraph are the **historical** state of the fault;
in the current DB those rows are repaired.)*

### F7 · The crash window between the commit and the parquet
The per-week order was *commit DB → parquet → state*: a cut between the first two leaves the
week **committed and recorded** but **without its aggregates**, and on resume it is skipped (it is already in
`weeks_done`) → silent loss. **It happened**: the Ctrl-C of 28 Sep fell on the commit of
`2022-W06` (7 days at zero and supply shifted by 6,650 BTC for 686 days, contaminating `supply`,
`cdd_per_supply` and `liveliness`).

Definitive fix (applied): the aggregates **live in the DB** (`daily_agg`, `age_band_agg`),
written in the **same transaction** as the data, and the annual parquet files are a **derived product** that is
rebuilt in full at startup (`rebuild_all_from_db`) and when each week is closed
(`rebuild_year_from_db`). A cut no longer loses anything: **it heals itself**. The "obvious"
solution was discarded (reversing the order to parquet→commit) because the merge by SUM could count a
reprocessed week twice; with the date as primary key, that is now impossible. Migrated with
`migrar_agregados_a_db.py` (**fidelity 36/36 files, 0 differences**) and verified with
`verificar_f7_autocuracion.py` (**5/5**, including the cut scenario).

### F8 · Silent traps in the F7 repair script
The script that recomputed the 7 days failed several times before producing valid data, for six
causes **of our own**, all silent: (F8.1) `strftime(to_timestamp(t))` uses the time zone of the DuckDB
**session**, not UTC → days shifted by 5 h and a phantom day; (F8.2) the bands were written
**without aggregating** (17,069 rows where 84 belong); (F8.3) in DuckDB `/` is **REAL** division, not integer →
the CDD stopped being exact (950,272 sat-days of error); (F8.4) **pandas** converts HUGEINT to
float64 when verifying totals; (F8.5) `n_created` **excluded the coinbase outputs**, which the indexer does
insert as live UTXOs. And (F8.6) the **coverage guard** looked each day up in the parquet of the year
**of the week** instead of the year **of the day** → 13 false aborts at a year boundary, detected
just before resuming (the guard had never been exercised because it was added with the indexer already
running).

Final verification of the repair (7 days, against the reference): `spent_output_count`,
`spent_value`, `fees` and `issuance` with **0 differences**; `utxo_eod_count` with the constant −2 of
BIP30; `cdd` with a residual of 3.7e-09 (rel. 1.9e-16). The offset stays constant with no step at all
→ the repair introduced no discontinuity.

---

## Attribution

| Finding | Whose is it? |
|---|---|
| F1 BIP30 | **Documented in OBM** §3.4; our difference is one of implementation (counting) |
| F2 CDD precision | **OBM's choice** (float); our exact value differs in the last digit |
| F3 difficulty | **OBM's method** (read from the node); the one that failed was our recomputation |
| F4 height/time order | **Our ETL** |
| F5 32-bit overflow | **Our progress instrumentation** |
| F6 multi-file merge | **Our file partitioning** (a consequence of F4) |
| F7 crash window | **Our write order** |
| F8 (6 traps) of the repair | **Our repair script** |

The first five findings in the "ours" column are not cosmetic: all five went on to correct
publishable data. That they were found is the useful result of the audit.

---

## Invariants and guards that are checked

| Invariant | What it detects | Command |
|---|---|---|
| `COUNT(live_outputs) == Σ n_inserted − Σ n_spent` (phantoms = 0) | lost/duplicated rows in the live UTXO (this is how F5 was found) | `python3 -c "…"` (see README) |
| Coverage: every week in `weeks_done` has its days in the parquet | the F7 crash window | `check_parquet_coverage()` at startup |
| Monotonicity of heights in `layer 1` | the height/time order (F4) | `check_capa1_monotonic()` at startup |
| Sum of bands = daily aggregate | ungrouped bands / wrongly computed CDD (F8.2, F8.3) | checked **separately**, on the integer columns of the DB (exact); on the **published** values it differs in the last decimal on **6,189** of 6,461 days (max. 5e-9) and coincides on the remaining **272**, because of the rounding of each band |
| Cross counts per week (`COUNT(txs)=ΣnTx`, `=Σvin`, `=Σvout`) and uniqueness of `(txid,vout)` | duplicates and overlaps in `layer 1` | `etl/capa1_btccore_parquet.py --validate` |
| Chain: `previousblockhash` of height *h* = `hash` of *h−1*, and contiguous heights without duplicates | gaps or overlaps between weekly files | checked on all 970,447 heights |

---

## Reproducing

```bash
cd /media/SSD4T/obm
python3 src/exporters/capa3_series.py     # 23 series from capa1 + capa2
python3 src/exporters/validar_capa3.py    # comparison + figures + VALIDATION.md
python3 src/exporters/verificar_f7_autocuracion.py   # negative test of the F7 self-healing
```

The number-by-number evidence, with the command that regenerates it in each case, is in
`AUDITORIA_HALLAZGOS.md`. The series and their validation, in `capa3/VALIDATION.md`.

---

## The dataset built

| Layer | Content | Status |
|---|---|---|
| `layer 1` | 970,447 blocks (0..970,446), 928 weeks × 4 tables, parquet | complete and validated |
| `layer 2` | 927 weeks (`2009-W01`..`2026-W40`); live UTXO in SQLite (~20 GiB); daily and age-band aggregates | complete; invariant 0 phantoms |
| `layer 3` | the 23 daily series | **21/23** bit-exact |
| `layer 4` | price/market | not included (out of scope) |

Construction cost on this machine: `layer 2` ~1 h per week in 2026 (≈50-85 min/week), several
days in total; `layer 1` 387 GiB of parquet.
