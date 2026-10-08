"""Migracion F7: rellena daily_agg / age_band_agg desde los parquet anuales existentes.

Capa2 se construyo cuando los agregados vivian SOLO en los parquet anuales; el arreglo F7
los mueve a la DB (en la MISMA transaccion que los datos) y deja los parquet como un
DERIVADO reconstruible. Este script hace esa migracion una sola vez y, al final,
reconstruye los ficheros desde la DB y comprueba que no cambia ni un valor.

Reejecutable: INSERT OR REPLACE, asi que volver a lanzarlo no duplica nada.

Uso:  python3 src/exporters/migrar_agregados_a_db.py
"""
import glob
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import indexer as ix


def _cargar(prefijo):
    out = {}
    for p in sorted(glob.glob(os.path.join(ix.CAPA2, f"{prefijo}*.parquet"))):
        if os.path.basename(p).endswith(".tmp"):
            continue
        out[os.path.basename(p)] = pd.read_parquet(p)
    return out


def _insertar(con, tabla, cols, df):
    con.executemany(
        f"INSERT OR REPLACE INTO {tabla} ({', '.join(cols)}) "
        f"VALUES ({', '.join(['?'] * len(cols))})",
        df[cols].itertuples(index=False, name=None),
    )


def main():
    con = ix.open_db()
    antes_d = _cargar("daily_aggregates_")
    antes_b = _cargar("age_band_aggregates_")
    print(f"parquet anuales encontrados: {len(antes_d)} diarios, {len(antes_b)} de bandas")
    if not antes_d:
        print("nada que migrar: no hay ficheros anuales")
        return 0

    cols_d, cols_b = list(ix.DAILY_DTYPES), list(ix.AGE_BAND_DTYPES)
    n_d = n_b = 0
    for df in antes_d.values():
        _insertar(con, "daily_agg", cols_d, df)
        n_d += len(df)
    for df in antes_b.values():
        _insertar(con, "age_band_agg", cols_b, df)
        n_b += len(df)
    con.commit()
    print(f"migradas {n_d:,} filas diarias y {n_b:,} de bandas")
    print(f"en la DB ahora: daily_agg="
          f"{con.execute('SELECT COUNT(*) FROM daily_agg').fetchone()[0]:,} | age_band_agg="
          f"{con.execute('SELECT COUNT(*) FROM age_band_agg').fetchone()[0]:,}")

    # Reconstruir los anuales DESDE la DB y comprobar que no cambia ni un valor.
    n_anios = ix.rebuild_all_from_db(con)
    print(f"reconstruidos los anuales de {n_anios} años desde la DB")

    despues_d = _cargar("daily_aggregates_")
    despues_b = _cargar("age_band_aggregates_")
    err = 0
    for nombre, a in list(antes_d.items()) + list(antes_b.items()):
        b = (despues_d | despues_b).get(nombre)
        if b is None:
            err += 1
            print(f"  FALTA {nombre}")
            continue
        try:
            pd.testing.assert_frame_equal(a, b, check_dtype=False)
        except AssertionError as e:
            err += 1
            print(f"  DIFIERE {nombre}: {str(e).splitlines()[0]}")
    total = len(antes_d) + len(antes_b)
    print(f"fidelidad: {total} ficheros comparados, {err} con diferencias")
    con.close()
    return err


if __name__ == "__main__":
    sys.exit(main())
