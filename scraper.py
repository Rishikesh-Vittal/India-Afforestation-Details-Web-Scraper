import asyncio
import os
import csv
import argparse
from datetime import datetime
from playwright.async_api import async_playwright

LOG_FILE = "downloads_log.csv"

def safe_folder_name(name):
    return name.replace(" ", "_").replace("/", "_")

def get_arguments():
    parser = argparse.ArgumentParser(description="eGreenWatch GIS Scraper")

    parser.add_argument("--state", required=True, help="State name exactly as shown")
    parser.add_argument("--site", required=True, help="Site Type exactly as shown")

    return parser.parse_args()

def write_log(row):
    file_exists = os.path.isfile(LOG_FILE)

    with open(LOG_FILE, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        if not file_exists:
            writer.writerow([
                "State", "SiteType", "Page",
                "S.No", "Circle", "Division", "Range",
                "SiteName", "AreaHa", "GPSID",
                "FileName", "Status", "Timestamp"
            ])

        writer.writerow(row)

async def wait_for_full_grid_load(page, previous_first_gps):
    await page.wait_for_function(
        """
        (prev) => {
            const rows = document.querySelectorAll("table[id*='gdCALs'] tbody tr");
            let validCount = 0;
            let firstGPS = null;

            for (let row of rows) {
                const cells = row.querySelectorAll("td");
                if (cells.length >= 9) {
                    const gps = cells[8].innerText.trim();
                    if (gps && !isNaN(gps)) {
                        validCount++;
                        if (!firstGPS) firstGPS = gps;
                    }
                }
            }

            return validCount > 0 && firstGPS !== prev;
        }
        """,
        arg=previous_first_gps,
        timeout=90000
    )

async def get_first_gpsid(page):
    locator = page.locator("table[id*='gdCALs'] tbody tr td:nth-child(9)")
    return (await locator.first.inner_text()).strip()

async def run():
    args = get_arguments()
    state = args.state
    site_type = args.site

    base_download_dir = "downloads"

    state_folder = safe_folder_name(state)
    site_folder = safe_folder_name(site_type)

    DOWNLOAD_DIR = os.path.join(base_download_dir, state_folder, site_folder)

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        await page.goto("https://egreenwatch.nic.in/Public/Reports/View_Download_KML.aspx")

        # Select dropdowns
        await page.select_option("select[id*='ddlState']", label=state)
        await page.select_option("select[id*='ddlSiteType']", label=site_type)

        print("\nSolve CAPTCHA and click 'View Sites...' manually...")

        # Wait for navigation caused by CAPTCHA submit
        await page.wait_for_load_state("networkidle", timeout=120000)

        # Now wait for table rows to appear
        print("Waiting for actual data rows to load...")

        await page.wait_for_function("""
        () => {
            const rows = document.querySelectorAll("table[id*='gdCALs'] tbody tr");
            if (!rows || rows.length === 0) return false;

            for (let row of rows) {
                const cells = row.querySelectorAll("td");
                if (cells.length >= 9) {
                    const gps = cells[8].innerText.trim();
                    if (gps && !isNaN(gps)) {
                        return true;
                    }
                }
            }
            return false;
        }
        """, timeout=120000)

        print("Actual data rows detected.")

        current_page = 1
		
        # -------- LOOP THROUGH PAGES --------
        while True:
            print(f"\nProcessing Page {current_page}")
            await asyncio.sleep(2)
            # -------- EXTRACT ROWS --------
            rows = page.locator("table[id*='gdCALs'] tbody tr")
            row_count = await rows.count()
            print("Rows found:", row_count)

            valid_rows = []

            for i in range(row_count):
                row = rows.nth(i)
                cells = row.locator("td")
                cell_count = await cells.count()

                # Only process real data rows
                if cell_count >= 10:
                    first_cell_text = (await cells.nth(0).inner_text()).strip()
                    gps_text = (await cells.nth(8).inner_text()).strip()

                    if not first_cell_text.isdigit():
                        continue

                    # Check 10th cell (download column) has a real download control
                    download_cell = cells.nth(9)

                    # Look for clickable things in the "download" cell
                    clickable = download_cell.locator("a, input, img")
                    clickable_count = await clickable.count()

                    if clickable_count == 0:
                        continue  # probably pager/footer row

                    # If it's a link, make sure it's NOT a pager link (Page$...)
                    is_pager = False
                    links = download_cell.locator("a")
                    link_count = await links.count()

                    for j in range(link_count):
                        href = await links.nth(j).get_attribute("href")
                        if href and "Page$" in href:
                            is_pager = True
                            break

                    if is_pager:
                        continue  # exclude pagination row

                    # Optional sanity check: GPS should exist
                    if not gps_text:
                        continue

                    valid_rows.append(row)

            print("Valid data rows:", len(valid_rows))

            for row in valid_rows:
                cells = row.locator("td")

                sno = (await cells.nth(0).inner_text()).strip()
                circle = (await cells.nth(1).inner_text()).strip()
                division = (await cells.nth(2).inner_text()).strip()
                range_name = (await cells.nth(3).inner_text()).strip()
                site_name = (await cells.nth(4).inner_text()).strip()
                area = (await cells.nth(5).inner_text()).strip()
                gps_id = (await cells.nth(8).inner_text()).strip()

                print(sno, gps_id)

                filename = f"{sno}_{gps_id}.kml"
                filepath = os.path.join(DOWNLOAD_DIR, filename)

                print(f"Downloading {filename}")

                status = "FAILED"

                for attempt in range(2):  # try max 2 times
                    try:
                        download_cell = row.locator("td").nth(9)

                        # Prefer an actual clickable child in the download cell
                        download_target = download_cell.locator("a, input, img").first

                        # If it's an anchor, reject pager links explicitly
                        if await download_target.count() > 0:
                            tag_name = await download_target.evaluate("(el) => el.tagName.toLowerCase()")
                            if tag_name == "a":
                                href = await download_target.get_attribute("href")
                                if href and "Page$" in href:
                                    raise RuntimeError("Pager link detected in download column; skipping fake row")

                            async with page.expect_download(timeout=30000) as download_info:
                                await download_target.click()
                            download = await download_info.value
                            await download.save_as(filepath)
                            status = "SUCCESS"
                        else:
                            raise RuntimeError("No download control found in download column")

                    except Exception as e:
                        print(f"Attempt {attempt+1} failed for {filename}: {e}")
                        await asyncio.sleep(1)  # small delay before retry

                write_log([
                    state,
                    site_type,
                    current_page,
                    sno,
                    circle,
                    division,
                    range_name,
                    site_name,
                    area,
                    gps_id,
                    filename,
                    status,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ])

            await asyncio.sleep(2)  # cooldown before next page

            next_page_number = current_page + 1

            pager_links = page.locator("a[href*='Page$']")
            link_count = await pager_links.count()

            page_targets = []
            for i in range(link_count):
                href = await pager_links.nth(i).get_attribute("href")
                if not href:
                    continue

                idx = href.find("Page$")
                if idx == -1:
                    continue

                num_part = href[idx + len("Page$"):]
                digits = ""
                for ch in num_part:
                    if ch.isdigit():
                        digits += ch
                    else:
                        break

                if digits:
                    page_targets.append(int(digits))

            forward_pages = sorted({p for p in page_targets if p > current_page})

            if not forward_pages:
                print("No forward pages available. Finished.")
                break

            target = forward_pages[0]
            print(f"Navigating to Page {target}")

            previous_first_gps = await get_first_gpsid(page)

            # Click exact pager link (avoid Page$1 matching Page$10, Page$11, etc.)
            pager_links = page.locator("a[href*='Page$']")
            link_count = await pager_links.count()

            clicked = False
            for i in range(link_count):
                link = pager_links.nth(i)
                href = await link.get_attribute("href")
                if not href:
                    continue

                idx = href.find("Page$")
                if idx == -1:
                    continue

                num_part = href[idx + len("Page$"):]
                digits = ""
                for ch in num_part:
                    if ch.isdigit():
                        digits += ch
                    else:
                        break

                if digits and int(digits) == target:
                    await link.click()
                    clicked = True
                    break

            if not clicked:
                raise RuntimeError(f"Exact pager link for page {target} not found")

            await wait_for_full_grid_load(page, previous_first_gps)
            await page.wait_for_timeout(1500)

            current_page = target

        print("\nScraping completed.")
        await browser.close()

asyncio.run(run())