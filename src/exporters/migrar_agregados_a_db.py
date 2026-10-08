"""Migration F7: fills daily_agg / age_band_agg from the existing annual parquet files.

Capa2 was built when the aggregates lived ONLY in the annual parquet files; fix F7
moves them into the DB (in the SAME transaction as the data) and leaves the parquet files as a
RECONSTRUCTIBLE DERIVATIVE. This script performs that migration once and, at the end,
rebuilds the files from the DB and checks that not a single value changes.

Re-runnable: INSERT OR REPLACE, so running it again does not duplicate anything.

Usage:  python3 src/exporters/migrar_agregados_a_db.py
"""
import glob
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import indexer as ix


def _load(prefix):
    out = {}
    for p in sorted(glob.glob(os.path.join(ix.CAPA2, f"{prefix}*.parquet"))):
        if os.path.basename(p).endswith(".tmp"):
            continue
        out[os.path.basename(p)] = pd.read_parquet(p)
    return out


def _insert(con, table, cols, df):
    con.executemany(
        f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) "
        f"VALUES ({', '.join(['?'] * len(cols))})",
        df[cols].itertuples(index=False, name=None),
    )


def main():
    con = ix.open_db()
    before_daily = _load("daily_aggregates_")
    before_bands = _load("age_band_aggregates_")
    print(f"annual parquet files found: {len(before_daily)} daily, {len(before_bands)} age-band")
    if not before_daily:
        print("nothing to migrate: no annual files")
        return 0

    cols_d, cols_b = list(ix.DAILY_DTYPES), list(ix.AGE_BAND_DTYPES)
    n_d = n_b = 0
    for df in before_daily.values():
        _insert(con, "daily_agg", cols_d, df)
        n_d += len(df)
    for df in before_bands.values():
        _insert(con, "age_band_agg", cols_b, df)
        n_b += len(df)
    con.commit()
    print(f"migrated {n_d:,} daily rows and {n_b:,} age-band rows")
    print(f"in the DB now: daily_agg="
          f"{con.execute('SELECT COUNT(*) FROM daily_agg').fetchone()[0]:,} | age_band_agg="
          f"{con.execute('SELECT COUNT(*) FROM age_band_agg').fetchone()[0]:,}")

    # Rebuild the annual files FROM the DB and check that not a single value changes.
    n_years = ix.rebuild_all_from_db(con)
    print(f"rebuilt {n_years} years of annual files from the DB")

    after_daily = _load("daily_aggregates_")
    after_bands = _load("age_band_aggregates_")
    err = 0
    for name, a in list(before_daily.items()) + list(before_bands.items()):
        b = (after_daily | after_bands).get(name)
        if b is None:
            err += 1
            print(f"  MISSING {name}")
            continue
        try:
            pd.testing.assert_frame_equal(a, b, check_dtype=False)
        except AssertionError as e:
            err += 1
            print(f"  DIFFERS {name}: {str(e).splitlines()[0]}")
    total = len(before_daily) + len(before_bands)
    print(f"fidelity: {total} files compared, {err} with differences")
    con.close()
    return err


if __name__ == "__main__":
    sys.exit(main())
