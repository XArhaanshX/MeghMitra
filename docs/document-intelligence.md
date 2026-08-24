# Document intelligence pipeline

Package: `services/document-intelligence/src/document_intelligence/`. Read the module docstrings
first -- they're the primary documentation; this file is orientation + known limitations.

## Stages

| Module | Input -> Output | Notes |
|---|---|---|
| `loader.py` | PDF path -> `DocumentMetadata` + `DocumentPage[]` | `pdftotext -layout` primary, `pypdf` fallback. See "Known limitation" below. |
| `chunker.py` | `DocumentPage` -> `Chunk[]` | Line-level classification: `heading` / `table_row` / `paragraph`. Never merges lines across pages. |
| `extractor.py` | `Chunk[]` + `DocumentMetadata` -> `DACPRuleDraft[]` | Deterministic header-vocabulary mapping. Not an LLM, not fuzzy-matched. |
| `confidence.py` | `DACPRuleFields` -> score + notes | Weighted, inspectable -- not a learned model. |
| `validator.py` | `DACPRuleDraft` -> `DACPRule` | Applies `ankur_domain.policies`, assigns `review_status`. Never assigns `approved`. |
| `pipeline.py` | orchestrates the above | `run_ingestion()` is the single entry point; wraps the run in an `ExtractionRun` record. |
| `ingest.py` | CLI | `python -m document_intelligence.ingest <pdf> --district <d> --state <s>` |

## Extraction is deliberately conservative

`extractor.py` only produces a candidate rule from a `TABLE_ROW` chunk when:

1. it's part of a table whose header row was recognized (`_is_header_row` requires a `condition`
   column plus at least one other known column -- this is what distinguishes a DACP
   contingency-measures table from an unrelated table in the same document, e.g. land-use or
   irrigation-source stats), **or**
2. no header was recognized on the current page, but the document has already entered its DACP
   contingency-measures section (`seen_dacp_section`) -- this is the safety-net path, and it's
   explicitly lower-confidence (`had_header_context=False` in `score_draft`).

Rows encountered *before* any DACP header has been seen anywhere in the document are skipped
entirely, not extracted as low-confidence noise. This bounds extraction to the actual
contingency-measures section instead of treating every 2-column table in a 30+ page profile
document as a candidate rule.

A `-` or blank cell always maps to `None`. Cells are never inferred, defaulted, or filled from
general agricultural knowledge -- if the source document doesn't say it, the field stays `null`.

## Known limitation: multi-line wrapped table cells

The real Sirsa DACP (`data/raw/HAR16-Sirsa-30-06-2011.pdf`) wraps each contingency-table row's
cell text across multiple physical lines (`pdftotext -layout` preserves column x-position, but a
single row's "Condition" cell might span 2-3 lines while "Suggested Contingency measures" spans
1). The current extractor reads one physical line at a time, so it currently:

- correctly scopes extraction to the contingency-measures section (verified: rows only start
  appearing from page 7 onward, matching the real table layout),
- but only captures a fragment of most multi-line rows per draft, which keeps confidence below
  `MIN_AUTO_ELIGIBLE_CONFIDENCE` and routes ~100% of real-document extractions to
  `needs_review`.

This is the correct failure mode (incomplete data is quarantined, never presented as trustworthy)
but not yet a usable end-to-end extraction of Sirsa's rules. **Next step**: group chunker output
by page + column x-position band before handing rows to the extractor, so a table row's full
multi-line cell text is reassembled before field-mapping. See `README.md` "Next recommended
implementation" for the prioritized list.

## Extending the header vocabulary

`extractor.py`'s `_HEADER_KEYWORDS` dict maps normalized header text to `DACPRuleFields`
attribute names. If a new district's DACP uses different column headers (e.g. "Response
strategy" instead of "Suggested Contingency measure"), add the mapping there -- keep it flat and
explicit (no fuzzy matching) so the mapping stays auditable from a diff.

## OCR

`ocr.py` defines an `OCREngine` `Protocol`. `NullOCREngine` (default) makes "OCR required, none
configured" an explicit `ExtractionMethod.OCR_UNAVAILABLE` state rather than a crash or invented
text. `TesseractOCREngine` is provided behind the `document-intelligence[ocr]` extra
(`pytesseract` + `pdf2image`, requires system `tesseract` + `poppler`) for scanned DACP plans.
