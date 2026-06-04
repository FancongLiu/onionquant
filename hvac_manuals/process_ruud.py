"""
Targeted Ruud processor — fetches known product pages, extracts PDF links, downloads spec sheets.
"""
import sys, io, re, json, time, logging
from pathlib import Path
import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

PROJECT_DIR = Path(__file__).parent
PDF_DIR = PROJECT_DIR / "pdf_downloads"
MANIFEST_PATH = PROJECT_DIR / "manifest.json"
PDF_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

session = requests.Session()
session.timeout = 30
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
})

# Known Ruud product page URLs for our series
RUUD_PRODUCT_PAGES = {
    "RGEG": "https://www.ruud.com/product/RuudRGEG2T-Renaissance-Line-15-25-Ton-Copy-1Rheem-RGEG2T-Commercial-RenaissancePackageGasElectric",
    "RGEDZT": "https://www.ruud.com/product/ruud-commercial-package-gas-electric-RGEDZT",
    "RLNL": "https://www.ruud.com/product/ruud-commercial-package-ac-rlnl-b-rlnl-g-rlnl-h-15-20-ton",
    "RHPH": "https://www.ruud.com/product/Reat-Pu-RHPH2T-Commercialpackagedheatpump-ruud",
    "RHPDYC": "https://www.ruud.com/product/RHPDYC-Renaissance-Line-Achiever-Plus-Series-Packaged-Heat-Pump",
    "RHPCYB": "https://www.ruud.com/product/RHPCYB-Renaissance-Line-Achiever-Series-Packaged-Heat-Pump",
    "RHPDZT": "https://www.ruud.com/product/ruud-commercial-package-heat-pump-RHPDZT",
    "RHPCZT": "https://www.ruud.com/product/ruud-commercial-package-heatpump-RHPCZR-RHPCZT",
    "RKNL": "https://www.ruud.com/product/ruud-commercial-package-ac-rlkn-b-6-ton",  # RLKN is similar series
    "RACY": None,  # Try from listing page
    "RHPHYB": None,  # Need to find
    "VACDZR": None,  # V-series air handler
    "VACDZS": None,
}

def safe_fn(n):
    return re.sub(r'[<>:"/\\|?*]', "_", str(n))[:200]

def load_m():
    return json.loads(open(MANIFEST_PATH, "r", encoding="utf-8").read())

def save_m(m):
    json.dump(m, open(MANIFEST_PATH, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

def fetch(url, timeout=30):
    try:
        r = session.get(url, timeout=timeout, allow_redirects=True)
        r.encoding = "utf-8"
        return r.status_code, r.text
    except Exception as e:
        return -1, str(e)

def extract_pdfs_from_html(html):
    """Extract all .pdf URLs from HTML, preferring myrheem.com ones."""
    results = []
    # Direct PDF links
    for url in re.findall(r'href\s*=\s*"(https?://[^"]+\.pdf)"', html):
        results.append(url)
    # Also urls in script tags
    for url in re.findall(r'"(https?://[^"]+\.pdf)"', html):
        if url not in results:
            results.append(url)
    # Prefer spec sheets over warranty cards
    spec_sheets = [u for u in results if 'warranty' not in u.lower() and 'spec' not in u.lower()]
    warranty = [u for u in results if 'warranty' in u.lower()]
    # Just return all (prefer non-warranty first)
    ordered = [u for u in results if 'warranty' not in u.lower()]
    ordered += [u for u in results if 'warranty' in u.lower()]
    return ordered

def download_pdf(url, outpath):
    if outpath.exists() and outpath.stat().st_size > 1000:
        return True
    try:
        r = session.get(url, timeout=120)
        if r.status_code == 200 and len(r.content) > 1000 and r.content[:4] == b"%PDF":
            outpath.write_bytes(r.content)
            log.info(f"    Downloaded: {outpath.stat().st_size/1024:.0f}KB")
            return True
    except Exception:
        pass
    return False

def process_ruud():
    manifest = load_m()
    log.info(f"Processing remaining Ruud entries...")

    # Get remaining Ruud entries
    ruud_pending = [(mid, e) for mid, e in manifest.items()
                    if e["brand"] == "RUUD" and e.get("status") != "found"]

    log.info(f"Pending Ruud entries: {len(ruud_pending)}")
    found = 0

    for mid, entry in ruud_pending:
        series = entry["series"]
        brand = entry["brand"]
        models = entry.get("models", [])
        parent_url = RUUD_PRODUCT_PAGES.get(series)

        log.info(f"  {mid}: series={series} page={'found' if parent_url else 'NOT FOUND'}")

        if not parent_url:
            entry["status"] = "not_found"
            entry["evidence"] = f"No Ruud product page URL known for series {series}"
            save_m(manifest)
            continue

        # Fetch product page
        code, html = fetch(parent_url)
        if code != 200:
            entry["status"] = "not_found"
            entry["evidence"] = f"Product page returned HTTP {code}"
            save_m(manifest)
            continue

        # Extract PDF links
        pdfs = extract_pdfs_from_html(html)
        log.info(f"    Found {len(pdfs)} PDF links on product page")

        if not pdfs:
            entry["status"] = "not_found"
            entry["evidence"] = f"No PDF links on product page {parent_url}"
            save_m(manifest)
            continue

        # Try downloading
        success = False
        for pdf_url in pdfs[:5]:
            ref_id = entry.get("reference_ids", ["0"])[0]
            ref_type = (entry.get("refrigerants", ["UNKNOWN"])[0] or "UNKNOWN").replace("/","-").replace(" ","-")
            stem = pdf_url.split("/")[-1].replace(".pdf", "")[:80]
            fname = safe_fn(f"{stem}__Ref{ref_id}_{brand}_{series}_{ref_type}.pdf")
            outpath = PDF_DIR / fname

            if download_pdf(pdf_url, outpath):
                entry["pdf_filename"] = fname
                entry["pdf_url"] = pdf_url
                entry["status"] = "found"
                entry["verdict"] = "Downloaded from product page"
                entry["score"] = 10
                entry["evidence"] = f"Source: {parent_url}"
                log.info(f"    => FOUND: {fname}")
                success = True
                found += 1
                break

        if not success:
            entry["status"] = "not_found"
            entry["evidence"] = f"PDF download failed for {len(pdfs)} links on product page"

        save_m(manifest)
        time.sleep(0.5)

    log.info(f"Ruud processing done: {found}/{len(ruud_pending)} found")

if __name__ == "__main__":
    process_ruud()
