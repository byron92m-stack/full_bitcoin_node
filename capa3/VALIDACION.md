# Validación de capa3 frente a la referencia OBM v0.1.0

Generado: 2026-10-08 10:25

- Cobertura de capa3: hasta **2026-10-08**
- Comparación limitada a: **2026-10-04**
- Cobertura de la referencia: hasta **2026-09-11**
- Series exactas: **22/23**

| Serie | Días comparados | Días con diferencia | Error máximo | Veredicto |
|---|---:|---:|---:|---|
| `obm_block_count_daily` | 6463 | 0 | 0 | EXACTA |
| `obm_block_weight_wu_daily` | 6461 | 0 | 0 | EXACTA |
| `obm_cdd_age_band_btcxdays_daily` | 6463 | 0 | 0 | EXACTA |
| `obm_cdd_btcxdays_daily` | 6461 | 1 | 1E-8 | DIFIERE |
| `obm_cdd_per_supply_days_daily` | 6459 | 0 | 0 | EXACTA |
| `obm_difficulty_eod_daily` | 6461 | 0 | 0 | EXACTA |
| `obm_dormancy_days_daily` | 6463 | 0 | 0 | EXACTA |
| `obm_est7d_hashrate_ehs_daily` | 6461 | 0 | 0 | EXACTA |
| `obm_fee_share_revenue_ratio_daily` | 6463 | 0 | 0 | EXACTA |
| `obm_fees_btc_daily` | 6463 | 0 | 0 | EXACTA |
| `obm_issuance_btc_daily` | 6463 | 0 | 0 | EXACTA |
| `obm_liveliness_ratio_daily` | 6461 | 0 | 0 | EXACTA |
| `obm_miner_revenue_btc_daily` | 6463 | 0 | 0 | EXACTA |
| `obm_raw_output_value_btc_daily` | 6461 | 0 | 0 | EXACTA |
| `obm_spent_output_count_daily` | 6463 | 0 | 0 | EXACTA |
| `obm_spent_value_age_band_btc_daily` | 6463 | 0 | 0 | EXACTA |
| `obm_spent_value_btc_daily` | 6463 | 0 | 0 | EXACTA |
| `obm_spent_value_ge155d_btc_daily` | 6463 | 0 | 0 | EXACTA |
| `obm_spent_value_ge365d_btc_daily` | 6463 | 0 | 0 | EXACTA |
| `obm_spent_value_lt155d_btc_daily` | 6463 | 0 | 0 | EXACTA |
| `obm_supply_btc_daily` | 6463 | 0 | 0 | EXACTA |
| `obm_tx_count_daily` | 6463 | 0 | 0 | EXACTA |
| `obm_utxo_eod_count_daily` | 6461 | 0 | 0 | EXACTA |

## Discrepancias conocidas y causa raíz

- **`obm_cdd_btcxdays_daily`** (1 días, máx. 1E-8): Redondeo de OBM al acumular value_btc x age_days por input; residual <= ~1,5 sat-dias.

## Reproducir

```bash
python3 src/indexer.py                      # capa1 -> capa2 (~2 dias)
python3 src/exporters/capa3_series.py       # 23 series -> capa3/
python3 src/exporters/validar_capa3.py      # este informe
```
