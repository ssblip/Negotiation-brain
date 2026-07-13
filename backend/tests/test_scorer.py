"""Tests for Feature 2 — Must Have / Good to Have scoring logic."""
import pytest
from app.scorer import compute_spec_score, get_mandatory_failures


# ---------- fixtures ----------

SPECS_MIXED = [
    {"name": "IP Rating",  "field_type": "CAT",  "required_value": "IP65", "weight": 1.0, "mandatory": True},
    {"name": "ISO 9001",   "field_type": "BOOL", "required_value": "true", "weight": 1.0, "mandatory": True},
    {"name": "Warranty",   "field_type": "NUM",  "required_value": 24,     "weight": 2.0, "mandatory": False},
    {"name": "Defect Rate","field_type": "NUM",  "required_value": 0.5,    "weight": 1.0, "mandatory": False},
]

SPECS_ALL_MANDATORY = [
    {"name": "IP Rating",  "field_type": "CAT",  "required_value": "IP65", "weight": 1.0, "mandatory": True},
    {"name": "ISO 9001",   "field_type": "BOOL", "required_value": "true", "weight": 1.0, "mandatory": True},
]

SPECS_ALL_GOODTOHAVE = [
    {"name": "Warranty",    "field_type": "NUM", "required_value": 24,  "weight": 2.0, "mandatory": False},
    {"name": "Defect Rate", "field_type": "NUM", "required_value": 0.5, "weight": 1.0, "mandatory": False},
]

SPECS_NO_MANDATORY_FLAG = [
    {"name": "Warranty",    "field_type": "NUM", "required_value": 24, "weight": 1.0},
]


# ---------- get_mandatory_failures ----------

class TestGetMandatoryFailures:
    def test_passes_all_mandatory(self):
        vals = {"IP Rating": "IP65", "ISO 9001": "true", "Warranty": 30, "Defect Rate": 0.3}
        assert get_mandatory_failures(SPECS_MIXED, vals) == []

    def test_fails_one_mandatory(self):
        vals = {"IP Rating": "IP54", "ISO 9001": "true", "Warranty": 30}
        assert get_mandatory_failures(SPECS_MIXED, vals) == ["IP Rating"]

    def test_fails_all_mandatory(self):
        vals = {"IP Rating": "IP54", "ISO 9001": "false"}
        result = get_mandatory_failures(SPECS_MIXED, vals)
        assert "IP Rating" in result
        assert "ISO 9001" in result
        assert len(result) == 2

    def test_good_to_have_failure_not_in_result(self):
        # Warranty is Good to Have — a bad value should not appear in mandatory failures
        vals = {"IP Rating": "IP65", "ISO 9001": "true", "Warranty": 0, "Defect Rate": 99}
        assert get_mandatory_failures(SPECS_MIXED, vals) == []

    def test_missing_vendor_value_is_failure(self):
        # Vendor didn't provide IP Rating at all — should count as failure
        vals = {"ISO 9001": "true"}
        result = get_mandatory_failures(SPECS_MIXED, vals)
        assert "IP Rating" in result

    def test_empty_specs_returns_empty(self):
        assert get_mandatory_failures([], {"anything": "value"}) == []

    def test_no_mandatory_specs_returns_empty(self):
        vals = {"Warranty": 12}  # bad value but not mandatory
        assert get_mandatory_failures(SPECS_ALL_GOODTOHAVE, vals) == []

    def test_specs_without_mandatory_flag_treated_as_goodtohave(self):
        # Old specs without 'mandatory' key — default is False, no failures
        vals = {"Warranty": 0}
        assert get_mandatory_failures(SPECS_NO_MANDATORY_FLAG, vals) == []


# ---------- compute_spec_score ----------

class TestComputeSpecScore:
    def test_no_specs_returns_100(self):
        assert compute_spec_score([], {}) == 100.0

    def test_all_mandatory_specs_returns_100(self):
        # All specs are mandatory — no Good to Have specs to score
        vals = {"IP Rating": "IP65", "ISO 9001": "true"}
        assert compute_spec_score(SPECS_ALL_MANDATORY, vals) == 100.0

    def test_goodtohave_only_scored(self):
        # Mandatory specs excluded from weighted avg
        # Warranty=30 vs target=24 → 100 (capped); Defect Rate=0.3 vs target=0.5 → 60
        # weights: Warranty=2, Defect=1 → (100×2 + 60×1) / 3 = 86.67
        vals = {"IP Rating": "IP65", "ISO 9001": "true", "Warranty": 30, "Defect Rate": 0.3}
        score = compute_spec_score(SPECS_MIXED, vals)
        assert abs(score - 86.67) < 0.1

    def test_mandatory_failure_does_not_affect_spec_score(self):
        # Vendor fails Must Have IP Rating but has good Good to Have scores
        # spec_score should still reflect Good to Have performance only
        vals_pass = {"IP Rating": "IP65", "ISO 9001": "true", "Warranty": 30, "Defect Rate": 0.3}
        vals_fail = {"IP Rating": "IP54", "ISO 9001": "false", "Warranty": 30, "Defect Rate": 0.3}
        assert compute_spec_score(SPECS_MIXED, vals_pass) == compute_spec_score(SPECS_MIXED, vals_fail)

    def test_all_goodtohave_weighted_average(self):
        # Warranty=12 vs 24 → 50; Defect=0.5 vs 0.5 → 100; weights 2:1
        # (50×2 + 100×1) / 3 = 66.67
        vals = {"Warranty": 12, "Defect Rate": 0.5}
        score = compute_spec_score(SPECS_ALL_GOODTOHAVE, vals)
        assert abs(score - 66.67) < 0.1

    def test_old_specs_without_mandatory_flag_still_scored(self):
        # Backward compat — specs without 'mandatory' key should be treated as Good to Have
        vals = {"Warranty": 24}
        assert compute_spec_score(SPECS_NO_MANDATORY_FLAG, vals) == 100.0

    def test_missing_vendor_values_score_50_neutral(self):
        # Vendor provided no values — NUM with no value scores 50 (neutral)
        score = compute_spec_score(SPECS_ALL_GOODTOHAVE, {})
        assert score == 50.0

    def test_score_capped_at_100(self):
        # Warranty=100 vs target=24 → ratio > 1, capped at 100
        vals = {"Warranty": 100, "Defect Rate": 0.5}
        score = compute_spec_score(SPECS_ALL_GOODTOHAVE, vals)
        assert score <= 100.0
