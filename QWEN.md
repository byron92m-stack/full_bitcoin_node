# Handover — OBM replica + reproducibility audit

> Entry point for any code agent. Status: **2026-10-08**.
> If anything here contradicts the code or the logs, **the code wins**.

## What it is
Own pipeline that reproduces the **23 daily series of Open Bitcoin Metrics (OBM) v0.1.0**
from a full Bitcoin Core node, and the basis of an **independent
reproducibility audit** (the paper is called "Verifiable Full-Node-Derived…": its thesis is
reproducibility). See `README.md` (4-layer architecture) and `AUDITORIA_HALLAZGOS.md`.

## Status
| Layer | Status |
|---|---|
| layer 1 | **COMPLETE and validated**: 970,447 blocks (0..970,446), 0 gaps, 928 weeks × 4 tables. `python3 etl/capa1_btccore_parquet.py --validate` ✓ |
| layer 2 | **COMPLETE**: 927 weeks (2009-W01..2026-W40), invariant `COUNT = Σins−Σspent` with 0 phantom rows. Resumable: `python3 src/indexer.py` → option **2** (NEVER 1, it deletes `capa2/`) |
| layer 3 | **VALIDATED: 21/23 bit-exact series** against `obm_reference/metrics`, with the tolerance derived from the decimals the reference publishes. The two differences are in CDD: `cdd_btcxdays` (1 day, 1E-8 = 1 sat-day) and `cdd_age_band` (111 days / 113 cells, 1E-12 = 1 ulp; exact ties where we round half-even). See `capa3/VALIDATION.md` |
| layer 4 | empty (price/market, pending — see `ROADMAP.md`) |

## How to check the live status
```bash
cd /media/SSD4T/obm
tail -3 logs/indexer.log
python3 -c "import json;d=json.load(open('state_indexer.json'));print(d['last_processed_week'],d['utxo_count'])"
# layer 2 health invariant (takes minutes over ~100 M rows):
python3 -c "
import sqlite3
c=sqlite3.connect('file:/media/SSD4T/obm/capa2/live_outputs.sqlite?mode=ro',uri=True,timeout=600)
n=c.execute('SELECT COUNT(*) FROM live_outputs').fetchone()[0]
_,i,s=c.execute('SELECT COUNT(*),SUM(n_inserted),SUM(n_spent) FROM weeks_done').fetchone()
print(f'COUNT={n:,} derived={i-s:,} PHANTOMS={n-(i-s):,}')"   # PHANTOMS must be 0
```

## When layer 2 finishes (exact order)
```bash
python3 src/exporters/capa3_series.py      # 23 series -> capa3/
python3 src/exporters/validar_capa3.py     # -> capa3/VALIDATION.md + figures/
grep -cE "UTXO not found|negative fees|negative issuance" logs/indexer.log   # must be 0
```
Obtained on 2026-10-08: **21/23 bit-exact** (see `Status`); the two differences are in CDD and
are worth 1 ulp of the last published decimal. When regenerating it after an extension, if anything else comes out,
**stop and notify**.

## Non-negotiable rules (each one cost a real bug)
1. **The order is HEIGHT, not time.** Block timestamps are not monotonic. Partitioning
   the chain by timestamp-week breaks UTXO resolution (see F4).
2. **Exact CDD**: `cdd_sat_days + cdd_rem_86400/86400`. NEVER truncate per input.
3. **NEVER `con.total_changes`**: the C API truncates at 32 bits and wraps around (see F5). Use
   `cursor.rowcount`.
4. **BIP30**: OBM does last-write-wins and its counter counts the 2 copies; our DB
   deduplicates like Core. The adjustment lives in layer 3 (`--no-bip30` to disable it).
5. **Difficulty is READ from the node** (`capa1/difficulty_epochs.parquet`), it is not recomputed
   from `bits` (1 ULP of difference — see F3).
6. **Age bands in DAYS** (`age_seconds/86400`); the 155d/365d thresholds in SECONDS.
7. **Do not touch** `capa2/live_outputs.sqlite`, `weeks_done` or `state_indexer.json` while
   the indexer is running. Reading them in `mode=ro` is fine.
8. **Zero numbers by hand**: every published number comes from a re-runnable script.

## Traps already stepped on
| Symptom | Cause | Fix |
|---|---|---|
| `5 UTXO not found` + `negative fees` in block 293,303 | partitioning by timestamp-week (F4) | monotonic partitioning by height + re-partitioning + merging by sum |
| `utxo_eod_count` negative on 1,713 days | `total_changes` at 32 bits (F5) | `cursor.rowcount` + `src/exporters/reparar_wrap_2017.py` |
| `cdd` with a 1.8e-9 error | truncation per input (F2) | `cdd_rem_86400` + `cdd_ge*_rem_86400` columns |
| Everything in the `10y_plus` band | SECONDS were being passed to a function with DAY boundaries | `get_age_band(age_seconds / SECONDS_PER_DAY)` |
| Days with spent_value at 0 after a re-partitioning | merge with `keep="last"` on dates split between two weeks | merge by SUMMING flows |
| `difficulty` off by 1 ULP | recomputed from `bits` (F3) | read the field from the node |
| Phantom day and dates shifted by ~5 h in DuckDB queries | `strftime(to_timestamp(t))` formats in the SESSION time zone | `SET TimeZone='UTC'` (F8.1) |
| CDD error of thousands of sat-days in SQL | in DuckDB `/` is REAL division (HUGEINT→DOUBLE) | use `//` and check in SQL (F8.3/F8.4) |
| `utxo_eod_count` short by ~140-190/day | `n_created` excluded the coinbase outputs | count them: they are live UTXOs (F8.5) |
| 17,000 band rows in a single week | one row per age was being written, not per band | `GROUP BY date, age_band` (F8.2) |

## Environment
- Python 3.14 · pandas 3.0.2 · pyarrow 23.0.1 · duckdb 1.5.2 · statsmodels · scipy · sklearn · matplotlib
- Bitcoin Core 26.0.0 in `/media/SSD4T/bitcoin/.bitcoin` — **OFF** (layer 2 does not need it).
  Restart: `bitcoind -datadir=/media/SSD4T/bitcoin/.bitcoin -daemon`
- Official reference in `obm_reference/`: `metrics/` (23 CSV), `paper/` (the manuscript),
  `tools/` (the authors' code — useful for the audit).
- **git** repository initialised. The code, the documentation **and the layer-3 dataset**
  (`capa3/`: the 23 series, `validation_series.csv`, `VALIDATION.md`, the figures and
  `MANIFEST.sha256`) are versioned; the rest of the data is **not** (`capa1/`, `capa2/`, `capa4/`,
  `obm_reference/`, `state_*.json`, `*.bak_*`, `tmp/`) nor are the logs, except `logs/evidencia/`.
  See `.gitignore`.
- The logs in `logs/evidencia/` are **evidence** of findings F4/F5: do not delete them.

## Conventions
- Documentation, comments and identifiers in **English** (the OBM schema names are kept as published).
- `layer 1`-`layer 3` must be reproducible **with the node only** (nothing external).
- `.bak_*` backups are deleted (the history lives in the audit text).

## Priority pending work
1. Close layer 3 + validate (above).
2. **Package A**: `AUDITORIA.md` from `AUDITORIA_HALLAZGOS.md` (the 8 findings are already
   closed with numbers). Rule: adversarial review by an independent agent before
   publishing.
3. `ROADMAP.md`: layer 4 (price/market) → econometric study → balances layer.

## F7 — RESOLVED (data on 30 Sep, code on 8 Oct)

The 28 Sep Ctrl-C landed inside the `con.commit()` for 2022-W06: the DB was left committed with the week in
`weeks_done`, but **its 7 days were not written** to the yearly parquet. Effect: 7 days at zero + the
supply shifted by 6,650 BTC from 2022-02-13 (it was contaminating `supply`, `cdd_per_supply`,
`liveliness`). See F7 in `AUDITORIA_HALLAZGOS.md`.

- **Data**: `src/exporters/reparar_semana_2022W06.py` and `reparar_utxo_eod_w06.py` recomputed
  the 7 days from layer 1 (`prevouts resueltos: 6,574,407/6,574,407`) and they match the reference.
- **Code (definitive fix)**: the daily and per-band aggregates now live **in the DB**
  (`daily_agg`, `age_band_agg`), written in the **SAME transaction** as the data, and the yearly parquet
  files are a **derivative** that is rebuilt in full on startup (`rebuild_all_from_db`) and when
  each week closes (`rebuild_year_from_db`). A cut between the commit and the parquet no longer loses
  anything: it heals itself on the next startup. Moreover, since there is a single row per date,
  the double-counting risk of the old merge by SUM disappears (F4), which was the reason for
  discarding the idea of reversing the order to parquet→commit.
- **Migration** (run on 8 Oct): `src/exporters/migrar_agregados_a_db.py` — 6,465 daily rows
  and 60,792 band rows *at the time of migrating* (the DB has more today, because layer 2 kept
  processing); fidelity **36/36 files, 0 differences**.
- **Verification**: `src/exporters/verificar_f7_autocuracion.py` reproduces the scenario in an
  isolated environment (gap → healing → idempotency → replacement instead of summing): 5/5 OK.
- `check_parquet_coverage()` is kept as a check that the rebuild covered every
  week in `weeks_done`.
