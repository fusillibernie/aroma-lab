"""GC-MS literature data for natural aromatic materials.

This module provides access to published GC-MS composition data for
common natural fragrance materials, including typical percentage
ranges for major components with proper citation tracking.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from .data_models import Citation, ComponentRange, NaturalComposition

logger = logging.getLogger(__name__)

# Default data file location
DEFAULT_COMPOSITIONS_FILE = Path(__file__).parent.parent.parent / "data" / "literature" / "natural_compositions.json"


class GCMSLiteratureDatabase:
    """Database of published GC-MS compositions for natural materials.

    Provides access to literature-derived composition data for common
    natural aromatic materials with proper citation tracking.
    """

    def __init__(self, data_file: Optional[Path] = None):
        """Initialize the GC-MS literature database.

        Args:
            data_file: Path to JSON file with composition data.
                      Defaults to data/literature/natural_compositions.json
        """
        self.data_file = data_file or DEFAULT_COMPOSITIONS_FILE
        self._compositions: dict[str, NaturalComposition] = {}
        self._botanical_index: dict[str, str] = {}  # botanical_name -> name
        self._loaded = False

    def load(self) -> None:
        """Load composition data from the JSON file."""
        if not self.data_file.exists():
            logger.warning(f"Composition data file not found: {self.data_file}")
            return

        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            compositions_list = data.get("compositions", [])
            for item in compositions_list:
                composition = NaturalComposition.from_dict(item)
                # Index by name (lowercase for case-insensitive lookup)
                self._compositions[composition.name.lower()] = composition
                # Also index by botanical name
                if composition.botanical_name:
                    self._botanical_index[composition.botanical_name.lower()] = composition.name.lower()
                # Index by common names
                for common_name in composition.common_names:
                    self._compositions[common_name.lower()] = composition

            self._loaded = True
            logger.info(f"Loaded {len(compositions_list)} natural compositions")

        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load composition data: {e}")
            raise

    def _ensure_loaded(self) -> None:
        """Ensure data is loaded before queries."""
        if not self._loaded:
            self.load()

    def get_by_name(self, name: str) -> Optional[NaturalComposition]:
        """Get composition data by material name.

        Args:
            name: Material name or common name (case-insensitive).

        Returns:
            NaturalComposition if found, None otherwise.
        """
        self._ensure_loaded()
        return self._compositions.get(name.lower())

    def get_by_botanical_name(self, botanical_name: str) -> Optional[NaturalComposition]:
        """Get composition data by botanical name.

        Args:
            botanical_name: Latin botanical name (case-insensitive).

        Returns:
            NaturalComposition if found, None otherwise.
        """
        self._ensure_loaded()
        material_name = self._botanical_index.get(botanical_name.lower())
        if material_name:
            return self._compositions.get(material_name)
        return None

    def get_all_materials(self) -> list[str]:
        """Get list of all material names in the database.

        Returns:
            List of material names.
        """
        self._ensure_loaded()
        # Return unique primary names only
        seen = set()
        names = []
        for comp in self._compositions.values():
            if comp.name not in seen:
                names.append(comp.name)
                seen.add(comp.name)
        return sorted(names)

    def get_all_compositions(self) -> list[NaturalComposition]:
        """Get all composition data.

        Returns:
            List of all NaturalComposition objects.
        """
        self._ensure_loaded()
        # Return unique compositions only
        seen = set()
        compositions = []
        for comp in self._compositions.values():
            if comp.name not in seen:
                compositions.append(comp)
                seen.add(comp.name)
        return compositions

    def search_by_component(self, cas_number: str) -> list[NaturalComposition]:
        """Find all materials containing a specific component.

        Args:
            cas_number: CAS number of the component.

        Returns:
            List of materials containing the component.
        """
        self._ensure_loaded()
        results = []
        seen = set()
        for comp in self._compositions.values():
            if comp.name in seen:
                continue
            for component in comp.components:
                if component.cas_number == cas_number:
                    results.append(comp)
                    seen.add(comp.name)
                    break
        return results

    def get_major_components(
        self,
        name: str,
        threshold: float = 5.0
    ) -> list[ComponentRange]:
        """Get major components of a material above a percentage threshold.

        Args:
            name: Material name.
            threshold: Minimum typical percentage (default 5%).

        Returns:
            List of ComponentRange for major components.
        """
        composition = self.get_by_name(name)
        if composition:
            return composition.get_major_components(threshold)
        return []

    def get_character_compounds(self, name: str) -> list[ComponentRange]:
        """Get character-impact compounds for a material.

        These are the compounds that define the characteristic
        odor of the natural material.

        Args:
            name: Material name.

        Returns:
            List of character-impact compounds.
        """
        composition = self.get_by_name(name)
        if not composition:
            return []

        character_cas = set(composition.character_compounds)
        return [
            c for c in composition.components
            if c.cas_number in character_cas
        ]

    def get_citations_for_material(self, name: str) -> list[Citation]:
        """Get all citations for a material's composition data.

        Args:
            name: Material name.

        Returns:
            List of citations.
        """
        composition = self.get_by_name(name)
        if composition:
            return composition.citations
        return []

    def compare_materials(
        self,
        name1: str,
        name2: str
    ) -> dict:
        """Compare compositions of two materials.

        Args:
            name1: First material name.
            name2: Second material name.

        Returns:
            Dictionary with 'common_components', 'unique_to_first',
            'unique_to_second'.
        """
        comp1 = self.get_by_name(name1)
        comp2 = self.get_by_name(name2)

        if not comp1 or not comp2:
            return {
                "common_components": [],
                "unique_to_first": [],
                "unique_to_second": [],
                "error": "One or both materials not found"
            }

        cas1 = {c.cas_number for c in comp1.components}
        cas2 = {c.cas_number for c in comp2.components}

        common_cas = cas1 & cas2
        unique1 = cas1 - cas2
        unique2 = cas2 - cas1

        return {
            "common_components": [
                c for c in comp1.components if c.cas_number in common_cas
            ],
            "unique_to_first": [
                c for c in comp1.components if c.cas_number in unique1
            ],
            "unique_to_second": [
                c for c in comp2.components if c.cas_number in unique2
            ]
        }


# Singleton database instance
_database: Optional[GCMSLiteratureDatabase] = None


def get_database() -> GCMSLiteratureDatabase:
    """Get or create the default GC-MS literature database.

    Returns:
        The singleton GCMSLiteratureDatabase instance.
    """
    global _database
    if _database is None:
        _database = GCMSLiteratureDatabase()
    return _database


def get_composition(name: str) -> Optional[NaturalComposition]:
    """Get composition data for a natural material.

    Convenience function using the default database.

    Args:
        name: Material name (case-insensitive).

    Returns:
        NaturalComposition if found, None otherwise.
    """
    return get_database().get_by_name(name)


def get_major_components(name: str, threshold: float = 5.0) -> list[ComponentRange]:
    """Get major components of a natural material.

    Convenience function using the default database.

    Args:
        name: Material name.
        threshold: Minimum typical percentage.

    Returns:
        List of major components.
    """
    return get_database().get_major_components(name, threshold)


def list_materials() -> list[str]:
    """List all available materials.

    Convenience function using the default database.

    Returns:
        List of material names.
    """
    return get_database().get_all_materials()


def find_materials_with_component(cas_number: str) -> list[str]:
    """Find materials containing a specific component.

    Convenience function using the default database.

    Args:
        cas_number: CAS number of the component.

    Returns:
        List of material names containing the component.
    """
    compositions = get_database().search_by_component(cas_number)
    return [c.name for c in compositions]


# Common natural material categories for reference
MATERIAL_CATEGORIES = {
    "florals": [
        "Rose Otto",
        "Rose Absolute",
        "Jasmine Absolute",
        "Ylang Ylang",
        "Tuberose Absolute",
        "Orange Blossom Absolute",
        "Neroli"
    ],
    "woods": [
        "Sandalwood Oil",
        "Cedarwood Virginia",
        "Cedarwood Atlas",
        "Vetiver Oil",
        "Patchouli Oil",
        "Guaiac Wood Oil"
    ],
    "citrus": [
        "Bergamot Oil",
        "Lemon Oil",
        "Orange Oil Sweet",
        "Grapefruit Oil",
        "Lime Oil",
        "Mandarin Oil"
    ],
    "herbs": [
        "Lavender Oil",
        "Rosemary Oil",
        "Clary Sage Oil",
        "Basil Oil",
        "Thyme Oil"
    ],
    "spices": [
        "Clove Bud Oil",
        "Cinnamon Bark Oil",
        "Cardamom Oil",
        "Black Pepper Oil",
        "Ginger Oil"
    ],
    "resins": [
        "Frankincense Oil",
        "Myrrh Oil",
        "Benzoin Resinoid",
        "Labdanum Absolute"
    ]
}


def get_materials_by_category(category: str) -> list[str]:
    """Get list of materials in a category.

    Args:
        category: Category name (florals, woods, citrus, herbs, spices, resins).

    Returns:
        List of material names in the category.
    """
    return MATERIAL_CATEGORIES.get(category.lower(), [])


def get_all_categories() -> list[str]:
    """Get list of all material categories.

    Returns:
        List of category names.
    """
    return list(MATERIAL_CATEGORIES.keys())
