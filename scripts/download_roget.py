"""
download_roget.py
Download Roget's Thesaurus 1911 from Project Gutenberg and save to
data/roget/roget1911.txt. Verifies file size after download.

Source: https://www.gutenberg.org/cache/epub/10681/pg10681.txt
"""
import hashlib
import sys
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ROGET_DIR    = PROJECT_ROOT / "data" / "roget"
ROGET_FILE   = ROGET_DIR / "roget1911.txt"
ROGET_URL    = "https://www.gutenberg.org/cache/epub/10681/pg10681.txt"
MIN_BYTES    = 800_000   # Sanity check — the file is ~900KB

def download():
    ROGET_DIR.mkdir(parents=True, exist_ok=True)
    if ROGET_FILE.exists():
        print(f"Already downloaded: {ROGET_FILE} ({ROGET_FILE.stat().st_size:,} bytes)")
        return
    print(f"Downloading from {ROGET_URL} ...")
    urllib.request.urlretrieve(ROGET_URL, ROGET_FILE)
    size = ROGET_FILE.stat().st_size
    print(f"Downloaded: {size:,} bytes")
    if size < MIN_BYTES:
        print(f"WARNING: File seems too small (expected >{MIN_BYTES:,} bytes). Check the URL.")
        sys.exit(1)
    print("Download complete.")

if __name__ == "__main__":
    download()
