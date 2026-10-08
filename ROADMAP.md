# Roadmap (post-audit)

Each phase is independent and deliverable on its own. Estimated cost and prerequisites are given.

## Phase 0 — Close layer 3  *(closed on 8 Oct)*
`layer 2` finishes → `capa3_series.py` + `validar_capa3.py`. Obtained on 2026-10-08: **21/23 bit-exact**
(the two differences are in CDD, at 1 ulp of the last published decimal).
**Deliverable**: layer 3 closed + `VALIDATION.md` + figures.

## Phase 1 — Package A: reproducibility audit  *(written on 8 Oct; closure pending)*
From `AUDITORIA_HALLAZGOS.md` (the 8 findings, F1-F8, already closed with numbers).
**Deliverable**: `AUDITORIA.md` + `LIMITACIONES.md` + git repo + adversarial review by an independent
agent. **It is the piece that demonstrates rigour and engineering.**
*(Done on 8 Oct: the two documents, the adversarial review in an external harness —14 findings,
A1-A14, already incorporated— and the 4 commits. The final closure of the package is still pending.)*

## Phase 2 — layer 4: market  *(1 week)*
Daily price from **Binance** (1d klines; `data.binance.vision`, no API key) since 2017-08,
**spliced** with Bitstamp/Coinbase/CoinDesk BPI for 2010-2017 (document the venue change).
Funding rate and futures open interest are added.
**Unlocks**: NVT, MVRV, realized price, hashprice, fees in USD.
*Rule*: `layer 1`-`layer 3` remain reproducible **with the node only**; layer 4 is separate.

## Phase 3 — Research track: econometrics of the OBM series  *(2-4 weeks)*
It is the declared purpose of the paper ("economic and econometric research") and the dataset is from
Jul-2026: **any serious study is a new contribution**.
Candidates: structural breaks (fee share, supply growth), heavy tails in
CDD/fees, halving event studies, hashrate-fees-price cointegration, GARCH
with on-chain exogenous variables. Tools already installed (`statsmodels`, `scipy`, `sklearn`).
**Deliverable**: a paper/notebook with 5-6 figures and an honest limitations section.

## Phase 4 — Balances track (no addresses)  *(3-5 days)*
Balance by **output size** ("whale outputs"), by script type, **HODL waves** and
**URPD** (cost basis, requires layer 4). All from `live_outputs` — minutes of compute.
**Deliverable**: visual panel + methodological note.

## Phase 5 (optional) — Addresses / entities  *(weeks)*
Tip rich list (join `live_outputs` × `capa1/outputs` + derive address, 1-3 h). Tracking
of a specific list with `scantxoutset` (seconds per address). Entity clustering =
a separate research project (co-spend heuristic; it breaks with CoinJoin).
*Note*: the whale *proxies* without addresses (Phase 4) are more robust and already exist.

## Phase 6 (optional) — Trading strategy  *(only if it is decided)*
**Hard limit**: daily and autocorrelated data → ~50-100 independent episodes → low statistical
power, and on-chain metrics are public and slow.
Correct order: (1) aligned data mart, (2) **honest backtest without look-ahead** (signal from day *d*
→ open of *d+1*, costs, walk-forward, multiple-testing correction), (3) **risk** overlay
(position sizing), never a return predictor with ML on 6.400 samples.
The most valuable deliverable of this phase is usually **"what does NOT work"**.
