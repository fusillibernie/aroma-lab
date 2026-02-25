"""Regional and species variation profiles for natural aromatics."""

from dataclasses import dataclass, field


@dataclass
class MarkerCompound:
    """A compound that serves as a marker for variation identification."""
    cas_number: str
    name: str
    typical_range_percent: tuple[float, float]  # (min, max)
    significance: str  # Why this compound matters


@dataclass
class RegionalVariation:
    """Describes how a natural varies by origin/species."""
    base_name: str  # e.g., "Rose Oil", "Cedarwood Oil"
    variation_name: str  # e.g., "Turkish Rose", "Virginia Cedarwood"
    botanical_name: str | None = None
    region: str | None = None

    # Key differentiating markers
    markers: list[MarkerCompound] = field(default_factory=list)

    # Typical composition ranges for major compounds
    typical_composition: dict[str, tuple[float, float]] = field(default_factory=dict)

    # Characteristic notes/descriptors
    character_notes: list[str] = field(default_factory=list)

    # Comparison to other variations
    similar_to: list[str] = field(default_factory=list)
    differs_from: dict[str, str] = field(default_factory=dict)  # variation -> difference description


# Example variation data (to be expanded with real literature data)
ROSE_VARIATIONS = [
    RegionalVariation(
        base_name="Rose Oil",
        variation_name="Turkish Rose (Rosa damascena)",
        botanical_name="Rosa damascena Mill.",
        region="Turkey (Isparta)",
        markers=[
            MarkerCompound(
                cas_number="5989-27-5",
                name="Citronellol",
                typical_range_percent=(20, 35),
                significance="Primary alcohol, contributes to rosy character",
            ),
            MarkerCompound(
                cas_number="106-24-1",
                name="Geraniol",
                typical_range_percent=(15, 25),
                significance="Secondary alcohol, adds freshness",
            ),
            MarkerCompound(
                cas_number="502-99-8",
                name="Rose oxide",
                typical_range_percent=(0.5, 2.0),
                significance="Key character impact compound - green, metallic rose",
            ),
        ],
        typical_composition={
            "citronellol": (20, 35),
            "geraniol": (15, 25),
            "nerol": (5, 12),
            "linalool": (1, 3),
            "rose oxide": (0.5, 2.0),
        },
        character_notes=["honeyed", "warm", "deep", "slightly spicy"],
    ),
    RegionalVariation(
        base_name="Rose Oil",
        variation_name="Bulgarian Rose (Rosa damascena)",
        botanical_name="Rosa damascena Mill.",
        region="Bulgaria (Rose Valley)",
        markers=[
            MarkerCompound(
                cas_number="5989-27-5",
                name="Citronellol",
                typical_range_percent=(25, 40),
                significance="Higher citronellol than Turkish",
            ),
            MarkerCompound(
                cas_number="502-99-8",
                name="Rose oxide",
                typical_range_percent=(0.3, 1.0),
                significance="Lower rose oxide gives softer character",
            ),
        ],
        typical_composition={
            "citronellol": (25, 40),
            "geraniol": (12, 20),
            "nerol": (7, 15),
            "linalool": (1, 4),
        },
        character_notes=["bright", "fresh", "lighter", "more citrus-like"],
        differs_from={
            "Turkish Rose": "Lower rose oxide, higher citronellol, brighter character",
        },
    ),
]

CEDARWOOD_VARIATIONS = [
    RegionalVariation(
        base_name="Cedarwood Oil",
        variation_name="Virginia Cedarwood",
        botanical_name="Juniperus virginiana",
        region="Eastern USA",
        markers=[
            MarkerCompound(
                cas_number="469-61-4",
                name="Cedrene",
                typical_range_percent=(15, 30),
                significance="Primary sesquiterpene",
            ),
            MarkerCompound(
                cas_number="77-53-2",
                name="Cedrol",
                typical_range_percent=(20, 35),
                significance="Key alcohol, woody character",
            ),
        ],
        character_notes=["pencil-like", "dry", "woody", "slightly sweet"],
    ),
    RegionalVariation(
        base_name="Cedarwood Oil",
        variation_name="Texas Cedarwood",
        botanical_name="Juniperus ashei",
        region="Texas, USA",
        markers=[
            MarkerCompound(
                cas_number="77-53-2",
                name="Cedrol",
                typical_range_percent=(25, 45),
                significance="Higher cedrol content than Virginia",
            ),
        ],
        character_notes=["smoky", "tarry", "more intense", "camphoraceous"],
        differs_from={
            "Virginia Cedarwood": "Higher cedrol, smokier, more tarry character",
        },
    ),
    RegionalVariation(
        base_name="Cedarwood Oil",
        variation_name="Chinese Cedarwood",
        botanical_name="Cupressus funebris",
        region="China",
        markers=[
            MarkerCompound(
                cas_number="77-53-2",
                name="Cedrol",
                typical_range_percent=(5, 15),
                significance="Lower cedrol than American varieties",
            ),
        ],
        character_notes=["lighter", "greener", "less woody", "more resinous"],
        differs_from={
            "Virginia Cedarwood": "Much lower cedrol, greener, less pencil-like",
        },
    ),
]


class VariationDatabase:
    """Database of natural aromatic variations."""

    def __init__(self):
        self._variations: dict[str, list[RegionalVariation]] = {}

        # Load built-in variations
        self._load_builtin()

    def _load_builtin(self):
        """Load built-in variation data."""
        for var in ROSE_VARIATIONS:
            self.add_variation(var)
        for var in CEDARWOOD_VARIATIONS:
            self.add_variation(var)

    def add_variation(self, variation: RegionalVariation):
        """Add a variation to the database."""
        base = variation.base_name.lower()
        if base not in self._variations:
            self._variations[base] = []
        self._variations[base].append(variation)

    def get_variations(self, base_name: str) -> list[RegionalVariation]:
        """Get all variations for a base material."""
        return self._variations.get(base_name.lower(), [])

    def identify_variation(
        self,
        base_name: str,
        composition: dict[str, float],  # compound_name -> percentage
    ) -> tuple[RegionalVariation | None, float]:
        """Identify which variation a composition matches.

        Returns (best_match, confidence_score).
        """
        variations = self.get_variations(base_name)
        if not variations:
            return None, 0.0

        best_match = None
        best_score = 0.0

        for var in variations:
            score = self._score_match(var, composition)
            if score > best_score:
                best_score = score
                best_match = var

        return best_match, best_score

    def _score_match(
        self,
        variation: RegionalVariation,
        composition: dict[str, float],
    ) -> float:
        """Score how well a composition matches a variation."""
        if not variation.markers:
            return 0.0

        scores = []
        comp_lower = {k.lower(): v for k, v in composition.items()}

        for marker in variation.markers:
            name_lower = marker.name.lower()
            if name_lower in comp_lower:
                value = comp_lower[name_lower]
                min_val, max_val = marker.typical_range_percent

                if min_val <= value <= max_val:
                    # Perfect match - value is within range
                    scores.append(1.0)
                else:
                    # Partial match - how far outside range?
                    if value < min_val:
                        distance = min_val - value
                    else:
                        distance = value - max_val

                    # Score decreases with distance from range
                    range_size = max_val - min_val
                    normalized_distance = distance / (range_size + 1)
                    scores.append(max(0, 1 - normalized_distance))
            else:
                # Marker not found in composition
                scores.append(0.0)

        return sum(scores) / len(scores) if scores else 0.0

    def compare_variations(
        self,
        base_name: str,
        var_a_name: str,
        var_b_name: str,
    ) -> dict:
        """Compare two variations of the same base material."""
        variations = {v.variation_name.lower(): v for v in self.get_variations(base_name)}

        var_a = variations.get(var_a_name.lower())
        var_b = variations.get(var_b_name.lower())

        if not var_a or not var_b:
            return {"error": "One or both variations not found"}

        return {
            "variation_a": var_a.variation_name,
            "variation_b": var_b.variation_name,
            "a_character": var_a.character_notes,
            "b_character": var_b.character_notes,
            "key_differences": var_a.differs_from.get(var_b.variation_name,
                var_b.differs_from.get(var_a.variation_name, "Not documented")),
        }
