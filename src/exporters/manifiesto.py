#!/usr/bin/env python3
"""Manifiesto SHA-256 de los bytes validados (capa3) y de la referencia congelada.

Por que existe: las 23 series de `capa3/*.csv` y la referencia de `obm_reference/` NO estan
versionadas (son datos), asi que sin un manifiesto no se pueden identificar los bytes exactos
que produjeron `capa3/VALIDACION.md` (hallazgo A6 de la revision adversarial).

Salida: capa3/MANIFEST.sha256   (formato `sha256sum`: `<hash>  <ruta>`)

Uso:  python3 src/exporters/manifiesto.py
"""
import datetime
import glob
import hashlib
import os

OBM = "/media/SSD4T/obm"
PATRONES = ("capa3/obm_*_daily.csv",              # las 23 series publicadas
            "capa3/validacion_series.csv",        # la tabla de la validacion
            "capa3/VALIDACION.md",                # el informe
            "obm_reference/metrics/*/*.csv")      # la referencia contra la que se compara


def sha256(ruta):
    h = hashlib.sha256()
    with open(ruta, "rb") as fh:
        for bloque in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def main():
    lineas = [
        "# SHA-256 de los bytes validados (capa3) y de la referencia congelada de OBM.",
        f"# Generado: {datetime.datetime.now():%Y-%m-%d %H:%M}",
        "# Regenerar: python3 src/exporters/manifiesto.py",
        "",
    ]
    n = 0
    for patron in PATRONES:
        for ruta in sorted(glob.glob(os.path.join(OBM, patron))):
            lineas.append(f"{sha256(ruta)}  {os.path.relpath(ruta, OBM)}")
            n += 1
    destino = os.path.join(OBM, "capa3", "MANIFEST.sha256")
    with open(destino, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lineas) + "\n")
    print(f"{destino}: {n} ficheros con hash")


if __name__ == "__main__":
    main()
