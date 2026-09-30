#!/usr/bin/env python3
"""Compara capa3/ contra la referencia oficial OBM v0.1.0, serie a serie y dia a dia.
Uso:  python3 comparar_capa3.py [--hasta YYYY-MM-DD]"""
import csv, os, sys
from decimal import Decimal

CAPA3 = "/media/SSD4T/obm/capa3"
REF = "/media/SSD4T/obm/obm_reference/metrics"
BANDAS = ["0d_1d","1d_1w","1w_1m","1m_3m","3m_6m","6m_1y","1y_2y","2y_3y","3y_5y","5y_7y","7y_10y","10y_plus"]
ANCHAS = {"obm_spent_value_age_band_btc_daily": [f"spent_value_{b}_btc" for b in BANDAS],
          "obm_cdd_age_band_btcxdays_daily":    [f"cdd_{b}_btcxdays" for b in BANDAS]}
DEC = {"obm_block_count_daily":0,"obm_block_weight_wu_daily":0,"obm_tx_count_daily":0,
       "obm_spent_output_count_daily":0,"obm_utxo_eod_count_daily":0,
       "obm_difficulty_eod_daily":12,"obm_est7d_hashrate_ehs_daily":12,
       "obm_fee_share_revenue_ratio_daily":12,"obm_dormancy_days_daily":12,
       "obm_cdd_per_supply_days_daily":12,"obm_liveliness_ratio_daily":12}

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
    hasta = sys.argv[sys.argv.index("--hasta")+1] if "--hasta" in sys.argv else None
    ok = mal = 0
    print(f"{'serie':<44}{'dias':>7}{'distintos':>11}  {'max_diff':>20}  veredicto")
    for serie in sorted(os.listdir(REF)):
        d = os.path.join(REF, serie)
        if not os.path.isdir(d): continue
        pr, pc = os.path.join(d, f"{serie}.csv"), os.path.join(CAPA3, f"{serie}.csv")
        if not (os.path.exists(pr) and os.path.exists(pc)):
            print(f"{serie:<44}{'--':>7}{'--':>11}  {'--':>20}  FALTA"); mal += 1; continue
        cols = ANCHAS.get(serie)
        r, c = leer(pr, cols), leer(pc, cols)
        if hasta:
            r = {k: v for k, v in r.items() if k <= hasta}
            c = {k: v for k, v in c.items() if k <= hasta}
        tol = Decimal(1).scaleb(-DEC.get(serie, 8)) / 2
        dias = sorted(set(r) & set(c)); nd = 0; mx = Decimal(0); peor = "-"
        for dia in dias:
            a, b = r[dia], c[dia]
            if cols:
                for i, col in enumerate(cols):
                    dif = None if (a[i] is None or b[i] is None) else abs(a[i]-b[i])
                    if (a[i] is None) != (b[i] is None) or (dif is not None and dif > tol):
                        nd += 1
                        if dif is not None and dif > mx: mx, peor = dif, f"{dia} {col}"
                        break
            else:
                dif = None if (a is None or b is None) else abs(a-b)
                if (a is None) != (b is None) or (dif is not None and dif > tol):
                    nd += 1
                    if dif is not None and dif > mx: mx, peor = dif, dia
        ver = "OK" if (nd == 0 and dias) else ("SIN COBERTURA" if not dias else "DIFIERE")
        if ver == "OK": ok += 1
        else: mal += 1
        print(f"{serie:<44}{len(dias):>7}{nd:>11}  {f'{mx:.12f}':>20}  {ver}"
              + (f"  peor={peor}" if nd else ""))
    print(f"\nresumen: {ok} series EXACTAS, {mal} con diferencias/cobertura parcial")

if __name__ == "__main__":
    main()
