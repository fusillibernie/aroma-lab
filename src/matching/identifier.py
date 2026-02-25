"""Compound identification from GC-MS peaks."""

from dataclasses import dataclass

import pubchempy as pcp

from src.models import GCMSPeak


@dataclass
class IdentificationResult:
    """Result of compound identification."""
    cas_number: str | None
    compound_name: str
    confidence: float  # 0-1
    source: str  # e.g., "pubchem", "nist", "library_match"
    synonyms: list[str]


class CompoundIdentifier:
    """Identify compounds from GC-MS peak data."""

    def __init__(self):
        self._cache: dict[str, IdentificationResult] = {}

    def identify_by_name(self, name: str) -> IdentificationResult | None:
        """Look up compound by name using PubChem."""
        if name in self._cache:
            return self._cache[name]

        try:
            compounds = pcp.get_compounds(name, "name")
            if not compounds:
                return None

            compound = compounds[0]

            # Extract CAS from synonyms if available
            cas = None
            synonyms = compound.synonyms or []
            for syn in synonyms:
                if self._is_cas_number(syn):
                    cas = syn
                    break

            result = IdentificationResult(
                cas_number=cas,
                compound_name=compound.iupac_name or name,
                confidence=0.9 if compound.iupac_name else 0.7,
                source="pubchem",
                synonyms=synonyms[:10],  # Limit synonyms
            )

            self._cache[name] = result
            return result

        except Exception:
            return None

    def identify_by_cas(self, cas: str) -> IdentificationResult | None:
        """Look up compound by CAS number."""
        if cas in self._cache:
            return self._cache[cas]

        try:
            compounds = pcp.get_compounds(cas, "name")  # CAS works as name search
            if not compounds:
                return None

            compound = compounds[0]
            result = IdentificationResult(
                cas_number=cas,
                compound_name=compound.iupac_name or cas,
                confidence=0.95,
                source="pubchem",
                synonyms=compound.synonyms[:10] if compound.synonyms else [],
            )

            self._cache[cas] = result
            return result

        except Exception:
            return None

    def identify_peak(self, peak: GCMSPeak) -> IdentificationResult | None:
        """Attempt to identify a GC-MS peak."""
        # Try CAS first (most reliable)
        if peak.cas_number:
            result = self.identify_by_cas(peak.cas_number)
            if result:
                return result

        # Fall back to name
        if peak.compound_name:
            return self.identify_by_name(peak.compound_name)

        return None

    @staticmethod
    def _is_cas_number(s: str) -> bool:
        """Check if string looks like a CAS number (XXXXXXX-XX-X format)."""
        parts = s.split("-")
        if len(parts) != 3:
            return False
        try:
            return (
                len(parts[0]) >= 2 and parts[0].isdigit() and
                len(parts[1]) == 2 and parts[1].isdigit() and
                len(parts[2]) == 1 and parts[2].isdigit()
            )
        except Exception:
            return False
