"""Match GC-MS compounds to obtainable aromachemicals."""

from dataclasses import dataclass

from src.models import Aromachemical, GCMSPeak


@dataclass
class MatchResult:
    """Result of matching a peak to an aromachemical."""
    peak: GCMSPeak
    aromachemical: Aromachemical | None
    match_type: str  # "exact", "substitute", "unavailable"
    confidence: float
    notes: str = ""
    alternatives: list[Aromachemical] | None = None


class AromachemicalMatcher:
    """Match identified compounds to obtainable aromachemicals."""

    def __init__(self, aromachemical_db: list[Aromachemical]):
        """Initialize with database of available aromachemicals."""
        self._by_cas: dict[str, Aromachemical] = {}
        self._by_name: dict[str, Aromachemical] = {}

        for ac in aromachemical_db:
            self._by_cas[ac.cas_number] = ac
            self._by_name[ac.name.lower()] = ac
            if ac.iupac_name:
                self._by_name[ac.iupac_name.lower()] = ac

    def match_peak(self, peak: GCMSPeak) -> MatchResult:
        """Find the best aromachemical match for a peak."""
        # Try exact CAS match
        if peak.cas_number and peak.cas_number in self._by_cas:
            return MatchResult(
                peak=peak,
                aromachemical=self._by_cas[peak.cas_number],
                match_type="exact",
                confidence=1.0,
            )

        # Try name match
        if peak.compound_name:
            name_lower = peak.compound_name.lower()
            if name_lower in self._by_name:
                return MatchResult(
                    peak=peak,
                    aromachemical=self._by_name[name_lower],
                    match_type="exact",
                    confidence=0.95,
                )

        # TODO: Implement substitution logic
        # - Find similar compounds by structure
        # - Find similar compounds by odor profile
        # - Find similar compounds by functional group

        return MatchResult(
            peak=peak,
            aromachemical=None,
            match_type="unavailable",
            confidence=0.0,
            notes="No matching aromachemical found in database",
        )

    def find_substitutes(
        self,
        target: Aromachemical,
        max_results: int = 5,
    ) -> list[tuple[Aromachemical, float]]:
        """Find potential substitutes for an aromachemical.

        Returns list of (aromachemical, similarity_score) tuples.
        """
        # TODO: Implement substitution algorithm based on:
        # 1. Same odor family
        # 2. Similar volatility
        # 3. Similar molecular structure
        # 4. Literature-documented substitutions

        candidates = []

        for ac in self._by_cas.values():
            if ac.cas_number == target.cas_number:
                continue

            score = 0.0

            # Same odor families
            if ac.odor_families and target.odor_families:
                common = set(ac.odor_families) & set(target.odor_families)
                score += 0.3 * (len(common) / len(target.odor_families))

            # Same volatility
            if ac.volatility == target.volatility:
                score += 0.2

            # Similar boiling point (within 20°C)
            if ac.boiling_point_c and target.boiling_point_c:
                bp_diff = abs(ac.boiling_point_c - target.boiling_point_c)
                if bp_diff < 20:
                    score += 0.2 * (1 - bp_diff / 20)

            if score > 0.1:
                candidates.append((ac, score))

        # Sort by score descending
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[:max_results]
