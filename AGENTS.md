# AGENTS.md

The full context of the project is in **[QWEN.md](QWEN.md)** — read it before touching anything.

This file **does not repeat** the state or the rules: the live state (layers, invariants, known
traps and how to check them) is only in `QWEN.md`, so that there are not two places to maintain and
this one cannot become outdated.

- One-line summary: a 3-layer pipeline that replicates the 23 series of OBM v0.1.0 from a Bitcoin
  Core node of our own; the reproducibility audit is in `AUDITORIA.md`.
- Module and invariant map: `docs/MAPA_CODIGO.md`.
