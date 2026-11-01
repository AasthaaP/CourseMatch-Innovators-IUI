"""Download the catalog HTML into data/raw/ and do nothing else.

Spec: S3 (Section 9.1). Owner: Aastha.
Run on a machine that can reach catalog.tamu.edu: python scripts/scrape_catalog.py
"""
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data/raw"
HEADERS = {"User-Agent": "Mozilla/5.0 (CourseMatch course project; Texas A&M CSCE 634)"}
FILES = {
    "grad_csce.html": "https://catalog.tamu.edu/graduate/course-descriptions/csce/",
    "grad_ecen.html": "https://catalog.tamu.edu/graduate/course-descriptions/ecen/",
    "ugrad_csce.html": "https://catalog.tamu.edu/undergraduate/course-descriptions/csce/",
    "ugrad_ecen.html": "https://catalog.tamu.edu/undergraduate/course-descriptions/ecen/",
    "ugrad_math.html": "https://catalog.tamu.edu/undergraduate/course-descriptions/math/",
    "ugrad_stat.html": "https://catalog.tamu.edu/undergraduate/course-descriptions/stat/",
    "program_mscs.html": "https://catalog.tamu.edu/graduate/colleges-schools-interdisciplinary/engineering/computer-science/",
}


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for i, (name, url) in enumerate(FILES.items()):
        if i:
            time.sleep(1)
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        (RAW_DIR / name).write_text(response.text, encoding="utf-8")
        print(f"{name}  {len(response.content)} bytes  {response.text.count('courseblock')} blocks")


if __name__ == "__main__":
    main()
