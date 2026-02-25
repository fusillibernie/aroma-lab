"""Scientific literature data extraction tools for Aroma Lab.

This module provides tools for extracting and managing scientific
literature data related to fragrance materials, including:

- PubChem API client for compound data
- IFRA restriction data and compliance checking
- Published GC-MS composition data for natural materials
- Data models for literature data
"""

from .data_models import (
    Citation,
    ComponentRange,
    IFRACategory,
    IFRARestriction,
    NaturalComposition,
    PubChemCompound,
    RestrictionType,
    SafetyData,
)

from .pubchem_client import (
    PubChemClient,
    PubChemError,
    fetch_compound,
    fetch_compound_by_name,
    get_cas_number,
    get_molecular_formula,
    get_physical_properties,
)

from .ifra_data import (
    IFRADatabase,
    check_compliance,
    get_category_description,
    get_limit,
    is_restricted,
    CATEGORY_DESCRIPTIONS,
    RESTRICTION_REASONS,
)

from .gcms_literature import (
    GCMSLiteratureDatabase,
    find_materials_with_component,
    get_all_categories,
    get_composition,
    get_major_components,
    get_materials_by_category,
    list_materials,
    MATERIAL_CATEGORIES,
)

__all__ = [
    # Data models
    "Citation",
    "ComponentRange",
    "IFRACategory",
    "IFRARestriction",
    "NaturalComposition",
    "PubChemCompound",
    "RestrictionType",
    "SafetyData",

    # PubChem client
    "PubChemClient",
    "PubChemError",
    "fetch_compound",
    "fetch_compound_by_name",
    "get_cas_number",
    "get_molecular_formula",
    "get_physical_properties",

    # IFRA data
    "IFRADatabase",
    "check_compliance",
    "get_category_description",
    "get_limit",
    "is_restricted",
    "CATEGORY_DESCRIPTIONS",
    "RESTRICTION_REASONS",

    # GC-MS literature
    "GCMSLiteratureDatabase",
    "find_materials_with_component",
    "get_all_categories",
    "get_composition",
    "get_major_components",
    "get_materials_by_category",
    "list_materials",
    "MATERIAL_CATEGORIES",
]
