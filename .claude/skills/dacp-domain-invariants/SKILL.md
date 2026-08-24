---
name: dacp-domain-invariants
description: Changing anything in packages/domain/src/ankur_domain/policies.py or services.py, the review/approval workflow, or the extracted_rules table/migrations. Use to check a change against Ankur's core safety invariants before it ships.
---

# Domain invariant checklist

Full explanation: `docs/domain-model.md`. This skill is the pre-flight checklist for any change
touching approval, review routing, or citation handling.

## The two invariants (never weaken these)

1. **No citation -> no approved rule.**
   Enforced by `ankur_domain.policies.can_approve()` (checked in `ReviewService.approve()`) and
   independently by the `approved_rules_require_citation` `CHECK` constraint on
   `extracted_rules` in `db/migrations/0001_init.sql`. A change that lets a rule reach
   `review_status = approved` without a valid citation is a regression, full stop -- including
   changes made "temporarily for a demo."

2. **Extraction never self-approves.**
   `document_intelligence.validator.validate_draft()` only ever assigns `pending` or
   `needs_review` via `ankur_domain.policies.initial_review_status()`. If you're adding a new
   extraction path (a second extractor, a batch importer, a fixture loader used in a non-test
   context), it must go through `validate_draft()` too -- never construct a `DACPRule` with
   `review_status=APPROVED` directly outside the human-reviewer approval endpoint.

## Before merging a change here

- [ ] Does `can_approve()` still require `has_valid_citation()` and nothing weaker?
- [ ] Does every code path that creates a `DACPRule` from extraction route through
      `initial_review_status()` (directly or via `validate_draft()`)?
- [ ] If you touched the DB schema: does the `CHECK` constraint on `extracted_rules` still match
      the Python-level invariant? (They're intentionally redundant -- don't let them drift.)
- [ ] Did you run `tests/unit/test_citations.py` and `tests/unit/test_confidence.py`? These are
      the invariant tests specifically -- a passing full suite isn't a substitute for confirming
      these two files still pass and still assert what they say they assert.
- [ ] If you added a new repository method: did you implement it in **both**
      `ankur_domain/memory.py` and `apps/api/app/db.py`, and do they behave identically? A drift
      between them means tests (in-memory) pass while production (Postgres) doesn't enforce the
      same thing, or vice versa.

## Confidence is not an approval gate for humans

`can_approve()` deliberately does **not** check `confidence`. A human reviewer may approve a
low-confidence rule after manually verifying it against the source PDF page -- what's blocked is
the *automated* pipeline ever treating a low-confidence draft as trustworthy without review. Do
not "fix" this by adding a confidence check to `can_approve()`; that would block legitimate human
overrides. If you think confidence should gate something new, gate it in
`is_advisory_eligible()` or a new read-time check, not in the approval write path. See
`tests/unit/test_confidence.py::test_low_confidence_rule_is_not_advisory_eligible_even_if_marked_approved`
for the test that pins this design down.
