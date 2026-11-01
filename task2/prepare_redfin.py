#!/usr/bin/env python3
"""Prepare compact monthly Redfin views and Python horizon/ridgeline figures."""

from __future__ import annotations

import json
import re
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".mplconfig"))
os.environ.setdefault("XDG_CACHE_HOME", str(ROOT / ".cache"))
Path(os.environ["MPLCONFIGDIR"]).mkdir(parents=True, exist_ok=True)
Path(os.environ["XDG_CACHE_HOME"]).mkdir(parents=True, exist_ok=True)

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.ndimage import gaussian_filter1d


SOURCE = ROOT / "redfin_housing.csv"
OUT = ROOT / "data" / "processed" / "redfin"
MONTH_DIR = OUT / "months"
IMAGES = ROOT / "images"
TIERS = ["Small-volume", "Medium-low", "Medium-high", "High-volume"]
CENSUS_REGIONS = ["Northeast", "Midwest", "South", "West"]
STATE_TO_REGION = {
    **dict.fromkeys(["CT", "ME", "MA", "NH", "RI", "VT", "NJ", "NY", "PA"], "Northeast"),
    **dict.fromkeys(["IL", "IN", "MI", "OH", "WI", "IA", "KS", "MN", "MO", "NE", "ND", "SD"], "Midwest"),
    **dict.fromkeys(["DE", "FL", "GA", "MD", "NC", "SC", "VA", "WV", "AL", "KY", "MS", "TN", "AR", "LA", "OK", "TX", "DC"], "South"),
    **dict.fromkeys(["AK", "AZ", "CA", "CO", "HI", "ID", "MT", "NV", "NM", "OR", "UT", "WA", "WY"], "West"),
}
STATE_PATTERN = re.compile(r",\s*([A-Z]{2})\s+metro area$")

FIELDS = {
    "HOMES SOLD": "homes_sold",
    "MEDIAN SALE PRICE NSA ($)": "sale_price",
    "MEDIAN SALE PRICE NSA YOY (%)": "sale_price_yoy",
    "MEDIAN DAYS ON MARKET (DAYS)": "days_on_market",
    "MEDIAN DAYS ON MARKET YOY (DAYS)": "days_on_market_yoy",
    "ACTIVE LISTINGS": "active_listings",
    "INVENTORY": "inventory",
    "PENDING SALES": "pending_sales",
    "MONTHS OF SUPPLY": "months_supply",
    "AVERAGE SALE TO LIST RATIO (%)": "sale_to_list_ratio",
    "SHARE SOLD ABOVE ORIGINAL LIST (%)": "above_list_share",
    "NEW LISTINGS": "new_listings",
    "MEDIAN NEW LISTING PRICE ($)": "new_listing_price",
    "MEDIAN SALE PRICE PER SQ.FT. ($)": "sale_price_per_sqft",
}


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def json_number(value):
    if pd.isna(value):
        return None
    number = float(value)
    return int(number) if number.is_integer() else round(number, 4)


def add_market_tier(data: pd.DataFrame) -> pd.DataFrame:
    baseline = data[data["period"].dt.year.isin([2024, 2025])]
    volume = baseline.groupby("region_id")["HOMES SOLD"].median().reindex(data["region_id"].drop_duplicates()).fillna(0)
    ranks = volume.rank(method="first")
    tier_map = pd.qcut(ranks, 4, labels=TIERS).astype(str)
    return data.assign(tier=data["region_id"].map(tier_map))


def make_horizon_plot(data, metric, title, ylabel, fold, group_column, group_names, output):
    grouped = data.groupby(["period", group_column], observed=False)[metric].median().unstack(group_column).reindex(columns=group_names)
    dates = grouped.index.to_pydatetime()
    colors_pos = ["#fdd49e", "#fdbb84", "#fc8d59", "#d7301f"]
    colors_neg = ["#dadaeb", "#9e9ac8", "#756bb1", "#54278f"]
    fig, axes = plt.subplots(len(TIERS), 1, figsize=(13, 8.2), sharex=True, constrained_layout=True)
    for ax, tier in zip(axes, group_names):
        values = grouped[tier].to_numpy(dtype=float)
        for band in range(4):
            above = np.clip(values - band * fold, 0, fold)
            below = -np.clip(-values - band * fold, 0, fold)
            ax.fill_between(dates, 0, above, color=colors_pos[band], linewidth=0)
            ax.fill_between(dates, 0, below, color=colors_neg[band], linewidth=0)
        ax.axhline(0, color="#303943", linewidth=.8)
        ax.set_ylim(-fold, fold)
        ax.set_yticks([])
        ax.set_ylabel(tier, rotation=0, ha="right", va="center", labelpad=12, fontsize=10, weight="bold")
        ax.grid(axis="x", color="#fff", linewidth=.8, alpha=.9)
        ax.spines[["left", "right", "top"]].set_visible(False)
    axes[-1].xaxis.set_major_locator(mdates.YearLocator())
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    axes[-1].set_xlabel("Month (monthly median across metro areas)")
    fig.suptitle(f"{title}\n{ylabel}; four horizon bands per side, centered on no year-over-year change", fontsize=14, weight="bold")
    fig.savefig(output, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def density_ridges(groups, title, xlabel, output, transform=None, inverse_ticks=None, clip=None):
    colors = plt.get_cmap("viridis")(np.linspace(.12, .9, len(groups)))
    fig, ax = plt.subplots(figsize=(12.5, max(4.8, 0.78 * len(groups))), constrained_layout=True)
    all_values = np.concatenate([values[np.isfinite(values)] for values in groups.values() if len(values)])
    if clip is not None:
        xmax = float(np.quantile(all_values, clip))
        all_values = all_values[all_values <= xmax]
    else:
        xmax = float(np.max(all_values))
    xmin = float(np.min(all_values))
    pad = max((xmax - xmin) * .04, 1e-6)
    grid = np.linspace(max(xmin - pad, 1.0) if transform else xmin - pad, xmax + pad, 500)
    for idx, (label, raw_values) in enumerate(groups.items()):
        values = np.asarray(raw_values, dtype=float)
        values = values[np.isfinite(values)]
        if clip is not None:
            values = values[values <= xmax]
        plotted = transform(values) if transform else values
        curve_x = transform(grid) if transform else grid
        kde = gaussian_filter1d(np.histogram(plotted, bins=120, range=(curve_x.min(), curve_x.max()), density=True)[0], sigma=1.5)
        centers = np.linspace(curve_x.min(), curve_x.max(), len(kde))
        if kde.max() > 0:
            kde = kde / kde.max() * .78
        offset = len(groups) - idx - 1
        ax.fill_between(centers, offset, offset + kde, color=colors[idx], alpha=.78, linewidth=0)
        ax.plot(centers, offset + kde, color="#28323d", linewidth=.7)
        ax.text(curve_x.min(), offset + .12, f"{label}  ·  n={len(values):,}", va="bottom", ha="left", fontsize=9, weight="bold")
    ax.set_yticks([])
    ax.set_xlim((transform(grid).min(), transform(grid).max()) if transform else (xmin - pad, xmax + pad))
    ax.spines[["left", "right", "top"]].set_visible(False)
    ax.grid(axis="x", color="#e6e9ed", linewidth=.8)
    if inverse_ticks:
        positions, labels = inverse_ticks
        ax.set_xticks(positions, labels)
    ax.set_xlabel(xlabel)
    fig.suptitle(title, fontsize=14, weight="bold")
    fig.savefig(output, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main():
    if not SOURCE.exists():
        raise FileNotFoundError(f"Expected {SOURCE}")
    data = pd.read_csv(SOURCE, na_values=["NA"])
    data["period"] = pd.to_datetime(data["PERIOD BEGIN"], errors="coerce")
    data["region_id"] = data["REGION ID"].astype("int64").astype(str)
    data["state"] = data["REGION NAME"].str.extract(STATE_PATTERN, expand=False)
    if data["state"].isna().any():
        bad = data.loc[data["state"].isna(), "REGION NAME"].drop_duplicates().head().tolist()
        raise ValueError(f"Could not extract state from all metro names: {bad}")
    data = add_market_tier(data)
    data["census_region"] = data["state"].map(STATE_TO_REGION)
    if data["census_region"].isna().any():
        raise ValueError("A state code is missing from the Census-region mapping.")
    months = sorted(data["period"].dropna().unique())

    for period, rows in data.groupby("period", sort=True):
        records = []
        for _, original in rows.iterrows():
            record = {"region_id": original["region_id"], "region": original["REGION NAME"],
                      "state": original["state"], "census_region": original["census_region"], "tier": original["tier"]}
            for source, key in FIELDS.items():
                record[key] = json_number(original[source])
            records.append(record)
        write_json(MONTH_DIR / f"{pd.Timestamp(period):%Y-%m}.json", {"date": f"{pd.Timestamp(period):%Y-%m}", "metros": records})

    # Python horizon views use the actual monthly timeline and fixed market-size groups.
    make_horizon_plot(data, "MEDIAN SALE PRICE NSA YOY (%)",
                      "Horizon view · year-over-year sale-price change by metro size",
                      "Median sale-price change (%)", 5, "tier", TIERS,
                      IMAGES / "redfin_horizon_price_yoy.png")
    make_horizon_plot(data, "MEDIAN DAYS ON MARKET YOY (DAYS)",
                      "Horizon view · days-on-market change by Census region",
                      "Median days-on-market change (days)", 10, "census_region", CENSUS_REGIONS,
                      IMAGES / "redfin_horizon_days_yoy.png")

    year_groups = {}
    for year, rows in data.groupby(data["period"].dt.year, sort=True):
        per_metro = rows.groupby("region_id")["MEDIAN SALE PRICE NSA ($)"].median().dropna().to_numpy(dtype=float)
        year_groups[str(year)] = per_metro
    price_ticks = np.log10(np.array([50_000, 100_000, 200_000, 400_000, 800_000, 1_600_000]))
    price_labels = ["$50k", "$100k", "$200k", "$400k", "$800k", "$1.6m"]
    density_ridges(year_groups, "Ridgeline view · annual metro sale-price distributions",
                   "Annual median sale price per metro (log scale)",
                   IMAGES / "redfin_ridgeline_price_by_year.png",
                   transform=np.log10, inverse_ticks=(price_ticks, price_labels))

    recent = data[data["period"].between(pd.Timestamp("2025-09-01"), pd.Timestamp("2026-08-01"))]
    days_by_tier = {tier: rows.groupby("region_id")["MEDIAN DAYS ON MARKET (DAYS)"].median().dropna().to_numpy(dtype=float)
                    for tier, rows in recent.groupby("tier", observed=False)}
    density_ridges(days_by_tier, "Ridgeline view · days on market by metro-size tier",
                   "Metro-level median days on market (Sep 2025–Aug 2026)",
                   IMAGES / "redfin_ridgeline_days_by_tier.png", clip=.99)

    latest = data[data["period"] == data["period"].max()]
    month_counts = data.groupby("period").size()
    summary = {
        "source_rows": int(len(data)), "region_count": int(data["region_id"].nunique()),
        "state_count": int(data["state"].nunique()), "months": [f"{pd.Timestamp(x):%Y-%m}" for x in months],
        "date_start": f"{pd.Timestamp(months[0]):%Y-%m}", "date_end": f"{pd.Timestamp(months[-1]):%Y-%m}",
        "missing_region_months": int(data["region_id"].nunique() * len(months) - len(data)),
        "tier_counts": data.drop_duplicates("region_id")["tier"].value_counts().reindex(TIERS, fill_value=0).to_dict(),
        "latest": {"month": f"{latest['period'].iloc[0]:%Y-%m}",
                   "median_sale_price": json_number(latest["MEDIAN SALE PRICE NSA ($)"].median()),
                   "median_sale_price_yoy": json_number(latest["MEDIAN SALE PRICE NSA YOY (%)"].median()),
                   "median_days_on_market": json_number(latest["MEDIAN DAYS ON MARKET (DAYS)"].median()),
                   "median_inventory": json_number(latest["INVENTORY"].median())},
        "core_missing_percent": {FIELDS[col]: round(float(data[col].isna().mean() * 100), 2)
                                 for col in ["HOMES SOLD", "MEDIAN SALE PRICE NSA ($)",
                                             "MEDIAN DAYS ON MARKET (DAYS)", "ACTIVE LISTINGS", "INVENTORY"]},
        "note": "Monthly metro panel; 4 fixed market-size tiers use each metro's median monthly homes sold in 2024–2025.",
    }
    write_json(OUT / "summary.json", summary)
    print(f"Prepared {len(data):,} rows for {summary['region_count']} metros and {len(months)} months.")
    print(f"Wrote {len(months)} month files and four figures under {ROOT}.")


if __name__ == "__main__":
    main()
