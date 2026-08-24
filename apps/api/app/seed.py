"""Load the Sirsa demo rule set through the real review chokepoint.

Drafts come from `data/fixtures/sirsa_demo_seed.json`. They are validated
(`document_intelligence.validator.validate_draft` — never `approved`) then
moved to approved only via `ReviewService.approve`, with the source document's
page_count attached so a citation past page 31 cannot sneak through.

CLI (API + Postgres running):

    make seed
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ankur_domain.services import DocumentService, ReviewService, RuleService
from ankur_schemas.citation import Citation
from ankur_schemas.document import DocumentMetadata
from ankur_schemas.enums import DocumentStatus, ReviewStatus
from ankur_schemas.rule import DACPRule, DACPRuleDraft, DACPRuleFields
from document_intelligence.validator import validate_draft

logger = logging.getLogger("ankur.seed")

FIXTURE_NAME = "sirsa_demo_seed.json"
PDF_RELATIVE = Path("data") / "raw" / "HAR16-Sirsa-30-06-2011.pdf"
DEMO_MARKER = "ankur-demo-seed"
EXTRACTOR_VERSION = "demo-seed/0.1.0"


def _repo_root() -> Path:
    """Walk up from this file until the demo fixture is visible.

    Editable installs keep `app/seed.py` in `apps/api/`; a wheel would not.
    Searching for the fixture avoids a hard-coded parent-count.
    """
    here = Path(__file__).resolve()
    for candidate in (here.parent, *here.parents):
        if (candidate / "data" / "fixtures" / FIXTURE_NAME).exists():
            return candidate
    raise FileNotFoundError(f"could not find data/fixtures/{FIXTURE_NAME}")


def _fixture_path() -> Path:
    return _repo_root() / "data" / "fixtures" / FIXTURE_NAME


@dataclass(frozen=True, slots=True)
class SeedResult:
    document: DocumentMetadata
    approved: list[DACPRule]
    skipped: int


def _load_fixture() -> dict:
    return json.loads(_fixture_path().read_text(encoding="utf-8"))


async def seed_sirsa_demo(
    *,
    documents: DocumentService,
    rules: RuleService,
    review: ReviewService,
    reviewed_by: str = "demo-seed",
) -> SeedResult:
    """Idempotent: re-running does not duplicate rows already tagged as demo seed."""
    existing = [rule for rule in await rules.list() if DEMO_MARKER in rule.notes]
    if existing:
        document = await _existing_document(documents)
        return SeedResult(document=document, approved=existing, skipped=len(existing))

    fixture = _load_fixture()
    document = await _ensure_document(documents, fixture["document"])
    approved: list[DACPRule] = []
    now = datetime.now(UTC)

    for raw in fixture["drafts"]:
        draft = DACPRuleDraft(
            document_id=document.id,
            fields=DACPRuleFields(**raw["fields"]),
            citation=Citation(**raw["citation"]),
            confidence=raw["confidence"],
            extractor_version=EXTRACTOR_VERSION,
            extracted_at=now,
            notes=[DEMO_MARKER],
        )
        validated = validate_draft(draft)
        if validated.review_status == ReviewStatus.APPROVED:
            raise RuntimeError("demo seed must not self-approve; validate_draft assigned approved")
        stored = (await rules.record_extracted([validated]))[0]
        approved.append(await review.approve(stored.id, reviewed_by=reviewed_by))

    return SeedResult(document=document, approved=approved, skipped=0)


async def _existing_document(documents: DocumentService) -> DocumentMetadata:
    matches = [d for d in await documents.list() if d.filename == "HAR16-Sirsa-30-06-2011.pdf"]
    if not matches:
        raise RuntimeError("demo seed rows exist but the Sirsa document is missing")
    return matches[0]


async def _ensure_document(documents: DocumentService, meta: dict) -> DocumentMetadata:
    matches = [d for d in await documents.list() if d.filename == meta["filename"]]
    if matches:
        return matches[0]
    return await documents.register(
        DocumentMetadata(
            filename=meta["filename"],
            district=meta["district"],
            state=meta["state"],
            page_count=meta["page_count"],
            sha256=_pdf_sha256(),
            status=DocumentStatus.REGISTERED,
            registered_at=datetime.now(UTC),
        )
    )


def _pdf_sha256() -> str | None:
    pdf_path = _repo_root() / PDF_RELATIVE
    if not pdf_path.exists():
        return None
    return hashlib.sha256(pdf_path.read_bytes()).hexdigest()


async def _seed_postgres() -> SeedResult:
    from app.config import get_settings
    from app.db import (
        PostgresDocumentRepository,
        PostgresRuleRepository,
        create_pool,
    )

    settings = get_settings()
    pool = await create_pool(settings.database_url)
    try:
        doc_repo = PostgresDocumentRepository(pool)
        rule_repo = PostgresRuleRepository(pool)
        result = await seed_sirsa_demo(
            documents=DocumentService(documents=doc_repo),
            rules=RuleService(rules=rule_repo),
            review=ReviewService(rules=rule_repo, documents=doc_repo),
        )
    finally:
        await pool.close()
    return result


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Seed cited Sirsa demo rules via ReviewService.")
    parser.parse_args()
    result = asyncio.run(_seed_postgres())
    print(f"document={result.document.id} approved={len(result.approved)} skipped={result.skipped}")
    for rule in result.approved:
        print(
            f"  {rule.fields.condition_code} p{rule.citation.page} "
            f"{rule.review_status.value} {rule.fields.crop}"
        )


if __name__ == "__main__":
    main()
