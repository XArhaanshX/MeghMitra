"""Tests for the seam between the rule base and the trigger engine.

Covers the five modules added to join them:

    tables      geometric table reconstruction (wrapped cells -> logical rows)
    normalize   condition prose -> ConditionCode
    naming      DACP filename -> district
    rulestore   ingested corpus -> (district, condition_code) index
    endtoend    the safety claims that hold the whole path together

The last group is the one that matters. Four claims are load-bearing, and each
has a test whose failure means the system would say something it has no
authority to say:

    test_unreviewed_rules_never_emit          silence is the default
    test_simulated_approval_still_enforces_citation_bounds
                                              the demo shortcut is not a bypass
    test_non_dry_spell_conditions_do_not_borrow_the_dry_spell_threshold
                                              the flood-row bug stays fixed
    test_normalizer_and_engine_agree_on_priority
                                              the join cannot drift silently
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from ankur_domain.policies import can_emit_advisory
from ankur_schemas.citation import Citation
from ankur_schemas.condition import ConditionCode, DrySpellForecast, MoistureState
from ankur_schemas.enums import ReviewStatus
from ankur_schemas.rule import DACPRule, DACPRuleFields
from document_intelligence.naming import district_from_filename
from document_intelligence.normalize import normalize_condition
from document_intelligence.tables import (
    TableRegion,
    assemble_rows,
    column_bands,
    find_table_regions,
)
from trigger_engine.conditions import CONDITION_PRIORITY
from trigger_engine.decision import PROBABILITY_DRIVEN_CONDITIONS, AdvisoryAction
from trigger_engine.endtoend import simulate_reviewer_approval
from trigger_engine.pipeline import emit_advisory
from trigger_engine.rulestore import RuleStore, district_key

# A verbatim excerpt from data/raw/Haryana/HAR16-Sirsa-30-06-2011.pdf page 9, as
# `pdftotext -layout` renders it. The condition wraps over five physical lines
# and the column titles ("Major", "Farming", "situation") are interleaved down
# the middle of it -- both of the things that made line-level extraction produce
# 450 fragments for this document.
SIRSA_PAGE_9 = """\
Condition                                              Suggested Contingency measures
Early season drought
(Normal onset)        Major           Crop/cropping system              Crop management

Normal onset          Farming         Pearl millet: HHB-94, HHB-197,
followed by 15-20                     HHB-67 (Improved)
days dry spell        situation
after sowing          Light           Pearl millet + Greengram- Satya,
leading to poor       textured        Mothbean: RMO- 40                 poor plant population
germination/crop      sandy soils     (Intercropping 8:4/6:3)
stand etc.            susceptible to  Clusterbean: HG-563               go for re-sowing as
                      wind erosion    Cowpea: Charodi for grain         and when rains resume.
"""


def _region(text: str) -> TableRegion:
    regions = find_table_regions(text, page=9)
    assert regions, "expected the Condition banner to open a region"
    return regions[0]


class TestTableReconstruction:
    def test_wrapped_condition_is_reassembled_into_one_cell(self) -> None:
        """The whole point: five physical lines, one condition."""
        rows = assemble_rows(_region(SIRSA_PAGE_9))
        conditions = [row.cells[0] for row in rows]

        assert any(
            "Normal onset followed by 15-20 days dry spell after sowing" in condition
            for condition in conditions
        ), f"wrapped condition was not reassembled; got {conditions}"

    def test_column_titles_do_not_leak_into_data_cells(self) -> None:
        """'Major', 'Farming' and 'situation' are labels, not a farming situation."""
        rows = assemble_rows(_region(SIRSA_PAGE_9))
        target = next(row for row in rows if "after sowing" in row.cells[0])

        assert "Major" not in target.cells[1]
        assert "situation" not in target.cells[1]
        assert "Light textured sandy soils" in target.cells[1]

    def test_banner_row_is_not_emitted_as_a_rule(self) -> None:
        rows = assemble_rows(_region(SIRSA_PAGE_9))
        assert all(row.cells[0].strip().lower() != "condition" for row in rows)

    def test_source_lines_are_kept_verbatim_for_the_citation(self) -> None:
        """A citation must quote text a reviewer can find on the page."""
        rows = assemble_rows(_region(SIRSA_PAGE_9))
        target = next(row for row in rows if "after sowing" in row.cells[0])

        assert "Normal onset" in target.source_text
        for line in target.source_lines:
            assert line in SIRSA_PAGE_9

    def test_prose_page_yields_no_regions(self) -> None:
        """Most of a DACP is district profile. It must not become rules."""
        assert find_table_regions("1.1 District profile\n\nSirsa lies in Haryana.\n", page=2) == []

    def test_unreadable_columns_give_up_rather_than_guess(self) -> None:
        """No whitespace corridor -> no rows. Silence beats a misaligned row."""
        region = TableRegion(page=1, start_line=0, lines=["Condition", "abc", "def"])
        assert column_bands(region.lines) == []
        assert assemble_rows(region) == []


class TestConditionNormalization:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            (
                "Normal onset followed by 15-20 days dry spell after sowing leading to "
                "poor germination/crop stand etc.",
                ConditionCode.DRY_SPELL_AFTER_SOWING,
            ),
            ("Early season drought (delayed onset) Delay by 4 weeks", ConditionCode.DELAYED_ONSET),
            ("Terminal drought (Early withdrawal of monsoon)", ConditionCode.TERMINAL_DROUGHT),
            ("Mid season drought (long dry spell)", ConditionCode.MID_SEASON_DRY_SPELL),
            ("Continuous high rainfall leading to water logging", ConditionCode.UNSEASONAL_RAIN),
        ],
    )
    def test_known_conditions_map(self, text: str, expected: ConditionCode) -> None:
        assert normalize_condition(text) is expected

    @pytest.mark.parametrize("text", ["", "   ", None, "Insufficient groundwater recharge"])
    def test_unrecognized_prose_is_unmapped_not_guessed(self, text: str | None) -> None:
        assert normalize_condition(text) is ConditionCode.UNMAPPED

    def test_after_sowing_beats_the_generic_dry_spell(self) -> None:
        """Both phrases are present; the specific row carries the re-sow variety."""
        assert (
            normalize_condition("Mid season long dry spell after sowing")
            is ConditionCode.DRY_SPELL_AFTER_SOWING
        )

    def test_normalizer_and_engine_agree_on_priority(self) -> None:
        """The extractor's ordering must match the engine's, or the join misses.

        `document_intelligence` and `trigger_engine` are siblings that may not
        import each other, so the priority tuple is duplicated. Duplication is
        only safe while something checks it -- a disagreement here does not raise
        at runtime, it just makes advisories silently never fire.
        """
        from document_intelligence.normalize import _PRIORITY

        assert tuple(code for code, _ in _PRIORITY) == CONDITION_PRIORITY

    def test_unmapped_is_not_emittable(self) -> None:
        """A normalization failure must never become a trigger."""
        from ankur_schemas.condition import EMITTABLE_CONDITION_CODES

        assert ConditionCode.UNMAPPED not in EMITTABLE_CONDITION_CODES


class TestDistrictNaming:
    @pytest.mark.parametrize(
        ("stem", "state", "expected"),
        [
            ("HAR16-Sirsa-30-06-2011", "Haryana", "Sirsa"),
            ("NL2-Wokha-20.11.2014", "Nagaland", "Wokha"),
            ("UP67-Lakhimpur_Kheri-31.07.14", "Uttar Pradesh", "Lakhimpur Kheri"),
            ("Orissa_6-_Puri_31.05.2011", "Orissa", "Puri"),
            ("GUJ_6-Porbandar_30.04.2011", "Gujarat", "Porbandar"),
            # The two cases where the district is named after its own state.
            ("1North_Goa", "Goa", "North Goa"),
            ("A_N_1-Nicobar-03.05.2015", "Andaman & Nicobar Islands", "Nicobar"),
        ],
    )
    def test_district_is_recovered(self, stem: str, state: str, expected: str) -> None:
        assert district_from_filename(stem, state=state) == expected

    def test_unparseable_stem_falls_back_rather_than_returning_empty(self) -> None:
        assert district_from_filename("2011", state="Haryana") == "2011"

    def test_lookup_key_folds_spelling_variants(self) -> None:
        assert district_key("Sirsa") == district_key("sirsa") == district_key("  SIRSA ")


def _rule(
    *,
    code: ConditionCode | None,
    page: int = 9,
    status: ReviewStatus = ReviewStatus.NEEDS_REVIEW,
    document_id: str | None = None,
) -> DACPRule:
    return DACPRule(
        document_id=document_id,
        fields=DACPRuleFields(district="Sirsa", condition="test condition", condition_code=code),
        citation=Citation(document="HAR16-Sirsa-30-06-2011.pdf", page=page),
        confidence=0.7,
        extractor_version="test/1.0",
        extracted_at=datetime.now(UTC),
        review_status=status,
    )


@pytest.fixture
def store(tmp_path) -> RuleStore:
    """A one-document corpus in the on-disk shape `ingest_all_dacp.py` writes."""
    document_id = str(uuid4())
    payload = {
        "document": {
            "id": document_id,
            "filename": "HAR16-Sirsa-30-06-2011.pdf",
            "district": "Sirsa",
            "state": "Haryana",
            "page_count": 31,
            "status": "registered",
            "registered_at": "2026-08-24T20:46:19.230985Z",
        },
        "run": {},
        "rules": [
            json.loads(
                _rule(
                    code=ConditionCode.DRY_SPELL_AFTER_SOWING, document_id=document_id
                ).model_dump_json()
            ),
            json.loads(
                _rule(code=ConditionCode.UNMAPPED, document_id=document_id).model_dump_json()
            ),
            # Cites page 44 of a 31-page document. The real Sirsa fixture does
            # exactly this, which is why the page bound exists.
            json.loads(
                _rule(
                    code=ConditionCode.MID_SEASON_DRY_SPELL, page=44, document_id=document_id
                ).model_dump_json()
            ),
        ],
    }
    target = tmp_path / "sirsa" / "HAR16-Sirsa-30-06-2011.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(payload), encoding="utf-8")
    return RuleStore.from_processed(tmp_path)


class TestRuleStore:
    def test_rules_are_indexed_by_district_and_code(self, store: RuleStore) -> None:
        assert len(store.candidates("Sirsa", ConditionCode.DRY_SPELL_AFTER_SOWING)) == 1

    def test_unmapped_rules_are_counted_but_never_served(self, store: RuleStore) -> None:
        assert store.coverage().unmapped_rules == 1
        assert store.candidates("Sirsa", ConditionCode.UNMAPPED) == []

    def test_unknown_district_returns_nothing_rather_than_a_neighbour(
        self, store: RuleStore
    ) -> None:
        """Serving a different district's plan would be inventing advice."""
        assert store.candidates("Fatehabad", ConditionCode.DRY_SPELL_AFTER_SOWING) == []

    def test_page_count_is_available_for_the_citation_bound(self, store: RuleStore) -> None:
        rule = store.candidates("Sirsa", ConditionCode.DRY_SPELL_AFTER_SOWING)[0]
        assert store.page_count_for(rule) == 31


class TestSafetyClaims:
    def test_unreviewed_rules_never_emit(self, store: RuleStore) -> None:
        """The corpus has 9,103 rules and zero approvals. All of them must abstain."""
        rule = store.candidates("Sirsa", ConditionCode.DRY_SPELL_AFTER_SOWING)[0]
        assert rule.review_status is ReviewStatus.NEEDS_REVIEW

        may_emit, reasons = can_emit_advisory(
            rule, ConditionCode.DRY_SPELL_AFTER_SOWING, page_count=31
        )
        assert may_emit is False
        assert any("not 'approved'" in reason for reason in reasons)

    def test_simulated_approval_still_enforces_citation_bounds(self, store: RuleStore) -> None:
        """The demo shortcut simulates judgement, never a check a machine can make."""
        out_of_range = store.candidates("Sirsa", ConditionCode.MID_SEASON_DRY_SPELL)
        assert out_of_range, "fixture should provide a rule citing page 44 of 31"
        assert simulate_reviewer_approval(out_of_range, store) == []

        approved = simulate_reviewer_approval(
            store.candidates("Sirsa", ConditionCode.DRY_SPELL_AFTER_SOWING), store
        )
        assert len(approved) == 1
        assert approved[0].review_status is ReviewStatus.APPROVED
        assert "SIMULATED" in (approved[0].reviewed_by or "")

    def test_non_dry_spell_conditions_do_not_borrow_the_dry_spell_threshold(self) -> None:
        """The flood row. `decide` only ever reasoned about dry spells.

        Before this gate, an UNSEASONAL_RAIN detection with a high dry-spell
        probability and a sown crop returned RE_SOW -- telling a farmer to buy
        seed again because their field was under water.
        """
        assert ConditionCode.UNSEASONAL_RAIN not in PROBABILITY_DRIVEN_CONDITIONS

        rule = _rule(code=ConditionCode.UNSEASONAL_RAIN, status=ReviewStatus.APPROVED)
        state = MoistureState(
            block_id="Baragudha",
            as_of=date(2025, 8, 14),
            soil_moisture_fraction=0.95,
            consecutive_dry_days=0,
            days_since_sowing=40,
            rain_3d_mm=180.0,
            rain_3d_normal_mm=20.0,
        )
        forecast = DrySpellForecast(
            block_id="Baragudha",
            issued_on=date(2025, 8, 14),
            lead_days=14,
            probability=0.99,
            climatological_rate=0.3,
            model_version="test",
        )

        action, decision, _matched, reasons = emit_advisory(
            state,
            forecast,
            [rule],
            cost_loss_ratio=0.2,
            crop_already_sown=True,
            document_page_count=31,
        )

        assert action is AdvisoryAction.ABSTAIN
        assert decision is None
        assert any("no probabilistic decision rule" in reason for reason in reasons)

    def test_dry_spell_after_sowing_still_emits_when_everything_holds(self) -> None:
        """The gate must not have broken the flagship path it was added beside."""
        rule = _rule(code=ConditionCode.DRY_SPELL_AFTER_SOWING, status=ReviewStatus.APPROVED)
        state = MoistureState(
            block_id="Baragudha",
            as_of=date(2025, 7, 16),
            soil_moisture_fraction=0.10,
            consecutive_dry_days=9,
            days_since_sowing=11,
            rain_3d_mm=0.0,
            rain_3d_normal_mm=15.0,
        )
        forecast = DrySpellForecast(
            block_id="Baragudha",
            issued_on=date(2025, 7, 16),
            lead_days=14,
            probability=0.80,
            climatological_rate=0.3,
            model_version="test",
        )

        action, decision, matched, reasons = emit_advisory(
            state,
            forecast,
            [rule],
            cost_loss_ratio=0.2,
            crop_already_sown=True,
            document_page_count=31,
        )

        assert action is AdvisoryAction.RE_SOW
        assert decision is not None
        assert matched is rule
        assert reasons == []
