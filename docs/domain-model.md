# Domain model & invariants

Source of truth: `packages/schemas/src/ankur_schemas/` (data shapes) and
`packages/domain/src/ankur_domain/policies.py` (rules). This doc explains *why*; read those
files for the exact implementation.

## `DACPRule`

The central object (`ankur_schemas/rule.py`). Every field except `district` and `condition` is
nullable -- DACP documents are inconsistent in what they specify, and a missing value must stay
`null`, never guessed or backfilled from general agricultural knowledge.

```json
{
  "fields": {
    "district": "Sirsa",
    "crop": "Pearl millet",
    "condition": "Normal onset followed by 15-20 day dry spell after sowing",
    "crop_stage": "After sowing",
    "action": "Re-sow",
    "variety": "HHB-67 Improved",
    "seed_rate": null,
    "actor": "Block Agriculture Officer"
  },
  "citation": { "document": "HAR16-Sirsa-30-06-2011.pdf", "page": 37 },
  "confidence": 0.94,
  "review_status": "pending"
}
```

`DACPRuleDraft` is the pre-validation shape extraction produces; `RuleValidator.validate_draft`
turns a draft into a `DACPRule` with an assigned `review_status`. A draft has no identity and no
review history -- re-running extraction never mutates a persisted rule, it produces new drafts.

## Review lifecycle (`ReviewStatus`)

```text
pending        extracted, schema-valid, not yet looked at by a human
needs_review   ambiguous / low-confidence / failed an invariant at extraction time
approved       a human confirmed the rule matches the source document
rejected       a human determined the extraction is wrong or unusable
```

Extraction (`document_intelligence.validator.validate_draft`) only ever assigns `pending` or
`needs_review` -- **never** `approved`. Only `ReviewService.approve()` /
`POST /rules/{id}/approve` can move a rule to `approved`, and only a human calls that endpoint.

## The two invariants everything else defers to

Both live in `ankur_domain/policies.py` as pure functions (no I/O), which is what makes them
unit-testable without a database (`tests/unit/test_citations.py`,
`tests/unit/test_confidence.py`) and reusable from both `document_intelligence` (extraction-time
routing) and `apps/api` (approval-time enforcement).

1. **No citation → no approved rule.**
   `has_valid_citation()` requires a non-blank `document` and a `page >= 1`. When the caller
   knows the source document's length, `page_count` is an optional tightening: a page past the
   end of the file is rejected. `can_approve()` checks this and is the *only* gate
   `ReviewService.approve()` enforces -- independent of confidence, review history, or who's
   asking. `ReviewService` looks up `document.page_count` when the rule has a `document_id`.
   Enforced a second time at the database layer via a `CHECK` constraint on `extracted_rules`
   (`db/migrations/0001_init.sql`): a row cannot be written with `review_status = 'approved'`
   and a blank citation, even by a bug that bypasses the Python layer entirely.

2. **Low confidence → no automated advisory eligibility.**
   `requires_review()` routes any draft below `MIN_AUTO_ELIGIBLE_CONFIDENCE` (0.85) to
   `needs_review` at extraction time -- the pipeline never presents a confidently-wrong rule as
   merely `pending`. `is_advisory_eligible()` is the read-time gate the future trigger engine
   will use: `review_status == approved AND has_valid_citation`. Note confidence does not
   re-enter that check after approval -- a human *can* approve a low-confidence rule once they've
   manually verified it against the source page; what's blocked is the *automated* path treating
   a low-confidence extraction as trustworthy. See
   `tests/unit/test_confidence.py::test_low_confidence_rule_is_not_advisory_eligible_even_if_marked_approved`
   for the explicit test of this design decision.

## Extending the schema

DACP documents vary district to district. If a future district's plan needs a field
`DACPRuleFields` doesn't have: add it as `str | None = None` (never required, never a closed
enum unless the vocabulary is genuinely fixed across all target districts -- see the comment at
the top of `ankur_schemas/enums.py`). Update `db/migrations/` with a new migration file (never
edit `0001_init.sql` in place once it has shipped) -- `extracted_rules.fields` is JSONB, so new
optional fields need no migration for the data itself, only for any new indexed/queryable
columns you add to `rule_citations` or similar.
