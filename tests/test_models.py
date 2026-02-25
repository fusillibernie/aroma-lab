"""Tests for core data models."""

import pytest

from src.models import (
    Aromachemical,
    Formula,
    FormulaIngredient,
    OdorFamily,
    Volatility,
)


class TestAromachemical:
    def test_basic_creation(self):
        ac = Aromachemical(
            cas_number="106-24-1",
            name="Geraniol",
            odor_description="Sweet, floral, rose-like",
        )
        assert ac.cas_number == "106-24-1"
        assert ac.name == "Geraniol"
        assert ac.ifra_restricted is False

    def test_with_all_fields(self):
        ac = Aromachemical(
            cas_number="106-24-1",
            name="Geraniol",
            iupac_name="(2E)-3,7-dimethylocta-2,6-dien-1-ol",
            molecular_formula="C10H18O",
            molecular_weight=154.25,
            odor_description="Sweet, floral, rose-like",
            odor_families=[OdorFamily.FLORAL],
            volatility=Volatility.HEART,
            boiling_point_c=230,
            cost_per_kg_usd=45.0,
            suppliers=["Sigma", "TCI"],
        )
        assert ac.volatility == Volatility.HEART
        assert OdorFamily.FLORAL in ac.odor_families


class TestFormula:
    def test_total_percentage(self):
        geraniol = Aromachemical(cas_number="106-24-1", name="Geraniol")
        citronellol = Aromachemical(cas_number="106-22-9", name="Citronellol")

        formula = Formula(
            name="Test Rose",
            ingredients=[
                FormulaIngredient(aromachemical=geraniol, percentage=30.0),
                FormulaIngredient(aromachemical=citronellol, percentage=70.0),
            ],
        )

        assert formula.total_percentage == 100.0

    def test_validation_correct_total(self):
        geraniol = Aromachemical(cas_number="106-24-1", name="Geraniol")
        formula = Formula(
            name="Test",
            ingredients=[
                FormulaIngredient(aromachemical=geraniol, percentage=100.0),
            ],
        )
        issues = formula.validate()
        assert len(issues) == 0

    def test_validation_wrong_total(self):
        geraniol = Aromachemical(cas_number="106-24-1", name="Geraniol")
        formula = Formula(
            name="Test",
            ingredients=[
                FormulaIngredient(aromachemical=geraniol, percentage=50.0),
            ],
        )
        issues = formula.validate()
        assert len(issues) == 1
        assert "50.00%" in issues[0]

    def test_validation_ifra_restriction(self):
        restricted = Aromachemical(
            cas_number="101-39-3",
            name="Methylcinnamaldehyde",
            ifra_restricted=True,
            max_usage_percent=0.5,
        )

        formula = Formula(
            name="Test",
            ingredients=[
                FormulaIngredient(aromachemical=restricted, percentage=2.0),
            ],
        )

        issues = formula.validate()
        assert any("IFRA" in issue for issue in issues)
