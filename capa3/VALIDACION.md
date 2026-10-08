# Validación de capa3 frente a la referencia OBM v0.1.0

Generado: 2026-10-08 11:09

- Cobertura de capa3: hasta **2026-10-08**
- Comparación limitada a: **2026-10-04**
- Cobertura de la referencia: hasta **2026-09-11**
- Series exactas: **21/23**
- Tolerancia: **medio último decimal publicado** por la referencia, derivado del propio fichero (por serie y, en las tablas anchas, por columna). La columna `dec` indica los decimales usados.

| Serie | Días comparados | Días con diferencia | Error máximo | dec | Veredicto |
|---|---:|---:|---:|---:|---|
| `obm_block_count_daily` | 6463 | 0 | 0 | 0 | EXACTA |
| `obm_block_weight_wu_daily` | 6461 | 0 | 0 | 0 | EXACTA |
| `obm_cdd_age_band_btcxdays_daily` | 6463 | 111 | 1E-12 | 12 | DIFIERE |
| `obm_cdd_btcxdays_daily` | 6461 | 1 | 1E-8 | 8 | DIFIERE |
| `obm_cdd_per_supply_days_daily` | 6459 | 0 | 0 | 12 | EXACTA |
| `obm_difficulty_eod_daily` | 6461 | 0 | 0 | 12 | EXACTA |
| `obm_dormancy_days_daily` | 6463 | 0 | 0 | 12 | EXACTA |
| `obm_est7d_hashrate_ehs_daily` | 6461 | 0 | 0 | 12 | EXACTA |
| `obm_fee_share_revenue_ratio_daily` | 6463 | 0 | 0 | 12 | EXACTA |
| `obm_fees_btc_daily` | 6463 | 0 | 0 | 8 | EXACTA |
| `obm_issuance_btc_daily` | 6463 | 0 | 0 | 8 | EXACTA |
| `obm_liveliness_ratio_daily` | 6461 | 0 | 0 | 12 | EXACTA |
| `obm_miner_revenue_btc_daily` | 6463 | 0 | 0 | 8 | EXACTA |
| `obm_raw_output_value_btc_daily` | 6461 | 0 | 0 | 8 | EXACTA |
| `obm_spent_output_count_daily` | 6463 | 0 | 0 | 0 | EXACTA |
| `obm_spent_value_age_band_btc_daily` | 6463 | 0 | 0 | 8 | EXACTA |
| `obm_spent_value_btc_daily` | 6463 | 0 | 0 | 8 | EXACTA |
| `obm_spent_value_ge155d_btc_daily` | 6463 | 0 | 0 | 8 | EXACTA |
| `obm_spent_value_ge365d_btc_daily` | 6463 | 0 | 0 | 8 | EXACTA |
| `obm_spent_value_lt155d_btc_daily` | 6463 | 0 | 0 | 8 | EXACTA |
| `obm_supply_btc_daily` | 6463 | 0 | 0 | 8 | EXACTA |
| `obm_tx_count_daily` | 6463 | 0 | 0 | 0 | EXACTA |
| `obm_utxo_eod_count_daily` | 6461 | 0 | 0 | 0 | EXACTA |

## Discrepancias conocidas y causa raíz

- **`obm_cdd_age_band_btcxdays_daily`** (111 días, máx. 1E-12): 111 dias / 113 celdas con 1 ULP del ultimo decimal publicado (1e-12). Son empates EXACTOS en el 13.o decimal: nuestra cifra es el redondeo half-even del valor exacto en las 113 celdas (verificado) y la de OBM queda un ULP por debajo.
- **`obm_cdd_btcxdays_daily`** (1 días, máx. 1E-8): 1 dia (2010-05-22) con 1 sat-dia (1e-8 BTC-dias) de diferencia: es el residuo del redondeo propio de OBM al acumular el CDD (en un tramo medido de 2.622 dias el residuo llega a ~1,5 sat-dias y afecta a ~2,7% de los dias).

## Reproducir

```bash
python3 src/indexer.py                      # capa1 -> capa2 (~2 dias)
python3 src/exporters/capa3_series.py       # 23 series -> capa3/
python3 src/exporters/validar_capa3.py      # este informe
```
