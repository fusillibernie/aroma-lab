"""Aromachemical database manager."""

import json
from pathlib import Path
from typing import Iterator

from src.models import Aromachemical, OdorFamily, Volatility


class AromachemicalDB:
    """In-memory database of aromachemicals with persistence."""

    def __init__(self, data_dir: Path | None = None):
        """Initialize database.

        Args:
            data_dir: Directory containing aromachemical JSON files.
                     If None, starts with empty database.
        """
        self._by_cas: dict[str, Aromachemical] = {}
        self._by_name: dict[str, Aromachemical] = {}  # lowercase name -> Aromachemical
        self._data_dir = data_dir

        if data_dir and data_dir.exists():
            self._load_from_dir(data_dir)

    def _load_from_dir(self, data_dir: Path) -> None:
        """Load all JSON files from directory."""
        for json_file in data_dir.glob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if isinstance(data, list):
                    for item in data:
                        ac = self._dict_to_aromachemical(item)
                        self.add(ac)
                elif isinstance(data, dict):
                    ac = self._dict_to_aromachemical(data)
                    self.add(ac)
            except Exception as e:
                print(f"Warning: Failed to load {json_file}: {e}")

    def _dict_to_aromachemical(self, data: dict) -> Aromachemical:
        """Convert dictionary to Aromachemical object."""
        # Handle enum conversions
        odor_families = []
        for fam in data.get("odor_families", []):
            if isinstance(fam, str):
                try:
                    odor_families.append(OdorFamily(fam.lower()))
                except ValueError:
                    pass  # Skip unknown families

        volatility = None
        if vol := data.get("volatility"):
            try:
                volatility = Volatility(vol.lower())
            except ValueError:
                pass

        return Aromachemical(
            cas_number=data["cas_number"],
            name=data["name"],
            iupac_name=data.get("iupac_name"),
            molecular_formula=data.get("molecular_formula"),
            molecular_weight=data.get("molecular_weight"),
            odor_description=data.get("odor_description", ""),
            odor_families=odor_families,
            volatility=volatility,
            odor_threshold_ppm=data.get("odor_threshold_ppm"),
            boiling_point_c=data.get("boiling_point_c"),
            vapor_pressure_mmhg=data.get("vapor_pressure_mmhg"),
            log_p=data.get("log_p"),
            suppliers=data.get("suppliers", []),
            cost_per_kg_usd=data.get("cost_per_kg_usd"),
            natural_occurrence=data.get("natural_occurrence", []),
            ifra_restricted=data.get("ifra_restricted", False),
            max_usage_percent=data.get("max_usage_percent"),
        )

    def _aromachemical_to_dict(self, ac: Aromachemical) -> dict:
        """Convert Aromachemical to dictionary for JSON serialization."""
        data = {
            "cas_number": ac.cas_number,
            "name": ac.name,
        }

        # Only include non-None/non-empty values
        if ac.iupac_name:
            data["iupac_name"] = ac.iupac_name
        if ac.molecular_formula:
            data["molecular_formula"] = ac.molecular_formula
        if ac.molecular_weight:
            data["molecular_weight"] = ac.molecular_weight
        if ac.odor_description:
            data["odor_description"] = ac.odor_description
        if ac.odor_families:
            data["odor_families"] = [f.value for f in ac.odor_families]
        if ac.volatility:
            data["volatility"] = ac.volatility.value
        if ac.odor_threshold_ppm is not None:
            data["odor_threshold_ppm"] = ac.odor_threshold_ppm
        if ac.boiling_point_c is not None:
            data["boiling_point_c"] = ac.boiling_point_c
        if ac.vapor_pressure_mmhg is not None:
            data["vapor_pressure_mmhg"] = ac.vapor_pressure_mmhg
        if ac.log_p is not None:
            data["log_p"] = ac.log_p
        if ac.suppliers:
            data["suppliers"] = ac.suppliers
        if ac.cost_per_kg_usd is not None:
            data["cost_per_kg_usd"] = ac.cost_per_kg_usd
        if ac.natural_occurrence:
            data["natural_occurrence"] = ac.natural_occurrence
        if ac.ifra_restricted:
            data["ifra_restricted"] = ac.ifra_restricted
        if ac.max_usage_percent is not None:
            data["max_usage_percent"] = ac.max_usage_percent

        return data

    def add(self, aromachemical: Aromachemical) -> None:
        """Add an aromachemical to the database."""
        self._by_cas[aromachemical.cas_number] = aromachemical
        self._by_name[aromachemical.name.lower()] = aromachemical

        if aromachemical.iupac_name:
            self._by_name[aromachemical.iupac_name.lower()] = aromachemical

    def get_by_cas(self, cas_number: str) -> Aromachemical | None:
        """Get aromachemical by CAS number."""
        return self._by_cas.get(cas_number)

    def get_by_name(self, name: str) -> Aromachemical | None:
        """Get aromachemical by name (case-insensitive)."""
        return self._by_name.get(name.lower())

    def search(
        self,
        query: str | None = None,
        odor_family: OdorFamily | None = None,
        volatility: Volatility | None = None,
        max_cost: float | None = None,
        natural_only: bool = False,
    ) -> list[Aromachemical]:
        """Search aromachemicals with filters."""
        results = []

        for ac in self._by_cas.values():
            # Text query search
            if query:
                query_lower = query.lower()
                if not (
                    query_lower in ac.name.lower() or
                    query_lower in ac.odor_description.lower() or
                    (ac.iupac_name and query_lower in ac.iupac_name.lower())
                ):
                    continue

            # Odor family filter
            if odor_family and odor_family not in ac.odor_families:
                continue

            # Volatility filter
            if volatility and ac.volatility != volatility:
                continue

            # Cost filter
            if max_cost is not None:
                if ac.cost_per_kg_usd is None or ac.cost_per_kg_usd > max_cost:
                    continue

            # Natural occurrence filter
            if natural_only and not ac.natural_occurrence:
                continue

            results.append(ac)

        return results

    def search_by_odor(self, *descriptors: str) -> list[Aromachemical]:
        """Search by odor descriptors (matches any)."""
        results = []
        descriptors_lower = [d.lower() for d in descriptors]

        for ac in self._by_cas.values():
            desc_lower = ac.odor_description.lower()
            if any(d in desc_lower for d in descriptors_lower):
                results.append(ac)

        return results

    def get_by_volatility(self, volatility: Volatility) -> list[Aromachemical]:
        """Get all aromachemicals of a specific volatility."""
        return [ac for ac in self._by_cas.values() if ac.volatility == volatility]

    def get_by_family(self, family: OdorFamily) -> list[Aromachemical]:
        """Get all aromachemicals in an odor family."""
        return [ac for ac in self._by_cas.values() if family in ac.odor_families]

    def __len__(self) -> int:
        """Return number of aromachemicals in database."""
        return len(self._by_cas)

    def __iter__(self) -> Iterator[Aromachemical]:
        """Iterate over all aromachemicals."""
        return iter(self._by_cas.values())

    def __contains__(self, cas_number: str) -> bool:
        """Check if CAS number is in database."""
        return cas_number in self._by_cas

    def save(self, output_file: Path) -> None:
        """Save entire database to a single JSON file."""
        data = [self._aromachemical_to_dict(ac) for ac in self._by_cas.values()]
        data.sort(key=lambda x: x["name"])  # Sort alphabetically

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def save_by_category(self, output_dir: Path) -> None:
        """Save database split by odor family into separate files."""
        output_dir.mkdir(parents=True, exist_ok=True)

        # Group by primary odor family
        by_family: dict[str, list[dict]] = {"uncategorized": []}

        for ac in self._by_cas.values():
            data = self._aromachemical_to_dict(ac)
            if ac.odor_families:
                family = ac.odor_families[0].value
            else:
                family = "uncategorized"

            if family not in by_family:
                by_family[family] = []
            by_family[family].append(data)

        # Write each category
        for family, chemicals in by_family.items():
            if chemicals:
                chemicals.sort(key=lambda x: x["name"])
                output_file = output_dir / f"{family}.json"
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(chemicals, f, indent=2, ensure_ascii=False)

    def stats(self) -> dict:
        """Get database statistics."""
        stats = {
            "total_count": len(self._by_cas),
            "by_volatility": {},
            "by_family": {},
            "with_cost": 0,
            "ifra_restricted": 0,
        }

        for ac in self._by_cas.values():
            # Count by volatility
            vol = ac.volatility.value if ac.volatility else "unclassified"
            stats["by_volatility"][vol] = stats["by_volatility"].get(vol, 0) + 1

            # Count by family
            for fam in ac.odor_families:
                stats["by_family"][fam.value] = stats["by_family"].get(fam.value, 0) + 1

            # Count with cost data
            if ac.cost_per_kg_usd is not None:
                stats["with_cost"] += 1

            # Count IFRA restricted
            if ac.ifra_restricted:
                stats["ifra_restricted"] += 1

        return stats
