"""NEGATIVE test of the F7 fix: a cut between the commit and the parquet repairs itself.

Reproduces, in a minimal and ISOLATED capa2 (DB and parquet in a temporary directory), the
2022-W06 scenario: a week with its aggregates committed in the DB but without its
days in the annual parquet. Then it calls the startup reconstruction and checks that:

  1. the days that were missing appear with the DB values;
  2. rebuilding twice gives the same result (idempotent);
  3. reinserting a date REPLACES it, it does not add it (this was the risk of the SUM merge).

Usage:  python3 src/exporters/verificar_f7_autocuracion.py     # 0 = OK
"""
import os
import shutil
import sys
import tempfile

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import indexer as ix


def _row(date, height, value, n_spends, fees):
    r = dict(ix.empty_daily_row(date))
    r.update(last_height=height, spent_value_sats=value,
             spent_output_count=n_spends, fees_sats=fees)
    return r


def _insert_days(con, days):
    cols = list(ix.DAILY_DTYPES)
    con.executemany(
        f"INSERT OR REPLACE INTO daily_agg ({', '.join(cols)}) "
        f"VALUES ({', '.join(['?'] * len(cols))})",
        [tuple(r[c] for c in cols) for r in days.values()],
    )
    con.commit()


def main():
    tmp = tempfile.mkdtemp(prefix="f7_autocura_")
    orig_capa2, orig_db = ix.CAPA2, ix.DB_PATH
    ix.CAPA2, ix.DB_PATH = tmp, os.path.join(tmp, "live_outputs.sqlite")
    failures = 0
    try:
        con = ix.open_db()
        parquet = os.path.join(tmp, "daily_aggregates_2022.parquet")

        # --- step A: two days written normally ---
        _insert_days(con, {
            "2022-02-07": _row("2022-02-07", 721000, 111, 1, 7),
            "2022-02-08": _row("2022-02-08", 721100, 222, 2, 8)})
        ix.rebuild_all_from_db(con)
        a = pd.read_parquet(parquet)
        ok_a = list(a["date"]) == ["2022-02-07", "2022-02-08"] and int(a["spent_value_sats"].sum()) == 333
        print(f"step A  parquet with 2 days ......................... {'OK' if ok_a else 'FAIL'}")
        failures += 0 if ok_a else 1

        # --- step B: the F7 cut: one more day is committed and the parquet is NOT written ---
        _insert_days(con, {"2022-02-09": _row("2022-02-09", 721200, 333, 3, 9)})
        b = pd.read_parquet(parquet)
        ok_b = list(b["date"]) == ["2022-02-07", "2022-02-08"]     # the parquet is still short
        print(f"step B  short parquet (F7 gap) ............... {'OK' if ok_b else 'FAIL'}")
        failures += 0 if ok_b else 1

        # --- step C: startup reconstruction -> it heals itself ---
        ix.rebuild_all_from_db(con)
        c = pd.read_parquet(parquet)
        ok_c = (list(c["date"]) == ["2022-02-07", "2022-02-08", "2022-02-09"]
                and int(c["spent_value_sats"].sum()) == 666
                and int(c.loc[c["date"] == "2022-02-09", "fees_sats"].iloc[0]) == 9)
        print(f"step C  rebuilt, gap healed ............... {'OK' if ok_c else 'FAIL'}")
        failures += 0 if ok_c else 1

        # --- step D: idempotence ---
        ix.rebuild_all_from_db(con)
        d = pd.read_parquet(parquet)
        ok_d = c.equals(d)
        print(f"step D  rebuilding twice is idempotent ..... {'OK' if ok_d else 'FAIL'}")
        failures += 0 if ok_d else 1

        # --- step E: reinserting a date replaces it, it does NOT add it ---
        _insert_days(con, {"2022-02-09": _row("2022-02-09", 721201, 5, 1, 1)})
        ix.rebuild_all_from_db(con)
        e = pd.read_parquet(parquet)
        v = int(e.loc[e["date"] == "2022-02-09", "spent_value_sats"].iloc[0])
        ok_e = (len(e) == 3 and v == 5 and int(e["spent_value_sats"].sum()) == 338)
        print(f"step E  reinserting replaces (does not add) ........... {'OK' if ok_e else 'FAIL'}"
              f"  [2022-02-09 = {v}, should be 5]")
        failures += 0 if ok_e else 1

        con.close()
    finally:
        ix.CAPA2, ix.DB_PATH = orig_capa2, orig_db
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\nresult: {'ALL OK' if failures == 0 else str(failures) + ' FAILURES'}")
    return failures


if __name__ == "__main__":
    sys.exit(main())
