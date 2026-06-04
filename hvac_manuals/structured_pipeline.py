"""
Fast structured-source pipeline — no web search, just sitemaps + CDNs + known patterns.
Continuously saves manifest.json so progress is always visible.
"""
import sys, io, re, json, time, logging
from pathlib import Path
from collections import defaultdict
import requests
import openpyxl

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

PROJECT_DIR = Path(__file__).parent
PDF_DIR = PROJECT_DIR / "pdf_downloads"
MANIFEST_PATH = PROJECT_DIR / "manifest.json"
EXCEL_PATH = Path(r"E:\HVAC_PDF_search\Unitary_pdf_manual_search_0519_lite.xlsx")

PDF_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

session = requests.Session()
session.timeout = 30
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
})

# ═══════════════ HELPERS ═══════════════

def model_token(m):
    if not m: return "UNKNOWN"
    mm = re.match(r"^([A-Z]+\d+[A-Z]?)", str(m))
    return mm.group(1) if mm else str(m)[:10]

def model_series(m):
    if not m: return "UNKNOWN"
    mm = re.match(r"^([A-Z]+)", str(m))
    return mm.group(1) if mm else "UNKNOWN"

def normalize_brand(b):
    b = str(b).upper()
    for k in ["JOHNSON CONTROLS","CARRIER","BRYANT","LENNOX","BOSCH","RUUD","RHEEM","YORK"]:
        if k in b: return k
    return b

def safe_fn(n):
    return re.sub(r'[<>:"/\\|?*]', "_", str(n))[:200]

def load_manifest():
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_manifest(m):
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=2, ensure_ascii=False)

def fetch(url, timeout=30):
    try:
        r = session.get(url, timeout=timeout, allow_redirects=True)
        r.encoding = "utf-8"
        return r.status_code, r.text
    except Exception as e:
        return -1, str(e)

def extract_docs_from_html(html):
    results = []
    doc_urls = re.findall(r'"DocumentURL"\s*:\s*"(https?://[^"]+\.pdf)"', html)
    doc_types = re.findall(r'"documentType"\s*:\s*"([^"]+)"', html)
    for i, url in enumerate(doc_urls):
        dt = doc_types[i] if i < len(doc_types) else "PDF"
        results.append({"url": url, "type": dt, "source": "DocumentURL"})
    # Also href pdfs
    for url in re.findall(r'href\s*=\s*"(https?://[^"]+\.pdf)"', html):
        if url not in [r["url"] for r in results]:
            results.append({"url": url, "type": "PDF", "source": "href"})
    return results

def match_sitemap(xml_text, tokens, path_hint="/product/"):
    urls = re.findall(r"<loc>([^<]+)</loc>", xml_text)
    results = []
    for url in urls:
        for t in tokens:
            if t.upper() in url.upper() and path_hint in url.lower():
                results.append((t, url))
                break
    return list(dict.fromkeys(u for _, u in results))

def download_pdf(url, outpath, timeout=120):
    if outpath.exists() and outpath.stat().st_size > 1000:
        return True
    try:
        r = session.get(url, timeout=timeout)
        if r.status_code == 200 and len(r.content) > 1000 and r.content[:4] == b"%PDF":
            outpath.write_bytes(r.content)
            return True
    except Exception:
        pass
    return False

# ═══════════════ VERIFY ═══════════════

def verify_pdf(pdf_path, entry):
    try:
        import pdfplumber
    except ImportError:
        return {"verdict": "Not verified", "score": 0, "evidence": "pdfplumber missing"}

    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            texts = [p.extract_text() or "" for p in pdf.pages[:50]]
        text = "\n".join(texts)
    except Exception as e:
        return {"verdict": "Not found", "score": 0, "evidence": f"Extraction failed: {e}"}

    if len(text) < 100:
        return {"verdict": "Not found", "score": 0, "evidence": "Text too short"}

    tu = text.upper()
    brand = entry.get("brand", "")
    series = entry.get("series", "")
    models = entry.get("models", [])
    refs = entry.get("refrigerants", [])
    caps = entry.get("capacities", [])

    evidence = []
    score = 0

    # Brand (5 pts)
    aliases = {
        "RHEEM":["RHEEM","RUUD"],"RUUD":["RUUD","RHEEM"],
        "CARRIER":["CARRIER","BRYANT"],"BRYANT":["BRYANT","CARRIER"],
        "LENNOX":["LENNOX"],"BOSCH":["BOSCH"],
        "YORK":["YORK","JOHNSON CONTROLS","JCI"],
        "JOHNSON CONTROLS":["JOHNSON CONTROLS","JCI","YORK","CHOICE"],
    }
    for a in aliases.get(brand, [brand]):
        if a in tu:
            evidence.append(f"Brand:{a}")
            score += 5
            break
    if score == 0:
        evidence.append(f"Brand NOT found:{brand}")

    # Model (5 pts)
    mm = False
    for mdl in models:
        if mdl and mdl.upper() in tu:
            evidence.append(f"Model:{mdl}")
            score += 5
            mm = True
            break
    if not mm:
        if series and series.upper() in tu:
            evidence.append(f"Series:{series}")
            score += 3
            mm = True
        else:
            evidence.append(f"Model NOT found:{models[:3]}")

    # Refrigerant (5 pts)
    rm = False
    for r in refs:
        if not r: continue
        for v in [r, r.replace("-",""), r.replace("-"," ")]:
            if v.upper() in tu:
                evidence.append(f"Refrigerant:{r}")
                score += 5
                rm = True
                break
        if rm: break
    if not rm: evidence.append(f"Refrigerant NOT confirmed:{refs}")

    # Capacity (5 pts)
    cm = False
    for c in caps:
        if not c: continue
        for n in re.findall(r"(\d+)", str(c))[:2]:
            if n in text:
                evidence.append(f"Capacity:{n}BTU")
                score += 5
                cm = True
                break
        if cm: break

    # Performance bonus (5 pts)
    if re.search(r'EER\s*[:\s]*\d+\.?\d*', tu) or re.search(r'IEER\s*[:\s]*\d+\.?\d*', tu):
        evidence.append("Performance data present")
        score += 5

    if score >= 15: verdict = "High confidence"
    elif score >= 8: verdict = "Needs human confirmation"
    elif score >= 3: verdict = "Low confidence"
    else: verdict = "Not found"

    return {"verdict": verdict, "score": score, "evidence": "; ".join(evidence)}

# ═══════════════ BRAND STRATEGIES ═══════════════

def process_rheem(entry):
    """Rheem/Ruud: sitemap → product page → DocumentURL → download"""
    models = entry.get("models", [])
    series = entry.get("series", "")
    brand = entry.get("brand", "RHEEM")
    sitemaps = [
        "https://www.rheem.com/wp-sitemap-products-1.xml",
        "https://www.rheem.com/wp-sitemap-products-2.xml",
    ]
    tokens = list(set([model_token(m) for m in models] + [series]))

    results = []
    for sm in sitemaps:
        code, xml = fetch(sm)
        if code != 200: continue
        purls = match_sitemap(xml, tokens)
        log.info(f"  [{brand}/{series}] Sitemap: {len(purls)} product pages")
        for purl in purls[:3]:
            code, html = fetch(purl)
            if code != 200 or not html: continue
            docs = extract_docs_from_html(html)
            for doc in docs:
                results.append(doc["url"])
        if results: break

    if not results and brand == "RUUD":
        # Try Rheem sitemap for same series
        return process_rheem({**entry, "brand": "RHEEM"})

    return results

def process_carrier(entry):
    """Carrier/Bryant: carriercca.com CDN patterns"""
    models = entry.get("models", [])
    series = entry.get("series", "")
    token = model_token(models[0]) if models else series
    model_full = models[0] if models else ""
    brand = entry.get("brand", "CARRIER")

    results = []
    cdn_patterns = [
        f"https://www.carriercca.com/pdf/products_pdf/{model_full}_Product_Data.pdf",
        f"https://www.carriercca.com/pdf/products_pdf/{token}_Product_Data.pdf",
        f"https://www.carriercca.com/pdf/products_pdf/{series}_Product_Data.pdf",
        f"https://www.carriercca.com/pdf/products_pdf/{token}_PD.pdf",
    ]
    for url in cdn_patterns:
        try:
            r = session.head(url, timeout=15)
            if r.status_code == 200:
                results.append(url)
                break
        except Exception:
            pass

    # Also try Carrier sitemap
    if not results:
        code, xml = fetch("https://www.carrier.com/residential/en/us/sitemap.xml")
        if code == 200:
            purls = match_sitemap(xml, [token, series], "/products/")
            for purl in purls[:2]:
                code, html = fetch(purl)
                if html:
                    for doc in extract_docs_from_html(html):
                        results.append(doc["url"])
    return results

def process_bosch(entry):
    """Bosch: public CDN patterns"""
    models = entry.get("models", [])
    token = model_token(models[0]) if models else entry.get("series", "")

    results = []
    cdn_base = "https://www.bosch-homecomfort.com/us/media/country_pool/documents"
    # Try common Bosch document paths
    guesses = [
        f"{cdn_base}/engineering-submittal-sheets/{token}_ESS.pdf",
        f"{cdn_base}/engineering-submittal-sheets/climate-5000-ductless-(2.0)/{token}_ESS.pdf",
        f"{cdn_base}/downloads-for-bosch-products/heat-pumps-manuals/{token}_manual.pdf",
    ]
    for url in guesses:
        try:
            r = session.head(url, timeout=15)
            if r.status_code == 200:
                results.append(url)
        except Exception:
            pass
    return results

def process_lennox(entry):
    """Lennox: sitemap + known patterns"""
    models = entry.get("models", [])
    token = model_token(models[0]) if models else entry.get("series", "")

    results = []
    code, xml = fetch("https://www.lennox.com/sitemap.xml")
    if code == 200:
        purls = match_sitemap(xml, [token, entry.get("series", "")], "/products/")
        for purl in purls[:2]:
            code, html = fetch(purl)
            if html:
                for doc in extract_docs_from_html(html):
                    results.append(doc["url"])
    return results

def process_jci(entry):
    """JCI/York: docs.johnsoncontrols.com + cgproducts CDN"""
    models = entry.get("models", [])
    series = entry.get("series", "")
    token = model_token(models[0]) if models else series

    results = []
    # Try JCI API
    api_url = f"https://docs.johnsoncontrols.com/ductedsystems/api/khub/documents?search={token}"
    try:
        r = session.get(api_url, timeout=20)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                for doc in data[:3]:
                    did = doc.get("id", "")
                    if did:
                        results.append(f"https://docs.johnsoncontrols.com/ductedsystems/api/khub/documents/{did}/content")
    except Exception:
        pass

    # Try cgproducts legacy
    if not results:
        for model in models[:2]:
            results.append(f"https://cgproducts.johnsoncontrols.com/MET_PDF/{model}.pdf")

    return results

STRATEGIES = {
    "RHEEM": process_rheem,
    "RUUD": process_rheem,
    "CARRIER": process_carrier,
    "BRYANT": process_carrier,
    "BOSCH": process_bosch,
    "LENNOX": process_lennox,
    "JOHNSON CONTROLS": process_jci,
    "YORK": process_jci,
}

# ═══════════════ MAIN ═══════════════

def main():
    manifest = load_manifest()
    log.info(f"Loaded {len(manifest)} manuals from manifest.json")

    # Count current state
    done = sum(1 for v in manifest.values() if v.get("status") == "found")
    log.info(f"Already found: {done}")

    # Get pending entries, prioritize by brand
    brand_order = ["RHEEM","RUUD","BOSCH","CARRIER","BRYANT","LENNOX","YORK","JOHNSON CONTROLS"]
    pending = sorted(
        [(mid, e) for mid, e in manifest.items() if e.get("status") != "found"],
        key=lambda x: (brand_order.index(x[1]["brand"]) if x[1]["brand"] in brand_order else 99, x[1]["series"])
    )

    log.info(f"Pending: {len(pending)}")

    found_count = done
    for i, (mid, entry) in enumerate(pending):
        brand = entry["brand"]
        series = entry["series"]
        fn = STRATEGIES.get(brand)

        log.info(f"[{i+1}/{len(pending)}] {brand}/{series} ({len(entry.get('models',[]))} models)")

        if not fn:
            log.warning(f"  No strategy for brand '{brand}'")
            continue

        try:
            candidates = fn(entry)
            success = False

            for pdf_url in candidates[:5]:
                ref_id = entry.get("reference_ids", ["0"])[0]
                ref_type = (entry.get("refrigerants", ["UNKNOWN"])[0] or "UNKNOWN").replace("/","-").replace(" ","-")
                stem = pdf_url.split("/")[-1].replace(".pdf", "")[:80]
                fname = safe_fn(f"{stem}__Ref{ref_id}_{brand}_{series}_{ref_type}.pdf")
                outpath = PDF_DIR / fname

                if download_pdf(pdf_url, outpath):
                    result = verify_pdf(outpath, entry)
                    entry["pdf_filename"] = fname
                    entry["pdf_url"] = pdf_url
                    entry["status"] = "found"
                    entry["verdict"] = result["verdict"]
                    entry["score"] = result["score"]
                    entry["evidence"] = result["evidence"]
                    log.info(f"  FOUND: {result['verdict']} (score={result['score']})")
                    success = True
                    found_count += 1
                    break

            if not success:
                entry["status"] = "not_found"
                entry["verdict"] = "Not found"
                entry["evidence"] = f"No PDF found from structured sources ({len(candidates)} candidates tried)"
                log.info(f"  NOT FOUND: {len(candidates)} candidates failed")

        except Exception as e:
            log.error(f"  ERROR: {e}")
            entry["status"] = "error"
            entry["evidence"] = str(e)[:200]

        # Save manifest every entry
        save_manifest(manifest)

        # Short delay to be nice to servers
        time.sleep(1)

    # Final summary
    found = sum(1 for v in manifest.values() if v.get("status") == "found")
    log.info(f"\nDONE: {found}/{len(manifest)} found")
    for b in brand_order:
        bs = sum(1 for v in manifest.values() if v.get("brand")==b)
        fs = sum(1 for v in manifest.values() if v.get("brand")==b and v.get("status")=="found")
        if bs > 0:
            log.info(f"  {b}: {fs}/{bs}")

if __name__ == "__main__":
    main()
