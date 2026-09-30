# Fase 1 — Replicación de las 10 series OBM de nivel bloque/emisión/comisiones/hashrate

Fecha: 2026-09-16 · Datos: `/media/SSD4T/btc-etl` (capa1 + capa3) · Referencia: CSV de OBM v0.1.0
Código: `src/fase1_replicar.py` (extractor) y `src/comparar.py` (comparador)
Evidencia cruda: `salida/informe_comparacion.txt` · Series emitidas: `salida/*.csv`

Ventana de solape: **2009-01-01 → 2026-07-01** (6 391 días). Los parquet on-chain terminan el
**2026-07-01** (altura 956 213); OBM llega al 2026-09-11, así que los 72 días finales no son
comparables (aparecen como "solo en OBM").

## Resultado

| Serie | Solape | Idénticos | Numéricos (tol 1e-9) | Error máx. abs. | 1ª divergencia |
|---|---|---|---|---|---|
| `obm_block_count_daily` | 6391 | 6390 | **6390 (100.0 %)** | 70 | 2026-07-01 |
| `obm_tx_count_daily` | 6391 | 6390 | **6390 (100.0 %)** | 276 500 | 2026-07-01 |
| `obm_miner_revenue_btc_daily` | 6391 | 6380 | 6381 (99.8 %) | 386.35503709 | 2017-12-30 |
| `obm_block_weight_wu_daily` | 6389 | 6377 | 6377 (99.8 %) | 678 832 513 | 2026-06-20 |
| `obm_issuance_btc_daily` | 6391 | 6031 | 6099 (95.4 %) | 218.75 | 2011-05-18 |
| `obm_fees_btc_daily` | 6391 | 6026 | 6027 (94.3 %) | 386.35503709 | 2011-05-18 |
| `obm_fee_share_revenue_ratio_daily` | 6391 | 6024 | 6025 (94.3 %) | 0.49743754202 | 2011-05-18 |
| `obm_est7d_hashrate_ehs_daily` | 6389 | 1245 | 5138 (80.4 %) | 619.275250136 | 2009-01-10 |
| `obm_difficulty_eod_daily` | 6389 | 443 | 5008 (78.4 %) | 0.5 | 2009-12-30 |
| `obm_supply_btc_daily` | 6391 | 867 | 867 (13.6 %) | 189.79497096 | 2011-05-18 |

**Dos series se replican exactamente** (100 % de los 6 390 días comparables; el único día que falla
es el último, 2026-07-01, que en nuestra copia está **incompleto**: 73 bloques frente a 143 porque
la cadena local termina a media jornada).

## Causas de cada divergencia (verificadas)

### 1. `capa1` guarda `difficulty` como `int64` → trunca la parte fraccionaria
`capa1/blocks.difficulty` es `int64`, pero la dificultad de Bitcoin es fraccionaria.
- 2009-12-30: OBM `1.182899534313`, nosotros `1.000000000000` (truncado a 1).
- 2026-05-14: OBM `132472011079030.500000000000`, nosotros `132472011079030.000000000000`.
Esto explica `difficulty_eod` (78.4 %) y arrastra a `est7d_hashrate` (80.4 %), porque el hashrate se
calcula con `Σ(difficulty·2³²)`. **El error absoluto es ≤ 0.5, pero relativo enorme en los primeros
años.** Arreglo: cambiar la columna a `DOUBLE`/`DECIMAL` en capa1 y re-extraer (o leer del nodo).

### 2. `capa1` tiene un hueco contiguo de 1 500 bloques (954 500 – 955 999) y 455 alturas duplicadas
- 955 169 filas para 954 714 alturas distintas; el hueco corresponde a **~9 días sin datos
  (2026-06-20 → 2026-06-28)** ⇒ esas fechas dan 0 en `block_weight` y `NaN` en `difficulty`/`hashrate`.
- 455 alturas duplicadas entre 951 750 y 954 408 (cada una ×2).
- `capa3` **sí cubre** ese hueco (956 214 alturas, sin huecos), por eso `block_count`/`tx_count`
  salen al 100 % usando capa3.

### 3. `capa3` trae filas duplicadas y 980 alturas con copias divergentes
- 958 818 filas para 956 214 alturas: **2 604 filas duplicadas**.
- **980 alturas con copias que difieren en `fees_sats`** (rango 2026-05-05 → 2026-06-19), hasta ×100:
  altura 954 408 → copias con `3 324 569` y `319 149 138` sats (idéntico `time`, `block_hash`,
  `nTx` y `subsidy`; solo cambian las comisiones). El `ROW_NUMBER() ORDER BY time DESC` clásico
  empata y elige **al azar**.
- **Regla de desambiguación on-chain (implementada y validada)**: la copia correcta es la que cumple
  `subsidy_sats + fees_sats == coinbase real de capa1`. Requiere deduplicar `capa1/outputs` por
  `(txid, vout)` antes de sumar, porque **los outputs también tienen filas repetidas** (si no, el
  coinbase sale doblado y solo 1 006/3 038 copias validan; con dedup, las 980 alturas tienen copia válida
  y **0 alturas infladas sobreviven**).

### 4. `capa3` define `subsidy_sats` como subsidio **de protocolo**, no realizado
En `etl/capa3_block_metrics.py`: `subsidy_sats = get_subsidy(height)` (fórmula `50e8 >> halvings`) y
`fees_sats = coinbase_total − subsidy_sats` (recortado a ≥0). OBM, en cambio:
- `issuance = coinbase_output − fees` → **emisión realizada** (menor que el subsidio si el minero
  cobró menos de lo permitido);
- `fees` = suma real de `Σinputs − Σoutputs` por transacción no-coinbase.

En los bloques donde el minero **cobró menos** de lo permitido, nosotros infravaloramos comisiones y
sobrevaloramos emisión. Ejemplo: 2011-05-18, OBM `19.65344120` vs nosotros `19.64344120` (−0.01 BTC).
Como `supply` es la suma acumulada de la emisión, el sesgo **se acumula**: `obm_supply` cae al 13.6 %
con un error máximo de **189.79 BTC** (el total quemado histórico).

### 5. Comisiones infladas en 2026 y deficits en 2012
- `obm_fees_btc_daily`: 365 días divergentes de 6 391; delta acumulado **+1 292.80 BTC**.
- Por año: **2012 (212 días)**, 2013 (67), 2018 (65), 2026 (8). En 2011-2012 nuestras comisiones son
  **menores** (bloques con coinbase incompleto/subdeclarado); en 2026 son **muchísimo mayores**
  (2026-06-06: OBM `2.92` vs nosotros `387.09`; cada bloque declara ~3.22 BTC de comisiones cuando lo
  normal es ~0.02-0.05). El patrón `fees ≈ 2·subsidy − subsidy` apunta a **coinbase contado dos veces**
  en esos lotes del ETL, incluidas alturas que *no* están en las 980 divergentes (todas sus copias
  comparten el valor inflado, así que la regla de divergencia no las toca).

## Correcciones necesarias para la Fase 2

1. **No confiar en `capa3.fees_sats`**: recalcular el total de coinbase por altura desde `capa1`
   (`inputs.is_coinbase ⨝ outputs`, deduplicando por `(txid, vout)`) para **todas** las alturas, y
   derivar `fees = coinbase − subsidy_protocolo`; validar contra el hueco de 2026 y contra 2012.
2. **Emisión realizada**: requiere comisiones verdaderas por transacción (`Σinputs − Σoutputs`),
   que es exactamente el trabajo de la Fase 2 con `capa6` (o el join de `capa1`). Con eso se arreglan
   `issuance`, `supply`, `fee_share` y `miner_revenue`.
3. **`difficulty` a coma flotante** en capa1 (o lectura directa del nodo) para `difficulty_eod` y `hashrate`.
4. **Rellenar el hueco 954 500–955 999** (re-ejecutar la extracción de capa1 con el nodo, o ampliar
   `block_weight`/`difficulty` desde el nodo) — sin él, ~9 días nunca cuadrarán.
5. Comparar solo hasta **2026-07-01**, o ampliar los parquet on-chain a septiembre para igualar la
   ventana de OBM.

## Valor del ejercicio

El comparador y el formato de salida ya están validados: dos series coinciden el **100 %** de los días
y otras dos por encima del **99.8 %**. Las divergencias restantes **no son ruido**: cada una está
atribuida a un defecto concreto y localizado del ETL (truncado de dificultad, hueco de extracción,
duplicados con comisiones infladas, y subsidio de protocolo en lugar de emisión realizada), más un
sesgo acumulado de 189.79 BTC en la oferta.

---

# Revisión 2 (misma ronda de trabajo)

## Corrección aplicada: dificultad desde `bits`

`capa1/blocks` sí guarda `bits` (el objetivo compacto), del que la dificultad se deriva **sin pérdida**
con el algoritmo exacto de Bitcoin Core (`GetDifficulty`: `0xffff / mantisa` e iteración ×256/÷256 en
`double`). Sustituyendo el `int64` truncado por esta vía:

| Serie | Antes | Después |
|---|---|---|
| `obm_difficulty_eod_daily` | 5008/6389 (78.4 %), err. máx. **0.5** | **6380/6389 (99.9 %)**, err. máx. **0.05** |
| `obm_est7d_hashrate_ehs_daily` | 5138/6389 (80.4 %), err. máx. **619.28** | **6377/6389 (99.8 %)**, err. máx. **63.08** |

La primera divergencia se desplaza de 2009-12-30 a **2026-06-21**, es decir, al hueco de datos.
El residuo de 1e-12 en el último decimal (p. ej. `181.543289364051` vs `…050`) es la aritmética
`double` de Core frente a la racional exacta: relativo ~1e-15, irrelevante y ya dentro de tolerancia.

## El hueco de capa1 es irrecuperable desde parquet

El hueco **no está solo en `blocks`**: falta en las cuatro tablas de capa1.

| Tabla capa1 | Tamaño | Filas en 954 500–955 999 |
|---|---|---|
| `blocks` | 150 MB | 0 |
| `inputs` | 148 GB | 0 |
| `outputs` | 129 GB | 0 |
| `txs` | 98 GB | 0 |

Además, la extracción se detuvo en la altura 956 213 (2026-07-01), no en septiembre como OBM. Recuperar
esos 1 500 bloques exige el nodo (que ahora **no está corriendo**) o ampliar la extracción.

## Fase 2 lanzada

`src/fase2_spent.py` está ejecutándose en segundo plano (job `bash-2`) sobre las 129 GB de `outputs`
y 148 GB de `inputs`, con `temp_directory` en el NVMe del workspace (**950 GB libres**). Produce, con
aritmética **entera** (satoshi-segundos, `HUGEINT`) para no perder precisión:

- `datos/coinbase_por_altura.parquet` — coinbase real por altura (dedup por `txid,vout`);
- `datos/outputs_daily.parquet` y `datos/inputs_daily.parquet` — lado creación y lado gasto por día;
- `datos/spent_daily.parquet` — el join grande: valor gastado, nº de gastos, CDD en satoshi-segundos,
  umbrales 155/365 d y las **12 bandas** (valor y CDD) con las fronteras exactas del indexador oficial.

`src/fase2_series.py` convierte esos agregados en las 13 series restantes (2 de ellas anchas) y
`src/comparar.py` ya compara tablas anchas celda a celda.

---

# Revisión 3 — validaciones de la ronda 2

## Series ya verificadas contra OBM antes del join grande

| Serie | Solape | Numéricos | Nota |
|---|---|---|---|
| `obm_raw_output_value_btc_daily` | 6375 | **6372 (100.0 %)** | solo fallan los 3 días del hueco |
| `obm_utxo_eod_count_daily` | 6375 | 1528 (24.0 %) | falla desde 2009-10-09 **por 1 unidad** |

`raw_output_value` al 100 % **valida el recubrimiento limpio de ficheros** (3 819 de 3 822; los 3
restantes son re-ejecuciones totalmente contenidas), sin necesidad de dedup global.

## Causa del fallo de `utxo_eod_count`: salidas no gastables

`obm_utxo_eod_count_daily` es el tamaño del **UTXO set de Bitcoin Core**, que **excluye las salidas
provablemente no gastables** (`nulldata`/OP_RETURN y scripts > 10 000 bytes) y el coinbase del
génesis. Nuestro conteo las incluía. La muestra lo confirma: en el último lote de 214 bloques hay
**540 575 salidas `nulldata`** de 2,1 M (25 %), que se acumulan a lo largo de los años y explican un
error máximo de 227 135 527 salidas.

Los `script_type` presentes en capa1/outputs son: `pubkey`, `pubkeyhash`, `scripthash`, `multisig`,
`witness_v0_keyhash`, `witness_v0_scripthash`, `witness_v1_taproot`, `witness_unknown`, `anchor` y
`nulldata` (el filtro a aplicar es `script_type <> 'nulldata'`).

## Identidad que corrige emisión y comisiones

Sumando por día la identidad contable de cada bloque:

```text
suma(inputs) = suma(outputs no-coinbase) + fees
fees_true_d  = spent_value_d - (outputs_value_d - coinbase_d)
issuance_d   = coinbase_d - fees_true_d        <- emision REALIZADA, como OBM
```

Con `coinbase_por_altura.parquet` (ya calculado: 954 714 alturas, **20 346 374.95944836 BTC**),
`outputs_daily.parquet` y `spent_value_d`, esto arregla `fees`, `issuance`, `supply`, `miner_revenue`
y `fee_share` sin necesidad del índice de OBM. Implementado en `src/series_corregidas.py`.

## Comprobación cruzada de totales

| Concepto | Nuestra lectura limpia de capa1 | Referencia del proyecto (`capa6`) |
|---|---|---|
| salidas creadas | 3 791 522 950 | 3 829 756 998 (+1.0 %) |
| inputs no-coinbase | 3 398 267 993 | 3 425 151 447 (+0.8 %) |

Nuestra cifra es ~1 % menor **sin** el hueco de 1 500 bloques (0.16 %). La diferencia apunta a que
`capa6` arrastra filas duplicadas de las re-ejecuciones, igual que `capa3` (2 604 filas) y `capa1`
(455 alturas). Es coherente con el patrón de duplicados ya documentado y conviene revisarlo.

## Estado del join grande

`src/fase2_buckets.py` particiona ambos lados en **64 buckets por hash(txid)**, en 8 trozos de
ficheros para acotar la memoria (el join directo y el `PARTITION_BY` global morían por OOM en ~11 GB).
En curso: 6/8 trozos de `spends` escritos, 64 buckets por trozo, 37 GB, 912 GB libres.
Después: paso C (64 joins bucket a bucket) y paso D (merge diario), con las **12 bandas de edad** y
el CDD en **satoshi-segundos enteros** para que el redondeo final sea exacto.


