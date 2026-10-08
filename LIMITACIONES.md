# Limitations of this audit

An honest document of what the reproducibility demonstrated in `AUDITORIA.md` does **not** cover. Each
point states what it is, why it matters and how it is bounded.

## 1 · Scope of the comparison

1. **The reference is a moving snapshot.** The comparison is against the 23 OBM CSVs of **v0.1.0** as
   they were published (Jul-2026, covering up to 2026-09-11). OBM may revise its series; this
   audit **does not** verify later versions, and a revision on their side would invalidate the cross-check.
   *Bounded*: the snapshot is frozen in `obm_reference/`, and `validar_capa3.py` can be
   re-run against any other one.

2. **"Exact" = within half the last published decimal**, and that tolerance is **derived from the reference
   file itself** (per series and, in the wide tables, per column), not from a hand-written table:
   on 2026-10-08 such a table said 8 decimals where the reference publishes 12, left the
   tolerance 10,000× looser and hid 113 cells (finding A1 of the adversarial review). It is not
   an infinitely precise comparison: in the 8-decimal series, a difference below
   5e-9 counts as a match. And in series of enormous magnitude —difficulty is around 1.3e14— the 12
   published decimals are **printing noise** (the `float64` ulp is ≈0.016), so there the
   tolerance is strict without being informative. The headline "21/23 bit-exact" means this rule.

3. **The reference series do not all have the same length** (between 6,459 and 6,463 dates).
   The denominator of the "21/23" has to be read per series, not globally.

## 2 · What is not bit-exact

4. **The CDD cannot be reproduced bit for bit, and it is not generic "floating point".** With the published
   tolerance two differences remain: **1 day** in `cdd_btcxdays` (1E-8 = 1 sat-day, the rounding
   residue with which OBM accumulates the CDD) and **111 days / 113 cells** in `cdd_age_band` (1E-12 = 1 ulp
   of the last decimal). Those 113 cells were checked one by one: they are **exact ties in
   decimal 13**, our figure is the *half-even* rounding of the exact value in **113/113** and OBM's
   differs by one unit of the last decimal, in either direction. *Bounded*: documented as F2 with the check included; the
   disagreement is on OBM's side.

5. **The ratios derived from the CDD inherit that bound** (`dormancy`, `cdd_per_supply`, `liveliness`).
   In this cross-check they come out exact even with the strict tolerance, but there is **no structural
   guarantee** that they will keep being so day by day: any day with a residue above the
   tolerance would show up as a last-digit difference.

## 3 · Pipeline dependencies and heuristics

6. **Difficulty has to be read from the node (F3).** Therefore `layer 1`–`layer 3` are **not** reproducible
   from isolated block files: the RPC is required. It is a property of OBM's method, not
   ours, but it limits the promise "with the node alone" to *with the node running*.

7. **The difficulty-epoch table has to be refreshed when layer 1 is extended.** It covered up to
   epoch 480 and the new blocks fell in 481: `capa3_series.py` would have used
   `difficulty_core(bits)` —precisely what F3 forbids— but it **warns** on screen instead of doing it
   silently. *Bounded*: it was regenerated on 8 Oct with the node running (**482 epochs, 0..481**, tip
   970,449) and the warning no longer appears; the risk returns every time layer 1 is extended, and it is closed
   by running `fix_difficulty_rpc.py` again.

8. **The "spendability" filter is a convention heuristic.** The live UTXO excludes
   `OP_RETURN`/nulldata outputs and anomalous `script_hex`. It is the convention that makes the count agree with
   OBM, but **it is not a property of the protocol**: it defines the population of outputs spoken about by
   all the UTXO and coin-age series.

9. **The day is UTC according to the block's `time`**, not `mediantime`. Timestamps are not monotonic and
   there are **2 inversions that cross a week boundary** in 970,447 blocks (F4); they are resolved
   by partitioning and scanning **by height**, so that the "day" of a block is that of its
   timestamp, but the processing order is that of the chain.

## 4 · Conventions replicated on purpose

10. **The BIP30 count (+2) is a convention, not a truth.** OBM counts the two copies of the two
    duplicate coinbases; Core keeps one. Our `live_outputs` follows Core and the adjustment is applied in
    layer 3. Anyone who uses `capa2/live_outputs.sqlite` directly will get the counts **without**
    that +2.

11. **The 12 age bands and the 155d/365d thresholds are OBM's definitions**, including its
    exact boundaries. We reproduce *its* partition, not a canonical one.

## 5 · Dataset coverage

12. **There is no layer 4 (price/market).** All the series that depend on price are left out (NVT,
    MVRV, realized price, hashprice, USD fees). `ROADMAP.md` places it apart **on
    purpose**, so as not to break the rule that layers 1–3 are reproduced with the node alone.

13. **There are no addresses or entities.** All entity-based analysis (rich list, clustering,
    flows by exchange) is left out. The *proxies* without addresses (output size, script
    type, HODL waves, URPD) are more robust, but they do not replace entities.

14. **The dataset ends where the ingested chain ends.** The tip is a moving target; any
    comparison with OBM (which publishes with its own delay) is valid only on the intersection of
    coverages.

## 6 · Cost and shape of the data

15. **Reproducing it is not cheap.** `layer 1` is 387 GiB of parquet and `layer 2` cost **~50-85 min per
    week** (several days in total) with about 8-11 M insertions and 7-8 M deletions per week.
    A reviewer with fewer compute hours will not be able to redo it in full.

16. **`layer 2` is a single-file SQLite (~20 GiB), not a distributed system.** Over one
    week the WAL reaches ~14 GB. Reproducibility is of *process*, not of infrastructure.

## 7 · What this audit does NOT verify

17. **It does not audit OBM's code** (it was not used): it verifies the *agreement with its published
    outputs*, not the correctness of its implementation or of its decisions.

18. **It does not verify that the reference is correct with respect to the chain.** If OBM and we
    shared the same mistaken interpretation (for example, the spendability filter), the
    cross-check **would not detect it**: we would agree on the error. The audit measures *agreement*, and
    agreement is strong evidence but not proof of truth.

19. **The bilateral test was applied to guards and validators, not to every function.** The five
    invariants and the repair scripts were tested with the real case and the negative case; the rest of the
    code is verified indirectly, through the global comparison against the reference.

## 8 · On the documentation

20. **"Zero hand-written numbers" holds in the pipeline, not in the documents.** The invariants, the
    validation, the repairs and the figures are regenerated by a script
    (`validar_capa3.py`, `verificar_f7_autocuracion.py`, `graficos_capa3.py`); but several figures in
    the reports are **transcriptions** of earlier runs (the states prior to repairs F5 and F7,
    the day counts of F2, the sizes) and today they are reproduced only by
    redoing the calculation. They are marked as historical where applicable.

21. **The figures are not audited by looking at them.** This model does not process PNG: figure captions are
    derived from the code that draws them and from the measurements, not from visual inspection. A figure may
    be badly cropped without this report detecting it.

## 9 · Nature of the conclusions

22. **None of this is causal inference or econometrics.** The dataset is a description of the
    chain; the series are autocorrelated and strongly non-stationary. Any use
    of these series to attribute causes or to predict prices requires, separately, the statistical
    treatment that `ROADMAP.md` (Phases 3 and 6) explicitly leaves out of this delivery.

## 10 · Gaps found by the round-2 adversarial review (2026-10-08)

23. **The last 27 days have no reference truth.** `layer 3` extends to **2026-10-08** but the reference
    ends **2026-09-11** (the comparison is additionally limited to `2026-10-04`). What is published
    beyond that is produced by the pipeline but **not cross-checked**: it is not part of the "21/23".
    *Bounded*: a later reference snapshot can validate those days; the pipeline itself is unchanged.

24. **The independence from the authors' code is asserted, not demonstrated.** The pipeline is written
    from scratch (no line of OBM's code was used), but the repository carries no provenance proof beyond
    that statement. *Bounded*: the audit is black-box on the data, so a shared mistake would not be
    detected either way.

25. **The code review that produced the data is not registered in the history.** The repository was
    reorganised and translated to English **after** the data was built, so the commit trail does not
    show the review that went with the build; that narrative lives in `AUDITORIA_HALLAZGOS.md`.
    *Bounded*: the numbers are re-runnable, so the evidence can be reproduced even if the history is
    not a linear trace.

26. **The tolerance rule has one unexercised edge: a series published with 0 decimals** would get a
    tolerance of **0.5**. No current series is in that case (the fewest decimals is 8), so it never
    fires; it is a latent trap if a future reference adds an integer-valued series. *Bounded*: handled
    by treating `dec = 0` as "exact" (tolerance 0).

27. **The manifest does not cover the whole reference.** `capa3/MANIFEST.sha256` hashes the 23 series,
    the validation table, the report and `obm_reference/metrics/*/*.csv`, but **not** the paper PDF
    (`obm_reference/paper/`), the authors' code (`obm_reference/tools/`) nor the figures
    (`capa3/figures/*.png`). *Bounded*: adding them is a one-line change in `manifiesto.py`; the
    figures are regenerable from the layer-3 CSV.
