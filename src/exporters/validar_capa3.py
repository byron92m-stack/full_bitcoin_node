#!/usr/bin/env python3
"""Validates the whole layer 3 against the official OBM v0.1.0 reference and writes the report.

- Checks the coverage (2009-01-01 -> last date of the reference).
- Compares the 23 series day by day (21 long + 2 wide tables).
- Writes capa3/VALIDATION.md, capa3/validation_series.csv and capa3/figures/*.png

Conventions replicated in the comparison (documented in the report):
  * utxo_eod_count: +1 since 2010-11-14 and +2 since 2010-11-15 (OBM counts BOTH copies of
    the duplicated BIP30 coinbases; live_outputs deduplicates like Bitcoin Core).
  * cdd: exact value = cdd_sat_days + cdd_rem_86400/86400   (in sat-days).
  * Tolerance: half the last decimal PUBLISHED by the reference, derived from the file itself
    (per series and, in the wide tables, per column). Never a hand-written table: on
    2026-10-08 the one for the wide CDD table said 8 decimals where the reference publishes
    12, which left the tolerance 10,000x too lax and hid 113 cells (finding A1 of the review).

Usage: python3 validar_capa3.py [--ref DIR] [--no-figures] [--no-limit]
"""
import csv
import datetime
import glob
import os
import sys

import pyarrow.parquet as pq
from decimal import Decimal

CAPA2 = "/media/SSD4T/obm/capa2"
CAPA3 = "/media/SSD4T/obm/capa3"
REF = "/media/SSD4T/obm/obm_reference/metrics"
FIGDIR = f"{CAPA3}/figures"
BANDS = ["0d_1d", "1d_1w", "1w_1m", "1m_3m", "3m_6m", "6m_1y",
         "1y_2y", "2y_3y", "3y_5y", "5y_7y", "7y_10y", "10y_plus"]
WIDE = {
    "obm_spent_value_age_band_btc_daily": [f"spent_value_{b}_btc" for b in BANDS],
    "obm_cdd_age_band_btcxdays_daily": [f"cdd_{b}_btcxdays" for b in BANDS],
}
KNOWN = {
    "obm_utxo_eod_count_daily":
        "BIP30: OBM counts both copies of the duplicated coinbases of 2010 (heights 91,842 and "
        "91,880); live_outputs deduplicates by (txid,vout) like Bitcoin Core. Neutralised with "
        "the compatibility adjustment of layer 3 (+1 on 2010-11-14, +2 since 2010-11-15).",
    "obm_cdd_btcxdays_daily":
        "1 day (2010-05-22) differing by 1 sat-day (1e-8 BTC-days): it is the residue of OBM's "
        "own rounding when accumulating CDD (over a measured 2,622-day span the residue reaches "
        "~1.5 sat-days and affects ~2.7% of the days).",
    "obm_cdd_age_band_btcxdays_daily":
        "111 days / 113 cells differing by 1 ULP of the last published decimal (1e-12). They are "
        "EXACT ties at the 13th decimal: our figure is the half-even rounding of the exact value "
        "in all 113 cells (verified) and OBM's is one ULP below.",
    "obm_cdd_per_supply_days_daily":
        "No differences: it inherits the CDD residue, but stays below its last decimal.",
    "obm_dormancy_days_daily":
        "No differences: it inherits the CDD residue, but stays below its last decimal.",
    "obm_liveliness_ratio_daily":
        "No differences: it inherits the accumulated CDD residue, but stays below its last decimal.",
    "obm_difficulty_eod_daily":
        "No differences even with the strict 12-decimal tolerance: difficulty is READ from the "
        "node, not recomputed from bits (F3).",
}


# The tolerance is NOT hand-written: it is derived from the decimals published by the reference
# itself, per series and (in the wide tables) per column: half the last published decimal. A
# hand-written table drifts as soon as a series changes; on 2026-10-08 the one for the wide CDD
# table said 8 decimals where the reference publishes 12, which left the tolerance 10,000x too
# lax and hid 113 cells (finding A1 of the adversarial review).
def published_decimals(path, cols=None):
    cols = cols or ["value"]
    dec = {}
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            for c in cols:
                v = (r.get(c) or "").strip()
                if v and v.lower() != "nan" and "." in v:
                    dec[c] = max(dec.get(c, 0), len(v.split(".")[1]))
    return {c: dec.get(c, 0) for c in cols}


def val(x):
    x = (x or "").strip()
    return None if x == "" or x.lower() == "nan" else Decimal(x)


def read(path, cols=None):
    out = {}
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            out[r["date"]] = [val(r.get(c)) for c in cols] if cols else val(r.get("value"))
    return out


def main():
    ref_dir, figs = REF, True
    if "--ref" in sys.argv:
        ref_dir = sys.argv[sys.argv.index("--ref") + 1]
    if "--no-figures" in sys.argv or "--sin-figuras" in sys.argv:
        figs = False
    # layer 3 writes rows for the WHOLE calendar (0/NaN outside its coverage): comparing without
    # a limit would count days that layer 2 has not processed yet as "differences".
    limit = None
    if "--no-limit" not in sys.argv and "--sin-limite" not in sys.argv:
        m = ""
        for f in glob.glob(f"{CAPA2}/daily_aggregates_*.parquet"):
            t = pq.read_table(f, columns=["date"])["date"].to_pylist()
            if t:
                m = max(m, max(map(str, t)))
        limit = m or None
    print(f"comparison limit = layer 2 coverage: {limit}\n")
    series = sorted(d for d in os.listdir(ref_dir) if os.path.isdir(os.path.join(ref_dir, d)))
    rows, long_series = [], {}
    print(f"{'series':<44}{'days':>7}{'different':>11}  {'max_diff':>22}  verdict")
    for s in series:
        pr = os.path.join(ref_dir, s, f"{s}.csv")
        pc = os.path.join(CAPA3, f"{s}.csv")
        if not (os.path.exists(pr) and os.path.exists(pc)):
            print(f"{s:<44}{'--':>7}{'--':>11}  {'--':>22}  MISSING FILE")
            rows.append({"serie": s, "dias": 0, "distintos": None, "max_diff": None,
                         "veredicto": "MISSING FILE", "dec": None})
            continue
        cols = WIDE.get(s)
        a, b = read(pr, cols), read(pc, cols)
        decs = published_decimals(pr, cols)
        tols = {c: Decimal(1).scaleb(-d) / 2 for c, d in decs.items()}
        days = sorted(d for d in (set(a) & set(b)) if limit is None or d <= limit)
        nd, mx, worst = 0, Decimal(0), "-"
        for d in days:
            x, y = a[d], b[d]
            if cols:
                for i, c in enumerate(cols):
                    dif = None if (x[i] is None or y[i] is None) else abs(x[i] - y[i])
                    if (x[i] is None) != (y[i] is None) or (dif is not None and dif > tols[c]):
                        nd += 1
                        if dif is not None and dif > mx:
                            mx, worst = dif, f"{d} {c}"
                        break
            else:
                dif = None if (x is None or y is None) else abs(x - y)
                if (x is None) != (y is None) or (dif is not None and dif > tols["value"]):
                    nd += 1
                    if dif is not None and dif > mx:
                        mx, worst = dif, d
        verdict = "EXACT" if (nd == 0 and days) else ("NO COVERAGE" if not days else "DIFFERS")
        print(f"{s:<44}{len(days):>7}{nd:>11}  {f'{mx:.12f}':>22}  {verdict}"
              + (f"  worst={worst}" if nd else ""))
        rows.append({"serie": s, "dias": len(days), "distintos": nd,
                     "max_diff": str(mx), "veredicto": verdict,
                     "dec": max(decs.values())})
        if not cols:
            long_series[s] = (a, b)

    ref_end = max((max(a) for a, _ in long_series.values() if a), default="-")
    c3_end = max((max(b) for _, b in long_series.values() if b), default="-")
    exact = sum(1 for f in rows if f["veredicto"] == "EXACT")
    print(f"\ncoverage: reference up to {ref_end} | layer 3 up to {c3_end}")
    print(f"summary: {exact}/{len(series)} series EXACT")

    os.makedirs(FIGDIR, exist_ok=True)
    with open(f"{CAPA3}/VALIDATION.md", "w", encoding="utf-8") as fh:
        fh.write("# Layer 3 validation against the OBM v0.1.0 reference\n\n")
        fh.write(f"Generated: {datetime.datetime.now():%Y-%m-%d %H:%M}\n\n")
        fh.write(f"- Layer 3 coverage: up to **{c3_end}**\n")
        fh.write(f"- Comparison limited to: **{limit or 'no limit'}**\n")
        fh.write(f"- Reference coverage: up to **{ref_end}**\n")
        fh.write(f"- Exact series: **{exact}/{len(series)}**\n")
        fh.write("- Tolerance: **half the last decimal published** by the reference, derived from "
                 "the file itself (per series and, in the wide tables, per column). The `dec` "
                 "column shows the decimals used.\n\n")
        fh.write("| Series | Days compared | Days differing | Max error | dec | Verdict |\n")
        fh.write("|---|---:|---:|---:|---:|---|\n")
        for f in rows:
            fh.write(f"| `{f['serie']}` | {f['dias']} | {f['distintos']} | "
                     f"{f['max_diff']} | {f.get('dec', '-')} | {f['veredicto']} |\n")
        fh.write("\n## Known discrepancies and root cause\n\n")
        for f in rows:
            if f["veredicto"] == "DIFFERS" and f["serie"] in KNOWN:
                fh.write(f"- **`{f['serie']}`** ({f['distintos']} days, max {f['max_diff']}): "
                         f"{KNOWN[f['serie']]}\n")
        fh.write("\n## Reproduce\n\n```bash\n"
                 "python3 src/indexer.py                      # layer 1 -> layer 2 (~2 days)\n"
                 "python3 src/exporters/capa3_series.py       # 23 series -> capa3/\n"
                 "python3 src/exporters/validar_capa3.py      # this report\n```\n")
    with open(f"{CAPA3}/validation_series.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["serie", "dias", "distintos", "max_diff",
                                           "veredicto", "dec"])
        w.writeheader()
        w.writerows(rows)
    print(f"written: {CAPA3}/VALIDATION.md + validation_series.csv")

    if not figs:
        return
    os.environ.setdefault("MPLCONFIGDIR", "/media/SSD4T/obm/tmp/mpl")
    os.makedirs(os.environ["MPLCONFIGDIR"], exist_ok=True)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except Exception as e:                                  # pragma: no cover
        print(f"  (no figures: {e})")
        return

    # 1) agreement per series
    fig, ax = plt.subplots(figsize=(11, 6))
    ss = [f["serie"].replace("obm_", "").replace("_daily", "") for f in rows]
    nd = [f["distintos"] or 0 for f in rows]
    vc = ["#2e7d32" if f["veredicto"] == "EXACT" else "#c62828" for f in rows]
    ax.barh(ss, nd, color=vc)
    ax.set_xlabel("days with a difference (0 = bit-exact)")
    ax.set_title(f"capa3 vs OBM v0.1.0 — {exact}/{len(series)} series bit-exact")
    ax.invert_yaxis()
    plt.tight_layout()
    plt.savefig(f"{FIGDIR}/validation_agreement.png", dpi=140)
    plt.close()

    # 2) utxo_eod_count: layer 3 publishes the value ALREADY adjusted (BIP30), so (ref - layer3)
    #    is 0 on every date. To show the step the adjustment has to be given back.
    if "obm_utxo_eod_count_daily" in long_series:
        from capa3_series import bip30_adjustment
        a, b = long_series["obm_utxo_eod_count_daily"]
        ds = sorted(set(a) & set(b))
        xs = [datetime.date.fromisoformat(d) for d in ds]
        ys = [float(a[d] - (b[d] - bip30_adjustment(datetime.date.fromisoformat(d))))
              if (a[d] is not None and b[d] is not None) else float("nan") for d in ds]
        fig, ax = plt.subplots(figsize=(11, 4))
        ax.plot(xs, ys, lw=0.8, color="#1565c0")
        ax.set_ylabel("reference − (capa3 without the adjustment)  [UTXOs]")
        ax.set_title("utxo_eod_count: the BIP30 step (+2 since 2010-11-15) that capa3 compensates")
        ax.xaxis.set_major_locator(mdates.YearLocator(2))
        plt.tight_layout()
        plt.savefig(f"{FIGDIR}/validation_utxo_diff.png", dpi=140)
        plt.close()

    # 3) the CDD differences, one by one (every other day is identical)
    pts = []
    for series_id in ("obm_cdd_btcxdays_daily", "obm_cdd_age_band_btcxdays_daily"):
        pr, pc = f"{REF}/{series_id}/{series_id}.csv", f"{CAPA3}/{series_id}.csv"
        if not (os.path.exists(pr) and os.path.exists(pc)):
            continue
        cols = WIDE.get(series_id)
        a, b = read(pr, cols), read(pc, cols)
        for d in sorted(set(a) & set(b)):
            if limit is not None and d > limit:
                continue
            if cols:
                for i in range(len(cols)):
                    x, y = a[d][i], b[d][i]
                    if x is not None and y is not None and x != y:
                        pts.append((datetime.date.fromisoformat(d), series_id, abs(float(x - y))))
            else:
                x, y = a[d], b[d]
                if x is not None and y is not None and x != y:
                    pts.append((datetime.date.fromisoformat(d), series_id, abs(float(x - y))))
    if pts:
        fig, ax = plt.subplots(figsize=(11, 4))
        for series_id, col, mk in (("obm_cdd_btcxdays_daily", "#6a1b9a", "o"),
                               ("obm_cdd_age_band_btcxdays_daily", "#00897b", "s")):
            xs = [p[0] for p in pts if p[1] == series_id]
            ys = [p[2] for p in pts if p[1] == series_id]
            if xs:
                ax.semilogy(xs, ys, mk, ms=4, ls="none", color=col,
                            label=series_id.replace("obm_", "").replace("_daily", ""))
        ax.set_ylabel("|reference − capa3|")
        ax.set_title(f"The CDD differences, one by one (the rest are 0): {len(pts)} points")
        ax.legend(frameon=False)
        ax.xaxis.set_major_locator(mdates.YearLocator(2))
        plt.tight_layout()
        plt.savefig(f"{FIGDIR}/validation_cdd_diff.png", dpi=140)
        plt.close()

    # 4) coverage: days compared per series
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.barh(ss, [f["dias"] for f in rows], color="#37474f")
    ax.set_xlabel("days compared")
    ax.set_title("Validation coverage per series")
    ax.invert_yaxis()
    plt.tight_layout()
    plt.savefig(f"{FIGDIR}/validation_coverage.png", dpi=140)
    plt.close()
    print(f"figures: {FIGDIR}/*.png")


if __name__ == "__main__":
    main()
