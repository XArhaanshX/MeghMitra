"""Tests for `ankur_geo`: state/district identity, alias resolution, and the
ML parameter objects that replace hardcoded Haryana constants.
"""

from __future__ import annotations

import pytest
from ankur_geo import (
    DEFAULT_CONDITION_THRESHOLDS,
    DEFAULT_SEASON_WINDOW,
    DISTRICTS,
    INDIA_BBOX,
    NORTHEAST_MONSOON_WINDOW,
    STATES,
    RegionResolutionError,
    resolve_region,
    resolve_state,
    state_by_code,
    state_by_name,
    states_with_district_name,
)


class TestStates:
    def test_36_states_and_uts(self) -> None:
        assert len(STATES) == 36

    def test_lookup_by_code_and_name_agree(self) -> None:
        assert state_by_code("HR") is state_by_name("Haryana")

    def test_unknown_name_returns_none_not_a_guess(self) -> None:
        assert state_by_name("Narnia") is None


class TestAliasResolution:
    @pytest.mark.parametrize(
        ("legacy", "canonical"),
        [
            ("Arunchal_Pradesh", "Arunachal Pradesh"),
            ("Chattisgarh", "Chhattisgarh"),
            ("Maharastra", "Maharashtra"),
            ("Orissa", "Odisha"),
            ("Uttarkhand", "Uttarakhand"),
            ("Jammu___Kashmir", "Jammu and Kashmir"),
            ("Andaman___Nicobar_Islands", "Andaman and Nicobar Islands"),
        ],
    )
    def test_all_seven_legacy_directory_names_resolve(self, legacy: str, canonical: str) -> None:
        assert resolve_state(legacy).name == canonical

    def test_legacy_and_canonical_spelling_resolve_to_the_same_state(self) -> None:
        assert resolve_state("Chattisgarh") is resolve_state("Chhattisgarh")

    def test_unrecognized_state_raises_rather_than_guesses(self) -> None:
        with pytest.raises(RegionResolutionError):
            resolve_state("Narnia")


class TestDistrictResolution:
    def test_district_derived_from_real_ingested_corpus(self) -> None:
        """Not a hand-authored gazetteer -- see districts.py module docstring."""
        assert len(DISTRICTS) > 600

    def test_real_district_resolves(self) -> None:
        region = resolve_region("Haryana", "Sirsa")
        assert region.state.name == "Haryana"
        assert region.district.name == "Sirsa"

    def test_same_district_under_wrong_state_raises(self) -> None:
        """Sirsa is a Haryana district. Asking under a different state must
        raise, not silently return Haryana's plan."""
        with pytest.raises(RegionResolutionError, match="not an ingested district of Punjab"):
            resolve_region("Punjab", "Sirsa")

    @pytest.mark.parametrize(
        ("district", "state_a", "state_b"),
        [
            ("Aurangabad", "Bihar", "Maharashtra"),
            ("Balrampur", "Uttar Pradesh", "Chhattisgarh"),
            ("Bijapur", "Karnataka", "Chhattisgarh"),
            ("Bilaspur", "Chhattisgarh", "Himachal Pradesh"),
            ("Hamirpur", "Himachal Pradesh", "Uttar Pradesh"),
            ("Pratapgarh", "Uttar Pradesh", "Rajasthan"),
            ("Raigarh", "Maharashtra", "Chhattisgarh"),
        ],
    )
    def test_cross_state_duplicate_district_names_resolve_to_the_right_state(
        self, district: str, state_a: str, state_b: str
    ) -> None:
        assert resolve_region(state_a, district).state.name == state_a
        assert resolve_region(state_b, district).state.name == state_b

    @pytest.mark.parametrize(
        "district",
        ["Aurangabad", "Balrampur", "Bijapur", "Bilaspur", "Hamirpur", "Pratapgarh", "Raigarh"],
    )
    def test_ambiguous_district_names_are_flagged(self, district: str) -> None:
        assert len(states_with_district_name(district)) == 2

    def test_unknown_district_message_names_the_real_state(self) -> None:
        """When a district exists under a different state, the error names it
        -- this is the case that matters most: a wrong-state guess would be
        the exact bug Phase 0 fixed in RuleStore, reintroduced here."""
        with pytest.raises(RegionResolutionError, match="IS ingested for:"):
            resolve_region("Kerala", "Bijapur")


class TestSeasonWindow:
    def test_default_reproduces_the_hardcoded_jjas_constant(self) -> None:
        """`trigger_engine.config.SEASON_LENGTH_DAYS` was hardcoded to 122."""
        assert DEFAULT_SEASON_WINDOW.length_days == 122

    def test_northeast_monsoon_window_has_a_different_length(self) -> None:
        assert NORTHEAST_MONSOON_WINDOW.length_days != DEFAULT_SEASON_WINDOW.length_days
        assert NORTHEAST_MONSOON_WINDOW.start_month == 10


class TestConditionThresholds:
    def test_defaults_reproduce_current_sirsa_derived_constants(self) -> None:
        assert DEFAULT_CONDITION_THRESHOLDS.delayed_onset_days == 21
        assert DEFAULT_CONDITION_THRESHOLDS.sowing_window_days == 30
        assert DEFAULT_CONDITION_THRESHOLDS.dry_spell_after_sowing_min_days == 15
        assert DEFAULT_CONDITION_THRESHOLDS.dry_spell_after_sowing_max_days == 20
        assert DEFAULT_CONDITION_THRESHOLDS.terminal_drought_doy_start == 250


class TestIndiaBbox:
    def test_bbox_covers_mainland_india(self) -> None:
        min_lon, min_lat, max_lon, max_lat = INDIA_BBOX
        assert min_lon < 77 < max_lon  # Delhi's longitude sits inside the box
        assert min_lat < 26 < max_lat  # Delhi's latitude sits inside the box
