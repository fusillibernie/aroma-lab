"""Data models for scientific literature data extraction.

This module provides Pydantic models for storing and validating
literature data including natural material compositions, safety data,
and compound information from PubChem.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class IFRACategory(Enum):
    """IFRA product categories for restriction levels."""
    CATEGORY_1 = "1"  # Lip products
    CATEGORY_2 = "2"  # Deodorants/antiperspirants
    CATEGORY_3 = "3"  # Eye products, men's facial products
    CATEGORY_4 = "4"  # Fine fragrance
    CATEGORY_5A = "5A"  # Body lotion (hydroalcoholic)
    CATEGORY_5B = "5B"  # Face cream
    CATEGORY_5C = "5C"  # Hand cream
    CATEGORY_5D = "5D"  # Baby products
    CATEGORY_6 = "6"  # Mouthwash, toothpaste
    CATEGORY_7A = "7A"  # Rinse-off hair products
    CATEGORY_7B = "7B"  # Leave-on hair products
    CATEGORY_8 = "8"  # Intimate wipes
    CATEGORY_9 = "9"  # Rinse-off skin products
    CATEGORY_10A = "10A"  # Household cleaners (spray)
    CATEGORY_10B = "10B"  # Household cleaners (other)
    CATEGORY_11A = "11A"  # Candles
    CATEGORY_11B = "11B"  # Reed diffusers
    CATEGORY_12 = "12"  # Air fresheners (non-spray)


class RestrictionType(Enum):
    """Type of IFRA restriction."""
    PROHIBITION = "prohibition"  # Completely banned
    RESTRICTION = "restriction"  # Usage limits apply
    SPECIFICATION = "specification"  # Purity requirements
    SENSITIZATION = "sensitization"  # Allergen limits


@dataclass
class Citation:
    """A literature citation for data provenance."""
    title: str
    authors: list[str] = field(default_factory=list)
    journal: Optional[str] = None
    year: Optional[int] = None
    volume: Optional[str] = None
    pages: Optional[str] = None
    doi: Optional[str] = None
    url: Optional[str] = None
    accessed_date: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "title": self.title,
            "authors": self.authors,
            "journal": self.journal,
            "year": self.year,
            "volume": self.volume,
            "pages": self.pages,
            "doi": self.doi,
            "url": self.url,
            "accessed_date": self.accessed_date
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Citation":
        """Create from dictionary."""
        return cls(
            title=data.get("title", ""),
            authors=data.get("authors", []),
            journal=data.get("journal"),
            year=data.get("year"),
            volume=data.get("volume"),
            pages=data.get("pages"),
            doi=data.get("doi"),
            url=data.get("url"),
            accessed_date=data.get("accessed_date")
        )

    def __str__(self) -> str:
        """Format citation as a string."""
        parts = []
        if self.authors:
            if len(self.authors) > 3:
                parts.append(f"{self.authors[0]} et al.")
            else:
                parts.append(", ".join(self.authors))
        if self.year:
            parts.append(f"({self.year})")
        parts.append(self.title)
        if self.journal:
            parts.append(f"{self.journal}")
            if self.volume:
                parts.append(f"{self.volume}")
            if self.pages:
                parts.append(f": {self.pages}")
        if self.doi:
            parts.append(f"DOI: {self.doi}")
        return " ".join(parts)


@dataclass
class ComponentRange:
    """A component with percentage range from literature."""
    cas_number: str
    name: str
    min_percent: float
    max_percent: float
    typical_percent: Optional[float] = None
    notes: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "cas_number": self.cas_number,
            "name": self.name,
            "min_percent": self.min_percent,
            "max_percent": self.max_percent,
            "typical_percent": self.typical_percent,
            "notes": self.notes
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ComponentRange":
        """Create from dictionary."""
        return cls(
            cas_number=data.get("cas_number", ""),
            name=data.get("name", ""),
            min_percent=data.get("min_percent", 0.0),
            max_percent=data.get("max_percent", 0.0),
            typical_percent=data.get("typical_percent"),
            notes=data.get("notes")
        )


@dataclass
class NaturalComposition:
    """Published GC-MS composition data for a natural material.

    This stores literature-derived composition data with proper citations,
    including typical percentage ranges for major components.
    """
    name: str
    botanical_name: Optional[str] = None
    common_names: list[str] = field(default_factory=list)

    # Geographic and extraction info
    origin: Optional[str] = None
    extraction_method: Optional[str] = None
    plant_part: Optional[str] = None

    # Composition data
    components: list[ComponentRange] = field(default_factory=list)

    # Key character-impact compounds
    character_compounds: list[str] = field(default_factory=list)  # CAS numbers

    # Citations for the data
    citations: list[Citation] = field(default_factory=list)

    # Metadata
    notes: str = ""
    last_updated: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "botanical_name": self.botanical_name,
            "common_names": self.common_names,
            "origin": self.origin,
            "extraction_method": self.extraction_method,
            "plant_part": self.plant_part,
            "components": [c.to_dict() for c in self.components],
            "character_compounds": self.character_compounds,
            "citations": [c.to_dict() for c in self.citations],
            "notes": self.notes,
            "last_updated": self.last_updated
        }

    @classmethod
    def from_dict(cls, data: dict) -> "NaturalComposition":
        """Create from dictionary."""
        return cls(
            name=data.get("name", ""),
            botanical_name=data.get("botanical_name"),
            common_names=data.get("common_names", []),
            origin=data.get("origin"),
            extraction_method=data.get("extraction_method"),
            plant_part=data.get("plant_part"),
            components=[ComponentRange.from_dict(c) for c in data.get("components", [])],
            character_compounds=data.get("character_compounds", []),
            citations=[Citation.from_dict(c) for c in data.get("citations", [])],
            notes=data.get("notes", ""),
            last_updated=data.get("last_updated")
        )

    def get_major_components(self, threshold: float = 5.0) -> list[ComponentRange]:
        """Get components with typical percentage above threshold."""
        return [
            c for c in self.components
            if (c.typical_percent and c.typical_percent >= threshold) or c.max_percent >= threshold
        ]


@dataclass
class IFRARestriction:
    """IFRA restriction data for a single material."""
    cas_number: str
    name: str
    restriction_type: RestrictionType

    # Category-specific limits (percentage)
    category_limits: dict[str, float] = field(default_factory=dict)

    # General limit if same for all categories
    general_limit: Optional[float] = None

    # Amendment information
    amendment_number: Optional[int] = None
    effective_date: Optional[str] = None

    # Additional info
    reason: Optional[str] = None
    notes: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "cas_number": self.cas_number,
            "name": self.name,
            "restriction_type": self.restriction_type.value,
            "category_limits": self.category_limits,
            "general_limit": self.general_limit,
            "amendment_number": self.amendment_number,
            "effective_date": self.effective_date,
            "reason": self.reason,
            "notes": self.notes
        }

    @classmethod
    def from_dict(cls, data: dict) -> "IFRARestriction":
        """Create from dictionary."""
        return cls(
            cas_number=data.get("cas_number", ""),
            name=data.get("name", ""),
            restriction_type=RestrictionType(data.get("restriction_type", "restriction")),
            category_limits=data.get("category_limits", {}),
            general_limit=data.get("general_limit"),
            amendment_number=data.get("amendment_number"),
            effective_date=data.get("effective_date"),
            reason=data.get("reason"),
            notes=data.get("notes")
        )

    def get_limit_for_category(self, category: IFRACategory) -> Optional[float]:
        """Get the usage limit for a specific product category."""
        if self.restriction_type == RestrictionType.PROHIBITION:
            return 0.0

        cat_value = category.value
        if cat_value in self.category_limits:
            return self.category_limits[cat_value]
        return self.general_limit


@dataclass
class SafetyData:
    """Safety and regulatory data for a compound.

    Combines IFRA/RIFM data with other safety information.
    """
    cas_number: str
    name: str

    # IFRA restrictions
    ifra_restriction: Optional[IFRARestriction] = None

    # Allergen information
    is_eu_allergen: bool = False
    allergen_threshold_percent: Optional[float] = None

    # RIFM data
    rifm_id: Optional[str] = None
    rifm_monograph_available: bool = False

    # Toxicity data
    oral_ld50_mg_kg: Optional[float] = None
    dermal_ld50_mg_kg: Optional[float] = None
    skin_sensitization_category: Optional[str] = None

    # Phototoxicity
    is_phototoxic: bool = False
    phototoxicity_limit: Optional[float] = None

    # Environmental
    biodegradable: Optional[bool] = None
    aquatic_toxicity: Optional[str] = None

    # Citations
    citations: list[Citation] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "cas_number": self.cas_number,
            "name": self.name,
            "ifra_restriction": self.ifra_restriction.to_dict() if self.ifra_restriction else None,
            "is_eu_allergen": self.is_eu_allergen,
            "allergen_threshold_percent": self.allergen_threshold_percent,
            "rifm_id": self.rifm_id,
            "rifm_monograph_available": self.rifm_monograph_available,
            "oral_ld50_mg_kg": self.oral_ld50_mg_kg,
            "dermal_ld50_mg_kg": self.dermal_ld50_mg_kg,
            "skin_sensitization_category": self.skin_sensitization_category,
            "is_phototoxic": self.is_phototoxic,
            "phototoxicity_limit": self.phototoxicity_limit,
            "biodegradable": self.biodegradable,
            "aquatic_toxicity": self.aquatic_toxicity,
            "citations": [c.to_dict() for c in self.citations]
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SafetyData":
        """Create from dictionary."""
        ifra_data = data.get("ifra_restriction")
        return cls(
            cas_number=data.get("cas_number", ""),
            name=data.get("name", ""),
            ifra_restriction=IFRARestriction.from_dict(ifra_data) if ifra_data else None,
            is_eu_allergen=data.get("is_eu_allergen", False),
            allergen_threshold_percent=data.get("allergen_threshold_percent"),
            rifm_id=data.get("rifm_id"),
            rifm_monograph_available=data.get("rifm_monograph_available", False),
            oral_ld50_mg_kg=data.get("oral_ld50_mg_kg"),
            dermal_ld50_mg_kg=data.get("dermal_ld50_mg_kg"),
            skin_sensitization_category=data.get("skin_sensitization_category"),
            is_phototoxic=data.get("is_phototoxic", False),
            phototoxicity_limit=data.get("phototoxicity_limit"),
            biodegradable=data.get("biodegradable"),
            aquatic_toxicity=data.get("aquatic_toxicity"),
            citations=[Citation.from_dict(c) for c in data.get("citations", [])]
        )

    def is_restricted(self) -> bool:
        """Check if compound has any IFRA restriction."""
        return self.ifra_restriction is not None

    def get_max_usage(self, category: IFRACategory) -> Optional[float]:
        """Get maximum usage percentage for a product category."""
        if not self.ifra_restriction:
            return None
        return self.ifra_restriction.get_limit_for_category(category)


@dataclass
class PubChemCompound:
    """Compound data from PubChem API."""
    cid: int  # PubChem Compound ID
    cas_number: Optional[str] = None
    name: str = ""
    iupac_name: Optional[str] = None
    molecular_formula: Optional[str] = None
    molecular_weight: Optional[float] = None

    # Synonyms
    synonyms: list[str] = field(default_factory=list)

    # Physical properties
    boiling_point_c: Optional[float] = None
    melting_point_c: Optional[float] = None
    density_g_ml: Optional[float] = None
    vapor_pressure_mmhg: Optional[float] = None
    vapor_pressure_temp_c: Optional[float] = None
    log_p: Optional[float] = None
    solubility_mg_ml: Optional[float] = None

    # Identifiers
    inchi: Optional[str] = None
    inchi_key: Optional[str] = None
    smiles: Optional[str] = None

    # Metadata
    fetched_date: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "cid": self.cid,
            "cas_number": self.cas_number,
            "name": self.name,
            "iupac_name": self.iupac_name,
            "molecular_formula": self.molecular_formula,
            "molecular_weight": self.molecular_weight,
            "synonyms": self.synonyms,
            "boiling_point_c": self.boiling_point_c,
            "melting_point_c": self.melting_point_c,
            "density_g_ml": self.density_g_ml,
            "vapor_pressure_mmhg": self.vapor_pressure_mmhg,
            "vapor_pressure_temp_c": self.vapor_pressure_temp_c,
            "log_p": self.log_p,
            "solubility_mg_ml": self.solubility_mg_ml,
            "inchi": self.inchi,
            "inchi_key": self.inchi_key,
            "smiles": self.smiles,
            "fetched_date": self.fetched_date
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PubChemCompound":
        """Create from dictionary."""
        return cls(
            cid=data.get("cid", 0),
            cas_number=data.get("cas_number"),
            name=data.get("name", ""),
            iupac_name=data.get("iupac_name"),
            molecular_formula=data.get("molecular_formula"),
            molecular_weight=data.get("molecular_weight"),
            synonyms=data.get("synonyms", []),
            boiling_point_c=data.get("boiling_point_c"),
            melting_point_c=data.get("melting_point_c"),
            density_g_ml=data.get("density_g_ml"),
            vapor_pressure_mmhg=data.get("vapor_pressure_mmhg"),
            vapor_pressure_temp_c=data.get("vapor_pressure_temp_c"),
            log_p=data.get("log_p"),
            solubility_mg_ml=data.get("solubility_mg_ml"),
            inchi=data.get("inchi"),
            inchi_key=data.get("inchi_key"),
            smiles=data.get("smiles"),
            fetched_date=data.get("fetched_date")
        )
