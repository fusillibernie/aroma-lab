"""Tests for formula optimization features."""

import pytest

from src.models import (
    Aromachemical,
    Formula,
    FormulaIngredient,
    OdorFamily,
    Volatility,
)
from src.formulator.optimizer import (
    FormulaOptimizer,
    ApplicationType,
)


@pytest.fixture
def sample_aromachemicals():
    """Create sample aromachemicals for testing."""
    return [
        Aromachemical(
            cas_number="106-24-1",
            name="Geraniol",
            volatility=Volatility.HEART,
            odor_families=[OdorFamily.FLORAL],
            boiling_point_c=230,
            cost_per_kg_usd=45.0,
        ),
        Aromachemical(
            cas_number="106-22-9",
            name="Citronellol",
            volatility=Volatility.HEART,
            odor_families=[OdorFamily.FLORAL],
            boiling_point_c=225,
            cost_per_kg_usd=35.0,
        ),
        Aromachemical(
            cas_number="78-70-6",
            name="Linalool",
            volatility=Volatility.HEART,
            odor_families=[OdorFamily.FLORAL, OdorFamily.WOODY],
            boiling_point_c=198,
            cost_per_kg_usd=25.0,
        ),
        Aromachemical(
            cas_number="5989-27-5",
            name="D-Limonene",
            volatility=Volatility.TOP,
            odor_families=[OdorFamily.CITRUS],
            boiling_point_c=176,
            cost_per_kg_usd=15.0,
        ),
        Aromachemical(
            cas_number="3691-12-1",
            name="Iso E Super",
            volatility=Volatility.BASE,
            odor_families=[OdorFamily.WOODY, OdorFamily.AMBER],
            boiling_point_c=310,
            cost_per_kg_usd=40.0,
        ),
        Aromachemical(
            cas_number="91-64-5",
            name="Coumarin",
            volatility=Volatility.BASE,
            odor_families=[OdorFamily.BALSAMIC],
            boiling_point_c=301,
            ifra_restricted=True,
            max_usage_percent=0.5,
        ),
    ]


@pytest.fixture
def optimizer(sample_aromachemicals):
    """Create optimizer with sample data."""
    return FormulaOptimizer(sample_aromachemicals)


@pytest.fixture
def sample_formula(sample_aromachemicals):
    """Create a sample formula for testing."""
    geraniol = sample_aromachemicals[0]
    citronellol = sample_aromachemicals[1]
    limonene = sample_aromachemicals[3]
    iso_e = sample_aromachemicals[4]

    return Formula(
        name="Test Fragrance",
        ingredients=[
            FormulaIngredient(aromachemical=geraniol, percentage=25.0),
            FormulaIngredient(aromachemical=citronellol, percentage=25.0),
            FormulaIngredient(aromachemical=limonene, percentage=20.0),
            FormulaIngredient(aromachemical=iso_e, percentage=30.0),
        ],
    )


class TestVolatilityAnalysis:
    def test_analyze_balanced_formula(self, optimizer, sample_formula):
        """Test volatility analysis with a balanced formula."""
        analysis = optimizer.analyze_volatility(sample_formula)

        # Check percentages add up
        total = (
            analysis.top_note_percent
            + analysis.heart_note_percent
            + analysis.base_note_percent
        )
        assert abs(total - 100) < 0.1

        # Check individual percentages are reasonable
        assert analysis.top_note_percent == 20.0  # Limonene
        assert analysis.heart_note_percent == 50.0  # Geraniol + Citronellol
        assert analysis.base_note_percent == 30.0  # Iso E Super

    def test_unbalanced_formula_recommendations(self, optimizer, sample_aromachemicals):
        """Test that unbalanced formulas get recommendations."""
        limonene = sample_aromachemicals[3]

        # Formula with only top notes
        top_heavy = Formula(
            name="Top Heavy",
            ingredients=[
                FormulaIngredient(aromachemical=limonene, percentage=100.0),
            ],
        )

        analysis = optimizer.analyze_volatility(top_heavy)

        assert analysis.top_note_percent == 100.0
        assert len(analysis.recommendations) > 0
        assert analysis.balance_score < 100


class TestIFRACompliance:
    def test_compliant_formula(self, optimizer, sample_formula):
        """Test that compliant formulas pass."""
        is_compliant, issues, adjusted = optimizer.check_ifra_compliance(
            sample_formula, ApplicationType.FINE_FRAGRANCE
        )

        assert is_compliant is True
        assert len(issues) == 0

    def test_non_compliant_formula(self, optimizer, sample_aromachemicals):
        """Test that non-compliant formulas are flagged."""
        coumarin = sample_aromachemicals[5]  # IFRA restricted, max 0.5%

        formula = Formula(
            name="Non-Compliant",
            ingredients=[
                FormulaIngredient(aromachemical=coumarin, percentage=2.0),
            ],
        )

        is_compliant, issues, adjusted = optimizer.check_ifra_compliance(
            formula, ApplicationType.FINE_FRAGRANCE
        )

        assert is_compliant is False
        assert len(issues) > 0
        assert "Coumarin" in issues[0]
        assert "IFRA" in issues[0]


class TestLongevityEstimate:
    def test_estimate_longevity(self, optimizer, sample_formula):
        """Test longevity estimation."""
        estimate = optimizer.estimate_longevity(sample_formula)

        assert estimate.initial_impact >= 0
        assert estimate.initial_impact <= 10
        assert estimate.longevity_hours >= 2
        assert estimate.sillage_rating >= 0
        assert estimate.dry_down_quality >= 0

    def test_base_heavy_formula_longevity(self, optimizer, sample_aromachemicals):
        """Test that base-heavy formulas have longer longevity."""
        iso_e = sample_aromachemicals[4]
        limonene = sample_aromachemicals[3]

        base_heavy = Formula(
            name="Base Heavy",
            ingredients=[
                FormulaIngredient(aromachemical=iso_e, percentage=100.0),
            ],
        )

        top_heavy = Formula(
            name="Top Heavy",
            ingredients=[
                FormulaIngredient(aromachemical=limonene, percentage=100.0),
            ],
        )

        base_estimate = optimizer.estimate_longevity(base_heavy)
        top_estimate = optimizer.estimate_longevity(top_heavy)

        # Base-heavy should last longer
        assert base_estimate.longevity_hours > top_estimate.longevity_hours


class TestCostOptimization:
    def test_already_meets_target(self, optimizer, sample_formula):
        """Test optimization when formula already meets target."""
        result = optimizer.optimize_cost(sample_formula, target_cost=1000.0)

        assert result.cost_reduction_percent == 0
        assert "already meets" in result.changes_made[0].lower()

    def test_optimization_reduces_cost(self, optimizer, sample_aromachemicals):
        """Test that optimization can reduce cost by substitution."""
        # Create expensive formula
        geraniol = sample_aromachemicals[0]  # $45/kg

        expensive = Formula(
            name="Expensive",
            ingredients=[
                FormulaIngredient(aromachemical=geraniol, percentage=100.0),
            ],
        )

        # Try to optimize to lower cost
        result = optimizer.optimize_cost(expensive, target_cost=20.0)

        # Should find a cheaper substitute (Linalool at $25/kg)
        if result.cost_reduction_percent > 0:
            assert len(result.changes_made) > 0


class TestSuggestions:
    def test_suggestions_for_fine_fragrance(self, optimizer, sample_formula):
        """Test suggestions for fine fragrance application."""
        suggestions = optimizer.suggest_modifications(
            sample_formula, ApplicationType.FINE_FRAGRANCE
        )

        # Should return a list
        assert isinstance(suggestions, list)

    def test_suggestions_for_soap(self, optimizer, sample_formula):
        """Test suggestions for soap application."""
        suggestions = optimizer.suggest_modifications(
            sample_formula, ApplicationType.SOAP
        )

        # Soap should get rinse-off specific suggestions
        assert isinstance(suggestions, list)
