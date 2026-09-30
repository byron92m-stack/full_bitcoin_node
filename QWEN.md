# Handover — réplica OBM + auditoría de reproducibilidad

> Punto de entrada para cualquier agente de código. Estado: **2026-09-28**.
> Si algo aquí contradice al código o a los logs, **manda el código**.

## Qué es
Pipeline propio que reproduce las **23 series diarias de Open Bitcoin Metrics (OBM) v0.1.0**
desde un nodo completo de Bitcoin Core, y base de una **auditoría independiente de
reproducibilidad** (el paper se llama "Verifiable Full-Node-Derived…": su tesis es la
reproducibilidad). Ver `README.md` (arquitectura de 4 capas) y `AUDITORIA_HALLAZGOS.md`.

## Estado
| Capa | Estado |
|---|---|
| capa1 | **COMPLETA y validada**: 968.458 bloques (0..968.457), 0 huecos, 926 semanas × 4 tablas. `python3 etl/capa1_btccore_parquet.py --validate` ✓ |
| capa2 | **EN CURSO**. Reanudable: `python3 src/indexer.py` → opción **2** (NUNCA 1, borraría 4 días de trabajo) |
| capa3 | 23 CSV generados; **hay que regenerarlos al cerrar capa2** |
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
python3 src/exporters/validar_capa3.py     # -> capa3/VALIDACION.md + figuras/
grep -cE "UTXO no encontrado|fees negativas|issuance negativa" logs/indexer.log   # debe ser 0
```
Esperado: **22/23 series bit-exactas** y `cdd_btcxdays` con residuo ≤1,5 sat-días en 1,5% de
los días (redondeo float de OBM). Si sale otra cosa, **parar y avisar**.

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
| `utxo_eod_count` negativo en 1.713 días | `total_changes` a 32 bits (F5) | `cursor.rowcount` + `src/reparar_wrap_2017.py` |
| `cdd` con error 1,8e-9 | truncado por input (F2) | columnas `cdd_rem_86400` + `cdd_ge*_rem_86400` |
| Todo en la banda `10y_plus` | se pasaban SEGUNDOS a una función con fronteras en DÍAS | `get_age_band(age_seconds / SEGUNDOS_DIA)` |
| Días con spent_value a 0 tras un re-particionado | fusión con `keep="last"` en fechas repartidas entre dos semanas | fusionar SUMANDO flujos |
| `difficulty` con 1 ULP | recalculada desde `bits` (F3) | leer el campo del nodo |

## Entorno
- Python 3.14 · pandas 3.0.2 · pyarrow 23.0.1 · duckdb 1.5.2 · statsmodels · scipy · sklearn · matplotlib
- Bitcoin Core 26.0.0 en `/media/SSD4T/bitcoin/.bitcoin` — **APAGADO** (capa2 no lo necesita).
  Rearranque: `bitcoind -datadir=/media/SSD4T/bitcoin/.bitcoin -daemon`
- Referencia oficial en `obm_reference/`: `metrics/` (23 CSV), `paper/` (el manuscrito),
  `tools/` (el código de los autores — útil para la auditoría).
- **No hay git** en el proyecto.
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

## PENDIENTE CRITICO (F7) — semana 2022-W06 sin agregados

El Ctrl-C del 28-sep cayó en `con.commit()` de 2022-W06: la DB la tiene commiteada y en
`weeks_done`, pero **sus 7 días no están en `capa2/daily_aggregates_2022.parquet`** (ni en las
bandas). Efecto: 7 días a cero + la oferta desplazada 6.650 BTC desde 2022-02-13 (contamina
`supply`, `cdd_per_supply`, `liveliness`). Ver F7 en `AUDITORIA_HALLAZGOS.md` para el método de
recomputación desde capa1. **No borrar ni resetear capa2**: la DB está bien; sólo falta ese parquet.

Arreglo de fondo en `src/indexer.py`: invertir el orden de `main()` a **parquet → commit DB →
estado** (hoy es commit → parquet → estado). Requiere reiniciar el indexer.

### Actualización F7 (29-sep)
- **F7-datos**: `src/exporters/reparar_semana_2022W06.py` recomputa los 7 días de 2022-W06
  desde capa1 (**en ejecución**; comprobar `logs/reparacion_w06.log` → debe terminar en
  `REPARADO` con `prevouts resueltos: 6.574.407 / 6.574.407`). Escribe con backup `.bak_w06`.
  El plan de join está verificado: hash sobre `inp` (6,5 M) + escaneo secuencial de outputs.
- **F7-código**: se añadió `check_parquet_cobertura()` a `src/indexer.py`: al arrancar **aborta**
  si alguna semana de `weeks_done` no tiene sus días en el parquet anual. **NO** se invirtió el
  orden a parquet→commit: con la fusión por SUMA, una semana reprocesada tras un rollback se
  contaría DOS veces (el layout anual no distingue una fecha compartida entre semanas —F4— de una
  semana reescrita). El arreglo definitivo es guardar los agregados semanales **en la DB**
  (misma transacción) y reconstruir los ficheros anuales desde ahí; queda documentado, no aplicado.
