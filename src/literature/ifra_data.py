"""IFRA (International Fragrance Association) restriction data.

This module provides data structures and functions for working with
IFRA restriction levels, including maximum usage percentages by
product category for regulated fragrance materials.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from .data_models import IFRACategory, IFRARestriction, RestrictionType

logger = logging.getLogger(__name__)

# Default data file location
DEFAULT_IFRA_DATA_FILE = Path(__file__).parent.parent.parent / "data" / "literature" / "ifra_restrictions.json"


class IFRADatabase:
    """Database of IFRA restrictions for fragrance materials.

    Provides lookup functionality for material restrictions by
    CAS number or name, including category-specific usage limits.
    """

    def __init__(self, data_file: Optional[Path] = None):
        """Initialize the IFRA database.

        Args:
            data_file: Path to JSON file with IFRA data.
                      Defaults to data/literature/ifra_restrictions.json
        """
        self.data_file = data_file or DEFAULT_IFRA_DATA_FILE
        self._restrictions: dict[str, IFRARestriction] = {}
        self._name_index: dict[str, str] = {}  # name -> CAS
        self._loaded = False

    def load(self) -> None:
        """Load IFRA data from the JSON file."""
        if not self.data_file.exists():
            logger.warning(f"IFRA data file not found: {self.data_file}")
            return

        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            restrictions_list = data.get("restrictions", [])
            for item in restrictions_list:
                restriction = IFRARestriction.from_dict(item)
                self._restrictions[restriction.cas_number] = restriction
                # Index by name (lowercase for case-insensitive lookup)
                self._name_index[restriction.name.lower()] = restriction.cas_number

            self._loaded = True
            logger.info(f"Loaded {len(self._restrictions)} IFRA restrictions")

        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load IFRA data: {e}")
            raise

    def _ensure_loaded(self) -> None:
        """Ensure data is loaded before queries."""
        if not self._loaded:
            self.load()

    def get_by_cas(self, cas_number: str) -> Optional[IFRARestriction]:
        """Get IFRA restriction by CAS number.

        Args:
            cas_number: CAS registry number.

        Returns:
            IFRARestriction if material is restricted, None otherwise.
        """
        self._ensure_loaded()
        return self._restrictions.get(cas_number)

    def get_by_name(self, name: str) -> Optional[IFRARestriction]:
        """Get IFRA restriction by material name.

        Args:
            name: Material name (case-insensitive).

        Returns:
            IFRARestriction if material is restricted, None otherwise.
        """
        self._ensure_loaded()
        cas_number = self._name_index.get(name.lower())
        if cas_number:
            return self._restrictions.get(cas_number)
        return None

    def is_restricted(self, cas_number: str) -> bool:
        """Check if a material is IFRA restricted.

        Args:
            cas_number: CAS registry number.

        Returns:
            True if material has any IFRA restriction.
        """
        self._ensure_loaded()
        return cas_number in self._restrictions

    def is_prohibited(self, cas_number: str) -> bool:
        """Check if a material is completely prohibited.

        Args:
            cas_number: CAS registry number.

        Returns:
            True if material is prohibited for all uses.
        """
        restriction = self.get_by_cas(cas_number)
        if restriction:
            return restriction.restriction_type == RestrictionType.PROHIBITION
        return False

    def get_limit(self, cas_number: str, category: IFRACategory) -> Optional[float]:
        """Get maximum usage percentage for a material in a product category.

        Args:
            cas_number: CAS registry number.
            category: IFRA product category.

        Returns:
            Maximum percentage allowed, or None if not restricted.
            Returns 0.0 if material is prohibited.
        """
        restriction = self.get_by_cas(cas_number)
        if restriction:
            return restriction.get_limit_for_category(category)
        return None

    def get_all_restrictions(self) -> list[IFRARestriction]:
        """Get all IFRA restrictions.

        Returns:
            List of all IFRARestriction objects.
        """
        self._ensure_loaded()
        return list(self._restrictions.values())

    def get_prohibited_materials(self) -> list[IFRARestriction]:
        """Get list of all prohibited materials.

        Returns:
            List of prohibited material restrictions.
        """
        self._ensure_loaded()
        return [
            r for r in self._restrictions.values()
            if r.restriction_type == RestrictionType.PROHIBITION
        ]

    def get_sensitizers(self) -> list[IFRARestriction]:
        """Get list of materials restricted due to sensitization.

        Returns:
            List of sensitization-restricted materials.
        """
        self._ensure_loaded()
        return [
            r for r in self._restrictions.values()
            if r.restriction_type == RestrictionType.SENSITIZATION
        ]

    def check_formula_compliance(
        self,
        formula: dict[str, float],
        category: IFRACategory
    ) -> list[dict]:
        """Check formula for IFRA compliance.

        Args:
            formula: Dictionary mapping CAS numbers to percentages.
            category: IFRA product category.

        Returns:
            List of violations, each with 'cas_number', 'name',
            'percentage', 'limit', and 'violation_type'.
        """
        self._ensure_loaded()
        violations = []

        for cas_number, percentage in formula.items():
            restriction = self.get_by_cas(cas_number)
            if restriction:
                if restriction.restriction_type == RestrictionType.PROHIBITION:
                    violations.append({
                        "cas_number": cas_number,
                        "name": restriction.name,
                        "percentage": percentage,
                        "limit": 0.0,
                        "violation_type": "prohibited"
                    })
                else:
                    limit = restriction.get_limit_for_category(category)
                    if limit is not None and percentage > limit:
                        violations.append({
                            "cas_number": cas_number,
                            "name": restriction.name,
                            "percentage": percentage,
                            "limit": limit,
                            "violation_type": "exceeds_limit"
                        })

        return violations


# IFRA Product Category Descriptions
CATEGORY_DESCRIPTIONS = {
    IFRACategory.CATEGORY_1: "Lip products of all types (solid and liquid lipsticks, lip balm, etc.)",
    IFRACategory.CATEGORY_2: "Deodorant and antiperspirant products of all types",
    IFRACategory.CATEGORY_3: "Hydroalcoholic products applied to recently shaved skin, eye products",
    IFRACategory.CATEGORY_4: "Fine fragrance products (eau de toilette, parfum, etc.)",
    IFRACategory.CATEGORY_5A: "Body lotion products (hydroalcoholic based)",
    IFRACategory.CATEGORY_5B: "Face creams, face masks",
    IFRACategory.CATEGORY_5C: "Hand cream products",
    IFRACategory.CATEGORY_5D: "Baby creams, lotions, and oils",
    IFRACategory.CATEGORY_6: "Mouthwash, toothpaste, breath spray",
    IFRACategory.CATEGORY_7A: "Rinse-off hair products (shampoo, conditioner)",
    IFRACategory.CATEGORY_7B: "Leave-on hair products (styling, treatment)",
    IFRACategory.CATEGORY_8: "Intimate wipes, baby wipes",
    IFRACategory.CATEGORY_9: "Rinse-off body products (shower gel, soap, bath products)",
    IFRACategory.CATEGORY_10A: "Household cleaning products (spray application)",
    IFRACategory.CATEGORY_10B: "Household cleaning products (non-spray)",
    IFRACategory.CATEGORY_11A: "Candles",
    IFRACategory.CATEGORY_11B: "Reed diffusers, liquid potpourri",
    IFRACategory.CATEGORY_12: "Air fresheners (non-spray, solid, membrane)"
}


def get_category_description(category: IFRACategory) -> str:
    """Get human-readable description of an IFRA category.

    Args:
        category: IFRA product category.

    Returns:
        Description of the category.
    """
    return CATEGORY_DESCRIPTIONS.get(category, "Unknown category")


# Singleton database instance
_database: Optional[IFRADatabase] = None


def get_database() -> IFRADatabase:
    """Get or create the default IFRA database.

    Returns:
        The singleton IFRADatabase instance.
    """
    global _database
    if _database is None:
        _database = IFRADatabase()
    return _database


def is_restricted(cas_number: str) -> bool:
    """Check if a material is IFRA restricted.

    Convenience function using the default database.

    Args:
        cas_number: CAS registry number.

    Returns:
        True if material has any IFRA restriction.
    """
    return get_database().is_restricted(cas_number)


def get_limit(cas_number: str, category: IFRACategory) -> Optional[float]:
    """Get IFRA limit for a material in a product category.

    Convenience function using the default database.

    Args:
        cas_number: CAS registry number.
        category: IFRA product category.

    Returns:
        Maximum percentage allowed, or None if not restricted.
    """
    return get_database().get_limit(cas_number, category)


def check_compliance(formula: dict[str, float], category: IFRACategory) -> list[dict]:
    """Check formula for IFRA compliance.

    Convenience function using the default database.

    Args:
        formula: Dictionary mapping CAS numbers to percentages.
        category: IFRA product category.

    Returns:
        List of violations.
    """
    return get_database().check_formula_compliance(formula, category)


# Common restriction reasons
RESTRICTION_REASONS = {
    "sensitization": "Skin sensitization potential based on RIFM data",
    "phototoxicity": "Phototoxic potential when exposed to UV light",
    "environmental": "Environmental concerns (persistence, bioaccumulation)",
    "specification": "Purity requirements to limit impurities",
    "carcinogenicity": "Carcinogenicity concerns",
    "reproductive": "Reproductive toxicity concerns",
    "neurotoxicity": "Neurotoxicity concerns",
    "general_toxicity": "General systemic toxicity"
}


def get_restriction_reason_description(reason: str) -> str:
    """Get description of a restriction reason code.

    Args:
        reason: Restriction reason code.

    Returns:
        Human-readable description.
    """
    return RESTRICTION_REASONS.get(reason, reason)
