"""Data loading utilities for aromachemical database."""

import csv
import json
from pathlib import Path

from src.models import Aromachemical, OdorFamily, Volatility


def load_from_json(file_path: Path) -> list[Aromachemical]:
    """Load aromachemicals from a JSON file."""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        data = [data]

    results = []
    for item in data:
        ac = _parse_aromachemical_dict(item)
        if ac:
            results.append(ac)

    return results


def load_from_csv(
    file_path: Path,
    column_mapping: dict[str, str] | None = None,
) -> list[Aromachemical]:
    """Load aromachemicals from a CSV file.

    Args:
        file_path: Path to CSV file
        column_mapping: Optional mapping of CSV columns to Aromachemical fields
                       e.g., {"CAS": "cas_number", "Product Name": "name"}

    Default expected columns:
        cas_number, name, odor_description, odor_families (comma-separated),
        volatility, cost_per_kg_usd, suppliers (comma-separated)
    """
    # Default column mappings (lowercase)
    default_mapping = {
        "cas": "cas_number",
        "cas_number": "cas_number",
        "cas #": "cas_number",
        "cas#": "cas_number",
        "name": "name",
        "product": "name",
        "product name": "name",
        "chemical name": "name",
        "odor": "odor_description",
        "odor description": "odor_description",
        "description": "odor_description",
        "scent": "odor_description",
        "family": "odor_families",
        "odor family": "odor_families",
        "odor families": "odor_families",
        "category": "odor_families",
        "volatility": "volatility",
        "note": "volatility",
        "top/heart/base": "volatility",
        "price": "cost_per_kg_usd",
        "cost": "cost_per_kg_usd",
        "cost_per_kg": "cost_per_kg_usd",
        "price_per_kg": "cost_per_kg_usd",
        "$/kg": "cost_per_kg_usd",
        "supplier": "suppliers",
        "suppliers": "suppliers",
        "vendor": "suppliers",
        "iupac": "iupac_name",
        "iupac_name": "iupac_name",
        "molecular_formula": "molecular_formula",
        "formula": "molecular_formula",
        "molecular_weight": "molecular_weight",
        "mw": "molecular_weight",
        "mol_weight": "molecular_weight",
        "boiling_point": "boiling_point_c",
        "bp": "boiling_point_c",
        "boiling_point_c": "boiling_point_c",
        "ifra": "ifra_restricted",
        "ifra_restricted": "ifra_restricted",
        "restricted": "ifra_restricted",
        "max_usage": "max_usage_percent",
        "max_usage_percent": "max_usage_percent",
        "ifra_limit": "max_usage_percent",
        "natural_occurrence": "natural_occurrence",
        "naturals": "natural_occurrence",
        "found_in": "natural_occurrence",
    }

    if column_mapping:
        default_mapping.update({k.lower(): v for k, v in column_mapping.items()})

    results = []

    with open(file_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        # Map actual columns to our fields
        field_mapping = {}
        for col in reader.fieldnames or []:
            col_lower = col.lower().strip()
            if col_lower in default_mapping:
                field_mapping[col] = default_mapping[col_lower]

        for row in reader:
            try:
                # Build aromachemical dict from row
                ac_dict = {}

                for csv_col, field in field_mapping.items():
                    value = row.get(csv_col, "").strip()
                    if not value:
                        continue

                    # Handle special field parsing
                    if field == "odor_families":
                        # Parse comma-separated families
                        families = [f.strip().lower() for f in value.split(",")]
                        ac_dict[field] = families
                    elif field == "suppliers":
                        # Parse comma-separated suppliers
                        ac_dict[field] = [s.strip() for s in value.split(",")]
                    elif field == "natural_occurrence":
                        ac_dict[field] = [n.strip() for n in value.split(",")]
                    elif field in ("cost_per_kg_usd", "molecular_weight", "boiling_point_c",
                                   "max_usage_percent", "odor_threshold_ppm"):
                        # Parse numeric fields
                        try:
                            # Remove currency symbols and commas
                            clean = value.replace("$", "").replace(",", "").strip()
                            ac_dict[field] = float(clean)
                        except ValueError:
                            pass
                    elif field == "ifra_restricted":
                        ac_dict[field] = value.lower() in ("yes", "true", "1", "y", "restricted")
                    elif field == "volatility":
                        # Normalize volatility
                        vol_lower = value.lower()
                        if vol_lower in ("top", "head", "t"):
                            ac_dict[field] = "top"
                        elif vol_lower in ("heart", "middle", "mid", "m", "h"):
                            ac_dict[field] = "heart"
                        elif vol_lower in ("base", "bottom", "b"):
                            ac_dict[field] = "base"
                    else:
                        ac_dict[field] = value

                # Require at minimum CAS and name
                if "cas_number" in ac_dict and "name" in ac_dict:
                    ac = _parse_aromachemical_dict(ac_dict)
                    if ac:
                        results.append(ac)

            except Exception as e:
                print(f"Warning: Failed to parse row: {e}")
                continue

    return results


def _parse_aromachemical_dict(data: dict) -> Aromachemical | None:
    """Parse a dictionary into an Aromachemical object."""
    if "cas_number" not in data or "name" not in data:
        return None

    # Parse odor families
    odor_families = []
    for fam in data.get("odor_families", []):
        if isinstance(fam, str):
            try:
                odor_families.append(OdorFamily(fam.lower()))
            except ValueError:
                pass  # Skip unknown families

    # Parse volatility
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
