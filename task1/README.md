# gridMET SciVis

An interactive Streamlit dashboard for three SciVis tasks using the gridMET CONUS daily weather dataset: color mapping, contour mapping, and wind vector (quiver) visualization.

## Requirements

- Python 3.10 or newer
- The prepared NetCDF file `gridmet_2022-01_to_2022-03.nc` (90 daily records from 2022-01-01 through 2022-03-31)

The NetCDF file is intentionally not stored in GitHub because it is large (about 438 MB). Download `gridmet_2022-01_to_2022-03.nc` from the [A2 SharePoint data folder](https://iiitbac-my.sharepoint.com/:f:/g/personal/swayam_savaliya_iiitb_ac_in/IgCrdybQ9RHERJXcxIb6hYxXAeQTCuwz6rFaqsATyG0z4zI?e=k06yQH) and place it at this path inside the `task1` folder:

```text
data/processed/gridmet_2022-01_to_2022-03.nc
```

## Setup and run

Follow the combined setup instructions in the repository's root `README.md`. The prepared NetCDF above is the only data file required to run Task 1. Once it is in place, start both task dashboards from the repository root with `python main.py`.

## Dashboard tabs

1. **Color mapping** — inspect daily scalar fields, palettes, normalization, quarter-global versus daily limits, and anomalies. Hover the map to see coordinates and the field value.
2. **Contour mapping** — view Marching Squares isolines, filled contours, or a comparison of both. Hover to inspect locations and values.
3. **Quiver plot** — explore wind speed and direction with adjustable arrow sampling and scaling. Hover a vector for wind speed, wind-from direction, and eastward/northward components.

If the prepared NetCDF file is missing, download it from the A2 SharePoint data folder and place it at the path listed above.

## Project files

- `app.py` — Streamlit dashboard.
- `scivis_utils.py` — data loading, field conversion, plotting, and vector helpers.
- `requirements.txt` — Python dependencies for running the dashboard.
- `generate_scivis_artifacts.py` — optional script for generating static assignment figures and the GIF; it requires the prepared NetCDF file.
- `images/scivis/fig5_precipitation_7sample_animation.gif` — animation shown in the dashboard.
