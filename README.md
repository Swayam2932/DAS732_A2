# DAS732 Assignment 2 — Data Visualization

This assignment has two dashboards: **Task 1 — SciVis** for gridMET weather fields, and **Task 2 — InfoVis** for clickstream networks and Redfin housing data.

## Download these files

Get the files from the [Assignment 2 data folder on SharePoint](https://iiitbac-my.sharepoint.com/:f:/g/personal/swayam_savaliya_iiitb_ac_in/IgCrdybQ9RHERJXcxIb6hYxXAeQTCuwz6rFaqsATyG0z4zI?e=k06yQH), then put them at these paths after cloning the repository:

| Task | File | Put it here | Needed for |
|---|---|---|---|
| **Task 1 — SciVis** | `gridmet_2022-01_to_2022-03.nc` | `task1/data/processed/gridmet_2022-01_to_2022-03.nc` | Required to run SciVis. This is the prepared January–March 2022 file. |
| **Task 2 — InfoVis** | No download needed | Already included under `task2/data/processed/` | Task 2 is ready to run after cloning the repository. |

For the dashboards, download only the required SciVis file shown above. Task 2’s data and figures are included in the repository.

## Install and run both dashboards

Install Python 3.10 or newer and the shared requirements from the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1` instead of the `source` command.

After placing the required SciVis file listed above, start the assignment launcher:

```sh
python main.py
```

Open <http://127.0.0.1:8000>. Use the **Task 1 — SciVis** and **Task 2 — InfoVis** buttons to open each dashboard. Leave the terminal running while you use the dashboards; press `Ctrl+C` to stop both.

## What is included

- **SciVis:** color mapping, contour mapping (Marching Squares and contour fill), and wind quiver plots.
- **InfoVis:** interactive clickstream network with three layouts; Redfin parallel coordinates with edge bundling; zoomable treemaps; horizon and ridgeline plots.

The repository includes the dashboard code, requirements, and prepared InfoVis data/figures. Large source datasets and the prepared gridMET NetCDF are kept in the SharePoint folder rather than GitHub.
