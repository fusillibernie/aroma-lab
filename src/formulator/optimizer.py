"""Formula optimization algorithms for Aroma Lab.

Provides cost optimization, IFRA compliance, volatility balancing,
and longevity/sillage estimation.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import math

from src.models import (
    Aromachemical,
    Formula,
    FormulaIngredient,
    Volatility,
    OdorFamily,
)


class ApplicationType(Enum):
    """Product application types with different requirements."""
    FINE_FRAGRANCE = "fine_fragrance"
    EAU_DE_TOILETTE = "eau_de_toilette"
    EAU_DE_COLOGNE = "eau_de_cologne"
    BODY_LOTION = "body_lotion"
    SHAMPOO = "shampoo"
    SOAP = "soap"
    CANDLE = "candle"
    HOME_CARE = "home_care"
    AIR_FRESHENER = "air_freshener"


@dataclass
class OptimizationResult:
    """Result of formula optimization."""
    original_formula: Formula
    optimized_formula: Formula
    cost_reduction_percent: float
    fidelity_change: float
    changes_made: list[str]
    warnings: list[str]


@dataclass
class VolatilityAnalysis:
    """Analysis of formula volatility distribution."""
    top_note_percent: float
    heart_note_percent: float
    base_note_percent: float
    balance_score: float  # 0-100, higher is better balanced
    recommendations: list[str]


@dataclass
class LongevityEstimate:
    """Estimated performance characteristics."""
    initial_impact: float  # 0-10 scale
    longevity_hours: float  # estimated duration
    sillage_rating: float  # 0-10 scale (projection)
    dry_down_quality: float  # 0-10 scale
    notes: list[str]


# IFRA category limits by application type
IFRA_CATEGORY_LIMITS = {
    ApplicationType.FINE_FRAGRANCE: 1,  # Category 4
    ApplicationType.EAU_DE_TOILETTE: 1,
    ApplicationType.EAU_DE_COLOGNE: 1,
    ApplicationType.BODY_LOTION: 2,  # Category 5
    ApplicationType.SHAMPOO: 3,  # Category 9
    ApplicationType.SOAP: 3,
    ApplicationType.CANDLE: 4,  # Category 10
    ApplicationType.HOME_CARE: 4,
    ApplicationType.AIR_FRESHENER: 4,
}


class FormulaOptimizer:
    """Optimize fragrance formulas for cost, compliance, and performance."""

    def __init__(self, aromachemical_db: list[Aromachemical]):
        """Initialize with available aromachemicals."""
        self.db = {ac.cas_number: ac for ac in aromachemical_db}
        self._build_substitution_map()

    def _build_substitution_map(self) -> None:
        """Build map of potential substitutions based on odor profiles."""
        self.substitutes: dict[str, list[tuple[Aromachemical, float]]] = {}

        for cas, ac in self.db.items():
            similar = []
            for other_cas, other_ac in self.db.items():
                if cas == other_cas:
                    continue

                similarity = self._calculate_similarity(ac, other_ac)
                if similarity > 0.6:  # 60% similarity threshold
                    similar.append((other_ac, similarity))

            # Sort by similarity descending
            similar.sort(key=lambda x: x[1], reverse=True)
            self.substitutes[cas] = similar[:5]  # Keep top 5 substitutes

    def _calculate_similarity(self, a: Aromachemical, b: Aromachemical) -> float:
        """Calculate similarity score between two aromachemicals (0-1)."""
        score = 0.0
        factors = 0

        # Same volatility is important
        if a.volatility and b.volatility and a.volatility == b.volatility:
            score += 0.3
        factors += 0.3

        # Odor family overlap
        if a.odor_families and b.odor_families:
            a_families = set(a.odor_families)
            b_families = set(b.odor_families)
            overlap = len(a_families & b_families) / max(len(a_families | b_families), 1)
            score += 0.4 * overlap
        factors += 0.4

        # Boiling point similarity (within 30C = good match)
        if a.boiling_point_c and b.boiling_point_c:
            bp_diff = abs(a.boiling_point_c - b.boiling_point_c)
            if bp_diff <= 30:
                score += 0.2 * (1 - bp_diff / 30)
        factors += 0.2

        # Molecular weight similarity
        if a.molecular_weight and b.molecular_weight:
            mw_diff = abs(a.molecular_weight - b.molecular_weight)
            if mw_diff <= 50:
                score += 0.1 * (1 - mw_diff / 50)
        factors += 0.1

        return score / factors if factors > 0 else 0

    def optimize_cost(
        self,
        formula: Formula,
        target_cost: float,
        min_fidelity: float = 80.0,
    ) -> OptimizationResult:
        """Optimize formula to meet cost target while maintaining character.

        Args:
            formula: Original formula to optimize
            target_cost: Target cost per kg in USD
            min_fidelity: Minimum acceptable fidelity score (0-100)

        Returns:
            OptimizationResult with optimized formula and changes
        """
        changes = []
        warnings = []

        # Calculate current cost
        current_cost = self._calculate_cost(formula)
        if current_cost is None:
            warnings.append("Unable to calculate cost - missing price data")
            return OptimizationResult(
                original_formula=formula,
                optimized_formula=formula,
                cost_reduction_percent=0,
                fidelity_change=0,
                changes_made=changes,
                warnings=warnings,
            )

        if current_cost <= target_cost:
            return OptimizationResult(
                original_formula=formula,
                optimized_formula=formula,
                cost_reduction_percent=0,
                fidelity_change=0,
                changes_made=["Formula already meets cost target"],
                warnings=warnings,
            )

        # Create copy of formula
        optimized = Formula(
            name=f"{formula.name} (Optimized)",
            target_natural=formula.target_natural,
            ingredients=[
                FormulaIngredient(
                    aromachemical=ing.aromachemical,
                    percentage=ing.percentage,
                    notes=ing.notes,
                )
                for ing in formula.ingredients
            ],
            version=str(float(formula.version) + 0.1),
        )

        # Sort ingredients by cost impact (cost * percentage)
        sorted_ingredients = sorted(
            enumerate(optimized.ingredients),
            key=lambda x: (
                (x[1].aromachemical.cost_per_kg_usd or 0) * x[1].percentage
            ),
            reverse=True,
        )

        # Try substituting expensive ingredients
        for idx, ing in sorted_ingredients:
            if self._calculate_cost(optimized) <= target_cost:
                break

            cas = ing.aromachemical.cas_number
            subs = self.substitutes.get(cas, [])

            for sub_ac, similarity in subs:
                # Check if substitute is cheaper
                if (
                    sub_ac.cost_per_kg_usd
                    and ing.aromachemical.cost_per_kg_usd
                    and sub_ac.cost_per_kg_usd < ing.aromachemical.cost_per_kg_usd
                ):
                    # Calculate fidelity impact
                    fidelity_impact = (1 - similarity) * 100 * (ing.percentage / 100)

                    if fidelity_impact <= (100 - min_fidelity):
                        old_name = ing.aromachemical.name
                        old_cost = ing.aromachemical.cost_per_kg_usd

                        optimized.ingredients[idx] = FormulaIngredient(
                            aromachemical=sub_ac,
                            percentage=ing.percentage,
                            notes=f"Substituted from {old_name} for cost",
                        )

                        changes.append(
                            f"Replaced {old_name} (${old_cost}/kg) with "
                            f"{sub_ac.name} (${sub_ac.cost_per_kg_usd}/kg)"
                        )
                        break

        # Calculate results
        new_cost = self._calculate_cost(optimized) or current_cost
        cost_reduction = ((current_cost - new_cost) / current_cost) * 100

        optimized.total_cost_per_kg = new_cost
        original_fidelity = formula.fidelity_score or 100
        # Estimate new fidelity based on changes
        fidelity_change = -len(changes) * 2  # Rough estimate

        return OptimizationResult(
            original_formula=formula,
            optimized_formula=optimized,
            cost_reduction_percent=cost_reduction,
            fidelity_change=fidelity_change,
            changes_made=changes,
            warnings=warnings,
        )

    def _calculate_cost(self, formula: Formula) -> Optional[float]:
        """Calculate total cost per kg for a formula."""
        total = 0.0
        has_prices = False

        for ing in formula.ingredients:
            if ing.aromachemical.cost_per_kg_usd:
                total += (ing.percentage / 100) * ing.aromachemical.cost_per_kg_usd
                has_prices = True

        return total if has_prices else None

    def check_ifra_compliance(
        self,
        formula: Formula,
        application: ApplicationType = ApplicationType.FINE_FRAGRANCE,
    ) -> tuple[bool, list[str], Formula]:
        """Check IFRA compliance and auto-adjust if needed.

        Args:
            formula: Formula to check
            application: Product application type

        Returns:
            Tuple of (is_compliant, issues, adjusted_formula)
        """
        issues = []
        adjustments_needed = []

        # Create copy for adjustments
        adjusted = Formula(
            name=formula.name,
            target_natural=formula.target_natural,
            ingredients=list(formula.ingredients),
            version=formula.version,
            notes=formula.notes,
        )

        for i, ing in enumerate(adjusted.ingredients):
            ac = ing.aromachemical

            if ac.ifra_restricted and ac.max_usage_percent is not None:
                # Apply application-specific factor
                category_factor = IFRA_CATEGORY_LIMITS.get(application, 1)
                adjusted_limit = ac.max_usage_percent * category_factor

                if ing.percentage > adjusted_limit:
                    issues.append(
                        f"{ac.name} at {ing.percentage:.2f}% exceeds IFRA limit "
                        f"of {adjusted_limit:.2f}% for {application.value}"
                    )
                    adjustments_needed.append((i, adjusted_limit))

        # Apply adjustments
        for idx, new_pct in adjustments_needed:
            old_pct = adjusted.ingredients[idx].percentage
            adjusted.ingredients[idx] = FormulaIngredient(
                aromachemical=adjusted.ingredients[idx].aromachemical,
                percentage=new_pct,
                notes=f"Reduced from {old_pct:.2f}% for IFRA compliance",
            )

        is_compliant = len(issues) == 0

        return is_compliant, issues, adjusted

    def analyze_volatility(self, formula: Formula) -> VolatilityAnalysis:
        """Analyze the volatility distribution of a formula.

        Returns analysis with recommendations for balance.
        """
        top = 0.0
        heart = 0.0
        base = 0.0

        for ing in formula.ingredients:
            vol = ing.aromachemical.volatility
            if vol == Volatility.TOP:
                top += ing.percentage
            elif vol == Volatility.HEART:
                heart += ing.percentage
            elif vol == Volatility.BASE:
                base += ing.percentage

        total = top + heart + base

        # Normalize
        if total > 0:
            top_pct = (top / total) * 100
            heart_pct = (heart / total) * 100
            base_pct = (base / total) * 100
        else:
            top_pct = heart_pct = base_pct = 0

        # Ideal balance varies by fragrance type, but roughly:
        # Fine fragrance: 15-25% top, 30-40% heart, 40-50% base
        # Fresh/citrus: 30-40% top, 35-45% heart, 20-30% base

        recommendations = []
        balance_score = 100.0

        # Check for imbalances
        if top_pct > 40:
            recommendations.append(
                f"High top note content ({top_pct:.1f}%) may result in "
                "poor longevity. Consider reducing citrus/light notes."
            )
            balance_score -= 15

        if top_pct < 10:
            recommendations.append(
                f"Low top note content ({top_pct:.1f}%) may result in "
                "weak initial impact. Consider adding fresh/citrus notes."
            )
            balance_score -= 10

        if heart_pct < 20:
            recommendations.append(
                f"Low heart note content ({heart_pct:.1f}%) may result in "
                "a hollow composition. Consider adding floral/spicy notes."
            )
            balance_score -= 15

        if base_pct < 25:
            recommendations.append(
                f"Low base note content ({base_pct:.1f}%) may result in "
                "poor longevity. Consider adding woody/amber/musk notes."
            )
            balance_score -= 15

        if base_pct > 65:
            recommendations.append(
                f"Very high base note content ({base_pct:.1f}%) may result in "
                "slow development and heavy feel."
            )
            balance_score -= 10

        balance_score = max(0, balance_score)

        return VolatilityAnalysis(
            top_note_percent=top_pct,
            heart_note_percent=heart_pct,
            base_note_percent=base_pct,
            balance_score=balance_score,
            recommendations=recommendations,
        )

    def estimate_longevity(self, formula: Formula) -> LongevityEstimate:
        """Estimate longevity and sillage based on vapor pressure and composition.

        Uses vapor pressure data and volatility classes to estimate performance.
        """
        notes = []

        # Calculate weighted average properties
        total_pct = 0.0
        weighted_bp = 0.0
        weighted_vp = 0.0
        high_impact_pct = 0.0
        base_note_pct = 0.0

        for ing in formula.ingredients:
            ac = ing.aromachemical
            pct = ing.percentage
            total_pct += pct

            if ac.boiling_point_c:
                weighted_bp += ac.boiling_point_c * pct

            if ac.vapor_pressure_mmhg:
                weighted_vp += ac.vapor_pressure_mmhg * pct

            # High-impact materials (musks, ambers, certain florals)
            if ac.volatility == Volatility.BASE:
                base_note_pct += pct
                if OdorFamily.MUSK in ac.odor_families or OdorFamily.AMBER in ac.odor_families:
                    high_impact_pct += pct

            # Low odor threshold = high impact
            if ac.odor_threshold_ppm and ac.odor_threshold_ppm < 0.1:
                high_impact_pct += pct * 0.5

        if total_pct > 0:
            weighted_bp /= total_pct
            weighted_vp /= total_pct

        # Estimate initial impact (0-10)
        # Based on top note content and high-impact materials
        volatility_analysis = self.analyze_volatility(formula)
        initial_impact = min(10, 5 + volatility_analysis.top_note_percent / 10)

        # Estimate longevity (hours)
        # Based on base note content and boiling points
        if weighted_bp > 0:
            # Higher BP = longer lasting
            longevity_base = 2 + (weighted_bp - 200) / 30  # hours
        else:
            longevity_base = 4  # default

        longevity_hours = longevity_base + (base_note_pct / 20)
        longevity_hours = max(2, min(12, longevity_hours))

        # Estimate sillage (0-10)
        # Based on vapor pressure and high-impact materials
        if weighted_vp > 0:
            sillage_base = 5 + math.log10(weighted_vp + 1)
        else:
            sillage_base = 5

        sillage_rating = min(10, sillage_base + high_impact_pct / 10)

        # Estimate dry-down quality (0-10)
        # Based on base note quality and balance
        dry_down = min(10, 5 + base_note_pct / 15 + volatility_analysis.balance_score / 20)

        # Add notes
        if longevity_hours < 4:
            notes.append("Short-lived formula - consider adding fixatives or base notes")
        elif longevity_hours > 8:
            notes.append("Long-lasting formula with good tenacity")

        if sillage_rating > 7:
            notes.append("Strong projection - may be overwhelming in close quarters")
        elif sillage_rating < 4:
            notes.append("Intimate sillage - best for personal wear")

        if high_impact_pct > 30:
            notes.append("High concentration of impactful materials - rich character")

        return LongevityEstimate(
            initial_impact=round(initial_impact, 1),
            longevity_hours=round(longevity_hours, 1),
            sillage_rating=round(sillage_rating, 1),
            dry_down_quality=round(dry_down, 1),
            notes=notes,
        )

    def suggest_modifications(
        self,
        formula: Formula,
        application: ApplicationType,
    ) -> list[str]:
        """Suggest modifications based on target application.

        Args:
            formula: Current formula
            application: Target product type

        Returns:
            List of suggestions
        """
        suggestions = []
        vol_analysis = self.analyze_volatility(formula)
        longevity = self.estimate_longevity(formula)

        if application in [
            ApplicationType.FINE_FRAGRANCE,
            ApplicationType.EAU_DE_TOILETTE,
        ]:
            if longevity.longevity_hours < 6:
                suggestions.append(
                    "For fine fragrance, consider increasing base notes "
                    "(musks, ambers, woods) to improve longevity"
                )
            if vol_analysis.balance_score < 70:
                suggestions.append(
                    "Balance could be improved - aim for ~20% top, ~35% heart, ~45% base"
                )

        elif application == ApplicationType.EAU_DE_COLOGNE:
            if vol_analysis.top_note_percent < 30:
                suggestions.append(
                    "Eau de Cologne typically features 30-40% top notes "
                    "(citrus, aromatic herbs)"
                )

        elif application in [ApplicationType.SOAP, ApplicationType.SHAMPOO]:
            suggestions.append(
                "Rinse-off products need higher fragrance impact - "
                "consider strong top notes and substantive bases"
            )
            if longevity.initial_impact < 6:
                suggestions.append(
                    "Increase high-impact materials for better perception during use"
                )

        elif application in [ApplicationType.CANDLE, ApplicationType.HOME_CARE]:
            if vol_analysis.top_note_percent > 30:
                suggestions.append(
                    "Reduce volatile top notes - they evaporate quickly "
                    "when heated/diffused"
                )
            suggestions.append(
                "Focus on heart and base notes with good diffusion "
                "(florals, woods, musks)"
            )

        elif application == ApplicationType.AIR_FRESHENER:
            suggestions.append(
                "Prioritize high-vapor-pressure materials for good diffusion"
            )
            if longevity.sillage_rating < 5:
                suggestions.append(
                    "Consider adding materials with good throw "
                    "(citrus, eucalyptus, pine)"
                )

        # Check IFRA compliance
        is_compliant, issues, _ = self.check_ifra_compliance(formula, application)
        if not is_compliant:
            suggestions.append(
                f"IFRA compliance issues found for {application.value}: "
                f"{len(issues)} materials need adjustment"
            )

        return suggestions
