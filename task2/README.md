# InfoVis Explorer

A local dashboard for the InfoVis part of DAS732 Assignment 2. The network view uses the Wikipedia clickstream dataset. Parallel coordinates, treemaps, horizon plots, and ridgeline plots use the Redfin housing dataset. These sources remain separate because they have different structures and support different tasks.

## Requirements

- Python 3.10 or newer
- `clickstream_data1.tsv` and `redfin_housing.csv` in this directory
- A modern browser

The clickstream TSV is about 1.4 GB. The Redfin CSV is about 20 MB and contains 75,665 monthly metro records from January 2020 through August 2026. Raw input files are ignored by Git; keep the source files beside the preparation scripts.

## Setup and run

For the combined assignment landing page and both dashboards, follow the repository's root `README.md` and run `python main.py` from the assignment root. The independent InfoVis setup below is available when working on this task alone.

From this directory, create an environment and install the Python dependencies:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Prepare the clickstream network and Redfin visualizations:

```sh
python prepare_infovis.py
python prepare_redfin.py
```

The first command scans the large clickstream TSV and may take a few minutes. The Redfin command writes one compact JSON file per month and four high-resolution Python plots.

Serve the dashboard locally:

```sh
python -m http.server 8000 --bind 127.0.0.1
```

Open <http://127.0.0.1:8000> in a browser. Stop the server with `Ctrl+C`.

D3 is bundled at `assets/d3.v7.min.js`, so the dashboard does not need a CDN connection at runtime. Re-run the relevant preparation script if its source data or generated output is changed or removed.

## Views and interactions

### 1. Clickstream network

The directed network uses internal `link` records. Select Spring (Fruchterman–Reingold), Kamada–Kawai, or ForceAtlas2; compare the three side-by-side previews; adjust the visible high-activity page count and edge-click threshold; search and label pages; hover for click, degree, and volume details; and click a node to highlight direct neighbors. For legibility, it shows a 120-page high-activity core and up to 1,800 strongest internal links. The dashboard reports the fraction of total internal-link click weight represented by the selected edges.

### 2. Redfin parallel coordinates with edge bundling

Each line represents one metro in the selected month. Reorder axes by dragging, brush multiple dimensions, filter the four fixed metro-size tiers, adjust bundling strength, and hover for the metro’s values. Lines bend toward the median profile of their metro-size tier; these bundles summarize similar multivariate records, not literal connections between metros. Counts, days, and price axes use log scales where needed to handle skew.

### 3. Redfin zoomable treemaps

Choose a monthly snapshot, select an additive area measure (homes sold, active listings, inventory, or pending sales), and color the cells by median sale price, year-over-year price change, or days on market. Explore either `State → Metro` or `Market-size tier → State → Metro`. Click a state or tier to zoom and use breadcrumbs to move back up. Median prices are encoded by color, never summed into area.

### 4. Redfin horizon and ridgeline plots

Redfin contains real monthly observations, so these plots use a time axis. Horizon variation 1 compares monthly year-over-year sale-price changes across metro-size tiers; variation 2 compares year-over-year days-on-market changes across four Census regions. Ridgeline variation 1 compares annual metro sale-price distributions; variation 2 compares metro-level days-on-market distributions across tiers for the latest 12 months. Market-size tiers are fixed using each metro’s median monthly homes sold during 2024–2025.

## Data processing and generated files

`prepare_infovis.py` scans the clickstream TSV with DuckDB. It generates the network core and its three layout coordinates. The network graph is intentionally compact; its selected share is shown in the dashboard.

`prepare_redfin.py` reads the complete monthly CSV, extracts the two-letter state code from every metro name, assigns fixed homes-sold quartiles, and writes monthly snapshots for the browser. Its horizon and ridgeline PNGs are generated with Matplotlib. The monthly panel has 946 metro areas and 80 observations per metro in most cases; there are 15 missing region-month records and a small number of missing metric values. The parallel plot omits rows with a missing value on any plotted axis.

Generated outputs include:

- `data/processed/summary.json` and `network.json` — clickstream counts and selected network
- `data/processed/redfin/summary.json` — housing coverage, latest-month summary, and tier counts
- `data/processed/redfin/months/YYYY-MM.json` — one month of metro metrics per file
- `images/redfin_horizon_*.png` and `images/redfin_ridgeline_*.png` — four Python figures

