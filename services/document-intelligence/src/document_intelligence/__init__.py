"""Document intelligence: DACP PDF -> structured, cited, confidence-scored rule drafts.

Structured information extraction, not a PDF chatbot. Pipeline stages:

    loader     PDF -> DocumentMetadata + page-numbered DocumentPage[]
    chunker    page text -> line-level Chunk[] (heading / table_row / paragraph)
    extractor  Chunk[] -> DACPRuleDraft[] (header-aware table mapping, never guesses)
    confidence score_draft() -> how much structural evidence backed the row
    validator  DACPRuleDraft -> DACPRule (applies ankur_domain policies, sets review_status)
    pipeline   run_ingestion() wires the above together, records an ExtractionRun

See `ingest.py` for the CLI entry point.
"""

from document_intelligence.pipeline import IngestionResult, run_ingestion

__all__ = ["IngestionResult", "run_ingestion"]
