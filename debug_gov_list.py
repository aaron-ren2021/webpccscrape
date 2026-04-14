"""Quickly dump the gov.pcc list page HTML structure to analyze what data is available."""
from __future__ import annotations

import sys
sys.path.insert(0, ".")

from dotenv import load_dotenv
load_dotenv()

from core.config import Settings
from crawler.common import optional_playwright_fetch_html, parse_html

settings = Settings.from_env()

print("Fetching gov.pcc list page...")
html = optional_playwright_fetch_html(
    settings.gov_url,
    settings,
    wait_selector="table[id='row']",
)

soup = parse_html(html)

# Find the main table
table = soup.select_one("table#row") or soup.select_one("table")
if not table:
    print("No table found!")
    sys.exit(1)

# Check table headers
headers = table.select("thead th, thead td, tr:first-child th, tr:first-child td")
print(f"\nTable headers ({len(headers)}):")
for i, th in enumerate(headers):
    print(f"  Column {i}: {th.get_text(strip=True)[:50]}")

# Check first few rows
rows = table.select("tbody tr")
print(f"\nRows found: {len(rows)}")

# Sample: first 3 rows
for ridx, row in enumerate(rows[:3]):
    cells = row.select("td")
    print(f"\n--- Row {ridx} ({len(cells)} cells) ---")
    for cidx, td in enumerate(cells):
        txt = td.get_text(" ", strip=True)[:100]
        link = td.select_one("a")
        href = link.get("href", "") if link else ""
        print(f"  td[{cidx}]: {txt}")
        if href:
            print(f"         href: {href[:80]}")

# Save full table HTML for analysis
with open("output/gov_list_table.html", "w") as f:
    f.write(str(table))
print(f"\nFull table saved to output/gov_list_table.html")
