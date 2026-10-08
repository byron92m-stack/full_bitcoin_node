#!/usr/bin/env python3
"""Valida capa3 completa contra la referencia oficial OBM v0.1.0 y genera el informe.

- Comprueba la cobertura (2009-01-01 -> ultima fecha de la referencia).
- Compara las 23 series dia a dia (21 largas + 2 tablas anchas).
- Escribe capa3/VALIDACION.md, capa3/validacion_series.csv y capa3/figuras/*.png

Convenciones replicadas en la comparacion (documentadas en el informe):
  * utxo_eod_count: +1 desde 2010-11-14 y +2 desde 2010-11-15 (OBM cuenta las DOS
    copias de los coinbases duplicados BIP30; live_outputs deduplica como Bitcoin Core).
  * cdd: valor exacto = cdd_sat_days + cdd_rem_86400/86400   (en sat-dias).
  * Tolerancia: medio ultimo decimal PUBLICADO por la referencia, derivado del propio fichero
    (por serie y, en las tablas anchas, por columna). Nunca una tabla escrita a mano: el
    2026-10-08 la del CDD ancho decia 8 decimales cuando la referencia publica 12, lo que
    dejaba la tolerancia 10.000x mas laxa y ocultaba 113 celdas (hallazgo A1 de la auditoria).

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
# La tolerancia NO va a mano: se deriva de los decimales que publica la PROPIA referencia, por
# serie y (en las tablas anchas) por columna: medio ultimo decimal publicado. Una tabla escrita a
# mano se desvia en cuanto cambia una serie: el 2026-10-08 la del CDD ancho decia 8 decimales
# cuando la referencia publica 12, lo que dejaba la tolerancia 10.000x mas laxa y ocultaba 113
# celdas (auditoria adversarial, hallazgo A1).
def decimales_publicados(ruta, cols=None):
    cols = cols or ["value"]
    dec = {}
    with open(ruta, newline="") as fh:
        for r in csv.DictReader(fh):
            for c in cols:
                v = (r.get(c) or "").strip()
                if v and v.lower() != "nan" and "." in v:
                    dec[c] = max(dec.get(c, 0), len(v.split(".")[1]))
    return {c: dec.get(c, 0) for c in cols}
CONOCIDAS = {
    "obm_utxo_eod_count_daily":
        "BIP30: OBM cuenta las dos copias de los coinbases duplicados de 2010 (alturas "
        "91.842 y 91.880); live_outputs deduplica por (txid,vout) como Bitcoin Core. "
        "Neutralizado con el ajuste de compatibilidad de capa3 (+1 el 2010-11-14, +2 desde 2010-11-15).",
    "obm_cdd_btcxdays_daily":
        "1 dia (2010-05-22) con 1 sat-dia (1e-8 BTC-dias) de diferencia: es el residuo del "
        "redondeo propio de OBM al acumular el CDD (en un tramo medido de 2.622 dias el residuo "
        "llega a ~1,5 sat-dias y afecta a ~2,7% de los dias).",
    "obm_cdd_age_band_btcxdays_daily":
        "111 dias / 113 celdas con 1 ULP del ultimo decimal publicado (1e-12). Son empates "
        "EXACTOS en el 13.o decimal: nuestra cifra es el redondeo half-even del valor exacto en "
        "las 113 celdas (verificado) y la de OBM queda un ULP por debajo.",
    "obm_cdd_per_supply_days_daily":
        "Sin diferencias: hereda el residuo del CDD, pero queda por debajo de su ultimo decimal.",
    "obm_dormancy_days_daily":
        "Sin diferencias: hereda el residuo del CDD, pero queda por debajo de su ultimo decimal.",
    "obm_liveliness_ratio_daily":
        "Sin diferencias: hereda el residuo del CDD acumulado, pero queda por debajo de su ultimo decimal.",
    "obm_difficulty_eod_daily":
        "Sin diferencias incluso con la tolerancia estricta de 12 decimales: la dificultad se LEE "
        "del nodo, no se recalcula desde bits (F3).",
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
                          "veredicto": "FALTA FICHERO", "dec": None})
            continue
        cols = ANCHAS.get(s)
        a, b = leer(pr, cols), leer(pc, cols)
        decs = decimales_publicados(pr, cols)
        tols = {c: Decimal(1).scaleb(-d) / 2 for c, d in decs.items()}
        dias = sorted(d for d in (set(a) & set(b)) if limite is None or d <= limite)
        nd, mx, peor = 0, Decimal(0), "-"
        for d in dias:
            x, y = a[d], b[d]
            if cols:
                for i, c in enumerate(cols):
                    dif = None if (x[i] is None or y[i] is None) else abs(x[i] - y[i])
                    if (x[i] is None) != (y[i] is None) or (dif is not None and dif > tols[c]):
                        nd += 1
                        if dif is not None and dif > mx:
                            mx, peor = dif, f"{d} {c}"
                        break
            else:
                dif = None if (x is None or y is None) else abs(x - y)
                if (x is None) != (y is None) or (dif is not None and dif > tols["value"]):
                    nd += 1
                    if dif is not None and dif > mx:
                        mx, peor = dif, d
        ver = "EXACTA" if (nd == 0 and dias) else ("SIN COBERTURA" if not dias else "DIFIERE")
        print(f"{s:<44}{len(dias):>7}{nd:>11}  {f'{mx:.12f}':>22}  {ver}"
              + (f"  peor={peor}" if nd else ""))
        filas.append({"serie": s, "dias": len(dias), "distintos": nd,
                      "max_diff": str(mx), "veredicto": ver,
                      "dec": max(decs.values())})
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
        fh.write(f"- Series exactas: **{exactas}/{len(series)}**\n")
        fh.write("- Tolerancia: **medio último decimal publicado** por la referencia, derivado del "
                 "propio fichero (por serie y, en las tablas anchas, por columna). La columna "
                 "`dec` indica los decimales usados.\n\n")
        fh.write("| Serie | Días comparados | Días con diferencia | Error máximo | dec | Veredicto |\n")
        fh.write("|---|---:|---:|---:|---:|---|\n")
        for f in filas:
            fh.write(f"| `{f['serie']}` | {f['dias']} | {f['distintos']} | "
                     f"{f['max_diff']} | {f.get('dec', '-')} | {f['veredicto']} |\n")
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
        w = csv.DictWriter(fh, fieldnames=["serie", "dias", "distintos", "max_diff", "veredicto", "dec"])
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

    # 2) utxo_eod_count: capa3 publica el valor YA ajustado (BIP30), asi que (ref - capa3) es 0 en
    #    todas las fechas. Para que la figura muestre el escalon hay que devolverle el ajuste.
    if "obm_utxo_eod_count_daily" in largas:
        from capa3_series import ajuste_bip30
        a, b = largas["obm_utxo_eod_count_daily"]
        ds = sorted(set(a) & set(b))
        xs = [datetime.date.fromisoformat(d) for d in ds]
        ys = [float(a[d] - (b[d] - ajuste_bip30(datetime.date.fromisoformat(d))))
              if (a[d] is not None and b[d] is not None) else float("nan") for d in ds]
        fig, ax = plt.subplots(figsize=(11, 4))
        ax.plot(xs, ys, lw=0.8, color="#1565c0")
        ax.set_ylabel("referencia − (capa3 sin el ajuste)  [UTXOs]")
        ax.set_title("utxo_eod_count: el escalón BIP30 (+2 desde 2010-11-15) que capa3 compensa")
        ax.xaxis.set_major_locator(mdates.YearLocator(2))
        plt.tight_layout()
        plt.savefig(f"{CAPA3}/figuras/diff_utxo.png", dpi=140)
        plt.close()

    # 3) las diferencias del CDD, una a una (el resto de los dias son identicos)
    pts = []
    for serie in ("obm_cdd_btcxdays_daily", "obm_cdd_age_band_btcxdays_daily"):
        pr, pc = f"{REF}/{serie}/{serie}.csv", f"{CAPA3}/{serie}.csv"
        if not (os.path.exists(pr) and os.path.exists(pc)):
            continue
        cols = ANCHAS.get(serie)
        a, b = leer(pr, cols), leer(pc, cols)
        for d in sorted(set(a) & set(b)):
            if limite is not None and d > limite:
                continue
            if cols:
                for i in range(len(cols)):
                    x, y = a[d][i], b[d][i]
                    if x is not None and y is not None and x != y:
                        pts.append((datetime.date.fromisoformat(d), serie, abs(float(x - y))))
            else:
                x, y = a[d], b[d]
                if x is not None and y is not None and x != y:
                    pts.append((datetime.date.fromisoformat(d), serie, abs(float(x - y))))
    if pts:
        fig, ax = plt.subplots(figsize=(11, 4))
        for serie, col, mk in (("obm_cdd_btcxdays_daily", "#6a1b9a", "o"),
                               ("obm_cdd_age_band_btcxdays_daily", "#00897b", "s")):
            xs = [p[0] for p in pts if p[1] == serie]
            ys = [p[2] for p in pts if p[1] == serie]
            if xs:
                ax.semilogy(xs, ys, mk, ms=4, ls="none", color=col,
                            label=serie.replace("obm_", "").replace("_daily", ""))
        ax.set_ylabel("|referencia − capa3|")
        ax.set_title(f"Las diferencias del CDD, una a una (el resto son 0): {len(pts)} puntos")
        ax.legend(frameon=False)
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