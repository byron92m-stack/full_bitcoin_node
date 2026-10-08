#!/usr/bin/env python3
"""SHA-256 manifest of the validated bytes (layer 3) and of the frozen reference.

Why it exists: pinning the exact bytes that produced `capa3/VALIDATION.md` (finding A6 of the
adversarial review). The 23 series are versioned in git, but the frozen reference
(`obm_reference/`) is not redistributed, so the manifest is what ties the published layer-3 bytes
to the reference they were validated against.

Output: capa3/MANIFEST.sha256   (`sha256sum` format: `<hash>  <path>`)

Usage:  python3 src/exporters/manifiesto.py
"""
import datetime
import glob
import hashlib
import os

OBM = "/media/SSD4T/obm"
PATTERNS = ("capa3/obm_*_daily.csv",             # the 23 published series
            "capa3/validation_series.csv",       # the validation table
            "capa3/VALIDATION.md",               # the report
            "obm_reference/metrics/*/*.csv")     # the reference we compare against


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main():
    lines = [
        "# SHA-256 of the validated bytes (layer 3) and of the frozen OBM reference.",
        f"# Generated: {datetime.datetime.now():%Y-%m-%d %H:%M}",
        "# Regenerate: python3 src/exporters/manifiesto.py",
        "",
    ]
    n = 0
    for pattern in PATTERNS:
        for path in sorted(glob.glob(os.path.join(OBM, pattern))):
            lines.append(f"{sha256(path)}  {os.path.relpath(path, OBM)}")
            n += 1
    target = os.path.join(OBM, "capa3", "MANIFEST.sha256")
    with open(target, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"{target}: {n} files hashed")


if __name__ == "__main__":
    main()
