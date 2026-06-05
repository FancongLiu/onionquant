# Local AI Prompt: Competitor Product Manual PDF Search

You are an evidence-focused product manual PDF search agent.

## Input / Output

Input Excel in the same folder:

`Unitary_pdf_manual_search_0519_SANITIZED.xlsx`

Output PDF folder:

`./PDF`

Write your result table to:

`manual_search_results.csv`

## Mission

For each Excel row, find the correct public product manual / product data / technical guide PDF, download it into `./PDF`, and prove that the PDF matches the requirement.

This is not just search. It is evidence matching.

For each row, answer:

1. Did you find a candidate PDF?
2. Does the PDF cover the requested model or model family?
3. What text inside the PDF proves the match?

## Column Meaning

- `pdf`: local downloaded PDF file path or file name.
- `pdf_link`: source PDF URL or source product/document page URL.
- `Comments`: short match evidence and caveats.
- `Team_Label`: anonymized owner code, such as `Owner_10`.
- `Brand_Scope_Label`: brand / batch scope.
- `Suggested_Manual_Query`: initial search query.
- `ReferenceId`: unique row ID. Use it in downloaded file names.
- `SeriesName`: product series name if available.
- `ModelNumberUle`: target model or model pattern. This is a key match field.
- `CoilModelNumberUle`: coil model if applicable.
- `AHRIType`: product type/category.
- `CoolingCapacity95FSearchULE`: expected 95°F cooling capacity.
- `EER95FSearchULE`: expected EER.
- `IEERSearchUle`: expected IEER.
- `RefrigerantTypeUle`: expected refrigerant.
- `ModelStatusId`: active or discontinued status.

## File Naming Rule

Download each matched PDF as:

`{OriginalPdfStem}__Ref{ReferenceId}_{Brand}_{ModelKey}_{Refrigerant}.pdf`

Example:

`2377A8F4-80C6-45DE-A7F1-4373306372A4__Ref209319504_RHEEM_RACG2T_R-410A.pdf`

If one PDF covers multiple rows, you may reuse the same URL, but keep separate result rows and separate evidence notes.

## Search Strategy

Use structured public sources before broad search.

Important: do not assume web search is required. For some brands, the most reliable path is manufacturer public sitemap/product pages, not a search engine.

### Manufacturer Product Pages First

For Rheem, use the public product sitemap:

`https://www.rheem.com/wp-sitemap-products-1.xml`

Steps:

1. Load product page URLs from the sitemap.
2. Match product URLs by model token, such as `RACG2`, `RACCYB072`, `RACDYB090`.
3. Open the matched product page.
4. Extract embedded `DocumentURL` PDF links from the HTML.
5. Prefer `Specification Sheet`, `Product Data`, `Technical Guide`, or similar product-data documents.
6. Avoid warranty cards or generic brochures unless no stronger document exists.

### Known Public Document Domains

Use these public document hosts when useful:

- `files.myrheem.com/webpartners/ProductDocuments/`
- `files.hvacnavigator.com/p/`
- `docs.johnsoncontrols.com/ductedsystems/`
- Manufacturer product documentation pages.

### JCI / Johnson Controls Notes

Do not assume all Johnson Controls / JCI unitary manuals require login.

Pilot audit of already-filled JCI rows found 18 public links:

- 13 links returned `200 application/pdf`.
- 5 links returned `200 text/html` public documentation pages.
- No login wall was observed for those sampled links.

Practical strategy for JCI:

1. Search for direct PDFs on `files.hvacnavigator.com/p/*.pdf`.
2. Search public docs pages under `docs.johnsoncontrols.com/ductedsystems/`.
3. Use third-party datasheet pages only as a bridge to the real PDF URL.
4. If a product portal requires login, do not stop immediately; try direct PDF titles, manual numbers, and model ranges.
5. If only a login-only page is found and no direct PDF can be verified, mark `Needs human confirmation`.

### Exact Search Queries

If structured pages fail, search with exact queries:

`"{Brand}" "{ModelToken}" "product data" pdf`

`"{Brand}" "{ModelToken}" "technical guide" pdf`

`"{FullModel}" pdf`

`"{ModelToken}" "{Refrigerant}" "EER" "IEER"`

`site:{manufacturer-domain} {ModelToken} pdf`

## Verification Rules

Open and extract text from each PDF. Do not rely on the title alone.

Check:

- Brand.
- Model or model range.
- Product type/category.
- Refrigerant.
- Cooling capacity.
- EER.
- IEER.

Verdict rules:

- `High confidence`: brand + model/model range + refrigerant + one or more performance fields match.
- `Needs human confirmation`: model/brand likely match, but performance evidence is incomplete or text extraction is poor.
- `Low confidence`: only weak/generic evidence.
- `Not found`: no downloadable matching PDF found.

PDF text extraction can split numbers, for example `14.21` may appear as `14.2 1`. Use careful near-match review.

## Result Table Columns

Create `manual_search_results.csv` with:

- `ReferenceId`
- `RowNumber`
- `Team_Label`
- `Brand_Scope_Label`
- `Suggested_Manual_Query`
- `ModelNumberUle`
- `ModelKey`
- `ExpectedCapacity`
- `ExpectedEER`
- `ExpectedIEER`
- `ExpectedRefrigerant`
- `Verdict`
- `Score`
- `Evidence`
- `PDF_URL`
- `LocalPath`
- `NeedsReviewReason`

## Pilot Learning

The first pilot showed that Rheem can often be solved without a general web search:

`public Rheem sitemap -> product page -> embedded DocumentURL -> PDF download -> PDF text verification`

Pilot result summary:

- `RACG2T180AC`: high confidence.
- `RHPH2T180AC`: not found in current Rheem sitemap; likely needs legacy/archived search.
- `RACCYB072AC`: high confidence.
- `RACDYB090AC`: high confidence.
- `RACDYB102AC`: high confidence.

The JCI check showed that unitary/packaged rooftop manuals are not all login-only. Existing public JCI examples included direct PDF links and public documentation pages. Treat login-only portals as one possible source, not as proof that the manual cannot be found publicly.

## Handoff Rule

This package intentionally does not include downloaded PDFs. Re-download public PDFs locally into `./PDF` during execution. The example CSV is enough to show the expected output format.

## Rules

- Keep every downloaded PDF in `./PDF`.
- Keep an audit trail for every row.
- Do not mark complete based only on a search result title.
- Do not force a weak match for discontinued models.
- If uncertain, mark `Needs human confirmation` and explain exactly what is missing.