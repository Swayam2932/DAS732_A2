# gridMET SciVis

An interactive Streamlit dashboard for three SciVis tasks using the gridMET CONUS daily weather dataset: color mapping, contour mapping, and wind vector (quiver) visualization.

## Requirements

- Python 3.10 or newer
- The prepared NetCDF file `gridmet_2022-01_to_2022-03.nc` (90 daily records from 2022-01-01 through 2022-03-31)

The NetCDF file is intentionally not stored in this Git repository because it is large (about 438 MB). Obtain the prepared file from your project files and place it at:

```text
data/processed/gridmet_2022-01_to_2022-03.nc
```

## Setup and run

Follow the combined setup instructions in the repository's root `README.md`. From the assignment root, create the prepared data with `python task1/process_gridmet.py` if the NetCDF file is not present, then start both task dashboards together with `python main.py`.

## Dashboard tabs

1. **Color mapping** — inspect daily scalar fields, palettes, normalization, quarter-global versus daily limits, and anomalies. Hover the map to see coordinates and the field value.
2. **Contour mapping** — view Marching Squares isolines, filled contours, or a comparison of both. Hover to inspect locations and values.
3. **Quiver plot** — explore wind speed and direction with adjustable arrow sampling and scaling. Hover a vector for wind speed, wind-from direction, and eastward/northward components.

If the prepared NetCDF file is missing, the dashboard displays the expected path. To recreate the quarter dataset instead, install the requirements and run `python process_gridmet.py`; that optional script downloads the 2022 source variables from the official gridMET archive and writes the prepared file to `data/processed/`.

## Project files

- `app.py` — Streamlit dashboard.
- `scivis_utils.py` — data loading, field conversion, plotting, and vector helpers.
- `requirements.txt` — Python dependencies for running the dashboard.
- `process_gridmet.py` — optional source-data download and preprocessing script.
- `generate_scivis_artifacts.py` — optional script for generating static assignment figures and the GIF; it requires the prepared NetCDF file.
- `images/scivis/fig5_precipitation_7sample_animation.gif` — animation shown in the dashboard.
