"""
Carrier processor: product page → shareddocs.com PDF links → download.
Groups 37 entries into ~13 product families.
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

# Map series tokens → carrier.com product page URL
# The key is the product FAMILY, value is the carrier.com URL
FAMILY_URLS = {
    "48FE": "https://www.carrier.com/us/en/commercial/packaged-outdoor/48fe/",
    "48GE": "https://www.carrier.com/us/en/commercial/packaged-outdoor/48ge/",
    "48V": "https://www.carrier.com/us/en/commercial/packaged-outdoor/48v/",
    "48K": "https://www.carrier.com/us/en/commercial/packaged-outdoor/48k/",
    "50A": "https://www.carrier.com/us/en/commercial/packaged-outdoor/50a/",
    "50P": "https://www.carrier.com/us/en/commercial/packaged-outdoor/50p/",
    "50GC": "https://www.carrier.com/us/en/commercial/packaged-outdoor/50gc/",
    "50FCQ": "https://www.carrier.com/us/en/commercial/packaged-outdoor/50fcq/",
    "50LC": "https://www.carrier.com/us/en/commercial/packaged-outdoor/50lc/",
    "50WE": "https://www.carrier.com/us/en/commercial/packaged-outdoor/50we/",
    "50XCW": "https://www.carrier.com/us/en/commercial/packaged-outdoor/50xcw/",
    "38AXZ": "https://www.carrier.com/us/en/commercial/split-systems-and-condensers/38axz/",
    "38AU": "https://www.carrier.com/us/en/commercial/split-systems-and-condensers/38auz/",
    "38AXQ": "https://www.carrier.com/us/en/commercial/split-systems-and-condensers/38axz/",
}

# Map manifest series → family key
def get_family(series):
    """Extract the product family from a series string like '48FE**08' or '50LC(D,E'"""
    # Try clean alphanumeric prefix
    m = re.match(r'^([0-9]+[A-Z]+)', series)
    if m:
        prefix = m.group(1)
        # Check against known families
        for fam in FAMILY_URLS:
            if prefix.startswith(fam):
                return fam
    return series[:4]  # fallback

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

def process_carrier():
    manifest = load_m()

    # Group entries by family
    families = {}
    for mid, entry in manifest.items():
        if entry["brand"] != "CARRIER" or entry.get("status") == "found":
            continue
        fam = get_family(entry["series"])
        if fam not in families:
            families[fam] = []
        families[fam].append((mid, entry))

    log.info(f"Processing Carrier: {sum(len(v) for v in families.values())} entries in {len(families)} families")

    # First, fetch each product page and cache PDF links
    family_pdfs = {}
    for fam in families:
        url = FAMILY_URLS.get(fam)
        if not url:
            log.info(f"  Family {fam}: no URL mapping")
            continue

        code, html = fetch(url)
        if code != 200:
            log.info(f"  Family {fam}: HTTP {code} from {url}")
            continue

        # Extract shareddocs.com PDF links
        pdfs = re.findall(r'href="(https?://www\.shareddocs\.com/hvac/docs/[^"]+\.pdf)"', html)
        pd_pdfs = [p for p in pdfs if 'PD' in p.split('/')[-1].upper() and 'PD.pdf' in p.lower() or 'PD.' in p]
        if not pd_pdfs:
            # Broader search
            pd_pdfs = [p for p in pdfs if 'product' in p.lower() or 'data' in p.lower()]

        log.info(f"  Family {fam}: {len(pdfs)} PDFs, {len(pd_pdfs)} Product Data from {url}")
        for p in pd_pdfs:
            log.info(f"    {p.split('/')[-1]}")
        family_pdfs[fam] = (url, pd_pdfs)

    # Now match entries to PDFs
    found = 0
    for fam, entries in families.items():
        if fam not in family_pdfs:
            for mid, entry in entries:
                entry["status"] = "not_found"
                entry["evidence"] = f"No product page or PDFs found for family {fam}"
            save_m(manifest)
            continue

        product_url, all_pdfs = family_pdfs[fam]

        for mid, entry in entries:
            if not all_pdfs:
                entry["status"] = "not_found"
                entry["evidence"] = f"No Product Data PDFs found on {product_url}"
                save_m(manifest)
                continue

            # Use the first matching PD PDF (or the one matching the capacity)
            series = entry["series"]
            caps = entry.get("capacities", [])
            best_pdf = all_pdfs[0]  # default to first

            # Try to match by capacity
            if caps:
                cap_str = str(caps[0])
                cap_nums = [int(n) for n in re.findall(r'(\d+)', cap_str) if int(n) > 10]
                if cap_nums:
                    btu_tons = max(cap_nums) / 12000  # rough tons
                    for pdf_url in all_pdfs:
                        fname = pdf_url.split('/')[-1]
                        # Parse tonnage range from filename like "48-50FE-4-7" or "48-50FE-8-16"
                        range_match = re.search(r'-(\d+)-(\d+)[A-Z]*\.pdf$', fname)
                        if range_match:
                            lo, hi = int(range_match.group(1)), int(range_match.group(2))
                            if lo <= btu_tons <= hi + 5:
                                best_pdf = pdf_url
                                break

            # Download
            ref_id = entry.get("reference_ids", ["0"])[0]
            ref_type = (entry.get("refrigerants", ["UNKNOWN"])[0] or "UNKNOWN").replace("/","-").replace(" ","-")
            brand = entry["brand"]
            stem = best_pdf.split("/")[-1].replace(".pdf", "")[:80]
            fname = safe_fn(f"{stem}__Ref{ref_id}_{brand}_{series}_{ref_type}.pdf")
            outpath = PDF_DIR / fname

            if download_pdf(best_pdf, outpath):
                entry["pdf_filename"] = fname
                entry["pdf_url"] = best_pdf
                entry["status"] = "found"
                entry["verdict"] = "Carrier product page"
                entry["score"] = 15
                entry["evidence"] = f"Source: {product_url}"
                found += 1
                log.info(f"  {mid}: FOUND {fname}")
            else:
                entry["status"] = "not_found"
                entry["evidence"] = f"Download failed: {best_pdf}"

            save_m(manifest)
            time.sleep(0.5)

    log.info(f"Carrier done: {found} found")

if __name__ == "__main__":
    process_carrier()
