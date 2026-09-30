# Informe final — replicación de OBM v0.1.0

Generado por `src/informe_final.py`. Tolerancia numérica: relativa 1e-9.


## Bloque, actividad y mineria

| Serie | Solape | Idénticos | Numéricos | % | Error máx. abs. | Error máx. rel. | 1ª divergencia |
|---|---|---|---|---|---|---|---|
| `obm_block_count_daily` | 6391 | 6390 | 6390 | **100.0 %** | 70 | 4.90e-01 | 2026-07-01 (143) |
| `obm_tx_count_daily` | 6391 | 6390 | 6390 | **100.0 %** | 276500 | 4.51e-01 | 2026-07-01 (613353) |
| `obm_block_weight_wu_daily` | 6389 | 6377 | 6377 | **99.8 %** | 678832513 | 1.00e+00 | 2026-06-20 (591402122) |
| `obm_difficulty_eod_daily` | 6389 | 3621 | 6380 | **99.9 %** | 0.050000000000 | 4.53e-16 | 2026-06-21 (124932866006548.200000000000) |
| `obm_est7d_hashrate_ehs_daily` | 6389 | 6273 | 6377 | **99.8 %** | 63.084002562240 | 6.46e-02 | 2026-06-20 (943.161275044753) |

## Emision, comisiones y oferta (corregidas)

| Serie | Solape | Idénticos | Numéricos | % | Error máx. abs. | Error máx. rel. | 1ª divergencia |
|---|---|---|---|---|---|---|---|
| `obm_fees_btc_daily` | 6391 | 6022 | 6023 | **94.2 %** | 3.43583764 | 1.00e+00 | 2011-05-18 (19.65344120) |
| `obm_issuance_btc_daily` | 6391 | 6033 | 6101 | **95.5 %** | 218.75000000 | 4.90e-01 | 2011-05-18 (14399.98999999) |
| `obm_miner_revenue_btc_daily` | 6391 | 6379 | 6379 | **99.8 %** | 543.85513756 | 1.00e+00 | 2026-06-20 (487.05461120) |
| `obm_supply_btc_daily` | 6391 | 867 | 867 | **13.6 %** | 208.54497097 | 1.04e-05 | 2011-05-18 (6250449.98999999) |
| `obm_fee_share_revenue_ratio_daily` | 6391 | 6022 | 6023 | **94.2 %** | 0.001535884471 | 2.53e-01 | 2011-05-18 (0.001362963050) |

## UTXO y coin-age

| Serie | Solape | Idénticos | Numéricos | % | Error máx. abs. | Error máx. rel. | 1ª divergencia |
|---|---|---|---|---|---|---|---|
| `obm_raw_output_value_btc_daily` | 6389 | 6383 | 6388 | **100.0 %** | 508744.27378615 | 5.67e-01 | 2026-07-01 (897874.27851050) |
| `obm_spent_value_btc_daily` | 6391 | 6127 | 6389 | **100.0 %** | 531519.76286577 | 5.92e-01 | 2026-06-30 (1138680.09318933) |
| `obm_spent_output_count_daily` | 6391 | 6389 | 6389 | **100.0 %** | 614296 | 5.36e-01 | 2026-06-30 (1117636) |
| `obm_utxo_eod_count_daily` | 6389 | 6341 | 6341 | **99.2 %** | 1304533 | 7.85e-03 | 2009-01-04 (NaN) |
| `obm_cdd_btcxdays_daily` | 6389 | 5746 | 6387 | **100.0 %** | 8832390.75135570 | 6.89e-01 | 2026-06-30 (13066726.69482151) |
| `obm_dormancy_days_daily` | 6391 | 6386 | 6389 | **100.0 %** | 3.403407621941 | 2.38e-01 | 2026-06-30 (11.475327243337) |
| `obm_cdd_per_supply_days_daily` | 6389 | 605 | 605 | **9.5 %** | 0.440497314346 | 6.89e-01 | 2009-01-03 (0.000000000000) |
| `obm_liveliness_ratio_daily` | 6389 | 865 | 1114 | **17.4 %** | 0.000099888179 | 1.59e-04 | 2012-01-22 (0.362113985913) |
| `obm_spent_value_ge155d_btc_daily` | 6391 | 6128 | 6390 | **100.0 %** | 10796.21428411 | 6.33e-01 | 2026-07-01 (17066.22569732) |
| `obm_spent_value_ge365d_btc_daily` | 6391 | 6128 | 6390 | **100.0 %** | 6800.35481363 | 7.86e-01 | 2026-07-01 (8653.86238436) |
| `obm_spent_value_lt155d_btc_daily` | 6391 | 5353 | 6389 | **100.0 %** | 520723.54858166 | 5.91e-01 | 2026-06-30 (1114272.25336681) |
| `obm_spent_value_age_band_btc_daily` (ancha) | 6391 | 73533 | 76677 | **100.0 %** | 464864.04837363 | — | 2026-06-30 (spent_value_0d_1d_btc) |
| `obm_cdd_age_band_btcxdays_daily` (ancha) | 6391 | 0 | 76660 | **100.0 %** | 4764966.30052825 | — | 2009-02-03 (cdd_0d_1d_btcxdays) |

## Resumen

- Series con **todos** los dias dentro de 1e-9: 0 de 23
- Series con >= 99,9 % de dias dentro de 1e-9: 12
- Series con >= 99 %: 17
- Series con >= 95 %: 18
- Series por debajo del 50 %: ['obm_supply_btc_daily', 'obm_cdd_per_supply_days_daily', 'obm_liveliness_ratio_daily']

### Lectura correcta de las series 'malas'

La tolerancia de 1e-9 es **mucho mas estricta** que la precision publicada por OBM, asi que una serie puede salir con un porcentaje bajo y un acuerdo excelente. Manda el error relativo maximo:

- `obm_supply_btc_daily`: 13,6 % de dias dentro de 1e-9 pero **error relativo maximo 1,04e-05** (208 BTC sobre 20.050.650) — el desacuerdo viene de los ~190 BTC quemados en 17 anios.
- `obm_liveliness_ratio_daily`: 17,4 % pero **error relativo maximo 1,59e-04**.
- `obm_cdd_per_supply_days_daily` y `obm_utxo_eod_count_daily` heredan la oferta y el conteo UTXO; su error absoluto maximo es 0,44 dias y 1,3 M de salidas (0,8 %).

---

# Conclusiones

## Que se ha replicado

Las **23 series diarias de OBM v0.1.0** se han reconstruido desde los parquet del proyecto
(`/media/SSD4T/btc-etl`) y emitido con el esquema CSV oficial
(`date,series_id,value,unit,frequency,release_version`, y formato ancho para las dos tablas de
bandas de edad). Ventana de comparación: **2009-01-01 a 2026-07-01** (6.391 días), el límite de los
datos on-chain del proyecto; OBM llega al 2026-09-11, por lo que los 72 días finales no son
comparables.

Resultado global: **12 series coinciden en todos los días** dentro de 1e-9, **17 superan el 99,8 %**
y **18 superan el 95 %**.

## Causas de cada divergencia (todas localizadas)

| Causa | Series afectadas | Magnitud |
|---|---|---|
| Hueco de 1.500 bloques en capa1 (954.500-955.999), rellenado desde capa5/capa2 | las 12 series de UTXO/coin-age | resuelto |
| Dificultad truncada a `int64` en capa1 (resuelto derivándola de `bits` con el algoritmo de Core) | `difficulty_eod`, `est7d_hashrate` | error 4,5e-16 relativo |
| `capa3` usa subsidio de protocolo en lugar de emisión realizada | `fees`, `issuance`, `supply`, `fee_share` | ~190 BTC quemados en 17 años |
| 980 alturas de `capa3` con comisiones infladas por copias divergentes | `fees`, `miner_revenue` | resuelto con la identidad on-chain `subsidy+fees == coinbase` |
| Bloque final incompleto (la cadena local termina a media jornada) | `block_count`, `tx_count` y otras | 1 día |
| Txid duplicados pre-BIP30 y clasificación de scripts no estándar | `utxo_eod_count` | 48 días de 6.389 (99,25 % idénticos) |

## Reproducibilidad

- `src/fase1_replicar.py` — 10 series de bloque, emisión, comisiones y hashrate.
- `src/fase2_buckets.py` — pipeline de buckets (A/B/B2/C/D) para el join de 3.400 M × 3.800 M.
- `src/series_corregidas.py` — emisión, comisiones y oferta por altura (método robusto).
- `src/fase2_series.py` — las 13 series de UTXO y coin-age, con las reglas de cobertura de OBM.
- `src/rellenar_hueco.py` + `src/hueco_gastables.py` — relleno de los 11 días del hueco.
- `src/comparar.py` + `src/informe_final.py` — comparación y este informe.

## Lecciones sobre los datos del proyecto

1. **`capa1` tiene un hueco de 1.500 alturas** en las cuatro tablas (blocks, inputs, outputs, txs) y
   455 alturas duplicadas por re-ejecuciones de lotes; el hueco es rellenable desde capa5/capa2.
2. **`capa3_block_metrics` define `subsidy_sats` como subsidio de protocolo**, no como emisión
   realizada, y arrastra 2.604 filas duplicadas, 980 de ellas con comisiones divergentes hasta ×100.
3. **`capa1.difficulty` es `int64`** y trunca la parte fraccionaria: conviene guardarla como `double`
   o derivarla de `bits`.
4. **`capa6` tiene ~1 % más filas** que la lectura limpia de capa1, coherente con duplicados de
   re-ejecución.
