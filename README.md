# OBM — Réplica verificable de Open Bitcoin Metrics v0.1.0

Pipeline propio, derivado **íntegramente de un nodo completo de Bitcoin Core**, que reproduce
las 23 series diarias de [Open Bitcoin Metrics (OBM) v0.1.0](https://github.com/diegorllanos/open-bitcoin-metrics)
y sirve de base para análisis on-chain y para una **auditoría independiente de reproducibilidad**.

## Arquitectura — 4 capas

```
        Bitcoin Core (nodo completo · txindex=1 · sin poda)   v26.0.0
                        │ JSON-RPC (getblock, getblockheader, ...)
        ┌───────────────▼───────────────────────────────────────┐
capa1/  │ etl/capa1_btccore_parquet.py                          │  blocks · txs
 386 GB │ parquet semanal (zstd), con clave primaria por tabla  │  inputs · outputs
        └───────────────┬───────────────────────────────────────┘
                        │
        ┌───────────────▼───────────────────────────────────────┐
capa2/  │ src/indexer.py  (spent-output indexer, §3.4 del paper)│  live_outputs.sqlite
  18 GB │ resuelve cada input contra su output previo           │  daily_aggregates_*.parquet
        │ commit por semana + journal weeks_done (atómico)      │  age_band_aggregates_*.parquet
        └───────────────┬───────────────────────────────────────┘
                        │
        ┌───────────────▼───────────────────────────────────────┐
capa3/  │ src/exporters/capa3_series.py                         │  obm_<serie>_daily.csv  ×23
  13 MB │ 21 series largas + 2 tablas anchas, esquema OBM exacto│  VALIDACION.md + figuras
        │ src/exporters/validar_capa3.py                        │
        └───────────────┬───────────────────────────────────────┘
                        │
        ┌───────────────▼───────────────────────────────────────┐
capa4/  │ mercado (pendiente)                                   │  klines diarios (precio)
        │ habilita métricas de valoración: NVT, MVRV, hashprice │  → familia de valoración
        └───────────────────────────────────────────────────────┘
```

`obm_reference/` guarda el **snapshot oficial** con el que se valida: `metrics/` (los 23 CSV),
`paper/` (el manuscrito) y `tools/` (el código de los autores).

## Orden de ejecución

```bash
# 1) capa1 — ETL desde el nodo (opción 1 = reset, 2 = continuar)
python3 etl/capa1_btccore_parquet.py

# 2) capa2 — indexer capa1 → capa2 (opción 1 = reset, 2 = continuar)
python3 src/indexer.py

# 3) capa3 — dificultad exacta del nodo (481 llamadas RPC), y las 23 series
python3 src/exporters/fix_difficulty_rpc.py
python3 src/exporters/capa3_series.py

# 4) validación frente a la referencia oficial
python3 src/exporters/validar_capa3.py        # -> capa3/VALIDACION.md + figuras/
```

Utilidades de mantenimiento (uso puntual, documentadas en el informe de auditoría):
`etl/reparticionar_semanas.py` (re-particionado de semanas por timestamps no monótonos) y
`src/reparar_wrap_2017.py` (reparación del desbordamiento de 32 bits del contador de progreso).

## Estado

| Capa | Estado |
|---|---|
| capa1 | completa: 968.458 bloques (0..968.457), 926 semanas × 4 tablas, 0 huecos, `--validate` ✓ |
| capa2 | **en curso** (2021-W50 → 2026-W38); invariante `filas == Σinsertadas − Σgastadas` ✓ |
| capa3 | las 23 series generadas; validación en `capa3/VALIDACION.md` |
| capa4 | pendiente (precio diario) |

## Validación frente a OBM

Comparación día a día contra `obm_reference/metrics`, con tolerancia derivada de los decimales
publicados de cada serie:

- **5 series de bloque** (`block_count`, `block_weight_wu`, `tx_count`, `difficulty_eod`,
  `est7d_hashrate`): **bit-exactas en las 6.461 fechas** de la referencia.
- Series de UTXO y coin-age: exactas sobre el tramo procesado, salvo un residuo de
  **≤1,5 sat-días** en 1,5% de los días de `cdd_btcxdays` (redondeo en coma flotante de OBM).
- `utxo_eod_count`: OBM cuenta las **dos copias** de los coinbases duplicados de 2010 (BIP30);
  `capa3` aplica el ajuste documentado (+1 el 2010-11-14, +2 desde el 2010-11-15).
  `--no-bip30` publica el valor "real" sin ese ajuste.

Detalle completo, causa raíz de cada discrepancia y las 6 lecciones de ingeniería en la
**auditoría de reproducibilidad** (en preparación).

## Requisitos

- Bitcoin Core sincronizado (mainnet, `txindex=1`, sin poda) — validado con v26.0.0
- Python 3.14 con `pyarrow`, `pandas`, `numpy`, `duckdb` (y `matplotlib` para las figuras)
- ~450 GB libres para capa1 + capa2

## Limitaciones

- La referencia es un **release rodante** (v0.1.0): la validación es un snapshot reproducible.
- El empalme de precios de capa4 mezclará venues distintos (documentado cuando exista).
- `supply` es emisión realizada acumulada; no incluye monedas perdidas ni el ajuste por
  outputs no gastables.
