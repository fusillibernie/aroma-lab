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

        Scoring weights:
          - Odor family overlap: 0.25
          - Odor description keyword similarity: 0.15
          - Volatility match: 0.15
          - Boiling point proximity (±30°C): 0.15
          - Molecular weight proximity (±50 g/mol): 0.10
          - Natural co-occurrence: 0.10
          - Log P proximity (±2.0): 0.05
          - Not IFRA restricted (bonus): 0.05
        """
        # Pre-compute target odor keywords
        target_keywords = set()
        if target.odor_description:
            target_keywords = {
                w for w in target.odor_description.lower().split()
                if len(w) > 2  # Skip trivial words
            }

        target_sources = set(s.lower() for s in target.natural_occurrence) if target.natural_occurrence else set()

        candidates = []

        for ac in self._by_cas.values():
            if ac.cas_number == target.cas_number:
                continue

            score = 0.0

            # 1. Odor family overlap (0.25)
            if ac.odor_families and target.odor_families:
                common = set(ac.odor_families) & set(target.odor_families)
                score += 0.25 * (len(common) / len(target.odor_families))

            # 2. Odor description keyword similarity (0.15)
            if target_keywords and ac.odor_description:
                ac_keywords = {w for w in ac.odor_description.lower().split() if len(w) > 2}
                if ac_keywords:
                    union = target_keywords | ac_keywords
                    intersection = target_keywords & ac_keywords
                    score += 0.15 * (len(intersection) / len(union))

            # 3. Same volatility (0.15)
            if ac.volatility and target.volatility:
                if ac.volatility == target.volatility:
                    score += 0.15

            # 4. Similar boiling point within 30°C (0.15)
            if ac.boiling_point_c and target.boiling_point_c:
                bp_diff = abs(ac.boiling_point_c - target.boiling_point_c)
                if bp_diff < 30:
                    score += 0.15 * (1 - bp_diff / 30)

            # 5. Molecular weight proximity within 50 g/mol (0.10)
            if ac.molecular_weight and target.molecular_weight:
                mw_diff = abs(ac.molecular_weight - target.molecular_weight)
                if mw_diff < 50:
                    score += 0.10 * (1 - mw_diff / 50)

            # 6. Natural co-occurrence (0.10)
            if target_sources and ac.natural_occurrence:
                ac_sources = set(s.lower() for s in ac.natural_occurrence)
                shared_sources = target_sources & ac_sources
                if shared_sources:
                    all_sources = target_sources | ac_sources
                    score += 0.10 * (len(shared_sources) / len(all_sources))

            # 7. Log P proximity within 2.0 (0.05)
            if ac.log_p is not None and target.log_p is not None:
                lp_diff = abs(ac.log_p - target.log_p)
                if lp_diff < 2.0:
                    score += 0.05 * (1 - lp_diff / 2.0)

            # 8. Bonus: not IFRA restricted (0.05)
            if not ac.ifra_restricted:
                score += 0.05

            if score > 0.15:
                candidates.append((ac, score))

        # Sort by score descending
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[:max_results]
