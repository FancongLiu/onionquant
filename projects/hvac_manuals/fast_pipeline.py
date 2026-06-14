"""
Fast pipeline with sitemap caching + CDN patterns. No web search.
Saves manifest.json after every brand.
"""

import io
import json
import logging
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

PROJECT_DIR = Path(__file__).parent
PDF_DIR = PROJECT_DIR / "pdf_downloads"
MANIFEST_PATH = PROJECT_DIR / "manifest.json"
EXCEL_PATH = Path(r"E:\HVAC_PDF_search\Unitary_pdf_manual_search_0519_lite.xlsx")
PDF_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

session = requests.Session()
session.timeout = 30
session.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
    }
)

# Global cache
CACHE = {}

# ═══════════════ HELPERS ═══════════════


def model_token(m):
    if not m:
        return "UNKNOWN"
    mm = re.match(r"^([A-Z]+\d+[A-Z]?)", str(m))
    return mm.group(1) if mm else str(m)[:10]


def model_series(m):
    if not m:
        return "UNKNOWN"
    mm = re.match(r"^([A-Z]+)", str(m))
    return mm.group(1) if mm else "UNKNOWN"


def safe_fn(n):
    return re.sub(r'[<>:"/\\|?*]', "_", str(n))[:200]


def load_m():
    return json.loads(open(MANIFEST_PATH, encoding="utf-8").read())


def save_m(m):
    json.dump(
        m, open(MANIFEST_PATH, "w", encoding="utf-8"), indent=2, ensure_ascii=False
    )


def fetch_cached(url, timeout=30):
    if url in CACHE:
        return CACHE[url]
    try:
        r = session.get(url, timeout=timeout, allow_redirects=True)
        r.encoding = "utf-8"
        result = (r.status_code, r.text)
    except Exception as e:
        result = (-1, str(e))
    CACHE[url] = result
    return result


def extract_docs(html):
    results = []
    doc_urls = re.findall(r'"DocumentURL"\s*:\s*"(https?://[^"]+\.pdf)"', html)
    doc_types = re.findall(r'"documentType"\s*:\s*"([^"]+)"', html)
    for i, url in enumerate(doc_urls):
        dt = doc_types[i] if i < len(doc_types) else "PDF"
        results.append({"url": url, "type": dt, "source": "DocumentURL"})
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


def download_pdf(url, outpath):
    if outpath.exists() and outpath.stat().st_size > 1000:
        return True
    try:
        r = session.get(url, timeout=120)
        if r.status_code == 200 and len(r.content) > 1000 and r.content[:4] == b"%PDF":
            outpath.write_bytes(r.content)
            log.info(f"    Downloaded: {outpath.stat().st_size / 1024:.0f}KB")
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
        return {
            "verdict": "Not found",
            "score": 0,
            "evidence": f"Extraction failed: {e}",
        }
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
    aliases = {
        "RHEEM": ["RHEEM", "RUUD"],
        "RUUD": ["RUUD", "RHEEM"],
        "CARRIER": ["CARRIER", "BRYANT"],
        "BRYANT": ["BRYANT", "CARRIER"],
        "LENNOX": ["LENNOX"],
        "BOSCH": ["BOSCH"],
        "YORK": ["YORK", "JOHNSON CONTROLS", "JCI"],
        "JOHNSON CONTROLS": ["JOHNSON CONTROLS", "JCI", "YORK", "CHOICE"],
    }
    for a in aliases.get(brand, [brand]):
        if a in tu:
            evidence.append(f"Brand:{a}")
            score += 5
            break
    if score == 0:
        evidence.append(f"Brand NOT found:{brand}")

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
        else:
            evidence.append(f"Model NOT found:{models[:3]}")

    rm = False
    for r in refs:
        if not r:
            continue
        for v in [r, r.replace("-", ""), r.replace("-", " ")]:
            if v.upper() in tu:
                evidence.append(f"Refrigerant:{r}")
                score += 5
                rm = True
                break
        if rm:
            break
    if not rm:
        evidence.append(f"Refrigerant NOT confirmed:{refs}")

    cm = False
    for c in caps:
        if not c:
            continue
        for n in re.findall(r"(\d+)", str(c))[:2]:
            if n in text:
                evidence.append(f"Capacity:{n}BTU")
                score += 5
                cm = True
                break
        if cm:
            break

    if re.search(r"EER\s*[:\s]*\d+\.?\d*", tu) or re.search(
        r"IEER\s*[:\s]*\d+\.?\d*", tu
    ):
        evidence.append("Performance data present")
        score += 5

    if score >= 15:
        verdict = "High confidence"
    elif score >= 8:
        verdict = "Needs human confirmation"
    elif score >= 3:
        verdict = "Low confidence"
    else:
        verdict = "Not found"

    return {"verdict": verdict, "score": score, "evidence": "; ".join(evidence)}


# ═══════════════ BRAND PROCESSORS ═══════════════

SITEMAP_RHEEM = "https://www.rheem.com/wp-sitemap-products-1.xml"
SITEMAP_CARRIER = "https://www.carrier.com/residential/en/us/sitemap.xml"
SITEMAP_LENNOX = "https://www.lennox.com/sitemap.xml"
SITEMAP_YORK = "https://www.york.com/sitemap.xml"


def process_brand(entries, brand_name, strategy="sitemap"):
    """Process all entries for one brand. Strategy: sitemap, cdn, or hybrid."""
    log.info(
        f"\n{'=' * 50}\nProcessing {brand_name} ({len(entries)} entries) - strategy: {strategy}\n{'=' * 50}"
    )
    found_count = 0

    for i, (mid, entry) in enumerate(entries):
        if entry.get("status") == "found":
            continue
        series = entry["series"]
        models = entry.get("models", [])
        tokens = list(set([model_token(m) for m in models] + [series]))

        log.info(f"[{i + 1}/{len(entries)}] {brand_name}/{series}")

        candidates = []

        # Sitemap strategy (runs for "sitemap" and "hybrid")
        if strategy in ("sitemap", "hybrid"):
            smap = None
            if brand_name in ("RHEEM", "RUUD"):
                smap = SITEMAP_RHEEM
            elif brand_name in ("CARRIER", "BRYANT"):
                smap = SITEMAP_CARRIER
            elif brand_name == "LENNOX":
                smap = SITEMAP_LENNOX
            elif brand_name in ("YORK", "JOHNSON CONTROLS"):
                smap = SITEMAP_YORK

            if smap:
                code, xml = fetch_cached(smap)
                if code == 200:
                    purls = match_sitemap(xml, tokens)
                    if purls:
                        log.info(f"  Sitemap: {len(purls)} matching product pages")
                        for purl in purls[:3]:
                            code, html = fetch_cached(purl)
                            if html:
                                for doc in extract_docs(html):
                                    candidates.append(doc["url"])

        # CDN strategy for brands with known CDN patterns
        if not candidates and strategy in ("cdn", "hybrid"):
            if brand_name == "CARRIER":
                for m in models[:2]:
                    for url in [
                        f"https://www.carriercca.com/pdf/products_pdf/{model_token(m)}_Product_Data.pdf",
                        f"https://www.carriercca.com/pdf/products_pdf/{m}_Product_Data.pdf",
                    ]:
                        try:
                            r = session.head(url, timeout=15)
                            if r.status_code == 200:
                                candidates.append(url)
                        except:
                            pass

            elif brand_name == "BOSCH":
                cdn = (
                    "https://www.bosch-homecomfort.com/us/media/country_pool/documents"
                )
                for m in models[:2]:
                    tk = model_token(m)
                    for path in [
                        f"{cdn}/engineering-submittal-sheets/{tk}_ESS.pdf",
                        f"{cdn}/engineering-submittal-sheets/climate-5000-ductless-(2.0)/{tk}_ESS.pdf",
                    ]:
                        try:
                            r = session.head(path, timeout=15)
                            if r.status_code == 200:
                                candidates.append(path)
                        except:
                            pass

            elif brand_name in ("JOHNSON CONTROLS", "YORK"):
                for m in models[:2]:
                    tk = model_token(m)
                    api = f"https://docs.johnsoncontrols.com/ductedsystems/api/khub/documents?search={tk}"
                    try:
                        r = session.get(api, timeout=20)
                        if r.status_code == 200:
                            data = r.json()
                            if isinstance(data, list):
                                for doc in data[:3]:
                                    did = doc.get("id", "")
                                    if did:
                                        candidates.append(
                                            f"https://docs.johnsoncontrols.com/ductedsystems/api/khub/documents/{did}/content"
                                        )
                    except:
                        pass

        # Try download
        success = False
        for pdf_url in candidates[:5]:
            ref_id = entry.get("reference_ids", ["0"])[0]
            ref_type = (
                (entry.get("refrigerants", ["UNKNOWN"])[0] or "UNKNOWN")
                .replace("/", "-")
                .replace(" ", "-")
            )
            stem = pdf_url.split("/")[-1].replace(".pdf", "")[:80]
            fname = safe_fn(f"{stem}__Ref{ref_id}_{brand_name}_{series}_{ref_type}.pdf")
            outpath = PDF_DIR / fname

            if download_pdf(pdf_url, outpath):
                result = verify_pdf(outpath, entry)
                entry["pdf_filename"] = fname
                entry["pdf_url"] = pdf_url
                entry["status"] = "found"
                entry["verdict"] = result["verdict"]
                entry["score"] = result["score"]
                entry["evidence"] = result["evidence"]
                log.info(f"  => {result['verdict']} (score={result['score']})")
                success = True
                found_count += 1
                break

        if not success:
            entry["status"] = "not_found"
            entry["verdict"] = "Not found"
            entry["evidence"] = (
                f"No structured source match ({len(candidates)} candidates)"
            )
            log.info(f"  => NOT FOUND ({len(candidates)} candidates)")

        save_m(load_m())  # save current state
        time.sleep(0.5)

    log.info(f"\n{brand_name} done: {found_count}/{len(entries)} found")
    return found_count


# ═══════════════ MAIN ═══════════════


def main():
    manifest = load_m()
    log.info(f"Loaded {len(manifest)} manuals")

    # Group by brand
    brand_entries = defaultdict(list)
    for mid, entry in manifest.items():
        if entry.get("status") != "found":
            brand_entries[entry["brand"]].append((mid, entry))

    # Brand processing order with strategies
    plan = [
        ("RUUD", "sitemap"),  # try Rheem sitemap (sister brand)
        ("BOSCH", "cdn"),  # public CDN
        ("CARRIER", "hybrid"),  # CDN + sitemap
        ("BRYANT", "sitemap"),  # try Carrier sitemap
        ("JOHNSON CONTROLS", "hybrid"),  # API + sitemap
        ("RHEEM", "sitemap"),  # retry remaining Rheem (different sitemap or web search)
    ]

    total_found = 0
    for brand_name, strategy in plan:
        entries = brand_entries.get(brand_name, [])
        if not entries:
            log.info(f"  {brand_name}: all done, skip")
            continue
        found = process_brand(entries, brand_name, strategy)
        total_found += found

    # Final summary
    m = load_m()
    found = sum(1 for v in m.values() if v.get("status") == "found")
    log.info(f"\n{'=' * 60}")
    log.info(f"FINAL: {found}/{len(m)} found")
    for b in ["RHEEM", "RUUD", "BOSCH", "CARRIER", "BRYANT", "JOHNSON CONTROLS"]:
        bs = sum(1 for v in m.values() if v.get("brand") == b)
        fs = sum(
            1 for v in m.values() if v.get("brand") == b and v.get("status") == "found"
        )
        if bs > 0:
            log.info(f"  {b}: {fs}/{bs}")


if __name__ == "__main__":
    main()
