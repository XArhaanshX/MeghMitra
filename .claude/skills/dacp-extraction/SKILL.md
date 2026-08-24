---
name: dacp-extraction
description: Working on the document-intelligence PDF-to-rule pipeline (loader, chunker, extractor, confidence, validator) in services/document-intelligence/. Use before adding a DACP document, extending the header vocabulary, debugging a bad extraction, or changing how PDF text/tables are parsed.
---

# DACP extraction pipeline

Full stage-by-stage reference: `docs/document-intelligence.md`. This skill covers the
non-obvious operational knowledge for changing the pipeline itself.

## Before touching `loader.py`

- Do not assume `pypdf.extract_text()` is correct for a given PDF. It silently mangles the real
  Sirsa DACP's font encoding (verified: inserts a spurious `H` in place of most spaces). Always
  cross-check a new document's extracted text against `pdftotext -layout <file> -` output
  directly in a shell before trusting either extractor's output for that file.
- `MIN_NATIVE_TEXT_CHARS` (loader.py) is the scanned-vs-native heuristic. If a real document has
  short but legitimate native-text pages (e.g. a mostly-blank cover page), don't lower this
  threshold globally to fix it -- that's a per-document edge case, not a pipeline bug.

## Before touching `extractor.py`

- `_HEADER_KEYWORDS` is intentionally flat and literal (no fuzzy matching, no LLM). Extend it by
  adding new normalized-header-substring -> field-name entries when a new district's DACP uses
  different column headers. Keep entries auditable from a diff.
- `_is_header_row()` requires a `condition` column match plus at least one other -- this is what
  keeps unrelated tables (land use, irrigation stats, agro-climatic profile) from being
  mis-detected as contingency-measure tables. Do not relax this without re-running extraction
  against the full real Sirsa PDF and manually checking the noise didn't come back (see
  "Verifying a change" below).
- `seen_dacp_section` gates the no-header-context fallback to only fire once a real DACP header
  has been seen somewhere earlier in the document. This bounds noise to the actual
  contingency-measures section. Don't remove this gate to "catch more rows" -- it will
  reintroduce extraction of unrelated document sections.
- Never add a code path that fills a missing field from anything other than the source PDF text
  for that exact row/cell. That includes: hardcoded per-crop defaults, "typical" values, or
  values copied from an adjacent row.

## Known limitation (read before "fixing" low extraction yield)

The real Sirsa DACP wraps table-row cell text across multiple physical lines. The extractor
reads one physical line at a time, so most real-document drafts only capture a fragment per row
and correctly land in `needs_review` (low confidence, not enough populated fields). This is the
*intended* safe behavior, not a bug to silently work around by lowering
`MIN_AUTO_ELIGIBLE_CONFIDENCE` or loosening `score_draft()`. The real fix is multi-line row
reassembly (group `chunker` output by page + column x-position band before extraction) -- see
`docs/document-intelligence.md` "Known limitation" and the README's "Next recommended
implementation".

## Verifying a change

```bash
uv run python -m document_intelligence.ingest data/raw/HAR16-Sirsa-30-06-2011.pdf \
    --district Sirsa --state Haryana --out /tmp/sirsa_result.json
```

Then spot-check `/tmp/sirsa_result.json` rules: do the `fields.crop`/`condition`/`action` values
on early-page (page 1-6) rules stay empty (correctly gated out), and do contingency-section
(page 7+) rows contain real DACP vocabulary? Run `make test` afterward --
`tests/integration/test_ingestion.py` asserts every extracted rule cites the real document and
a valid page range against this exact file.
