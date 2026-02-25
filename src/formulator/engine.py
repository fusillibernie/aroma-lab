"""Core formula generation engine."""

from dataclasses import dataclass

from src.models import (
    Aromachemical,
    Formula,
    FormulaIngredient,
    NaturalProfile,
)
from src.matching.matcher import AromachemicalMatcher, MatchResult


@dataclass
class FormulationConfig:
    """Configuration for formula generation."""
    # Minimum peak area % to include in formula
    min_peak_percent: float = 0.1

    # Whether to include unidentified peaks as placeholders
    include_unknowns: bool = False

    # Maximum cost per kg (None = no limit)
    max_cost_per_kg: float | None = None

    # Prefer naturals over synthetics when available
    prefer_naturals: bool = False

    # IFRA compliance mode
    ifra_compliant: bool = True


class FormulatorEngine:
    """Generate aromatic formulas from GC-MS profiles."""

    def __init__(
        self,
        matcher: AromachemicalMatcher,
        config: FormulationConfig | None = None,
    ):
        self.matcher = matcher
        self.config = config or FormulationConfig()

    def formulate(
        self,
        profile: NaturalProfile,
        name: str | None = None,
    ) -> Formula:
        """Generate a formula to recreate a natural profile."""
        formula = Formula(
            name=name or f"{profile.name} Recreation",
            target_natural=profile,
        )

        # Filter peaks by minimum percentage
        significant_peaks = [
            p for p in profile.peaks
            if p.area_percent >= self.config.min_peak_percent
        ]

        # Match each peak to an aromachemical
        matches: list[MatchResult] = []
        for peak in significant_peaks:
            match = self.matcher.match_peak(peak)
            matches.append(match)

        # Build formula from matches
        total_matched_percent = 0.0
        unmatched_percent = 0.0

        for match in matches:
            if match.aromachemical:
                # Check IFRA compliance
                if self.config.ifra_compliant and match.aromachemical.ifra_restricted:
                    max_pct = match.aromachemical.max_usage_percent
                    if max_pct and match.peak.area_percent > max_pct:
                        # Try to find substitute
                        subs = self.matcher.find_substitutes(match.aromachemical)
                        if subs:
                            # Use best substitute
                            match.aromachemical = subs[0][0]
                            match.notes = f"Substituted due to IFRA restriction"

                formula.ingredients.append(FormulaIngredient(
                    aromachemical=match.aromachemical,
                    percentage=match.peak.area_percent,
                    notes=match.notes,
                ))
                total_matched_percent += match.peak.area_percent
            else:
                unmatched_percent += match.peak.area_percent

        # Calculate total cost
        total_cost = 0.0
        for ing in formula.ingredients:
            if ing.aromachemical.cost_per_kg_usd:
                total_cost += (ing.percentage / 100) * ing.aromachemical.cost_per_kg_usd
        formula.total_cost_per_kg = total_cost if total_cost > 0 else None

        # Calculate fidelity score (how much of the profile we matched)
        total_profile_percent = sum(p.area_percent for p in significant_peaks)
        if total_profile_percent > 0:
            formula.fidelity_score = (total_matched_percent / total_profile_percent) * 100

        # Add notes about unmatched compounds
        if unmatched_percent > 0:
            formula.notes = f"{unmatched_percent:.1f}% of profile could not be matched to available aromachemicals."

        return formula

    def optimize_cost(
        self,
        formula: Formula,
        target_cost: float,
    ) -> Formula:
        """Optimize formula to meet cost target while maintaining character.

        Strategy:
        1. Identify most expensive ingredients
        2. Find cheaper substitutes
        3. Reduce non-critical ingredients
        """
        # TODO: Implement cost optimization
        # This is a complex optimization problem that may require:
        # - Understanding which ingredients are "key" to the character
        # - Finding acceptable substitutes
        # - Balancing cost vs fidelity

        return formula

    def compare_formulas(
        self,
        formula_a: Formula,
        formula_b: Formula,
    ) -> dict:
        """Compare two formulas and highlight differences."""
        a_chemicals = {i.aromachemical.cas_number: i for i in formula_a.ingredients}
        b_chemicals = {i.aromachemical.cas_number: i for i in formula_b.ingredients}

        only_in_a = set(a_chemicals.keys()) - set(b_chemicals.keys())
        only_in_b = set(b_chemicals.keys()) - set(a_chemicals.keys())
        in_both = set(a_chemicals.keys()) & set(b_chemicals.keys())

        differences = []
        for cas in in_both:
            pct_diff = a_chemicals[cas].percentage - b_chemicals[cas].percentage
            if abs(pct_diff) > 0.5:  # Significant difference
                differences.append({
                    "compound": a_chemicals[cas].aromachemical.name,
                    "formula_a_pct": a_chemicals[cas].percentage,
                    "formula_b_pct": b_chemicals[cas].percentage,
                    "difference": pct_diff,
                })

        return {
            "only_in_a": [a_chemicals[cas].aromachemical.name for cas in only_in_a],
            "only_in_b": [b_chemicals[cas].aromachemical.name for cas in only_in_b],
            "percentage_differences": differences,
        }
