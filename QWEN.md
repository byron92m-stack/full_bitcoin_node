# Handover — réplica OBM + auditoría de reproducibilidad

> Punto de entrada para cualquier agente de código. Estado: **2026-10-08**.
> Si algo aquí contradice al código o a los logs, **manda el código**.

## Qué es
Pipeline propio que reproduce las **23 series diarias de Open Bitcoin Metrics (OBM) v0.1.0**
desde un nodo completo de Bitcoin Core, y base de una **auditoría independiente de
reproducibilidad** (el paper se llama "Verifiable Full-Node-Derived…": su tesis es la
reproducibilidad). Ver `README.md` (arquitectura de 4 capas) y `AUDITORIA_HALLAZGOS.md`.

## Estado
| Capa | Estado |
|---|---|
| capa1 | **COMPLETA y validada**: 970.447 bloques (0..970.446), 0 huecos, 928 semanas × 4 tablas. `python3 etl/capa1_btccore_parquet.py --validate` ✓ |
| capa2 | **COMPLETA**: 927 semanas (2009-W01..2026-W40), invariante `COUNT = Σins−Σspent` con 0 fantasmas. Reanudable: `python3 src/indexer.py` → opción **2** (NUNCA 1, borra `capa2/`) |
| capa3 | **VALIDADA: 21/23 series bit-exactas** contra `obm_reference/metrics`, con la tolerancia derivada de los decimales que publica la referencia. Las dos diferencias son del CDD: `cdd_btcxdays` (1 día, 1E-8 = 1 sat-día) y `cdd_age_band` (111 días / 113 celdas, 1E-12 = 1 ulp; empates exactos donde redondeamos half-even). Ver `capa3/VALIDATION.md` |
| capa4 | vacía (precio/mercado, pendiente — ver `ROADMAP.md`) |

## Cómo consultar el estado en vivo
```bash
cd /media/SSD4T/obm
tail -3 logs/indexer.log
python3 -c "import json;d=json.load(open('state_indexer.json'));print(d['last_processed_week'],d['utxo_count'])"
# invariante de salud de capa2 (tarda minutos con ~100 M filas):
python3 -c "
import sqlite3
c=sqlite3.connect('file:/media/SSD4T/obm/capa2/live_outputs.sqlite?mode=ro',uri=True,timeout=600)
n=c.execute('SELECT COUNT(*) FROM live_outputs').fetchone()[0]
_,i,s=c.execute('SELECT COUNT(*),SUM(n_inserted),SUM(n_spent) FROM weeks_done').fetchone()
print(f'COUNT={n:,} derivado={i-s:,} FANTASMAS={n-(i-s):,}')"   # FANTASMAS debe ser 0
```

## Al terminar capa2 (orden exacto)
```bash
python3 src/exporters/capa3_series.py      # 23 series -> capa3/
python3 src/exporters/validar_capa3.py     # -> capa3/VALIDATION.md + figuras/
grep -cE "UTXO no encontrado|fees negativas|issuance negativa" logs/indexer.log   # debe ser 0
```
Obtenido el 2026-10-08: **21/23 bit-exactas** (ver el `Estado`); las dos diferencias son del CDD y
valen 1 ulp del último decimal publicado. Al regenerarlo tras una extensión, si sale otra cosa,
**parar y avisar**.

## Reglas NO negociables (cada una costó un bug real)
1. **El orden es ALTURA, no tiempo.** Los timestamps de bloque no son monótonos. Particionar
   la cadena por semana-del-timestamp rompe la resolución de UTXOs (ver F4).
2. **CDD exacto**: `cdd_sat_days + cdd_rem_86400/86400`. NUNCA truncar por input.
3. **NUNCA `con.total_changes`**: la API C trunca a 32 bits y da la vuelta (ver F5). Usar
   `cursor.rowcount`.
4. **BIP30**: OBM hace last-write-wins y su contador cuenta las 2 copias; nuestra DB
   deduplica como Core. El ajuste vive en capa3 (`--no-bip30` para desactivarlo).
5. **La dificultad se LEE del nodo** (`capa1/difficulty_epochs.parquet`), no se recalcula
   desde `bits` (1 ULP de diferencia — ver F3).
6. **Bandas de edad en DÍAS** (`age_seconds/86400`); los umbrales 155d/365d en SEGUNDOS.
7. **No tocar** `capa2/live_outputs.sqlite`, `weeks_done` ni `state_indexer.json` mientras
   el indexer corre. Sí se puede leer en modo `mode=ro`.
8. **Cero números a mano**: todo número publicado sale de un script re-ejecutable.

## Trampas ya pisadas
| Síntoma | Causa | Arreglo |
|---|---|---|
| `5 UTXO no encontrado` + `fees negativas` en el bloque 293.303 | particionado por semana-del-timestamp (F4) | partición monótona en altura + re-particionado + fusión por suma |
| `utxo_eod_count` negativo en 1.713 días | `total_changes` a 32 bits (F5) | `cursor.rowcount` + `src/exporters/reparar_wrap_2017.py` |
| `cdd` con error 1,8e-9 | truncado por input (F2) | columnas `cdd_rem_86400` + `cdd_ge*_rem_86400` |
| Todo en la banda `10y_plus` | se pasaban SEGUNDOS a una función con fronteras en DÍAS | `get_age_band(age_seconds / SEGUNDOS_DIA)` |
| Días con spent_value a 0 tras un re-particionado | fusión con `keep="last"` en fechas repartidas entre dos semanas | fusionar SUMANDO flujos |
| `difficulty` con 1 ULP | recalculada desde `bits` (F3) | leer el campo del nodo |
| Día fantasma y fechas corridas ~5 h en consultas DuckDB | `strftime(to_timestamp(t))` formatea en la zona de la SESIÓN | `SET TimeZone='UTC'` (F8.1) |
| CDD con error de miles de sat-días en SQL | en DuckDB `/` es división REAL (HUGEINT→DOUBLE) | usar `//` y verificar en SQL (F8.3/F8.4) |
| `utxo_eod_count` corto ~140-190/día | `n_creados` excluía las salidas coinbase | contarlas: son UTXO vivas (F8.5) |
| 17.000 filas de bandas en una semana | se escribía una fila por edad, no por banda | `GROUP BY date, age_band` (F8.2) |

## Entorno
- Python 3.14 · pandas 3.0.2 · pyarrow 23.0.1 · duckdb 1.5.2 · statsmodels · scipy · sklearn · matplotlib
- Bitcoin Core 26.0.0 en `/media/SSD4T/bitcoin/.bitcoin` — **APAGADO** (capa2 no lo necesita).
  Rearranque: `bitcoind -datadir=/media/SSD4T/bitcoin/.bitcoin -daemon`
- Referencia oficial en `obm_reference/`: `metrics/` (23 CSV), `paper/` (el manuscrito),
  `tools/` (el código de los autores — útil para la auditoría).
- Repo **git** inicializado. Se versiona el código y la documentación; **no** los datos
  (`capa1/`, `capa2/`, `capa4/`, `capa3/*.csv`, `obm_reference/`, `state_*.json`, `*.bak_*`,
  `tmp/`) ni los logs salvo `logs/evidencia/`. Ver `.gitignore`.
- Los logs de `logs/evidencia/` son **prueba** de los hallazgos F4/F5: no borrar.

## Convenciones
- Documentación y comentarios en **español**; identificadores de OBM en inglés.
- `capa1`-`capa3` deben ser reproducibles **sólo con el nodo** (nada externo).
- Los backups `.bak_*` se eliminan (el historial vive en el texto de la auditoría).

## Pendiente prioritario
1. Cerrar capa3 + validar (arriba).
2. **Paquete A**: `AUDITORIA.md` a partir de `AUDITORIA_HALLAZGOS.md` (los 6 hallazgos ya
   están cerrados con números). Regla: revisión adversarial de un agente independiente antes
   de publicar.
3. `ROADMAP.md`: capa4 (precio/mercado) → estudio econométrico → capa de balances.

## F7 — RESUELTO (datos el 30-sep, código el 8-oct)

El Ctrl-C del 28-sep cayó en `con.commit()` de 2022-W06: la DB quedó commiteada con la semana en
`weeks_done`, pero **sus 7 días no se escribieron** al parquet anual. Efecto: 7 días a cero + la
oferta desplazada 6.650 BTC desde 2022-02-13 (contaminaba `supply`, `cdd_per_supply`,
`liveliness`). Ver F7 en `AUDITORIA_HALLAZGOS.md`.

- **Datos**: `src/exporters/reparar_semana_2022W06.py` y `reparar_utxo_eod_w06.py` recomputaron
  los 7 días desde capa1 (`prevouts resueltos: 6.574.407/6.574.407`) y cuadran con la referencia.
- **Código (arreglo definitivo)**: los agregados diarios y por banda viven ahora **en la DB**
  (`daily_agg`, `age_band_agg`), escritos en la **MISMA transacción** que los datos, y los parquet
  anuales son un **derivado** que se reconstruye entero al arrancar (`rebuild_all_from_db`) y al
  cerrar cada semana (`rebuild_year_from_db`). Un corte entre el commit y el parquet ya no pierde
  nada: se cura solo en el siguiente arranque. Además, al haber una sola fila por fecha,
  desaparece el riesgo de doble conteo de la antigua fusión por SUMA (F4), que fue el motivo de
  descartar invertir el orden a parquet→commit.
- **Migración** (ejecutada el 8-oct): `src/exporters/migrar_agregados_a_db.py` — 6.465 filas
  diarias y 60.792 de bandas *en el momento de migrar* (la DB tiene hoy más, porque capa2 siguió
  procesando); fidelidad **36/36 ficheros, 0 diferencias**.
- **Verificación**: `src/exporters/verificar_f7_autocuracion.py` reproduce el escenario en un
  entorno aislado (hueco → curación → idempotencia → reemplazo en vez de suma): 5/5 OK.
- `check_parquet_cobertura()` se mantiene como comprobación de que la reconstrucción cubrió todas
  las semanas de `weeks_done`.
