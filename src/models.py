"""Core data models for Aroma Lab."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Volatility(Enum):
    """Fragrance volatility classification."""
    TOP = "top"
    HEART = "heart"
    BASE = "base"


class OdorFamily(Enum):
    """Primary odor families."""
    FLORAL = "floral"
    WOODY = "woody"
    CITRUS = "citrus"
    SPICY = "spicy"
    HERBACEOUS = "herbaceous"
    BALSAMIC = "balsamic"
    MUSK = "musk"
    AMBER = "amber"
    GREEN = "green"
    FRUITY = "fruity"
    ANIMALIC = "animalic"
    MARINE = "marine"
    EARTHY = "earthy"


@dataclass
class Aromachemical:
    """A single aromachemical compound."""
    cas_number: str
    name: str
    iupac_name: Optional[str] = None
    molecular_formula: Optional[str] = None
    molecular_weight: Optional[float] = None

    # Olfactory properties
    odor_description: str = ""
    odor_families: list[OdorFamily] = field(default_factory=list)
    volatility: Optional[Volatility] = None
    odor_threshold_ppm: Optional[float] = None

    # Physical properties
    boiling_point_c: Optional[float] = None
    vapor_pressure_mmhg: Optional[float] = None
    log_p: Optional[float] = None  # Octanol-water partition coefficient

    # Sourcing
    suppliers: list[str] = field(default_factory=list)
    cost_per_kg_usd: Optional[float] = None
    natural_occurrence: list[str] = field(default_factory=list)

    # Regulatory
    ifra_restricted: bool = False
    max_usage_percent: Optional[float] = None


@dataclass
class GCMSPeak:
    """A single peak from GC-MS analysis."""
    retention_time: float  # minutes
    area_percent: float
    cas_number: Optional[str] = None
    compound_name: Optional[str] = None
    match_quality: Optional[float] = None  # 0-100 library match score

    # Mass spec data
    base_peak_mz: Optional[float] = None
    molecular_ion_mz: Optional[float] = None
    key_fragments: list[float] = field(default_factory=list)


@dataclass
class NaturalProfile:
    """GC-MS profile of a natural aromatic material."""
    name: str
    botanical_name: Optional[str] = None
    origin: Optional[str] = None  # e.g., "Turkey", "Morocco", "Bulgaria"
    extraction_method: Optional[str] = None  # e.g., "steam distillation", "solvent extraction"

    # GC-MS composition
    peaks: list[GCMSPeak] = field(default_factory=list)

    # Key character-defining compounds (markers)
    key_markers: dict[str, float] = field(default_factory=dict)  # CAS -> typical %

    # Metadata
    source_reference: Optional[str] = None  # Literature citation
    analysis_date: Optional[str] = None
    notes: str = ""


@dataclass
class FormulaIngredient:
    """A single ingredient in a formula."""
    aromachemical: Aromachemical
    percentage: float
    notes: str = ""


@dataclass
class Formula:
    """A reconstructed aromatic formula."""
    name: str
    target_natural: Optional[NaturalProfile] = None
    ingredients: list[FormulaIngredient] = field(default_factory=list)

    # Formula metadata
    total_cost_per_kg: Optional[float] = None
    fidelity_score: Optional[float] = None  # How close to target (0-100)
    version: str = "1.0"
    notes: str = ""

    @property
    def total_percentage(self) -> float:
        """Sum of all ingredient percentages."""
        return sum(ing.percentage for ing in self.ingredients)

    def validate(self) -> list[str]:
        """Validate formula and return list of issues."""
        issues = []
        total = self.total_percentage
        if abs(total - 100.0) > 0.1:
            issues.append(f"Total percentage is {total:.2f}%, should be 100%")

        for ing in self.ingredients:
            if ing.aromachemical.ifra_restricted:
                if ing.aromachemical.max_usage_percent:
                    if ing.percentage > ing.aromachemical.max_usage_percent:
                        issues.append(
                            f"{ing.aromachemical.name} at {ing.percentage}% exceeds "
                            f"IFRA limit of {ing.aromachemical.max_usage_percent}%"
                        )
        return issues
