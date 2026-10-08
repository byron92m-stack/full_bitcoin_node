# Auditoría de reproducibilidad de OBM v0.1.0

**Qué es esto.** Una reimplementación independiente del dataset *Open Bitcoin Metrics*
(arXiv:2607.03124v1) partiendo **sólo de un nodo completo propio, Bitcoin Core v26.0.0**
(`txindex=1`, sin poda). El objetivo no es publicar métricas nuevas, sino comprobar si las de
OBM se pueden **re-derivar de la cadena** y documentar con números **dónde y por qué** difieren.

**Alcance.** Se auditan las 23 series diarias publicadas en `obm_reference/metrics/` (v0.1.0,
el snapshot entregado con el paper) contra el resultado de este pipeline. No se audita el
código de OBM (no se usó ninguna línea suya): es una auditoría de **caja negra sobre los datos**
y de **caja blanca sobre la metodología publicada** (paper + `APÉNDICE A` + `METODOLOGIA.md`).

---

## Método

1. **Pipeline propio en 4 capas.** `capa1` extrae la cadena del nodo a parquet semanal
   (`blocks`, `txs`, `inputs`, `outputs`); `capa2` es el *spent-output indexer* de §3.4 del paper
   (UTXO vivo en SQLite + agregados diarios y por banda de edad); `capa3` produce las 23 series;
   `capa4` (mercado) queda fuera por diseño. Reglas duras: **cero números a mano** (todo número
   publicado sale de un script re-ejecutable) y `capa1`–`capa3` reproducibles con el nodo.

2. **Comparación día a día** contra los CSV oficiales (`src/exporters/validar_capa3.py`), con la
   tolerancia fijada por los **decimales publicados** de cada serie (medio último dígito) para no
   confundir redondeo de presentación con discrepancia real.

3. **Verificación bilateral** de guardas y validadores: cada uno se prueba con la entrada real
   (caso positivo) y con una entrada truncada a propósito (caso negativo) que demuestre que sigue
   detectando el fallo.

4. **Invariantes de salud** que se comprueban tras cada tramo (ver más abajo).

---

## Resultado

`python3 src/exporters/validar_capa3.py` — comparación día a día con la tolerancia de cada serie:

| Bloque de series | Resultado |
|---|---|
| 5 series de bloque (`block_count`, `block_weight_wu`, `tx_count`, `difficulty_eod`, `est7d_hashrate`) | **bit-exactas** en las 6.461 fechas de la referencia |
| 12 series de flujo y de UTXO (`spent_output_count`, `spent_value` y sus umbrales 155d/365d, `fees`, `issuance`, `miner_revenue`, `raw_output_value`, `supply`, `utxo_eod_count`, `fee_share`) | **bit-exactas** |
| `spent_value_age_band` (tabla ancha de 12 columnas) | **bit-exacta** |
| `cdd_btcxdays` | **1 día** con diferencia (2010-05-22, 1E-8 BTC-días = 1 sat-día) |
| `cdd_age_band` (tabla ancha de 12 columnas) | **111 días / 113 celdas** con 1E-12 = 1 ulp del último decimal publicado |
| ratios derivadas del CDD (`dormancy`, `cdd_per_supply`, `liveliness`) | **bit-exactas** |

**21 de 23 series bit-exactas**; las dos que difieren son las del CDD y lo hacen en **una unidad
del último decimal publicado** (1 sat-día en un día de 2010; 1 ulp en 111 días de la tabla ancha),
donde está verificado que nuestro valor es el redondeo *half-even* exacto y el de OBM queda por
debajo (F2). Se compara **toda la referencia** (sus 23 series tienen entre 6.459 y 6.463 fechas), y
capa3 se extiende 27 días más allá de su final (hasta 2026-10-08).

---

## Hallazgos A — convenciones de OBM que hay que replicar

### F1 · BIP30: la referencia cuenta las DOS copias
OBM §3.4 documenta *last-write-wins* sobre los dos coinbases duplicados históricos. Nuestra
implementación usa `INSERT OR IGNORE` (unicidad `(txid,vout)` como Core) → la serie oficial va
**+1 el 2010-11-14** y **+2 desde el 2010-11-15**. Los dos outputs afectados **no se gastan nunca**,
así que la única consecuencia es el **conteo**; se compensa con un ajuste explícito en capa3
(flag `--no-bip30`) y `utxo_eod_count` pasa a ser exacta.

### F2 · El CDD no es bit-exacto: empates de redondeo en el último decimal
OBM define `CDD_i = V_i·A_i` con `A_i` **fraccionario**. Son dos efectos distintos, los dos medidos:

- **Truncar por input** pierde hasta 1 sat-día por output. En 2.622 días:
  2.320 días con error, máximo **3,33e-3 BTC-días** (rel. 1,77e-9). Con **dos acumuladores**
  (parte entera + resto; columnas `cdd_rem_86400`): 70 días, máximo **1,49e-8** — ≈20× mejor en
  relativo y ≈223.490× en absoluto.
- **Aun así no puede ser bit-exacto.** Con la tolerancia derivada del último decimal publicado
  quedan **1 día** en `cdd_btcxdays` (1E-8 = 1 sat-día) y **111 días / 113 celdas** en la tabla
  ancha `cdd_age_band` (1E-12). Las 113 celdas se comprobaron una a una: son **empates exactos en
  el decimal 13**, nuestra cifra es el redondeo **half-even** del valor exacto en **113/113** y la
  de OBM queda un ulp por debajo. El desacuerdo está del lado de OBM y no es "coma flotante"
  genérica: es su convención de redondeo. Las ratios que derivan del CDD sí salen exactas.

### F3 · La dificultad se LEE del nodo, no se recalcula
OBM A.6 la lee del campo `difficulty` del bloque. Reconstruirla desde `bits` (15 variantes probadas)
difiere en **1 ULP de float64 en 2.825 de 6.461 días**. Como es constante en cada época de 2016
bloques, basta con **481 llamadas RPC** (`getblockheader`) en vez de una por bloque (≈970.000) →
`capa1/difficulty_epochs.parquet`. **Lección**: las variables de estado del protocolo se leen, no se
recalculan.

*(Aviso 2026-10-08: ese fichero cubre hasta la **época 480**; la **481**, que empieza en los
bloques de `2026-W40`, falta, porque se generó con el tip anterior. `capa3_series.py` ya **avisa**
por pantalla en vez de recalcular en silencio —`AVISO: falta la epoca 481…`— y la solución es
relanzar `fix_difficulty_rpc.py` con el nodo encendido. Esas fechas quedan más allá del final de la
referencia, así que no entran en la validación.)*

### F6 · Fusión cuando una fecha cae en dos ficheros semanales
Consecuencia de particionar por semana ISO: una fecha puede aparecer en dos semanas (F4). La
fusión correcta **suma** los flujos y se queda con el **último** `utxo_eod_count` y el **máximo**
`last_height`.

---

## Hallazgos B — bugs de **nuestra** implementación

Estos no son discrepancias con OBM: son fallos propios, encontrados y corregidos durante la
construcción, y se documentan porque **ninguno se detecta mirando una sola serie** (los cuatro se
propagan a capa3).

### F4 · El orden altura/tiempo (ETL)
Los timestamps de bloque **no son monótonos** (16.119 inversiones crudas en los 970.447 bloques);
el índice de OBM escanea **por altura** (§3.4) y nosotros particionábamos por semana del timestamp.
De esas inversiones, **exactamente 2 cruzan una frontera de semana** y son las que rompían el
particionado: h=60.787 vs 60.788 (2010-06) y h=293.302 vs 293.303 (2014-03). Impacto medido en ese
segundo bloque: 5 inputs irresolubles, `spent_value` de ese día corto en **8.711.850.115 sats
(87,12 BTC)**, 5 UTXOs fantasma permanentes y un error de snapshot (+19 el 2014-03-30). Arreglo en
3 piezas: semana = `max(propia, anterior)`, re-particionado de los 2 bloques y fusión sumando flujos
(F6), más un **guard** que aborta si `capa1` no es monótona en altura.

### F5 · Desbordamiento de 32 bits en el contador de progreso
`sqlite3_total_changes()` devuelve un `int` de 32 bits y da la vuelta. En **2017-W13**
`n_inserted` quedó en **−4.290.243.423** (real 4.723.873) y `utxo_eod_count` desplazado **exactamente
2³²** durante **1.713 días** (2017-03-29 → 2021-12-05). **Lo detectó el invariante de conteo**.
Reparación exacta (`src/reparar_wrap_2017.py`) y arreglo de fondo: contar con `cursor.rowcount`
acotado al tamaño del lote. *(Los valores de este párrafo son el estado **histórico** de la avería;
en la DB actual esas filas están reparadas.)*

### F7 · La ventana de crash entre el commit y el parquet
El orden por semana era *commit DB → parquet → estado*: un corte entre los dos primeros deja la
semana **commiteada y registrada** pero **sin sus agregados**, y al reanudar se salta (ya está en
`weeks_done`) → pérdida silenciosa. **Ocurrió**: el Ctrl-C del 28-sep cayó en el commit de
`2022-W06` (7 días a cero y la oferta desplazada 6.650 BTC durante 686 días, contaminando `supply`,
`cdd_per_supply` y `liveliness`).

Arreglo definitivo (aplicado): los agregados **viven en la DB** (`daily_agg`, `age_band_agg`),
escritos en la **misma transacción** que los datos, y los parquet anuales son un **derivado** que se
reconstruye entero al arrancar (`rebuild_all_from_db`) y al cerrar cada semana
(`rebuild_year_from_db`). Un corte ya no pierde nada: **se cura solo**. Se descartó la solución
"obvia" (invertir el orden a parquet→commit) porque la fusión por SUMA podía contar dos veces una
semana reprocesada; con la fecha como clave primaria, eso ya es imposible. Migrado con
`migrar_agregados_a_db.py` (**fidelidad 36/36 ficheros, 0 diferencias**) y verificado con
`verificar_f7_autocuracion.py` (**5/5**, incluido el escenario de corte).

### F8 · Trampas silenciosas en el script de reparación de F7
El script que recomputó los 7 días falló varias veces antes de dar datos válidos, por cinco causas
**nuestras**, todas silenciosas: (F8.1) `strftime(to_timestamp(t))` usa la zona horaria de la
**sesión** de DuckDB, no UTC → días corridos 5 h y un día fantasma; (F8.2) las bandas se escribían
**sin agregar** (17.069 filas donde van 84); (F8.3) en DuckDB `/` es división **REAL**, no entera →
el CDD dejaba de ser exacto (950.272 sat-días de error); (F8.4) **pandas** convierte HUGEINT a
float64 al verificar totales; (F8.5) `n_creados` **excluía las salidas coinbase**, que el indexer sí
inserta como UTXO vivas. Y (F8.6) el **guard de cobertura** buscaba cada día en el parquet del año
**de la semana** en vez del año **del día** → 13 abortos falsos por frontera de año, detectado
justo antes de reanudar (el guard nunca se había ejercitado porque se añadió con el indexer ya en
marcha).

Verificación final de la reparación (7 días, contra la referencia): `spent_output_count`,
`spent_value`, `fees` e `issuance` con **0 diferencias**; `utxo_eod_count` con el −2 constante de
BIP30; `cdd` con residuo 3,7e-09 (rel. 1,9e-16). El offset se mantiene constante sin ningún escalón
→ la reparación no introdujo discontinuidad.

---

## Atribución

| Hallazgo | ¿De quién es? |
|---|---|
| F1 BIP30 | **Documentado en OBM** §3.4; nuestra diferencia es de implementación (conteo) |
| F2 precisión del CDD | **Elección de OBM** (float); nuestro valor exacto difiere en el último dígito |
| F3 dificultad | **Método de OBM** (leer del nodo); el que fallaba era nuestro recálculo |
| F4 orden altura/tiempo | **Nuestro ETL** |
| F5 desbordamiento 32 bits | **Nuestra instrumentación de progreso** |
| F6 fusión multi-fichero | **Nuestra partición en ficheros** (consecuencia de F4) |
| F7 ventana de crash | **Nuestro orden de escritura** |
| F8 (6 trampas) de la reparación | **Nuestro script de reparación** |

Los cinco primeros hallazgos de "nuestra" columna no son cosméticos: los cinco llegaron a corregir
datos publicables. Que se encontraran es el resultado útil de la auditoría.

---

## Invariantes y guardas que se comprueban

| Invariante | Qué detecta | Comando |
|---|---|---|
| `COUNT(live_outputs) == Σ n_inserted − Σ n_spent` (fantasmas = 0) | filas perdidas/duplicadas en el UTXO vivo (así se encontró F5) | `python3 -c "…"` (ver README) |
| Cobertura: cada semana de `weeks_done` tiene sus días en el parquet | la ventana de crash de F7 | `check_parquet_cobertura()` al arrancar |
| Monotonía de alturas en `capa1` | el orden altura/tiempo (F4) | `check_capa1_monotonic()` al arrancar |
| Suma de bandas = agregado diario | bandas sin agrupar / CDD mal calculado (F8.2, F8.3) | comprobado **aparte**, sobre las columnas enteras de la DB (exacto); sobre los valores **publicados** difiere en el último decimal en 272 de 6.461 días (máx. 5e-9), por el redondeo de cada banda |
| Conteos cruzados por semana (`COUNT(txs)=ΣnTx`, `=Σvin`, `=Σvout`) y unicidad de `(txid,vout)` | duplicados y solapes en `capa1` | `etl/capa1_btccore_parquet.py --validate` |
| Cadena: `previousblockhash` de la altura *h* = `hash` de *h−1*, y alturas contiguas sin duplicados | huecos o solapes entre ficheros semanales | comprobado en las 970.447 alturas |

---

## Reproducir

```bash
cd /media/SSD4T/obm
python3 src/exporters/capa3_series.py     # 23 series desde capa1 + capa2
python3 src/exporters/validar_capa3.py    # comparación + figuras + VALIDACION.md
python3 src/exporters/verificar_f7_autocuracion.py   # test negativo de la autocuración
```

La evidencia número a número, con el comando que la regenera en cada caso, está en
`AUDITORIA_HALLAZGOS.md`. Las series y su validación, en `capa3/VALIDACION.md`.

---

## El dataset construido

| Capa | Contenido | Estado |
|---|---|---|
| `capa1` | 970.447 bloques (0..970.446), 928 semanas × 4 tablas, parquet | completa y validada |
| `capa2` | 927 semanas (`2009-W01`..`2026-W40`); UTXO vivo en SQLite (~20 GiB); agregados diarios y por banda de edad | completa; invariante 0 fantasmas |
| `capa3` | las 23 series diarias | **21/23** bit-exactas |
| `capa4` | precio/mercado | no incluida (fuera de alcance) |

Coste de construcción en este equipo: `capa2` ~1 h por semana en 2026 (≈50-85 min/semana), varios
días en total; `capa1` 388 GiB de parquet.
