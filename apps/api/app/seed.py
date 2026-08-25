"""Load DACP demo rule sets through the real review chokepoint.

`seed_sirsa_demo` loads the flagship Haryana/Sirsa demo from
`data/fixtures/sirsa_demo_seed.json`. `seed_multi_state_demo` generalises it:
Haryana/Sirsa plus every state block in
`data/fixtures/multi_state_demo_seed.json`. Both validate drafts
(`document_intelligence.validator.validate_draft` — never `approved`) then
move to approved only via `ReviewService.approve`, with each source
document's page_count attached so a citation past its last page cannot
sneak through.

CLI (API + Postgres running):

    make seed               # Haryana/Sirsa only
    make seed-multi-state   # Haryana/Sirsa + every other state fixture
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
from document_intelligence.loader import load_document
from document_intelligence.validator import validate_draft

logger = logging.getLogger("ankur.seed")

FIXTURE_NAME = "sirsa_demo_seed.json"
MULTI_STATE_FIXTURE_NAME = "multi_state_demo_seed.json"
"""Additional states beyond Haryana/Sirsa -- see `seed_multi_state_demo`."""

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


def _multi_state_fixture_path() -> Path:
    return _repo_root() / "data" / "fixtures" / MULTI_STATE_FIXTURE_NAME


@dataclass(frozen=True, slots=True)
class SeedResult:
    document: DocumentMetadata
    approved: list[DACPRule]
    skipped: int


@dataclass(frozen=True, slots=True)
class MultiStateSeedResult:
    """Same shape as `SeedResult`, generalised to more than one document/state."""

    documents: list[DocumentMetadata]
    approved: list[DACPRule]
    skipped: int


def _load_fixture() -> dict:
    return json.loads(_fixture_path().read_text(encoding="utf-8"))


def _load_multi_state_fixture() -> dict:
    return json.loads(_multi_state_fixture_path().read_text(encoding="utf-8"))


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
        await _ensure_pages(documents, document)
        return SeedResult(document=document, approved=existing, skipped=len(existing))

    fixture = _load_fixture()
    document = await _ensure_document(documents, fixture["document"])
    await _ensure_pages(documents, document)
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


async def seed_multi_state_demo(
    *,
    documents: DocumentService,
    rules: RuleService,
    review: ReviewService,
    reviewed_by: str = "demo-seed",
) -> MultiStateSeedResult:
    """Multi-state generalisation of `seed_sirsa_demo`.

    Seeds Haryana/Sirsa from `data/fixtures/sirsa_demo_seed.json` -- the same
    file `seed_sirsa_demo` reads -- plus every additional state block in
    `data/fixtures/multi_state_demo_seed.json` (currently Nagaland/Dimapur and
    Manipur/Mpur Imphal East, both short real plans so in-range citations are
    easy to verify by hand). Haryana is intentionally not duplicated into the
    multi-state fixture.

    This deliberately does NOT call `seed_sirsa_demo` for the Haryana leg.
    That function's idempotency check is repo-wide ("does *any* rule carry
    DEMO_MARKER?"), which only stays correct as long as a single demo
    document ever exists in the repository. Once this function's other
    states also tag their rows with DEMO_MARKER, a repo-wide check would
    treat any one already-seeded state as proof every other state is seeded
    too. `_seed_document_rules` below applies the same idempotency pattern
    (and the same `ReviewService.approve` chokepoint, and the same
    never-self-approve safety check) scoped to one document at a time
    instead, so re-running this function only skips documents that are
    actually already seeded.
    """
    fixture_blocks = [_load_fixture(), *_load_multi_state_fixture()["states"]]

    seeded_documents: list[DocumentMetadata] = []
    approved: list[DACPRule] = []
    skipped = 0

    for block in fixture_blocks:
        document, block_approved, block_skipped = await _seed_document_rules(
            block["document"],
            block["drafts"],
            documents=documents,
            rules=rules,
            review=review,
            reviewed_by=reviewed_by,
        )
        seeded_documents.append(document)
        approved.extend(block_approved)
        skipped += block_skipped

    return MultiStateSeedResult(documents=seeded_documents, approved=approved, skipped=skipped)


async def _seed_document_rules(
    fixture_document: dict,
    fixture_drafts: list[dict],
    *,
    documents: DocumentService,
    rules: RuleService,
    review: ReviewService,
    reviewed_by: str,
) -> tuple[DocumentMetadata, list[DACPRule], int]:
    """Per-document seed loop shared by `seed_multi_state_demo`'s state blocks.

    Idempotent per document (`document_id` + `DEMO_MARKER`), unlike
    `seed_sirsa_demo`'s repo-wide check -- see `seed_multi_state_demo`'s
    docstring for why that distinction matters once multiple demo documents
    share a repository.
    """
    document = await _ensure_document(documents, fixture_document)
    await _ensure_pages(documents, document)

    existing = [
        rule
        for rule in await rules.list()
        if rule.document_id == document.id and DEMO_MARKER in rule.notes
    ]
    if existing:
        return document, existing, len(existing)

    approved: list[DACPRule] = []
    now = datetime.now(UTC)
    for raw in fixture_drafts:
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

    return document, approved, 0


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
            sha256=_pdf_sha256(meta["filename"], meta["state"]),
            status=DocumentStatus.REGISTERED,
            registered_at=datetime.now(UTC),
        )
    )


def _raw_root() -> Path:
    """Base directory for DACP source PDFs.

    `ANKUR_RAW_ROOT` (`app.config.Settings.ankur_raw_root`, default
    `"data/raw"`) so a container can point this at a mounted volume instead
    of a baked-in copy -- see apps/api/Dockerfile. A relative value resolves
    against the repo root; an absolute value (e.g. a mount path) is used
    as-is.
    """
    from app.config import get_settings

    raw_root = Path(get_settings().ankur_raw_root)
    return raw_root if raw_root.is_absolute() else _repo_root() / raw_root


def _pdf_candidate_dirs(state: str) -> tuple[Path, ...]:
    """Where a state's DACP plans may live under `_raw_root()`, newest layout first.

    `scripts/download_dacp.py` files every plan under `<raw_root>/<State>/`
    (state name, spaces replaced with underscores). A flat top-level
    `<raw_root>/` is kept as a fallback for checkouts predating that
    downloader (e.g. the Sirsa plan, tracked directly at `data/raw/`).
    Resolving instead of hard-coding one directory is what stops this from
    silently breaking again the next time the corpus is reorganized.
    """
    raw_root = _raw_root()
    return (raw_root / state.replace(" ", "_"), raw_root)


def _pdf_path(filename: str, state: str) -> Path | None:
    """Locate a DACP plan's PDF by filename, or None if this checkout hasn't downloaded it."""
    for directory in _pdf_candidate_dirs(state):
        candidate = directory / filename
        if candidate.exists():
            return candidate
    return None


async def _ensure_pages(documents: DocumentService, document: DocumentMetadata) -> None:
    """Attach real PDF page text so citation re-check and GET /pages work."""
    if await documents.list_pages(document.id):
        return
    pdf_path = _pdf_path(document.filename, document.state)
    if pdf_path is None:
        # Loud, because the consequence is silent and specific: without page text
        # `citation_appears_on_page` cannot verify anything, so it returns
        # "cannot verify" and every seeded citation passes unchecked. A seed that
        # quietly weakens a safety check is worse than one that fails.
        logger.warning(
            "%s not found under %s; seeding without page text, so citation "
            "snippets will NOT be verified against the source page",
            document.filename,
            " or ".join(str(directory) for directory in _pdf_candidate_dirs(document.state)),
        )
        return
    _, pages = load_document(pdf_path, district=document.district, state=document.state)
    remapped = [page.model_copy(update={"document_id": document.id}) for page in pages]
    await documents.add_pages(remapped)


def _pdf_sha256(filename: str, state: str) -> str | None:
    pdf_path = _pdf_path(filename, state)
    if pdf_path is None:
        return None
    return hashlib.sha256(pdf_path.read_bytes()).hexdigest()


async def _seed_postgres(*, multi_state: bool) -> SeedResult | MultiStateSeedResult:
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
        documents = DocumentService(documents=doc_repo)
        rule_service = RuleService(rules=rule_repo)
        review = ReviewService(rules=rule_repo, documents=doc_repo)
        if multi_state:
            result: SeedResult | MultiStateSeedResult = await seed_multi_state_demo(
                documents=documents, rules=rule_service, review=review
            )
        else:
            result = await seed_sirsa_demo(documents=documents, rules=rule_service, review=review)
    finally:
        await pool.close()
    return result


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Seed cited DACP demo rules via ReviewService.")
    parser.add_argument(
        "--multi-state",
        action="store_true",
        help=(
            "Seed Haryana/Sirsa plus the additional states in "
            "multi_state_demo_seed.json (default: Haryana/Sirsa only)."
        ),
    )
    args = parser.parse_args()
    result = asyncio.run(_seed_postgres(multi_state=args.multi_state))
    if isinstance(result, MultiStateSeedResult):
        states = sorted({rule.fields.state for rule in result.approved})
        print(
            f"documents={len(result.documents)} states={states} "
            f"approved={len(result.approved)} skipped={result.skipped}"
        )
    else:
        print(
            f"document={result.document.id} approved={len(result.approved)} "
            f"skipped={result.skipped}"
        )
    for rule in result.approved:
        print(
            f"  {rule.fields.state}/{rule.fields.district} {rule.fields.condition_code} "
            f"p{rule.citation.page} {rule.review_status.value} {rule.fields.crop}"
        )


if __name__ == "__main__":
    main()
