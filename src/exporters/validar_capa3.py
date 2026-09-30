#!/usr/bin/env python3
"""Valida capa3 completa contra la referencia oficial OBM v0.1.0 y genera el informe.

- Comprueba la cobertura (2009-01-01 -> ultima fecha de la referencia).
- Compara las 23 series dia a dia (21 largas + 2 tablas anchas).
- Escribe capa3/VALIDACION.md, capa3/validacion_series.csv y capa3/figuras/*.png

Convenciones replicadas en la comparacion (documentadas en el informe):
  * utxo_eod_count: +1 desde 2010-11-14 y +2 desde 2010-11-15 (OBM cuenta las DOS
    copias de los coinbases duplicados BIP30; live_outputs deduplica como Bitcoin Core).
  * cdd: valor exacto = cdd_sat_days + cdd_rem_86400/86400   (en sat-dias).

Uso: python3 validar_capa3.py [--ref DIR] [--sin-figuras]
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
BANDAS = ["0d_1d", "1d_1w", "1w_1m", "1m_3m", "3m_6m", "6m_1y",
          "1y_2y", "2y_3y", "3y_5y", "5y_7y", "7y_10y", "10y_plus"]
ANCHAS = {
    "obm_spent_value_age_band_btc_daily": [f"spent_value_{b}_btc" for b in BANDAS],
    "obm_cdd_age_band_btcxdays_daily": [f"cdd_{b}_btcxdays" for b in BANDAS],
}
DEC = {"obm_block_count_daily": 0, "obm_block_weight_wu_daily": 0, "obm_tx_count_daily": 0,
       "obm_spent_output_count_daily": 0, "obm_utxo_eod_count_daily": 0,
       "obm_difficulty_eod_daily": 12, "obm_est7d_hashrate_ehs_daily": 12,
       "obm_fee_share_revenue_ratio_daily": 12, "obm_dormancy_days_daily": 12,
       "obm_cdd_per_supply_days_daily": 12, "obm_liveliness_ratio_daily": 12,
       "obm_cdd_age_band_btcxdays_daily": 8}
CONOCIDAS = {
    "obm_utxo_eod_count_daily":
        "BIP30: OBM cuenta las dos copias de los coinbases duplicados de 2010 (alturas "
        "91.842 y 91.880); live_outputs deduplica por (txid,vout) como Bitcoin Core. "
        "Neutralizado con el ajuste de compatibilidad de capa3 (+1 el 2010-11-14, +2 desde 2010-11-15).",
    "obm_cdd_btcxdays_daily":
        "Redondeo de OBM al acumular value_btc x age_days por input; residual <= ~1,5 sat-dias.",
    "obm_cdd_age_band_btcxdays_daily": "Mismo origen que cdd_btcxdays (tabla ancha).",
    "obm_cdd_per_supply_days_daily": "Hereda el residual de cdd dividido por la oferta.",
    "obm_dormancy_days_daily": "Hereda el residual de cdd dividido por spent_value.",
    "obm_liveliness_ratio_daily": "Hereda el residual de cdd acumulado.",
    "obm_difficulty_eod_daily":
        "1 ULP de float64: Core evalua la dificultad con otra secuencia de operaciones; "
        "probadas 15 variantes equivalentes y todas dan el redondeo correcto.",
}


def val(x):
    x = (x or "").strip()
    return None if x == "" or x.lower() == "nan" else Decimal(x)


def leer(ruta, cols=None):
    out = {}
    with open(ruta, newline="") as fh:
        for r in csv.DictReader(fh):
            out[r["date"]] = [val(r.get(c)) for c in cols] if cols else val(r.get("value"))
    return out


def main():
    ref_dir, figs = REF, True
    if "--ref" in sys.argv:
        ref_dir = sys.argv[sys.argv.index("--ref") + 1]
    if "--sin-figuras" in sys.argv:
        figs = False
    # capa3 escribe filas para TODO el calendario (0/NaN fuera de su cobertura): comparar sin
    # limite contaria como "diferencias" los dias que capa2 aun no ha procesado.
    limite = None
    if "--sin-limite" not in sys.argv:
        m = ""
        for f in glob.glob(f"{CAPA2}/daily_aggregates_*.parquet"):
            t = pq.read_table(f, columns=["date"])["date"].to_pylist()
            if t: m = max(m, max(map(str, t)))
        limite = m or None
    print(f"limite de comparacion = cobertura de capa2: {limite}\n")
    series = sorted(d for d in os.listdir(ref_dir) if os.path.isdir(os.path.join(ref_dir, d)))
    filas, largas = [], {}
    print(f"{'serie':<44}{'dias':>7}{'distintos':>11}  {'max_diff':>22}  veredicto")
    for s in series:
        pr = os.path.join(ref_dir, s, f"{s}.csv")
        pc = os.path.join(CAPA3, f"{s}.csv")
        if not (os.path.exists(pr) and os.path.exists(pc)):
            print(f"{s:<44}{'--':>7}{'--':>11}  {'--':>22}  FALTA FICHERO")
            filas.append({"serie": s, "dias": 0, "distintos": None, "max_diff": None,
                          "veredicto": "FALTA FICHERO"})
            continue
        cols = ANCHAS.get(s)
        a, b = leer(pr, cols), leer(pc, cols)
        tol = Decimal(1).scaleb(-DEC.get(s, 8)) / 2
        dias = sorted(d for d in (set(a) & set(b)) if limite is None or d <= limite)
        nd, mx, peor = 0, Decimal(0), "-"
        for d in dias:
            x, y = a[d], b[d]
            if cols:
                for i, c in enumerate(cols):
                    dif = None if (x[i] is None or y[i] is None) else abs(x[i] - y[i])
                    if (x[i] is None) != (y[i] is None) or (dif is not None and dif > tol):
                        nd += 1
                        if dif is not None and dif > mx:
                            mx, peor = dif, f"{d} {c}"
                        break
            else:
                dif = None if (x is None or y is None) else abs(x - y)
                if (x is None) != (y is None) or (dif is not None and dif > tol):
                    nd += 1
                    if dif is not None and dif > mx:
                        mx, peor = dif, d
        ver = "EXACTA" if (nd == 0 and dias) else ("SIN COBERTURA" if not dias else "DIFIERE")
        print(f"{s:<44}{len(dias):>7}{nd:>11}  {f'{mx:.12f}':>22}  {ver}"
              + (f"  peor={peor}" if nd else ""))
        filas.append({"serie": s, "dias": len(dias), "distintos": nd,
                      "max_diff": str(mx), "veredicto": ver})
        if not cols:
            largas[s] = (a, b)

    fin_ref = max((max(a) for a, _ in largas.values() if a), default="-")
    fin3 = max((max(b) for _, b in largas.values() if b), default="-")
    exactas = sum(1 for f in filas if f["veredicto"] == "EXACTA")
    print(f"\ncobertura: referencia hasta {fin_ref} | capa3 hasta {fin3}")
    print(f"resumen: {exactas}/{len(series)} series EXACTAS")

    os.makedirs(f"{CAPA3}/figuras", exist_ok=True)
    with open(f"{CAPA3}/VALIDACION.md", "w", encoding="utf-8") as fh:
        fh.write("# Validación de capa3 frente a la referencia OBM v0.1.0\n\n")
        fh.write(f"Generado: {datetime.datetime.now():%Y-%m-%d %H:%M}\n\n")
        fh.write(f"- Cobertura de capa3: hasta **{fin3}**\n")
        fh.write(f"- Comparación limitada a: **{limite or 'sin límite'}**\n")
        fh.write(f"- Cobertura de la referencia: hasta **{fin_ref}**\n")
        fh.write(f"- Series exactas: **{exactas}/{len(series)}**\n\n")
        fh.write("| Serie | Días comparados | Días con diferencia | Error máximo | Veredicto |\n")
        fh.write("|---|---:|---:|---:|---|\n")
        for f in filas:
            fh.write(f"| `{f['serie']}` | {f['dias']} | {f['distintos']} | "
                     f"{f['max_diff']} | {f['veredicto']} |\n")
        fh.write("\n## Discrepancias conocidas y causa raíz\n\n")
        for f in filas:
            if f["veredicto"] == "DIFIERE" and f["serie"] in CONOCIDAS:
                fh.write(f"- **`{f['serie']}`** ({f['distintos']} días, máx. {f['max_diff']}): "
                         f"{CONOCIDAS[f['serie']]}\n")
        fh.write("\n## Reproducir\n\n```bash\n"
                 "python3 src/indexer.py                      # capa1 -> capa2 (~2 dias)\n"
                 "python3 src/exporters/capa3_series.py       # 23 series -> capa3/\n"
                 "python3 src/exporters/validar_capa3.py      # este informe\n```\n")
    with open(f"{CAPA3}/validacion_series.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["serie", "dias", "distintos", "max_diff", "veredicto"])
        w.writeheader()
        w.writerows(filas)
    print(f"escrito: {CAPA3}/VALIDACION.md + validacion_series.csv")

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
        print(f"  (sin figuras: {e})")
        return

    # 1) acuerdo por serie
    fig, ax = plt.subplots(figsize=(11, 6))
    ss = [f["serie"].replace("obm_", "").replace("_daily", "") for f in filas]
    nd = [f["distintos"] or 0 for f in filas]
    vc = ["#2e7d32" if f["veredicto"] == "EXACTA" else "#c62828" for f in filas]
    ax.barh(ss, nd, color=vc)
    ax.set_xlabel("días con diferencia (0 = bit-exacta)")
    ax.set_title(f"capa3 vs OBM v0.1.0 — {exactas}/{len(series)} series bit-exactas")
    ax.invert_yaxis()
    plt.tight_layout()
    plt.savefig(f"{CAPA3}/figuras/acuerdo_series.png", dpi=140)
    plt.close()

    # 2) utxo_eod_count: diferencia absoluta (esperado: -2 plano desde 2010-11-15)
    if "obm_utxo_eod_count_daily" in largas:
        a, b = largas["obm_utxo_eod_count_daily"]
        ds = sorted(set(a) & set(b))
        xs = [datetime.date.fromisoformat(d) for d in ds]
        ys = [float(a[d] - b[d]) if (a[d] is not None and b[d] is not None) else float("nan")
              for d in ds]
        fig, ax = plt.subplots(figsize=(11, 4))
        ax.plot(xs, ys, lw=0.8, color="#1565c0")
        ax.set_ylabel("referencia − capa3 (UTXOs)")
        ax.set_title("utxo_eod_count: diferencia frente a OBM (escalón BIP30 de −2 en 2010-11-15)")
        ax.xaxis.set_major_locator(mdates.YearLocator(2))
        plt.tight_layout()
        plt.savefig(f"{CAPA3}/figuras/diff_utxo.png", dpi=140)
        plt.close()

    # 3) error relativo del CDD (escala log)
    if "obm_cdd_btcxdays_daily" in largas:
        a, b = largas["obm_cdd_btcxdays_daily"]
        ds = sorted(set(a) & set(b))
        xs, ys = [], []
        for d in ds:
            if a[d] and b[d] and a[d] != 0:
                xs.append(datetime.date.fromisoformat(d))
                ys.append(max(float(abs(a[d] - b[d]) / abs(a[d])), 1e-18))
        fig, ax = plt.subplots(figsize=(11, 4))
        ax.semilogy(xs, ys, lw=0.7, color="#6a1b9a")
        ax.set_ylabel("error relativo |ref−capa3|/ref")
        ax.set_title("CDD: error relativo (mediana ~1e-16; picos = último dígito de OBM)")
        ax.xaxis.set_major_locator(mdates.YearLocator(2))
        plt.tight_layout()
        plt.savefig(f"{CAPA3}/figuras/error_cdd.png", dpi=140)
        plt.close()

    # 4) cobertura: dias comparados por serie
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.barh(ss, [f["dias"] for f in filas], color="#37474f")
    ax.set_xlabel("días comparados")
    ax.set_title("Cobertura de la validación por serie")
    ax.invert_yaxis()
    plt.tight_layout()
    plt.savefig(f"{CAPA3}/figuras/cobertura.png", dpi=140)
    plt.close()
    print(f"figuras: {CAPA3}/figuras/*.png")


if __name__ == "__main__":
    main()