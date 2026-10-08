# Layer 3 validation against the OBM v0.1.0 reference

Generated: 2026-10-08 13:25

- Layer 3 coverage: up to **2026-10-08**
- Comparison limited to: **2026-10-04**
- Reference coverage: up to **2026-09-11**
- Exact series: **21/23**
- Tolerance: **half the last decimal published** by the reference, derived from the file itself (per series and, in the wide tables, per column). The `dec` column shows the decimals used.

| Series | Days compared | Days differing | Max error | dec | Verdict |
|---|---:|---:|---:|---:|---|
| `obm_block_count_daily` | 6463 | 0 | 0 | 0 | EXACT |
| `obm_block_weight_wu_daily` | 6461 | 0 | 0 | 0 | EXACT |
| `obm_cdd_age_band_btcxdays_daily` | 6463 | 111 | 1E-12 | 12 | DIFFERS |
| `obm_cdd_btcxdays_daily` | 6461 | 1 | 1E-8 | 8 | DIFFERS |
| `obm_cdd_per_supply_days_daily` | 6459 | 0 | 0 | 12 | EXACT |
| `obm_difficulty_eod_daily` | 6461 | 0 | 0 | 12 | EXACT |
| `obm_dormancy_days_daily` | 6463 | 0 | 0 | 12 | EXACT |
| `obm_est7d_hashrate_ehs_daily` | 6461 | 0 | 0 | 12 | EXACT |
| `obm_fee_share_revenue_ratio_daily` | 6463 | 0 | 0 | 12 | EXACT |
| `obm_fees_btc_daily` | 6463 | 0 | 0 | 8 | EXACT |
| `obm_issuance_btc_daily` | 6463 | 0 | 0 | 8 | EXACT |
| `obm_liveliness_ratio_daily` | 6461 | 0 | 0 | 12 | EXACT |
| `obm_miner_revenue_btc_daily` | 6463 | 0 | 0 | 8 | EXACT |
| `obm_raw_output_value_btc_daily` | 6461 | 0 | 0 | 8 | EXACT |
| `obm_spent_output_count_daily` | 6463 | 0 | 0 | 0 | EXACT |
| `obm_spent_value_age_band_btc_daily` | 6463 | 0 | 0 | 8 | EXACT |
| `obm_spent_value_btc_daily` | 6463 | 0 | 0 | 8 | EXACT |
| `obm_spent_value_ge155d_btc_daily` | 6463 | 0 | 0 | 8 | EXACT |
| `obm_spent_value_ge365d_btc_daily` | 6463 | 0 | 0 | 8 | EXACT |
| `obm_spent_value_lt155d_btc_daily` | 6463 | 0 | 0 | 8 | EXACT |
| `obm_supply_btc_daily` | 6463 | 0 | 0 | 8 | EXACT |
| `obm_tx_count_daily` | 6463 | 0 | 0 | 0 | EXACT |
| `obm_utxo_eod_count_daily` | 6461 | 0 | 0 | 0 | EXACT |

## Known discrepancies and root cause

- **`obm_cdd_age_band_btcxdays_daily`** (111 days, max 1E-12): 111 days / 113 cells differing by 1 ULP of the last published decimal (1e-12). They are EXACT ties at the 13th decimal: our figure is the half-even rounding of the exact value in all 113 cells (verified) and OBM's differs by one unit of the last decimal, in either direction.
- **`obm_cdd_btcxdays_daily`** (1 days, max 1E-8): 1 day (2010-05-22) differing by 1 sat-day (1e-8 BTC-days): it is the residue of OBM's own rounding when accumulating CDD (over a measured 2,622-day span the residue reaches ~1.5 sat-days and affects ~2.7% of the days).

## Reproduce

```bash
python3 src/indexer.py                      # layer 1 -> layer 2 (~2 days)
python3 src/exporters/capa3_series.py       # 23 series -> capa3/
python3 src/exporters/validar_capa3.py      # this report
```
