# AGENTS.md

El contexto completo del proyecto está en **[QWEN.md](QWEN.md)** — léelo antes de tocar nada.

Este fichero **no repite** el estado ni las reglas: el estado vivo (capas, invariantes, trampas
conocidas y cómo comprobarlos) está sólo en `QWEN.md`, para que no haya dos sitios que mantener y
este no pueda quedarse desactualizado.

- Resumen de una línea: pipeline de 4 capas que replica las 23 series de OBM v0.1.0 desde un nodo
  Bitcoin Core propio; la auditoría de reproducibilidad está en `AUDITORIA.md`.
- Mapa de módulos e invariantes: `docs/MAPA_CODIGO.md`.
