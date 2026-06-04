"""
Generate comprehensive handoff file for remaining not_found items.
Output: E:/HVAC_PDF_search/HANDOFF_REMAINING_NOT_FOUND.md
"""
import json, openpyxl
from collections import defaultdict

# Load manifest
with open('e:/2026_AgentStudy/Python_code/hvac_manuals/manifest.json', 'r', encoding='utf-8') as f:
    manifest = json.load(f)

ref_to_entry = {}
for key, entry in manifest.items():
    for ref_id in entry.get('reference_ids', []):
        ref_to_entry[str(ref_id)] = entry

# Load Excel
wb = openpyxl.load_workbook('E:/HVAC_PDF_search/Unitary_pdf_manual_search_0519_lite.xlsx')
ws = wb.active

headers = {}
for c in range(1, ws.max_column + 1):
    headers[ws.cell(1, c).value] = c

ref_id_col = headers['ReferenceId']

# Collect data
team_data = defaultdict(lambda: {'total': 0, 'found': 0, 'high_conf': 0, 'not_found_rows': []})
all_not_found_series = {}

for row in range(2, ws.max_row + 1):
    ref_id = str(ws.cell(row, ref_id_col).value or '')
    team = str(ws.cell(row, headers['Team_Label']).value or '')
    brand = str(ws.cell(row, headers['Brand_Scope_Label']).value or '')
    model = str(ws.cell(row, headers['ModelNumberUle']).value or '')
    query = str(ws.cell(row, headers['Suggested_Manual_Query']).value or '')
    capacity = str(ws.cell(row, headers['CoolingCapacity95FSearchULE']).value or '')
    refrigerant = str(ws.cell(row, headers['RefrigerantTypeUle']).value or '')
    series = str(ws.cell(row, headers['SeriesName']).value or '')
    ari_type = str(ws.cell(row, headers['AHRIType']).value or '')
    model_status = str(ws.cell(row, headers['ModelStatusId']).value or '')

    entry = ref_to_entry.get(ref_id, {})
    status = entry.get('status', 'searching')
    score = entry.get('score', 0)

    team_data[team]['total'] += 1
    if status == 'found':
        team_data[team]['found'] += 1
        if score >= 10:
            team_data[team]['high_conf'] += 1
    elif status == 'not_found':
        series_key = entry.get('manual_id', ref_id)
        team_data[team]['not_found_rows'].append({
            'ref_id': ref_id,
            'brand': brand,
            'series': entry.get('series', series),
            'model': model,
            'capacity': capacity,
            'refrigerant': refrigerant,
            'ari_type': ari_type,
            'status': model_status,
            'evidence': entry.get('evidence', 'No public documentation available'),
            'query': query,
        })
        if series_key and series_key not in all_not_found_series:
            all_not_found_series[series_key] = entry

# Build output
lines = []
lines.append("=" * 80)
lines.append("HVAC Product Manual PDF Search - Remaining Not Found Items - HANDOFF PROMPT")
lines.append("=" * 80)
lines.append("")
lines.append("## Task Background")
lines.append("")
lines.append("From 482 HVAC product manual search requirements, 385 rows (80%) have been found.")
lines.append("97 rows remain not found, corresponding to 42 unique model series across 6 brands.")
lines.append("All public channels (manufacturer sitemaps, CDNs, APIs, document portals) have been exhausted.")
lines.append("")
lines.append("The completed results are in: Unitary_pdf_manual_search_RESULTS.xlsx")
lines.append("The tracking manifest is in: hvac_manuals/manifest.json (138/180 series found)")
lines.append("")
lines.append("## Not Found: 42 Model Series Summary")
lines.append("")
lines.append("| Brand | Series Count | Excel Rows | Primary Reason |")
lines.append("|---|---|---|---|")
for brand in ['RHEEM', 'RUUD', 'CARRIER', 'BRYANT', 'BOSCH', 'JOHNSON CONTROLS']:
    brand_series = {k: v for k, v in all_not_found_series.items() if v.get('brand') == brand}
    brand_rows = sum(len(v.get('row_indices', [])) for v in brand_series.values())
    reasons = []
    for v in brand_series.values():
        vd = v.get('verdict', '')
        if vd and vd not in reasons:
            reasons.append(vd[:80])
    reason_str = '; '.join(reasons[:2]) if reasons else 'Unknown'
    lines.append(f"| {brand} | {len(brand_series)} | {brand_rows} | {reason_str} |")

lines.append("")
lines.append("## Detailed Per-Series Breakdown with Search Suggestions")
lines.append("")

for key, entry in sorted(all_not_found_series.items()):
    brand = entry.get('brand', '?')
    series_name = entry.get('series', '?')
    models = entry.get('models', [])
    capacities = entry.get('capacities', [])
    refrigerants = entry.get('refrigerants', [])
    queries = entry.get('queries', [])
    evidence = entry.get('evidence', '')
    verdict = entry.get('verdict', '')
    row_count = len(entry.get('row_indices', []))

    lines.append(f"### {brand} - {series_name} ({row_count} rows)")
    lines.append("")
    lines.append(f"- **Models**: {', '.join(models[:3])}")
    lines.append(f"- **Capacities**: {', '.join(capacities[:3])}")
    lines.append(f"- **Refrigerant**: {', '.join(refrigerants[:3])}")
    lines.append(f"- **Current Verdict**: {verdict}")
    lines.append(f"- **Why Not Found**: {evidence}")
    lines.append(f"- **Query Already Tried**: {queries[0] if queries else 'N/A'}")

    if brand == 'JOHNSON CONTROLS':
        if series_name in ['KC', 'KD', 'KE', 'WC', 'WD', 'WE']:
            lines.append(f"- **Breakthrough Suggestion**: Commercial split systems. Try searching exact model digits + 'technical guide' + 'pdf'. JCI Fluid Topics API already tried (docs.johnsoncontrols.com/ductedsystems/api/khub/clustered-search) - no results. These are identical to Bosch KC/KD/KE/WC/WD/WE - also not found.")
        else:
            lines.append(f"- **Breakthrough Suggestion**: Try '{series_name}' + 'packaged rooftop' + 'pdf' + 'site:johnsoncontrols.com'")
    elif brand in ['RHEEM', 'RUUD']:
        lines.append(f"- **Breakthrough Suggestion**: {brand} legacy/discontinued model. Try sitemap (rheem.com/wp-sitemap-products-1.xml) or direct model number search. May be OEM identical to another brand's model.")
    elif brand == 'CARRIER':
        lines.append(f"- **Breakthrough Suggestion**: Try shareddocs.com or carrier.com product page. Legacy commercial equipment may have archived PDFs on other sites like manualslib.com or archive.org.")
    elif brand == 'BRYANT':
        lines.append(f"- **Breakthrough Suggestion**: Bryant = Carrier OEM. Search for identical Carrier model specs. 'bryant {series_name} technical guide pdf'")
    elif brand == 'BOSCH':
        lines.append(f"- **Breakthrough Suggestion**: Try bosch-thermotechnology.com product search or full model name + 'pdf'. May have been discontinued/replaced by newer R-454B generation.")

    lines.append("")

lines.append("---")
lines.append("")
lines.append("## Per-Person Progress Report")
lines.append("")

for team in sorted(team_data.keys()):
    d = team_data[team]
    pct = d['found'] / d['total'] * 100 if d['total'] > 0 else 0
    lines.append(f"### {team}")
    lines.append(f"- Assigned: {d['total']} rows")
    lines.append(f"- Found: {d['found']} rows ({pct:.0f}%)")
    lines.append(f"- High Confidence (score>=10): {d['high_conf']} rows")
    lines.append(f"- Not Found: {len(d['not_found_rows'])} rows")
    if d['not_found_rows']:
        lines.append("")
        lines.append("Not found items:")
        lines.append("")
        for item in d['not_found_rows']:
            lines.append(f"  - RefId={item['ref_id']} | {item['brand']} | {item['model'][:45]} | {item['capacity']} | {item['refrigerant']} | Status={item['status']}")
        lines.append("")

lines.append("---")
lines.append("")
lines.append("## Search Strategy Guide for the Next AI")
lines.append("")
lines.append("1. **Structured sources first**: Always check manufacturer sitemaps/APIs/CDNs before web search.")
lines.append("2. **JCI Fluid Topics API** (public, no auth):")
lines.append("   - Search: `POST https://docs.johnsoncontrols.com/ductedsystems/api/khub/clustered-search` with JSON `{\"search\": \"<model>\"}`")
lines.append("   - Download: `GET https://docs.johnsoncontrols.com/ductedsystems/api/khub/documents/{documentId}/content`")
lines.append("3. **Rheem/Ruud**: Sitemap at `rheem.com/wp-sitemap-products-1.xml` -> product page -> extract embedded DocumentURL")
lines.append("4. **Carrier/Bryant**: `shareddocs.com` + `carrier.com` product pages -> find embedded PDF URLs")
lines.append("5. **Bosch**: `bosch-thermotechnology.com` product search")
lines.append("6. **Legacy/Discontinued Models**: If not in current sitemap, try `archive.org` / `web.archive.org` for historical product page snapshots.")
lines.append("7. **OEM Cross-Reference**: Many brands share the same product:")
lines.append("   - JCI = Bosch OEM for KB/KJ/KT/WP/KLE/KLG/KX*/KY*/WX*/WY* series")
lines.append("   - Bryant = Carrier OEM")
lines.append("   - Ruud = Rheem OEM")
lines.append("   If brand A has no docs, the identical brand B model may have them.")
lines.append("8. **If login is truly required**: Mark as `Needs human confirmation` and specify exactly what account/permission is needed.")
lines.append("9. **Verification is mandatory**: Download PDF, extract text, verify model + refrigerant + capacity match. Do not trust search result titles alone.")
lines.append("")
lines.append(f"Generated: 2026-05-26")
lines.append(f"Data Source: manifest.json (138/180 series found), Excel (385/482 rows found)")
lines.append(f"PDFs downloaded: hvac_manuals/pdf_downloads/ (~94 PDFs)")
lines.append("Fluid Topics API doc list: hvac_manuals/jci_fluid_topics_docs.json (1208 docs)")

# Write
output_path = 'E:/HVAC_PDF_search/HANDOFF_REMAINING_NOT_FOUND.md'
with open(output_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print(f"Written to: {output_path}")
print(f"Total lines: {len(lines)}")

# Print per-person summary
print("\n=== Per-Person Summary ===")
for team in sorted(team_data.keys()):
    d = team_data[team]
    pct = d['found'] / d['total'] * 100 if d['total'] > 0 else 0
    print(f"  {team}: {d['found']}/{d['total']} ({pct:.0f}%) found, {len(d['not_found_rows'])} not_found, {d['high_conf']} high-confidence")
