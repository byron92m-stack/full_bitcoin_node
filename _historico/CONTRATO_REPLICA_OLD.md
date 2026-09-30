# Contrato de réplica — Open Bitcoin Metrics v0.1.0

Documento de referencia de la Fase 0. Fuentes: los 23 `README.md` oficiales del repo
`diegorllanos/open-bitcoin-metrics` (rama `main`), `tools/spent_output_indexer/README.md`
y el código de `obm_spent_output_indexer.py`. Los CSV publicados llegan hasta **2026-09-11**.

---

## A. Convenciones globales (aplican a las 23 series)

| Regla | Valor exacto |
|---|---|
| Asignación de fecha | `date = UTCDate(block_time)` — **`block_time`, no `mediantime`** |
| Calendario | 2009-01-01 → fecha final; una fila por día UTC, sin huecos |
| Esquema CSV | `date,series_id,value,unit,frequency,release_version` (21 series) |
| Excepción de esquema | `obm_spent_value_age_band_btc_daily` y `obm_cdd_age_band_btcxdays_daily`: **tabla ancha**, 12 columnas de banda + `unit,frequency,release_version` |
| Precisión | 8 decimales: series en BTC y BTC-days · 12 decimales: ratios, dormancy, difficulty, hashrate, `cdd_per_supply`, bandas de CDD · enteros sin decimales: conteos |
| Aritmética | `Decimal` de alta precisión (`getcontext().prec = 50` en el indexador) — **no float** |
| Valor indefinido | campo vacío o `NaN`; **no** se escribe 0 |
| Denominador cero | ratio → valor ausente (vacío), nunca 0 |
| Edad de un output | `age = max(0, (spent_time - created_time) / 86400)` en **días fraccionarios** sobre timestamps crudos |

## B. Las 23 series: fórmula y fuente en btc-etl

Cobertura = filas del CSV oficial descargado (6463 ≈ incluye 2009-01-01/02; 6461 = arranca el 01-03).

| # | Serie | Fórmula OBM | Fuente en tu proyecto | Unidad | Dec. | Cobertura |
|---|---|---|---|---|---|---|
| 1 | `obm_block_count_daily` | `\|B_d\|` | `capa1/blocks`: count por día | blocks | 0 | 6463 |
| 2 | `obm_block_weight_wu_daily` | `Σ weight_b` | `capa1/blocks.weight` | WU | 0 | 6461 |
| 3 | `obm_tx_count_daily` | `Σ nTx_b` (incluye coinbase) | `capa1/blocks.nTx` | transactions | 0 | 6463 |
| 4 | `obm_difficulty_eod_daily` | `Difficulty` del bloque de **mayor altura** del día | `capa1/blocks.difficulty` | difficulty | 12 | 6461 |
| 5 | `obm_est7d_hashrate_ehs_daily` | `Σ(Diff_b·2^32)/(max_ts−min_ts)` ventana 7 d / 1e18 | `capa1/blocks` | EH/s | 12 | 6461 |
| 6 | `obm_issuance_btc_daily` | `Σ(coinbase_output_b − fees_b)` | `capa1 outputs+inputs(is_coinbase)` o `capa3.subsidy_sats` | BTC | 8 | 6463 |
| 7 | `obm_supply_btc_daily` | `cumsum(issuance)` desde 2009-01-01 | derivada de (6) | BTC | 8 | 6463 |
| 8 | `obm_fees_btc_daily` | `Σ_j(Σin_j − Σout_j)` solo no-coinbase | `capa3.fees_sats` o `capa1` | BTC | 8 | 6463 |
| 9 | `obm_miner_revenue_btc_daily` | `Σ coinbase_output_b` | `capa3` (subsidy+fees) o `capa1` | BTC | 8 | 6463 |
| 10 | `obm_fee_share_revenue_ratio_daily` | `fees/(issuance+fees)` | derivada de (6)+(8) | ratio | 12 | 6463 |
| 11 | `obm_raw_output_value_btc_daily` | `Σ out_j` solo no-coinbase | `capa1/outputs` ⨝ txids no-coinbase | BTC | 8 | 6461 |
| 12 | `obm_spent_output_count_daily` | nº de prev-outputs gastados por inputs no-coinbase | `capa6_spends` / `capa1/inputs` | outputs | 0 | 6463 |
| 13 | `obm_spent_value_btc_daily` | `Σ value_i` de prev-outputs gastados | `capa6_spends ⨝ capa6_creates` | BTC | 8 | 6463 |
| 14 | `obm_cdd_btcxdays_daily` | `Σ value_i · age_i` | ídem (13) + `block_time` de creación | BTC-days | 8 | 6461 |
| 15 | `obm_dormancy_days_daily` | `CDD_d / spent_value_d` | derivada (13)/(14) | days | 12 | 6463 |
| 16 | `obm_cdd_per_supply_days_daily` | `CDD_d / supply_d` | derivada (7)/(14) | days | 12 | 6459 |
| 17 | `obm_liveliness_ratio_daily` | `cumsum(CDD)/cumsum(supply)` | derivada (7)/(14) | ratio | 12 | 6461 |
| 18 | `obm_spent_value_ge155d_btc_daily` | `Σ value_i·1{age_i ≥ 155 d}` | ídem (13) con umbral | BTC | 8 | 6463 |
| 19 | `obm_spent_value_ge365d_btc_daily` | `Σ value_i·1{age_i ≥ 365 d}` | ídem (13) con umbral | BTC | 8 | 6463 |
| 20 | `obm_spent_value_lt155d_btc_daily` | `spent_value − ge155d` (negativos≈0 → 0) | derivada (13)−(18) | BTC | 8 | 6463 |
| 21 | `obm_utxo_eod_count_daily` | UTXOs vivos tras el bloque de mayor altura del día | `cumsum(creates−spends)` | outputs | 0 | 6461 |
| 22 | `obm_spent_value_age_band_btc_daily` | 12 bandas de `value_i` | ídem (13) por banda | BTC | 8 | 6463 |
| 23 | `obm_cdd_age_band_btcxdays_daily` | 12 bandas de `value_i·age_i` | ídem (14) por banda | BTC-days | 12 | 6463 |

**Parentesco útil**: `raw_output_value` + `miner_revenue` = valor bruto de salida total del día; y `cdd_per_supply = CDD/supply` es exactamente el "CDD per supply" del paper.

## C. Bandas de edad — valores exactos (`AGE_BANDS`, intervalos semiabiertos `[lower, upper)`)

| Etiqueta | Desde (s) | Hasta (s) | Desde (días) | Hasta (días) |
|---|---|---|---|---|
| `0d_1d` | 0 | 86 400 | 0 | 1 |
| `1d_1w` | 86 400 | 604 800 | 1 | 7 |
| `1w_1m` | 604 800 | 2 592 000 | 7 | 30 |
| `1m_3m` | 2 592 000 | 7 776 000 | 30 | 90 |
| `3m_6m` | 7 776 000 | 15 552 000 | 90 | 180 |
| `6m_1y` | 15 552 000 | 31 536 000 | 180 | 365 |
| `1y_2y` | 31 536 000 | 63 072 000 | 365 | 730 |
| `2y_3y` | 63 072 000 | 94 608 000 | 730 | 1095 |
| `3y_5y` | 94 608 000 | 157 680 000 | 1095 | 1825 |
| `5y_7y` | 157 680 000 | 220 752 000 | 1825 | 2555 |
| `7y_10y` | 220 752 000 | 315 360 000 | 2555 | 3650 |
| `10y_plus` | 315 360 000 | ∞ | 3650 | ∞ |

Convenciones: **año = 365 días**, **mes = 30 días**; la banda se decide sobre `age_seconds`
**entero** (`age_band_for_seconds`), con `lower` inclusivo y `upper` exclusivo. El umbral de
155 días usa el mismo criterio de segundos (`155·86400`). Ojo: `6m_1y` llega hasta 365 d, así que
"1 año" = 365 d exactos.

## D. Casos límite que hay que respetar (o la comparación fallará)

1. **Txid coinbase duplicados pre-BIP30**: el indexador **sobrescribe** el outpoint anterior con el
   posterior (*last-write-wins*). El output sobrescrito **no se cuenta como gastado**, no genera
   spent value ni CDD. Es la causa nº 1 de diferencias en el UTXO set temprano.
2. **Días sin bloque**: 2009-01-01 y 2009-01-02 no tienen bloques (el génesis es del
   **2009-01-03 18:15:05 UTC**). Según la serie: las de flujo escriben **0 con fila presente**
   (`block_count`, `tx_count`, `fees`, `issuance`, `supply`…), y las que necesitan un bloque
   **omiten la fila** (`block_weight`, `difficulty_eod`, `utxo_eod_count`, `est7d`, `raw_output_value`,
   `cdd_btcxdays`, `liveliness` → 6461 filas). Hay que reproducir esa cobertura exacta.
3. **`est7d_hashrate`**: ventana = 7 días naturales que terminan a las 23:59:59 UTC del día `d`;
   `elapsed = max_ts − min_ts` de los bloques de la ventana (**no** `7·86400`). El propio README
   prohíbe derivarla de `difficulty_eod`, porque necesita la dificultad bloque a bloque alrededor
   de los retargets.
4. **`lt155d`** es una resta: `spent_value − ge155d`, con tolerancia a negativos diminutos → 0 por
   ruido de redondeo.
5. **Exclusiones de coinbase**: `fees`, `raw_output_value`, `spent_value`, `spent_output_count`, CDD
   y bandas **excluyen** la coinbase; `miner_revenue`, `issuance` y `tx_count` **la incluyen**.
6. **Ratios con denominador 0** → vacío (no 0). `cdd_per_supply` termina el **2026-09-09**, dos días
   antes que el resto: probablemente días finales con valor ausente.

## E. Fuentes en btc-etl: qué usar y qué cuesta

| Ruta | Fuente | Series | Coste |
|---|---|---|---|
| **A** | `capa1/blocks` (time, nTx, weight, difficulty, mediantime) + `capa3_block_metrics` (subsidy_sats, fees_sats) | 1-10 (10 series de bloque, emisión, comisiones, hashrate) | minutos |
| **B** | `capa6_creates ⨝ capa6_spends` (con `temp_directory` en disco, no en 20 GB de RAM) | 11-23 (UTXO y coin-age) | horas |
| **C (alternativa)** | `capa1/inputs` (tiene `prev_txid`, `prev_vout`, **`is_coinbase`**) ⨝ `capa1/outputs` (`value_sats`) | 11-23 sin tocar capa6 | por medir |

`capa1` trae `blocks` + `inputs(is_coinbase)` + `outputs` + `txs` (3 822 ficheros por tabla), lo que
permite resolver coinbase y valores gastados **sin** los 268 GB de capa6 — pero **sin** el `prefix`
que capa6 usa para desambiguar txids duplicados, que es justo el caso límite nº 1.

## F. Incógnitas a resolver en Fase 1

1. Qué codifica exactamente `capa6.prefix` y si su semántica coincide con el *last-write-wins* de OBM.
2. Si `capa3.subsidy_sats` es el subsidio de protocolo (`50e8 >> halvings`, como sugiere
   `get_subsidy`) — en tal caso `issuance` sale directo, y `miner_revenue = subsidy + fees`.
3. Confirmar el patrón de cobertura por serie (¿omite filas o escribe vacíos?) al reproducir los
   CSV, comparando fila a fila.
4. `capa6_creates` **no tiene** `is_coinbase`: identificarlo vía `capa1/inputs` por `txid`.
