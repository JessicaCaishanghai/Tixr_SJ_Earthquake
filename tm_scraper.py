"""
Ticketmaster San Jose Earthquakes Scraper
Scrapes all SJE-related events from the search results page,
then collects resale listings (Section / Price) for each event.
"""

import os
import re
import subprocess
import time

import pandas as pd

# Save all output files to the same directory as this script
OUT_DIR = os.path.dirname(os.path.abspath(__file__))
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

SEARCH_URL = "https://www.ticketmaster.com/search?q=san+jose+earthquakes"


def build_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,800")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_argument(
        "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install(), log_output=subprocess.DEVNULL),
        options=options,
    )
    driver.set_page_load_timeout(30)
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver


def get_page(driver, url, retries=3, wait=5):
    """Load a page with retries on failure."""
    for attempt in range(retries):
        try:
            driver.get(url)
            time.sleep(wait)
            return True
        except Exception as e:
            print(f"  [retry {attempt+1}/{retries}] {e.__class__.__name__}")
            time.sleep(3)
    return False


# ---------------------------------------------------------------------------
# Step 1: Search page → SJE event list
# ---------------------------------------------------------------------------

def scrape_event_list():
    print(f"Opening search page: {SEARCH_URL}")
    driver = build_driver()
    rows = []
    try:
        if not get_page(driver, SEARCH_URL, wait=5):
            print("Failed to load search page")
            return pd.DataFrame()

        # Scroll until no new content loads
        last_h = driver.execute_script("return document.body.scrollHeight")
        for _ in range(15):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            new_h = driver.execute_script("return document.body.scrollHeight")
            if new_h == last_h:
                break
            last_h = new_h

        cards = driver.find_elements(By.CSS_SELECTOR, "[data-testid='event-list-link']")
        print(f"Found {len(cards)} event cards")

        for card in cards:
            href = card.get_attribute("href") or ""
            if not href or "/event/" not in href:
                continue

            raw = re.sub(r"^Find Tickets[\s\|]*", "", card.text.strip())
            parts = raw.split("|")
            name_loc = parts[-1].strip()
            cs = name_loc.split(",")
            name  = cs[0].strip()
            city  = cs[1].strip() if len(cs) > 1 else None
            rest  = cs[2].strip() if len(cs) > 2 else ""
            state = rest[:2] if rest else None
            venue = rest[2:].strip() if len(rest) > 2 else None

            eid_m = re.search(r"/event/([^/?]+)", href)
            event_id = eid_m.group(1) if eid_m else None

            # Extract date from URL if present (long-form URLs embed mm-dd-yyyy)
            dm = re.search(r"(\d{2}-\d{2}-\d{4})", href)
            if dm:
                m, d, y = dm.group(1).split("-")
                date = f"{y}-{m}-{d}"
            else:
                # Fallback: parse grandparent div text for "Month DD, YYYY"
                date = None
                try:
                    gp_text = card.find_element(By.XPATH, "../..").text
                    mo = re.search(
                        r"(January|February|March|April|May|June|July|August|"
                        r"September|October|November|December)\s+(\d{1,2}),\s+(\d{4})",
                        gp_text,
                    )
                    if mo:
                        from datetime import datetime as dt
                        date = dt.strptime(
                            f"{mo.group(1)} {mo.group(2)} {mo.group(3)}", "%B %d %Y"
                        ).strftime("%Y-%m-%d")
                except Exception:
                    pass

            rows.append({
                "event_id": event_id,
                "name":     name,
                "date":     date,
                "city":     city,
                "state":    state,
                "venue":    venue,
                "url":      href,
            })
    finally:
        driver.quit()

    df = pd.DataFrame(rows)
    df = df[df["name"].str.strip() != ""].sort_values("date").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Step 2: Event page → resale listings (Section / Price)
# ---------------------------------------------------------------------------

def scrape_event_listings(event_name, event_date, event_url):
    driver = build_driver()
    rows = []
    try:
        if not get_page(driver, event_url, wait=6):
            print("  Page failed to load, skipping")
            return pd.DataFrame(columns=["event_name", "event_date", "section", "row", "ticket_type", "price", "entry_method"])

        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "[data-bdd='quick-picks-list-item-resale']")
                )
            )
        except Exception:
            pass

        # Scroll the listing panel until element count stabilizes
        try:
            panel = driver.find_element(By.CSS_SELECTOR, "[data-bdd='qp-split-scroll']")
            prev_count = 0
            for _ in range(30):
                driver.execute_script(
                    "arguments[0].scrollTop = arguments[0].scrollHeight", panel
                )
                time.sleep(1.2)
                cur_count = len(driver.find_elements(
                    By.CSS_SELECTOR, "[data-bdd='quick-picks-list-item-resale']"
                ))
                if cur_count == prev_count:
                    break
                prev_count = cur_count
        except Exception:
            pass

        cards = driver.find_elements(
            By.CSS_SELECTOR, "[data-bdd='quick-picks-list-item-resale']"
        )
        print(f"  {len(cards)} listings")

        for card in cards:
            lines = [l.strip() for l in card.text.split("\n") if l.strip()]
            section, row, ticket_type, price, entry = None, None, None, None, None
            for line in lines:
                if line.startswith("Sec"):
                    parts = line.split("•")
                    section = parts[0].replace("Sec", "").strip()
                    row = parts[1].replace("Row", "").strip() if len(parts) > 1 else None
                elif line.startswith("$"):
                    price = float(line.replace("$", "").replace(",", ""))
                elif "Ticket" in line:
                    ticket_type = line
                elif "Entry" in line or "Delivery" in line:
                    entry = line

            rows.append({
                "event_name":   event_name,
                "event_date":   event_date,
                "section":      section,
                "row":          row,
                "ticket_type":  ticket_type,
                "price":        price,
                "entry_method": entry,
            })
    finally:
        driver.quit()

    cols = ["event_name", "event_date", "section", "row", "ticket_type", "price", "entry_method"]
    return pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Step 1: Fetch event list
    df_events = scrape_event_list()
    if df_events.empty:
        print("No events found, exiting")
        return

    sje = df_events[
        df_events["name"].str.lower().str.contains("earthquake|san jose", na=False)
    ].reset_index(drop=True)

    print(f"\n{len(sje)} SJE events found:")
    print(sje[["name", "date", "venue"]].to_string())

    # Save event list
    p = os.path.join(OUT_DIR, "tm_sje_events.csv")
    sje.to_csv(p, index=False)
    print(f"\nEvent list saved to {p}")

    # Step 2: Scrape listings for each event
    print("\nScraping listings for each event...")
    all_listings = []
    for _, ev in sje.iterrows():
        print(f"\n→ {ev['name']} ({ev['date']})")
        df_l = scrape_event_listings(ev["name"], ev["date"], ev["url"])
        all_listings.append(df_l)
        time.sleep(2)

    df_all = pd.concat(all_listings, ignore_index=True)

    # Save listings
    p_listings = os.path.join(OUT_DIR, "tm_sje_listings.csv")
    df_all.to_csv(p_listings, index=False)
    print(f"\n{len(df_all)} listings saved to {p_listings}")

    # Section-level price summary
    if not df_all.empty and "section" in df_all.columns:
        print("\n=== Price Summary by Event × Section ===")
        summary = (
            df_all.groupby(["event_date", "event_name", "section"])["price"]
            .agg(count="count", min_price="min", avg_price="mean")
            .reset_index()
            .sort_values(["event_date", "min_price"])
        )
        print(summary.to_string())
        p_summary = os.path.join(OUT_DIR, "tm_sje_summary.csv")
        summary.to_csv(p_summary, index=False)
        print(f"\nSummary saved to {p_summary}")


if __name__ == "__main__":
    main()
