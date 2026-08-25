"""Multi-state demo seed goes through validate_draft + ReviewService.approve, never self-approves.

Mirrors test_seed_demo.py's assertions but for `seed_multi_state_demo`, which
seeds Haryana/Sirsa plus every state block in multi_state_demo_seed.json
(currently Nagaland/Dimapur and Manipur/Mpur Imphal East).
"""

from __future__ import annotations

from ankur_domain.memory import InMemoryDocumentRepository, InMemoryRuleRepository
from ankur_domain.services import DocumentService, ReviewService, RuleService
from ankur_schemas.enums import ReviewStatus
from app.seed import DEMO_MARKER, seed_multi_state_demo


async def test_seed_multi_state_approves_rules_across_states():
    documents = InMemoryDocumentRepository()
    rules = InMemoryRuleRepository()
    result = await seed_multi_state_demo(
        documents=DocumentService(documents=documents),
        rules=RuleService(rules=rules),
        review=ReviewService(rules=rules, documents=documents),
    )

    assert result.skipped == 0
    assert len(result.documents) == 3
    assert len(result.approved) == 9  # 3 states x 3 drafts each

    states = {rule.fields.state for rule in result.approved}
    assert states == {"Haryana", "Nagaland", "Manipur"}
    # At least two non-Haryana states landed approved rules with valid citations.
    assert len(states - {"Haryana"}) >= 2

    assert all(rule.review_status == ReviewStatus.APPROVED for rule in result.approved)
    assert all(DEMO_MARKER in rule.notes for rule in result.approved)

    documents_by_id = {document.id: document for document in result.documents}
    for rule in result.approved:
        document = documents_by_id[rule.document_id]
        assert document.state == rule.fields.state
        assert document.page_count is not None
        assert 1 <= rule.citation.page <= document.page_count

    again = await seed_multi_state_demo(
        documents=DocumentService(documents=documents),
        rules=RuleService(rules=rules),
        review=ReviewService(rules=rules, documents=documents),
    )
    assert again.skipped == 9
    assert len(await rules.list()) == 9
