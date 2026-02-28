"""Match GC-MS compounds to obtainable aromachemicals."""

import re
from dataclasses import dataclass, field

from src.models import Aromachemical, GCMSPeak


@dataclass
class MatchResult:
    """Result of matching a peak to an aromachemical."""
    peak: GCMSPeak
    aromachemical: Aromachemical | None
    match_type: str  # "exact", "fuzzy", "partial", "substitute", "unavailable"
    confidence: float
    notes: str = ""
    alternatives: list[Aromachemical] = field(default_factory=list)


def normalize_name(name: str) -> str:
    """Normalize compound name for fuzzy matching."""
    name = name.lower().strip()
    # Remove common prefixes
    for prefix in ["d-", "l-", "dl-", "(+)-", "(-)-", "(±)-", "(r)-", "(s)-",
                   "alpha-", "β-", "beta-", "γ-", "gamma-", "cis-", "trans-"]:
        if name.startswith(prefix):
            name = name[len(prefix):]
    # Remove trailing annotations
    name = re.sub(r'\s*\([^)]*\)\s*$', '', name)  # (CAS xxx), (natural), etc.
    name = re.sub(r'\s*#\d+\s*$', '', name)  # #1, #2
    name = re.sub(r',.*$', '', name)  # Take first part before comma
    name = re.sub(r'\s+', ' ', name).strip()
    return name


class AromachemicalMatcher:
    """Match identified compounds to obtainable aromachemicals."""

    def __init__(self, aromachemical_db: list[Aromachemical]):
        """Initialize with database of available aromachemicals."""
        self._by_cas: dict[str, Aromachemical] = {}
        self._by_name: dict[str, Aromachemical] = {}
        self._by_name_normalized: dict[str, Aromachemical] = {}
        self._all: list[Aromachemical] = list(aromachemical_db)

        for ac in aromachemical_db:
            self._by_cas[ac.cas_number] = ac
            self._by_name[ac.name.lower()] = ac
            self._by_name_normalized[normalize_name(ac.name)] = ac
            if ac.iupac_name:
                self._by_name[ac.iupac_name.lower()] = ac
                self._by_name_normalized[normalize_name(ac.iupac_name)] = ac

    def match_peak(self, peak: GCMSPeak) -> MatchResult:
        """Find the best aromachemical match for a peak."""
        # 1. Try exact CAS match
        if peak.cas_number and peak.cas_number in self._by_cas:
            return MatchResult(
                peak=peak,
                aromachemical=self._by_cas[peak.cas_number],
                match_type="exact",
                confidence=1.0,
            )

        # 2. Try exact name match
        if peak.compound_name:
            name_lower = peak.compound_name.lower()
            if name_lower in self._by_name:
                return MatchResult(
                    peak=peak,
                    aromachemical=self._by_name[name_lower],
                    match_type="exact",
                    confidence=0.95,
                )

            # 3. Try normalized name match (fuzzy)
            normalized = normalize_name(peak.compound_name)
            if normalized in self._by_name_normalized:
                return MatchResult(
                    peak=peak,
                    aromachemical=self._by_name_normalized[normalized],
                    match_type="fuzzy",
                    confidence=0.85,
                    notes=f"Matched normalized name: {normalized}",
                )

            # 4. Try partial match (substring)
            for db_name, ac in self._by_name_normalized.items():
                if len(normalized) > 4 and len(db_name) > 4:
                    if normalized in db_name or db_name in normalized:
                        return MatchResult(
                            peak=peak,
                            aromachemical=ac,
                            match_type="partial",
                            confidence=0.70,
                            notes=f"Partial match: {db_name}",
                        )

        # 5. Find alternatives by odor similarity
        alternatives = self._find_alternatives_by_odor(peak.compound_name)

        return MatchResult(
            peak=peak,
            aromachemical=None,
            match_type="unavailable",
            confidence=0.0,
            notes="No matching aromachemical found in database",
            alternatives=alternatives,
        )

    def _find_alternatives_by_odor(self, compound_name: str | None, max_results: int = 3) -> list[Aromachemical]:
        """Find potential alternatives based on compound name keywords."""
        if not compound_name:
            return []

        keywords = set(w.lower() for w in compound_name.split() if len(w) > 3)
        candidates = []

        for ac in self._all:
            if not ac.odor_description:
                continue
            odor_words = set(ac.odor_description.lower().split())
            overlap = keywords & odor_words
            if overlap:
                candidates.append((ac, len(overlap)))

        candidates.sort(key=lambda x: x[1], reverse=True)
        return [c[0] for c in candidates[:max_results]]

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
