# eGreenWatch Portal KML Scraper (Playwright)

This script automates downloading **KML files** from the eGreenWatch portal for a given **State** and **Site Type**.  
Site URL: https://egreenwatch.nic.in/Public/Reports/View_Download_KML.aspx
It uses **Playwright (Chromium)** to navigate the site, read the grid of results, and download each KML file into an organized folder structure.

⚠️ **Important:** The portal uses a CAPTCHA. You must **solve the CAPTCHA manually** and click **"View Sites..."** once the dropdowns are selected. After that, the script continues automatically.

---

## ✅ What this script does

- Selects **State** and **Site Type** from dropdowns
- Waits until the results grid contains **real data rows**
- Downloads each KML file in the table
- Moves through all pages using the pager links (`Page$...`)
- Saves files in a clean folder structure
- Writes a CSV log of every attempted download

---

## 🧠 Code Flow (Function-wise)

### safe_folder_name(name)

- Converts a state / site type label into a folder-safe string.
- Replaces spaces and / with _.
- Used to build the download directory name.

### get_arguments()

- Reads command-line arguments:
  - state (required)
  - site (required)
- Returns parsed values as args.state and args.site.

### write_log(row)

- Appends one row to downloads_log.csv.
- Writes headers automatically the first time the file is created.
- Logs: state, site type, page number, row metadata, file name, status, timestamp.

### get_first_gpsid(page)

- Reads the GPS ID from the first real row of the current page.
- Used to detect when the grid changes after clicking a pager link.

### wait_for_full_grid_load(page, previous_first_gps)

- Waits until the results grid refreshes after page navigation.
- Checks that:
  - at least one valid data row exists
  - the first GPS ID is different from the previous page
- Prevents reading stale rows before the next page loads fully.

## 🧭 Main Execution Flow (run())

### Step 1: Read inputs and prepare folders

- Reads state and site_type from CLI.
- Builds download folder:
  - downloads/<STATE>/<SITE_TYPE>/
- Creates the folder if it doesn’t exist.

### Step 2: Launch browser and open the portal

- Starts Playwright Chromium (non-headless so you can solve CAPTCHA).
- Opens:
  - https://egreenwatch.nic.in/Public/Reports/View_Download_KML.aspx

### Step 3: Select dropdowns (State + Site Type)

- Selects the provided values in the dropdown menus using Playwright.

### Step 4: Manual CAPTCHA + View Sites click

- Script pauses and waits while you:
  - solve CAPTCHA
  - click View Sites...
- Then script waits until real table rows are detected.

### Step 5: Page loop (download everything)

For each page:
- Read all rows from the table
- Filter valid rows (real data rows only)
- For each valid row:
  - Extract row fields (S.No, metadata, GPS ID)
  - Create filename: <SNO>_<GPSID>.kml
  - Click the download control safely (ignores pager/fake rows)
  - Save the downloaded file to the correct folder
  - Log result to downloads_log.csv

### Step 6: Navigate to the next page

- Collects pager links (a[href*='Page$'])
- Extracts page numbers and selects the next page number
- Clicks the exact pager link for the next page
- Waits for the grid to refresh using wait_for_full_grid_load()

### Step 7: Stop condition

- When no forward pages exist, the loop ends.
- Browser closes and script prints completion message.

---

## 🧾 Logging

Each attempted download writes one row to `downloads_log.csv` including:

- State, SiteType, Page
- S.No, Circle, Division, Range, SiteName, AreaHa, GPSID
- FileName
- Status (`SUCCESS` / `FAILED`)
- Timestamp

This helps track failures and what was downloaded.

---

## 📁 Output structure

Files are stored as:
downloads/<STATE>/<SITE_TYPE>/<SNO>_<GPSID>.kml
Eg: downloads/Andaman_Nicobar_Islands/CA_Land/1_32594.kml

---

## ⚙️ Requirements

- Python 3.9+
- Playwright

---

## 🔧 Installation

(Optional) Create and activate a virtual environment:

### Windows
```bash
python -m venv venv
venv\Scripts\activate
```

### Install dependencies:
```bash
pip install playwright
playwright install
```

---

## ▶️ How to run

### Run the script with state and site type (labels must match the dropdown exactly):
```bash
python scraper.py --state "Andaman Nicobar Islands" --site "CA Land"
```
- Mention the desired state name and the site type of our choice
- Site types:
  - CA Land
  - Diverted Land
  - Other Plantation Sites(Non-CA)
  - Plantation Work Sites (CA & Non-CA)
  - Asset Sites

### To do in the browser

- The script will open the eGreenWatch page and select the dropdown values
- Solve the CAPTCHA manually
- Click "View Sites..."
- The script will start downloading automatically page by page

---

## States with no data

