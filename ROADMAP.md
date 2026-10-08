# Roadmap (post-auditoría)

Cada fase es independiente y entregable por sí sola. Coste estimado y prerrequisitos indicados.

## Fase 0 — Cerrar capa3  *(cerrada el 8-oct)*
`capa2` termina → `capa3_series.py` + `validar_capa3.py`. Obtenido el 2026-10-08: **21/23 bit-exactas**
(las dos diferencias son del CDD, a 1 ulp del último decimal publicado).
**Entregable**: capa3 cerrada + `VALIDACION.md` + figuras.

## Fase 1 — Paquete A: auditoría de reproducibilidad  *(escrita el 8-oct; falta el cierre)*
A partir de `AUDITORIA_HALLAZGOS.md` (los 8 hallazgos, F1-F8, ya cerrados con números).
**Entregable**: `AUDITORIA.md` + `LIMITACIONES.md` + repo git + revisión adversarial de un agente
independiente. **Es la pieza que demuestra rigor e ingeniería.**
*(Hecho el 8-oct: los dos documentos, la revisión adversarial en un harness externo —14 hallazgos,
A1-A14, ya incorporados— y los 4 commits. Queda el cierre final del paquete.)*

## Fase 2 — capa4: mercado  *(1 semana)*
Precio diario de **Binance** (klines 1d; `data.binance.vision`, sin API key) desde 2017-08,
**empalmado** con Bitstamp/Coinbase/CoinDesk BPI para 2010-2017 (documentar el cambio de venue).
Se añaden funding rate y open interest de futuros.
**Desbloquea**: NVT, MVRV, realized price, hashprice, comisiones en USD.
*Regla*: `capa1`-`capa3` siguen siendo reproducibles **sólo con el nodo**; capa4 va aparte.

## Fase 3 — Track investigación: econometría de las series OBM  *(2-4 semanas)*
Es el propósito declarado del paper ("economic and econometric research") y el dataset es de
jul-2026: **cualquier estudio serio es una contribución nueva**.
Candidatos: cambios estructurales (cuota de comisiones, crecimiento de oferta), colas gruesas en
CDD/comisiones, estudio de eventos de halvings, cointegración hashrate-comisiones-precio, GARCH
con exógenas on-chain. Herramientas ya instaladas (`statsmodels`, `scipy`, `sklearn`).
**Entregable**: un paper/notebook con 5-6 figuras y una sección de limitaciones honesta.

## Fase 4 — Track balances (sin direcciones)  *(3-5 días)*
Balance por **tamaño de output** ("outputs ballena"), por tipo de script, **HODL waves** y
**URPD** (coste base, requiere capa4). Todo desde `live_outputs` — minutos de cómputo.
**Entregable**: panel visual + nota metodológica.

## Fase 5 (opcional) — Direcciones / entidades  *(semanas)*
Rich list del tip (join `live_outputs` × `capa1/outputs` + derivar dirección, 1-3 h). Seguimiento
de una lista concreta con `scantxoutset` (segundos por dirección). Clustering de entidades =
proyecto de investigación aparte (heurística de co-gasto; se rompe con CoinJoin).
*Nota*: los *proxies* de ballenas sin direcciones (Fase 4) son más robustos y ya están.

## Fase 6 (opcional) — Estrategia de trading  *(sólo si se decide)*
**Límite duro**: datos diarios y autocorrelacionados → ~50-100 episodios independientes → potencia
estadística baja, y las métricas on-chain son públicas y lentas.
Orden correcto: (1) data mart alineado, (2) **backtest honesto sin look-ahead** (señal del día *d*
→ open de *d+1*, costes, walk-forward, corrección por múltiples test), (3) overlay de **riesgo**
(tamaño de posición), nunca predictor de retorno con ML sobre 6.400 muestras.
El entregable más valioso de esta fase suele ser **"qué NO funciona"**.
