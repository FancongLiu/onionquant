# Send These Files To The Local Computer

Send the lightweight zip:

`LOCAL_AI_HANDOFF_LIGHT_NO_PDF.zip`

It contains only the files needed for the local AI to continue the task. It does not include downloaded PDFs.

## Files Inside

1. `LOCAL_AI_PROMPT_SANITIZED.md`

   The workflow prompt. Give this to the local AI first.

2. `Unitary_pdf_manual_search_0519_SANITIZED.xlsx`

   The requirement workbook. Owner names are anonymized as `Owner_01`, `Owner_02`, etc.

3. `pilot_first5_results_SANITIZED.csv`

   A small example result table showing how evidence, PDF URL, verdict, and local path should be recorded.

4. `README_SEND_THESE_FILES.md`

   This send-list and quick explanation.

## Do Not Send

Do not send the already downloaded PDF files unless needed for manual review. The local AI should re-download public PDFs into its own `./PDF` folder.

## Why This Is Enough

The local AI needs:

- the demand rows,
- the exact workflow,
- one completed example,
- and the public source URLs.

It does not need existing PDF binaries.

## Quick Finding From Pilot

For Rheem, general web search was not necessary for most pilot rows. The reliable route was:

`Rheem public sitemap -> product page -> embedded DocumentURL -> PDF download -> PDF text verification`

For JCI / Johnson Controls, public PDF/manual access exists for at least some rows. It is not accurate to assume all JCI unitary manuals require login, though some deep product portals may require an account.

Latest check: 18 already-filled JCI links in the workbook were tested. Result: 13 direct public PDFs and 5 public documentation HTML pages returned HTTP 200. So the recommended JCI route is direct PDF/document URLs first, login portals only as a fallback/limitation.