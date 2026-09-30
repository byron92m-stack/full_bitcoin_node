#!/usr/bin/env python3
"""Figuras de presentacion para capa 3 (dashboard + composicion por banda de edad).

Entrada : capa3/obm_*_daily.csv  (23 series OBM v0.1.0, 21 diarias + 2 anchas)
Salida  : capa3/graficos/{dashboard_series,spent_por_banda,cdd_por_banda}.png

No recalcula nada: solo lee lo que escribio src/exporters/capa3_series.py, asi las
figuras siempre coinciden con los CSV publicados.
"""
import os
from pathlib import Path

BASE = Path("/media/SSD4T/obm")
CAPA3 = BASE / "capa3"
OUT = CAPA3 / "graficos"
# matplotlib necesita cache escribible; en sandbox /tmp puede ser de solo lectura.
os.environ.setdefault("MPLCONFIGDIR", str(BASE / "tmp" / "mpl"))
os.makedirs(os.environ["MPLCONFIGDIR"], exist_ok=True)
os.makedirs(OUT, exist_ok=True)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

BANDAS = ["0d_1d", "1d_1w", "1w_1m", "1m_3m", "3m_6m", "6m_1y",
          "1y_2y", "2y_3y", "3y_5y", "5y_7y", "7y_10y", "10y_plus"]

# (serie, titulo, escala log)
PANELES = [
    ("obm_block_count_daily", "Bloques por dia", False),
    ("obm_tx_count_daily", "Transacciones por dia", False),
    ("obm_block_weight_wu_daily", "Peso de bloque (WU)", True),
    ("obm_supply_btc_daily", "Oferta en circulacion (BTC)", False),
    ("obm_issuance_btc_daily", "Emision (BTC)", False),
    ("obm_fees_btc_daily", "Comisiones (BTC)", False),
    ("obm_miner_revenue_btc_daily", "Ingreso minero (BTC)", False),
    ("obm_fee_share_revenue_ratio_daily", "Comisiones / ingreso minero", False),
    ("obm_raw_output_value_btc_daily", "Valor bruto de salidas (BTC)", True),
    ("obm_spent_value_btc_daily", "Valor gastado (BTC)", True),
    ("obm_spent_output_count_daily", "Salidas gastadas", True),
    ("obm_utxo_eod_count_daily", "UTXOs al cierre del dia", True),
    ("obm_cdd_btcxdays_daily", "CDD (BTC-dias)", True),
    ("obm_cdd_per_supply_days_daily", "CDD / oferta (dias)", True),
    ("obm_dormancy_days_daily", "Dormancy (dias)", True),
    ("obm_liveliness_ratio_daily", "Liveliness", False),
    ("obm_spent_value_ge155d_btc_daily", "Valor gastado >= 155d (BTC)", True),
    ("obm_spent_value_ge365d_btc_daily", "Valor gastado >= 365d (BTC)", True),
    ("obm_spent_value_lt155d_btc_daily", "Valor gastado < 155d (BTC)", True),
    ("obm_difficulty_eod_daily", "Dificultad al cierre", True),
    ("obm_est7d_hashrate_ehs_daily", "Hashrate estimado 7d (EH/s)", True),
]

ESTILO = {"figure.dpi": 140, "savefig.dpi": 140, "font.size": 9,
          "axes.grid": True, "grid.alpha": 0.25, "axes.spines.top": False,
          "axes.spines.right": False, "figure.facecolor": "white",
          "axes.titlesize": 10, "legend.fontsize": 7}


def leer_serie(serie: str, col: str = "value") -> pd.DataFrame:
    ruta = CAPA3 / f"{serie}.csv"
    if not ruta.exists():
        raise SystemExit(f"falta {ruta}\n  corre primero: python3 src/exporters/capa3_series.py")
    df = pd.read_csv(ruta, usecols=["date", col], parse_dates=["date"])
    return df.sort_values("date").reset_index(drop=True)


def leer_ancha(serie: str, prefijo: str) -> pd.DataFrame:
    ruta = CAPA3 / f"{serie}.csv"
    if not ruta.exists():
        raise SystemExit(f"falta {ruta}\n  corre primero: python3 src/exporters/capa3_series.py")
    df = pd.read_csv(ruta, parse_dates=["date"])
    cols = [f"{prefijo}_{b}_" + ("btc" if prefijo == "spent_value" else "btcxdays") for b in BANDAS]
    faltan = [c for c in cols if c not in df.columns]
    if faltan:
        raise SystemExit(f"columnas ausentes en {ruta.name}: {faltan}")
    return df[["date"] + cols].sort_values("date").reset_index(drop=True)


def panel_dashboard(figura_ax, serie: str, titulo: str, log: bool, ventana: int = 7):
    ax = figura_ax
    df = leer_serie(serie)
    x, y = df["date"], df["value"]
    ax.plot(x, y, color="#9ecae1", linewidth=0.6, alpha=0.9)
    ax.plot(x, y.rolling(ventana, min_periods=1).mean(), color="#08519c", linewidth=1.2)
    if log and (y > 0).any():
        ax.set_yscale("log")
    ax.set_title(titulo, loc="left")
    ax.margins(x=0.01)


def grafico_bandas(serie: str, prefijo: str, titulo: str, unidad: str, archivo: str,
                   ventana: int = 30):
    df = leer_ancha(serie, prefijo)
    fechas = df["date"]
    datos = df.drop(columns=["date"]).rolling(ventana, min_periods=1).mean()
    total = datos.sum(axis=1).replace(0, float("nan"))
    partes = [datos[c].to_numpy() for c in datos.columns]
    colores = [plt.get_cmap("viridis")(i / (len(BANDAS) - 1)) for i in range(len(BANDAS))]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 9), sharex=True,
                                   gridspec_kw={"hspace": 0.12})
    ax1.stackplot(fechas, *partes, labels=BANDAS, colors=colores, alpha=0.95)
    ax1.set_title(f"{titulo} — flujo diario (media movil {ventana}d)", loc="left")
    ax1.set_ylabel(unidad)
    ax1.margins(x=0.01)
    ax1.legend(loc="upper left", ncols=6, frameon=False)

    share = datos.div(total, axis=0) * 100
    ax2.stackplot(fechas, *[share[c].to_numpy() for c in share.columns],
                  labels=BANDAS, colors=colores, alpha=0.95)
    ax2.set_ylim(0, 100)
    ax2.set_ylabel("% del flujo del dia")
    ax2.set_xlabel("fecha (UTC)")
    ax2.margins(x=0.01)

    ruta = OUT / archivo
    fig.savefig(ruta, bbox_inches="tight")
    plt.close(fig)
    print(f"  {ruta.relative_to(BASE)}")


def main():
    plt.rcParams.update(ESTILO)

    filas, cols = 5, 5
    fig, axes = plt.subplots(filas, cols, figsize=(24, 20),
                             gridspec_kw={"hspace": 0.42, "wspace": 0.22})
    for ax, (serie, titulo, log) in zip(axes.ravel(), PANELES):
        panel_dashboard(ax, serie, titulo, log)
    for ax in axes.ravel()[len(PANELES):]:
        ax.axis("off")
    fig.suptitle("Replica OBM v0.1.0 — 21 series diarias (capa 3)  ·  azul = media movil 7d",
                 fontsize=16, x=0.01, ha="left")
    fig.savefig(OUT / "dashboard_series.png", bbox_inches="tight")
    plt.close(fig)
    print(f"  {(OUT / 'dashboard_series.png').relative_to(BASE)}")

    grafico_bandas("obm_spent_value_age_band_btc_daily", "spent_value",
                   "Valor gastado por banda de edad", "BTC/dia", "spent_por_banda.png")
    grafico_bandas("obm_cdd_age_band_btcxdays_daily", "cdd",
                   "CDD por banda de edad", "BTC-dias/dia", "cdd_por_banda.png")
    print("\nOK")


if __name__ == "__main__":
    main()
