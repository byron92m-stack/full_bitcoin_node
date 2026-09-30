# Auditoría de reproducibilidad de OBM v0.1.0 — hallazgos

Material bruto para el Paquete A (`AUDITORIA.md`). **Todos los números están medidos**; la
columna "reproducir" indica el script o comando que los regenera. Cero números a mano.

**Contexto**: reimplementación independiente (nodo propio, código propio, cero líneas de los
autores de OBM) del dataset descrito en *"Open Bitcoin Metrics: Verifiable Full-Node-Derived
Bitcoin Time Series for Economic Research"* (arXiv:2607.03124v1, jul-2026). Referencia de
comparación: `obm_reference/metrics/` (los 23 CSV oficiales, v0.1.0).

## Resultado global

`python3 src/exporters/validar_capa3.py` (comparación día a día, tolerancia = decimales publicados)

| Bloque de series | Resultado |
|---|---|
| 5 series de bloque (`block_count`, `block_weight_wu`, `tx_count`, `difficulty_eod`, `est7d_hashrate`) | **bit-exactas en las 6.461 fechas** de la referencia |
| Series de UTXO y coin-age | exactas en el tramo procesado; `utxo_eod_count` exacta con el ajuste BIP30 |
| `cdd_btcxdays` | ≤**1,5 sat-días** en ~1,5% de los días (redondeo float de OBM) |

Esperado al cerrar capa2: **22/23 bit-exactas** + 1 con residuo de último dígito.

---

## F1 — BIP30: la referencia cuenta las DOS copias (convención documentada en OBM)

**Hecho.** OBM §3.4: *"when the indexer encounters such a duplicate live outpoint, it overwrites
the earlier entry with the later one and records the event in metadata. The overwritten output is
not counted as spent and therefore does not generate spent value or CDD."*

**Nuestra implementación** usa `INSERT OR IGNORE` (*first-write-wins*), así que `live_outputs`
mantiene la unicidad `(txid,vout)` como Bitcoin Core.

**Medición.** La serie oficial va **+1 el 2010-11-14** y **+2 desde el 2010-11-15** (1.429 días
con diff=+2 en el tramo 2009-2014). Coincide exactamente con los dos coinbases duplicados:
`d5d27987…:0` en las alturas 91.812/91.842 y `e3bf3d07…:0` en 91.722/91.880.

**Impacto acotado.** Ninguno de esos dos outputs se gasta **nunca** (verificado buscando inputs
que los referencien) → la única consecuencia es el **conteo**; ninguna otra métrica se ve afectada.

**Arreglo.** Ajuste explícito y reversible en capa3 (`capa3_series.py`, flag `--no-bip30`) →
`utxo_eod_count` pasa a ser **exacta en las 4.715 fechas comparadas**.
*Reproducir*: `python3 src/exporters/validar_capa3.py` (días con diff≠0).

## F2 — Precisión del CDD: truncar por input cuesta 1,8e-9

**Hecho.** OBM: `CDD_i = V_i·A_i` con `A_i = (t_spend−t_create)/86400` **fraccionario**, guardado
"as satoshi-days" (A.4). Truncar por input (`(V·Δt)//86400`) pierde hasta 1 sat-día por input.

**Medición (2.622 días, 2009-01-03 → 2016-03-13):**

| | días con diferencia | error máx. (BTC-días) | error rel. máx. |
|---|---|---|---|
| truncado por input | 2.320 | 3,33e-3 | 1,77e-9 |
| **exacto** (2 acumuladores) | **70** | **1,49e-8** | **8,9e-11** |

→ **223.480× menos error**; el residuo restante es el redondeo en coma flotante de OBM.

**Arreglo.** Columnas `cdd_rem_86400` (+ `cdd_ge155d_rem_86400`, `cdd_ge365d_rem_86400` en daily,
y `cdd_rem_86400` en bandas): exacto = `cdd_sat_days + cdd_rem_86400/86400`.

**Cota int64 verificada con datos reales**: máximo diario de CDD = 518.269.161,94 BTC-días
(2024-05-28) = 5,18e16 sat-días → **178× de holgura**; la columna de restos ≤2,16e11 → **4,3e7×**.
*Reproducir*: comparar `cdd_sat_days` vs `cdd_sat_days + cdd_rem_86400/86400` contra la referencia.

## F3 — Difficulty: NO reproducible desde `bits`, sí desde el nodo (arreglado)

**Hecho.** OBM A.6: *"The mining difficulty is read from the block-level difficulty field returned
by Bitcoin Core"*.

**Medición.** Reconstruirla desde `bits` con **15 variantes** (incluido el bucle `GetDifficulty`
de Core) difiere de la referencia en **1 ULP de float64 en 2.825 de 6.461 días** (máx 0,05).
Comprobado contra el nodo: `getblock <h> 1` → `27428630902.25787` = **la referencia**; mi cálculo
desde bits → `27428630902.257874` ✗.

**Arreglo.** La dificultad es **constante dentro de cada época de 2016 bloques** → **481 llamadas
RPC** (`getblockhash`+`getblockheader`) en vez de 968.458 → `capa1/difficulty_epochs.parquet`
(`src/exporters/fix_difficulty_rpc.py`).
**Resultado**: `difficulty_eod` **y** `est7d_hashrate` pasan a ser **bit-exactas en las 6.461 fechas**.

**Lección**: para variables de estado del protocolo, **léelas del nodo; no las recalcules**.

## F4 — El orden altura/tiempo (bug de NUESTRO ETL, no de OBM)

**Hecho.** OBM §3.3 advierte de que los timestamps no son monótonos y §3.4 dice que el índice
**escanea en orden de altura** → OBM no tiene este problema. Nuestro ETL particionaba por semana
ISO **del timestamp** y el indexer procesaba esas semanas en orden.

**Medición.** Escaneando las **968.458 alturas** hay **exactamente 2 inversiones**:
`h=60.787` (2010-06-14 00:00, W24) vs `h=60.788` (2010-06-13 23:59, W23), y
`h=293.302` (2014-03-31 00:00, W14) vs `h=293.303` (2014-03-30 23:55, W13).

**Impacto medido** (bloque 293.303): 5 inputs irresolubles → `spent_value` de ese día corto en
**8.711.850.115 sats (87,12 BTC)** y `spent_output_count` −5 de 152.195, con `fees`/`issuance`
desviados; **5 UTXOs fantasma** (+5 permanente en el conteo); error de snapshot de un día (+19 el
2014-03-30) y un transitorio (+1 el 2010-06-13).

**Arreglo (3 piezas).** (a) ETL: semana = `max(propia, anterior)` → partición monótona en altura;
(b) re-particionado de los 2 bloques (`etl/reparticionar_semanas.py`); (c) fusión multi-fichero
**sumando** flujos (ver F6). Añadido un **guard** en `src/indexer.py` que aborta si capa1 no es
monótona en altura.

## F5 — Desbordamiento de 32 bits en el contador de progreso

**Hecho.** `sqlite3_total_changes()` devuelve un `int` de 32 bits (trunca). Al pasar 2³² cambios
acumulados, el contador **dio la vuelta**.

**Medición.** En **2017-W13** `weeks_done.n_inserted` quedó en **−4.290.243.423** (el valor real
era 4.723.873) y `utxo_eod_count` quedó desplazado en **exactamente 2³²** durante **1.713 días**
(2017-03-29 → 2021-12-05). Se detectó con el invariante
`filas(live_outputs) == SUM(n_inserted) − SUM(n_spent)`.

**Reparación exacta** (`src/reparar_wrap_2017.py`): +2³² a la semana 2017-W13 y a las fechas
≥ 2017-03-29 → verificado `COUNT == derivado == 77.000.836` y `FANTASMAS=0`.

**Arreglo de fondo.** `inserted = max(cursor.rowcount, 0)` (acotado al tamaño del lote) + una
verificación de rango que registra un error si `inserted` se sale de `[0, len(lote)]`.

## F6 — Semántica de la agregación cuando una fecha cae en dos ficheros

**Hecho.** Consecuencia de F4: la fecha 2010-06-13 quedó repartida entre `..._2010-W23` y
`..._2010-W24`. La fusión original usaba `drop_duplicates(keep="last")` → la fila parcial de W24
**sobrescribía** la completa de W23.

**Medición**: ese día perdió **148 outputs y 14.232 BTC** de `spent_value` (medido contra la
referencia).

**Regla correcta**: para una fecha repartida, **sumar** los flujos (`spent_value`,
`spent_output_count`, `cdd`, `fees`, `coinbase`, `issuance`, `ge155/ge365` y sus CDD) y quedarse
con el **último** `utxo_eod_count` y el **máximo** `last_height`. Implementado en
`append_daily_to_year` / `append_age_bands_to_year`.

---

## Qué NO es un bug de OBM (importante para la atribución)

| Hallazgo | ¿De quién es? |
|---|---|
| F1 BIP30 | **Documentado en OBM** §3.4 (last-write-wins). Nuestra diferencia es de implementación |
| F2 precisión del CDD | **Elección de implementación de OBM** (float); nuestro valor exacto es más preciso y difiere en el último dígito |
| F3 difficulty | **Método de OBM** (leer del nodo); nuestra reconstrucción desde `bits` era la que fallaba |
| F4 orden altura/tiempo | **Nuestro ETL** ✗ — OBM lo hace bien (escanea en orden de altura) |
| F5 desbordamiento 32 bits | **Nuestra instrumentación de progreso** ✗ |
| F6 fusión multi-fichero | **Nuestra partición en ficheros** ✗ (consecuencia de F4) |

## Reproducir toda la evidencia

```bash
cd /media/SSD4T/obm
python3 src/exporters/fix_difficulty_rpc.py     # F3 (necesita el nodo; ya generado)
python3 src/exporters/capa3_series.py           # 23 series
python3 src/exporters/validar_capa3.py          # validacion global + figuras
# F4: inversiones de semana en las 968.458 alturas (escaneo ~1 s sobre capa1/blocks)
# F5: reparacion ya aplicada (src/reparar_wrap_2017.py, idempotente)
```

## F7 — La ventana de crash entre el commit y la escritura del parquet (bug NUESTRO)

**Hecho.** En `main()` el orden por semana es: (1) `process_week()` que **commitea** en la DB
(incluida la fila de `weeks_done`), (2) escritura de los parquet de agregados, (3) guardado del
JSON de estado. Un corte entre (1) y (2) deja la semana **commiteada y registrada** pero **sin sus
agregados en parquet**, y al reanudar se salta (está en `weeks_done`) → **pérdida silenciosa y
permanente** de esos días.

**Ocurrió de verdad.** El 28-sep se interrumpió el indexer con Ctrl-C cayendo exactamente en
`con.commit()` de la semana **2022-W06**. Resultado medido: `weeks_done[2022-W06]` existe (el
commit se completó) pero `daily_aggregates_2022.parquet` **no tiene ninguno de sus 7 días**.

**Impacto medido** (validado contra la referencia): 7 días con flujos a cero (`spent_value` de
2022-02-08 corto en 11.956.176 BTC) **más un desplazamiento permanente de la oferta** de
**6.650 BTC** desde 2022-02-13 (la emisión de esa semana) que contamina `supply`,
`cdd_per_supply` y `liveliness` durante **686 días**.

**Arreglo de fondo (pendiente de aplicar).** Invertir el orden a: **parquet → commit DB → estado**.
Si el commit falla tras escribir el parquet, la semana se reprocesa y el parquet se reescribe con
los **mismos** valores (idempotente por fecha, `drop_duplicates`/suma), así que no hay riesgo.
Aplicarlo requiere reiniciar el indexer para que surta efecto.

**Arreglo de los datos ya perdidos (pendiente, ~1-3 h).** Los agregados de 2022-W06 son
**recomputables desde capa1 solo** (no hace falta el estado del UTXO): `spent_value` = Σ valores de
los prevouts resueltos (join de `capa1/inputs` de la semana contra `capa1/outputs`), `cdd` con
`age = t_spend − t_create` de las alturas respectivas, y `utxo_eod_count(d) = utxo_eod_count(fin de
2022-W05) + Σ(creados − gastados) hasta d`. Escribir esas filas en
`capa2/daily_aggregates_2022.parquet` y `age_band_aggregates_2022.parquet` deja capa3 completa.

## F8 — Cuatro trampas silenciosas en el script de reparación (bug NUESTRO, corregido)

Contexto: `src/exporters/reparar_semana_2022W06.py` (reparación de la ventana de crash F7)
falló tres veces antes de producir datos válidos. Las cuatro causas son de NUESTRA
implementación; ninguna involucra a OBM. Quedan documentadas porque son silenciosas y las
cuatro se habrían propagado a capa 3.

### F8.1 — `strftime(to_timestamp(t))` usa la zona horaria de la SESIÓN
DuckDB formatea en la zona de la sesión, no en UTC. Con `America/Guayaquil` (UTC-5) cada
día quedaba corrido 5 h y aparecía un día fantasma al inicio de la semana (2022-02-06 con
127.914 gastos, que son los bloques de 02-07 entre 00:00 y 04:59 UTC), pisando además el
02-06 correcto (826.967 gastos / 304.532.860.918.303 sats).
Arreglo: `SET TimeZone='UTC'` al abrir la conexión.
Repro: `SELECT strftime(to_timestamp(1644192614),'%Y-%m-%d')` → `2022-02-06` sin el SET,
`2022-02-07` con él (y `datetime.fromtimestamp(ts, timezone.utc)` en Python coincide).

### F8.2 — Bandas de edad sin agregar
El bucle en Python recorría cada edad entera (0…4.500 días) y escribía una fila por edad:
17.069 filas donde corresponden 84 (7 días × 12 bandas).
Arreglo: agregar en SQL con `CASE` + `GROUP BY date, age_band`.

### F8.3 — En DuckDB `/` es división REAL, no entera
`CAST(value_sats AS HUGEINT)*age/86400` se ejecuta como `CAST(... AS DOUBLE)/86400` (lo
delata el propio plan de DuckDB), así que el CDD se calculaba en coma flotante y dejaba de
ser exacto: 950.272 sat-días de error en un test de 2 M filas, con sumas dependientes del
orden de agrupación. Arreglo: `(CAST(value_sats AS HUGEINT)*age) // 86400`, la misma
semántica que `divmod(value_sats*age_seconds, 86400)` del indexer.
Lo detectó el assert del propio script: la suma por bandas y el agregado diario diferían
en 14 sat-días; con `//` coinciden exactamente.

### F8.4 — pandas convierte HUGEINT a float64
Verificar los totales sumando en pandas pierde precisión (dtype `float64`). Arreglo:
verificar en SQL (HUGEINT contra HUGEINT) sobre los DataFrames registrados en DuckDB.

### F8.5 — `n_creados` excluía las salidas coinbase
La condición `cb.txid IS NULL` (heredada del cálculo de fees) quitaba del conteo las
salidas coinbase, que el indexer SÍ inserta como UTXO vivas (PASO B). Resultado:
`utxo_eod_count` corto en ~1 salida por bloque (140-190/día, acumulativo). Se detectó
comparando contra la referencia: el desfase diario era exactamente el número de bloques del
día. Arreglo: contar toda salida que pase el filtro de gastabilidad, coinbase incluida.
`src/exporters/reparar_utxo_eod_w06.py` aplica sólo esa columna sin repetir el escaneo de
386 GB (idempotente).

### Verificación final de 2022-W06 (7 días, contra `obm_reference/metrics`)
```
obm_spent_output_count_daily   0 diferencias
obm_spent_value_btc_daily      0 diferencias
obm_fees_btc_daily             0 diferencias
obm_issuance_btc_daily         0 diferencias
obm_utxo_eod_count_daily       -2 constante (F1: BIP30, compensado en capa 3)
obm_cdd_btcxdays_daily         max 3,7e-09 BTC-días (residual float, rel. 1,9e-16)
```
Comprobación de integridad: el offset −2 se mantiene constante desde 2010-11-15 a lo largo
de todo 2022, sin ningún escalón → la reparación no introdujo discontinuidad. Los 7 días
están en el parquet (verificado con el guard corregido de F8.6).

### F8.6 — El guard de cobertura buscaba el día en el año de la semana
`check_parquet_cobertura()` (guard añadido para F7) resolvía cada día esperado contra
`daily_aggregates_<año-de-la-semana>.parquet`. Pero cada día se escribe en el parquet de **su**
año, y una semana ISO puede empezar o terminar en el año contiguo (F4): los días
2010-01-01..03 de `2009-W53` viven en `daily_aggregates_2010.parquet`. Efecto: 13 abortos
falsos por frontera de año (2009-W53, 2010-W52, 2011-W52, 2013-W01, 2014-W01, 2015-W01,
2015-W53, 2016-W52, 2019-W01, 2020-W01, 2020-W53, 2021-W52, 2022-W52), que habrían
bloqueado la reanudación de capa2 sin existir ningún hueco real.
No lo había ejercitado ningún arranque anterior porque se añadió al código con el indexer ya
en marcha (el proceso seguía con el módulo antiguo ya importado); se detectó al revisar el
estado justo antes de reanudar.
Arreglo: resolver cada día contra el parquet de su propio año. Verificación: 0 huecos sobre
las 792 semanas de `weeks_done`, y test negativo con un parquet truncado (sin 2012-06-15) →
el guard lo detecta.
