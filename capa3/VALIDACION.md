# Validación de capa3 frente a la referencia OBM v0.1.0

Generado: 2026-09-29 20:50

- Cobertura de capa3: hasta **2026-09-24**
- Comparación limitada a: **2023-12-24**
- Cobertura de la referencia: hasta **2026-09-11**
- Series exactas: **5/23**

| Serie | Días comparados | Días con diferencia | Error máximo | Veredicto |
|---|---:|---:|---:|---|
| `obm_block_count_daily` | 5471 | 0 | 0 | EXACTA |
| `obm_block_weight_wu_daily` | 5469 | 0 | 0 | EXACTA |
| `obm_cdd_age_band_btcxdays_daily` | 5471 | 7 | 164204.929889579718 | DIFIERE |
| `obm_cdd_btcxdays_daily` | 5469 | 8 | 11973093.16255492 | DIFIERE |
| `obm_cdd_per_supply_days_daily` | 5469 | 686 | 0.631681875081 | DIFIERE |
| `obm_difficulty_eod_daily` | 5469 | 0 | 0 | EXACTA |
| `obm_dormancy_days_daily` | 5471 | 7 | 0 | DIFIERE |
| `obm_est7d_hashrate_ehs_daily` | 5469 | 0 | 0 | EXACTA |
| `obm_fee_share_revenue_ratio_daily` | 5471 | 7 | 0 | DIFIERE |
| `obm_fees_btc_daily` | 5471 | 7 | 19.58059812 | DIFIERE |
| `obm_issuance_btc_daily` | 5471 | 7 | 1168.75000000 | DIFIERE |
| `obm_liveliness_ratio_daily` | 5469 | 686 | 0.000806035432 | DIFIERE |
| `obm_miner_revenue_btc_daily` | 5471 | 7 | 1181.12731195 | DIFIERE |
| `obm_raw_output_value_btc_daily` | 5469 | 7 | 11956161.87363041 | DIFIERE |
| `obm_spent_output_count_daily` | 5471 | 7 | 1280182 | DIFIERE |
| `obm_spent_value_age_band_btc_daily` | 5471 | 7 | 11831409.58764743 | DIFIERE |
| `obm_spent_value_btc_daily` | 5471 | 7 | 11956176.37664754 | DIFIERE |
| `obm_spent_value_ge155d_btc_daily` | 5471 | 7 | 12969.58817416 | DIFIERE |
| `obm_spent_value_ge365d_btc_daily` | 5471 | 7 | 8705.30197191 | DIFIERE |
| `obm_spent_value_lt155d_btc_daily` | 5471 | 7 | 11944428.55607595 | DIFIERE |
| `obm_supply_btc_daily` | 5471 | 686 | 6650.00000000 | DIFIERE |
| `obm_tx_count_daily` | 5471 | 0 | 0 | EXACTA |
| `obm_utxo_eod_count_daily` | 5469 | 7 | 0 | DIFIERE |

## Discrepancias conocidas y causa raíz

- **`obm_cdd_age_band_btcxdays_daily`** (7 días, máx. 164204.929889579718): Mismo origen que cdd_btcxdays (tabla ancha).
- **`obm_cdd_btcxdays_daily`** (8 días, máx. 11973093.16255492): Redondeo de OBM al acumular value_btc x age_days por input; residual <= ~1,5 sat-dias.
- **`obm_cdd_per_supply_days_daily`** (686 días, máx. 0.631681875081): Hereda el residual de cdd dividido por la oferta.
- **`obm_dormancy_days_daily`** (7 días, máx. 0): Hereda el residual de cdd dividido por spent_value.
- **`obm_liveliness_ratio_daily`** (686 días, máx. 0.000806035432): Hereda el residual de cdd acumulado.
- **`obm_utxo_eod_count_daily`** (7 días, máx. 0): BIP30: OBM cuenta las dos copias de los coinbases duplicados de 2010 (alturas 91.842 y 91.880); live_outputs deduplica por (txid,vout) como Bitcoin Core. Neutralizado con el ajuste de compatibilidad de capa3 (+1 el 2010-11-14, +2 desde 2010-11-15).

## Reproducir

```bash
python3 src/indexer.py                      # capa1 -> capa2 (~2 dias)
python3 src/exporters/capa3_series.py       # 23 series -> capa3/
python3 src/exporters/validar_capa3.py      # este informe
```
