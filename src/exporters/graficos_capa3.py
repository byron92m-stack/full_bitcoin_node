#!/usr/bin/env python3
"""Presentation figures for layer 3 (series dashboard + age-band composition).

Input  : capa3/obm_*_daily.csv  (the 23 OBM v0.1.0 series: 21 daily + 2 wide)
Output : capa3/figures/{series_dashboard,series_spent_by_age_band,series_cdd_by_age_band}.png

It recomputes nothing: it only reads what src/exporters/capa3_series.py wrote, so the
figures always match the published CSVs.
"""
import os
from pathlib import Path

BASE = Path("/media/SSD4T/obm")
CAPA3 = BASE / "capa3"
OUT = CAPA3 / "figures"
# matplotlib needs a writable cache; /tmp may be read-only in a sandbox.
os.environ.setdefault("MPLCONFIGDIR", str(BASE / "tmp" / "mpl"))
os.makedirs(os.environ["MPLCONFIGDIR"], exist_ok=True)
os.makedirs(OUT, exist_ok=True)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

BANDS = ["0d_1d", "1d_1w", "1w_1m", "1m_3m", "3m_6m", "6m_1y",
         "1y_2y", "2y_3y", "3y_5y", "5y_7y", "7y_10y", "10y_plus"]

# (series, title, log scale)
PANELS = [
    ("obm_block_count_daily", "Blocks per day", False),
    ("obm_tx_count_daily", "Transactions per day", False),
    ("obm_block_weight_wu_daily", "Block weight (WU)", True),
    ("obm_supply_btc_daily", "Supply (BTC)", False),
    ("obm_issuance_btc_daily", "Issuance (BTC)", False),
    ("obm_fees_btc_daily", "Fees (BTC)", False),
    ("obm_miner_revenue_btc_daily", "Miner revenue (BTC)", False),
    ("obm_fee_share_revenue_ratio_daily", "Fees / miner revenue", False),
    ("obm_raw_output_value_btc_daily", "Raw output value (BTC)", True),
    ("obm_spent_value_btc_daily", "Spent value (BTC)", True),
    ("obm_spent_output_count_daily", "Spent outputs", True),
    ("obm_utxo_eod_count_daily", "UTXOs at day end", True),
    ("obm_cdd_btcxdays_daily", "CDD (BTC-days)", True),
    ("obm_cdd_per_supply_days_daily", "CDD / supply (days)", True),
    ("obm_dormancy_days_daily", "Dormancy (days)", True),
    ("obm_liveliness_ratio_daily", "Liveliness", False),
    ("obm_spent_value_ge155d_btc_daily", "Spent value >= 155d (BTC)", True),
    ("obm_spent_value_ge365d_btc_daily", "Spent value >= 365d (BTC)", True),
    ("obm_spent_value_lt155d_btc_daily", "Spent value < 155d (BTC)", True),
    ("obm_difficulty_eod_daily", "Difficulty at day end", True),
    ("obm_est7d_hashrate_ehs_daily", "Estimated 7d hashrate (EH/s)", True),
]

STYLE = {"figure.dpi": 140, "savefig.dpi": 140, "font.size": 9,
         "axes.grid": True, "grid.alpha": 0.25, "axes.spines.top": False,
         "axes.spines.right": False, "figure.facecolor": "white",
         "axes.titlesize": 10, "legend.fontsize": 7}


def read_series(series: str, col: str = "value") -> pd.DataFrame:
    path = CAPA3 / f"{series}.csv"
    if not path.exists():
        raise SystemExit(f"missing {path}\n  run first: python3 src/exporters/capa3_series.py")
    df = pd.read_csv(path, usecols=["date", col], parse_dates=["date"])
    return df.sort_values("date").reset_index(drop=True)


def read_wide(series: str, prefix: str) -> pd.DataFrame:
    path = CAPA3 / f"{series}.csv"
    if not path.exists():
        raise SystemExit(f"missing {path}\n  run first: python3 src/exporters/capa3_series.py")
    df = pd.read_csv(path, parse_dates=["date"])
    cols = [f"{prefix}_{b}_" + ("btc" if prefix == "spent_value" else "btcxdays") for b in BANDS]
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise SystemExit(f"columns missing in {path.name}: {missing}")
    return df[["date"] + cols].sort_values("date").reset_index(drop=True)


def draw_panel(ax, series: str, title: str, log: bool, window: int = 7):
    df = read_series(series)
    x, y = df["date"], df["value"]
    ax.plot(x, y, color="#9ecae1", linewidth=0.6, alpha=0.9)
    ax.plot(x, y.rolling(window, min_periods=1).mean(), color="#08519c", linewidth=1.2)
    if log and (y > 0).any():
        ax.set_yscale("log")
    ax.set_title(title, loc="left")
    ax.margins(x=0.01)


def plot_age_bands(series: str, prefix: str, title: str, unit: str, filename: str,
                   window: int = 30):
    df = read_wide(series, prefix)
    dates = df["date"]
    data = df.drop(columns=["date"]).rolling(window, min_periods=1).mean()
    total = data.sum(axis=1).replace(0, float("nan"))
    parts = [data[c].to_numpy() for c in data.columns]
    colors = [plt.get_cmap("viridis")(i / (len(BANDS) - 1)) for i in range(len(BANDS))]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 9), sharex=True,
                                   gridspec_kw={"hspace": 0.12})
    ax1.stackplot(dates, *parts, labels=BANDS, colors=colors, alpha=0.95)
    ax1.set_title(f"{title} — daily flow ({window}-day moving average)", loc="left")
    ax1.set_ylabel(unit)
    ax1.margins(x=0.01)
    ax1.legend(loc="upper left", ncols=6, frameon=False)

    share = data.div(total, axis=0) * 100
    ax2.stackplot(dates, *[share[c].to_numpy() for c in share.columns],
                  labels=BANDS, colors=colors, alpha=0.95)
    ax2.set_ylim(0, 100)
    ax2.set_ylabel("% of the day's flow")
    ax2.set_xlabel("date (UTC)")
    ax2.margins(x=0.01)

    path = OUT / filename
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print(f"  {path.relative_to(BASE)}")


def main():
    plt.rcParams.update(STYLE)

    rows, cols = 5, 5
    fig, axes = plt.subplots(rows, cols, figsize=(24, 20),
                             gridspec_kw={"hspace": 0.42, "wspace": 0.22})
    for ax, (series, title, log) in zip(axes.ravel(), PANELS):
        draw_panel(ax, series, title, log)
    for ax in axes.ravel()[len(PANELS):]:
        ax.axis("off")
    fig.suptitle("OBM v0.1.0 replica — 21 daily series (layer 3)  ·  blue = 7-day moving average",
                 fontsize=16, x=0.01, ha="left")
    fig.savefig(OUT / "series_dashboard.png", bbox_inches="tight")
    plt.close(fig)
    print(f"  {(OUT / 'series_dashboard.png').relative_to(BASE)}")

    plot_age_bands("obm_spent_value_age_band_btc_daily", "spent_value",
                   "Spent value by age band", "BTC/day", "series_spent_by_age_band.png")
    plot_age_bands("obm_cdd_age_band_btcxdays_daily", "cdd",
                   "CDD by age band", "BTC-days/day", "series_cdd_by_age_band.png")
    print("\nOK")


if __name__ == "__main__":
    main()
