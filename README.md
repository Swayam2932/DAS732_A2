# DAS732 Assignment 2 — Data Visualization

This repository contains both parts of the DAS732 Assignment 2 visualization work. **Task 1 (SciVis)** explores daily gridMET weather fields with color mapping, contour mapping, and wind-vector plots. **Task 2 (InfoVis)** explores Wikipedia click flows as a network and Redfin housing markets with parallel coordinates, zoomable treemaps, horizon plots, and ridgelines.

The assignment home page connects the two dashboards. After setup, one command starts both applications and makes the two task buttons work:

```sh
python main.py
```

Open <http://127.0.0.1:8000>. SciVis opens at <http://127.0.0.1:8501>; InfoVis is served under `/task2/`. Keep the terminal running while using the dashboards and press `Ctrl+C` to stop both.

## 1. Install the requirements

Use Python 3.10 or newer. From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

On Windows PowerShell, create and activate the environment with:

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 2. Set up Task 1 — SciVis

The dashboard uses the prepared gridMET NetCDF file for January 1 through March 31, 2022:

```text
task1/data/processed/gridmet_2022-01_to_2022-03.nc
```

The prepared file is about 438 MB and is not stored in GitHub. To create it automatically, run from the repository root:

```sh
python task1/process_gridmet.py
```

This downloads the required annual 2022 gridMET variable files from the official archive into `task1/data/raw/gridmet_2022/`, trims them to January–March, and writes the prepared NetCDF at the path above. The raw annual files require roughly 2 GB of disk space. If you already have the prepared NetCDF, copy it directly to `task1/data/processed/` instead.

## 3. Set up Task 2 — InfoVis

The repository includes the compact processed dashboard data so InfoVis can run after cloning without downloading its large source datasets. To regenerate the processed files and figures, place both original inputs in `task2/`:

- `clickstream_data1.tsv` — the Wikipedia clickstream source, approximately 1.4 GB.
- `redfin_housing.csv` — the Redfin monthly housing-market source, approximately 20 MB.

Then run these commands from the repository root:

```sh
python task2/prepare_infovis.py
python task2/prepare_redfin.py
```

The scripts write network and monthly housing JSON files to `task2/data/processed/`, and the Redfin preparation script writes four horizon/ridgeline figures to `task2/images/`. The clickstream scan may take several minutes. The large original datasets are excluded from GitHub; obtain them from the assignment-provided data sources and place them at the filenames above.

## Dashboard contents

### Task 1 — SciVis

- **Color mapping:** compare palettes, continuous/discrete normalization, quarter-global and per-day limits, and field values over time.
- **Contour mapping:** explore Marching Squares isolines and filled contours, with a comparison of both algorithms.
- **Quiver plot:** inspect wind direction and speed with adjustable sampling and scaling.

### Task 2 — InfoVis

- **Network:** compare Spring, Kamada–Kawai, and ForceAtlas2 layouts for directed click flows, with search, filtering, labels, hover details, and neighbor selection.
- **Parallel coordinates:** explore Redfin metro metrics by month, reorder and brush dimensions, filter market-size tiers, and adjust edge bundling.
- **Zoomable treemap:** switch between state→metro and market-size tier→state→metro hierarchies; choose the area and color measures, zoom, and inspect details.
- **Horizon and ridgeline plots:** compare monthly housing trends and grouped distributions.

## Repository layout

```text
main.py                 Starts SciVis and serves the landing page plus InfoVis
index.html              Assignment landing page with the two dashboard buttons
requirements.txt        Shared Python dependencies
task1/                  SciVis app, utilities, and gridMET preparation script
task2/                  InfoVis app, preparation scripts, generated data and figures
```

See `task1/README.md` and `task2/README.md` for task-specific implementation details. Raw inputs, virtual environments, and local caches are intentionally excluded from version control.
