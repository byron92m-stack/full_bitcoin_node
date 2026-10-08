"""Test NEGATIVO del arreglo F7: un corte entre el commit y el parquet se repara solo.

Reproduce en un capa2 minimo y AISLADO (DB y parquet en un directorio temporal) el
escenario de 2022-W06: una semana con sus agregados commiteados en la DB pero sin sus
dias en el parquet anual. Despues llama a la reconstruccion de arranque y comprueba que:

  1. los dias que faltaban aparecen con los valores de la DB;
  2. reconstruir dos veces da lo mismo (idempotente);
  3. reinsertar una fecha la REEMPLAZA, no la suma (era el riesgo de la fusion por SUMA).

Uso:  python3 src/exporters/verificar_f7_autocuracion.py     # 0 = OK
"""
import os
import shutil
import sys
import tempfile

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import indexer as ix


def _dia(fecha, altura, valor, n_gastos, fees):
    r = dict(ix.empty_daily_row(fecha))
    r.update(last_height=altura, spent_value_sats=valor,
             spent_output_count=n_gastos, fees_sats=fees)
    return r


def _insertar_dias(con, dias):
    cols = list(ix.DAILY_DTYPES)
    con.executemany(
        f"INSERT OR REPLACE INTO daily_agg ({', '.join(cols)}) "
        f"VALUES ({', '.join(['?'] * len(cols))})",
        [tuple(r[c] for c in cols) for r in dias.values()],
    )
    con.commit()


def main():
    tmp = tempfile.mkdtemp(prefix="f7_autocura_")
    orig_capa2, orig_db = ix.CAPA2, ix.DB_PATH
    ix.CAPA2, ix.DB_PATH = tmp, os.path.join(tmp, "live_outputs.sqlite")
    fallos = 0
    try:
        con = ix.open_db()
        parquet = os.path.join(tmp, "daily_aggregates_2022.parquet")

        # --- paso A: dos dias escritos con normalidad ---
        _insertar_dias(con, {
            "2022-02-07": _dia("2022-02-07", 721000, 111, 1, 7),
            "2022-02-08": _dia("2022-02-08", 721100, 222, 2, 8)})
        ix.rebuild_all_from_db(con)
        a = pd.read_parquet(parquet)
        ok_a = list(a["date"]) == ["2022-02-07", "2022-02-08"] and int(a["spent_value_sats"].sum()) == 333
        print(f"paso A  parquet con 2 dias ......................... {'OK' if ok_a else 'FALLA'}")
        fallos += 0 if ok_a else 1

        # --- paso B: el corte de F7: se commitea un dia mas y NO se escribe el parquet ---
        _insertar_dias(con, {"2022-02-09": _dia("2022-02-09", 721200, 333, 3, 9)})
        b = pd.read_parquet(parquet)
        ok_b = list(b["date"]) == ["2022-02-07", "2022-02-08"]     # el parquet sigue corto
        print(f"paso B  parquet corto (hueco de F7) ............... {'OK' if ok_b else 'FALLA'}")
        fallos += 0 if ok_b else 1

        # --- paso C: reconstruccion de arranque -> se cura solo ---
        ix.rebuild_all_from_db(con)
        c = pd.read_parquet(parquet)
        ok_c = (list(c["date"]) == ["2022-02-07", "2022-02-08", "2022-02-09"]
                and int(c["spent_value_sats"].sum()) == 666
                and int(c.loc[c["date"] == "2022-02-09", "fees_sats"].iloc[0]) == 9)
        print(f"paso C  reconstruido, hueco curado ............... {'OK' if ok_c else 'FALLA'}")
        fallos += 0 if ok_c else 1

        # --- paso D: idempotencia ---
        ix.rebuild_all_from_db(con)
        d = pd.read_parquet(parquet)
        ok_d = c.equals(d)
        print(f"paso D  reconstruir dos veces es idempotente ..... {'OK' if ok_d else 'FALLA'}")
        fallos += 0 if ok_d else 1

        # --- paso E: reinsertar una fecha la reemplaza, NO la suma ---
        _insertar_dias(con, {"2022-02-09": _dia("2022-02-09", 721201, 5, 1, 1)})
        ix.rebuild_all_from_db(con)
        e = pd.read_parquet(parquet)
        v = int(e.loc[e["date"] == "2022-02-09", "spent_value_sats"].iloc[0])
        ok_e = (len(e) == 3 and v == 5 and int(e["spent_value_sats"].sum()) == 338)
        print(f"paso E  reinsertar reemplaza (no suma) ........... {'OK' if ok_e else 'FALLA'}"
              f"  [2022-02-09 = {v}, debe ser 5]")
        fallos += 0 if ok_e else 1

        con.close()
    finally:
        ix.CAPA2, ix.DB_PATH = orig_capa2, orig_db
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\nresultado: {'TODO OK' if fallos == 0 else str(fallos) + ' FALLOS'}")
    return fallos


if __name__ == "__main__":
    sys.exit(main())
