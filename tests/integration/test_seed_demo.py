"""Demo seed goes through validate_draft + ReviewService.approve, never self-approves."""

from __future__ import annotations

from ankur_domain.memory import InMemoryDocumentRepository, InMemoryRuleRepository
from ankur_domain.services import DocumentService, ReviewService, RuleService
from ankur_schemas.enums import ReviewStatus
from app.seed import DEMO_MARKER, seed_sirsa_demo


async def test_seed_approves_three_in_range_sirsa_rules():
    documents = InMemoryDocumentRepository()
    rules = InMemoryRuleRepository()
    result = await seed_sirsa_demo(
        documents=DocumentService(documents=documents),
        rules=RuleService(rules=rules),
        review=ReviewService(rules=rules, documents=documents),
    )

    assert result.skipped == 0
    assert len(result.approved) == 3
    assert result.document.page_count == 31
    assert len(await documents.get_pages(result.document.id)) == 31
    assert all(rule.review_status == ReviewStatus.APPROVED for rule in result.approved)
    assert all(rule.citation.page <= 31 for rule in result.approved)
    assert all(rule.document_id == result.document.id for rule in result.approved)
    assert all(DEMO_MARKER in rule.notes for rule in result.approved)
    assert {rule.fields.condition_code.value for rule in result.approved} == {
        "dry_spell_after_sowing",
        "delayed_onset",
        "mid_season_dry_spell",
    }

    again = await seed_sirsa_demo(
        documents=DocumentService(documents=documents),
        rules=RuleService(rules=rules),
        review=ReviewService(rules=rules, documents=documents),
    )
    assert again.skipped == 3
    assert len(await rules.list()) == 3
