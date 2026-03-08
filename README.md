# Aroma Lab

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/fusillibernie/aroma-lab?quickstart=1)
[![Open in Gitpod](https://gitpod.io/button/open-in-gitpod.svg)](https://gitpod.io/#https://github.com/fusillibernie/aroma-lab)

> **Try it now** -- Click either badge above to launch the app in your browser. No install needed. The server starts automatically and opens the UI on port 8000.

A fragrance formulation tool that uses GC-MS data analysis and aromachemical matching to recreate natural aromatic profiles with synthetic ingredients.

## Overview

Aroma Lab enables perfumers and flavor chemists to:
- **Parse GC-MS Data** - Import chromatography data from Agilent, Shimadzu, NIST, and mzML formats
- **Match Compounds** - Identify peaks and match them to obtainable aromachemicals
- **Generate Formulas** - Create synthetic reconstructions of natural profiles
- **Optimize Formulas** - Balance cost, compliance, and character
- **Check Compliance** - Validate against IFRA restrictions

## Installation

```bash
pip install -e .

# For development
pip install -e ".[dev]"

# For molecular structure features (optional)
pip install -e ".[chemistry]"
```

## Quick Start

### Command Line

```bash
# Search the aromachemical database
aroma-lab db search "rose"

# Show details for a specific compound
aroma-lab db show "106-22-9"

# View database statistics
aroma-lab db stats

# Import aromachemicals from CSV
aroma-lab db import aromachemicals.csv -o data/aromachemicals/custom.json

# Show variations of a natural material
aroma-lab variations "rose oil"
```

### Python API

```python
from src.models import Aromachemical, Formula, FormulaIngredient, NaturalProfile, GCMSPeak
from src.formulator import FormulatorEngine, FormulationConfig
from src.matching import AromachemicalMatcher
from src.database import AromachemicalDB

# Load aromachemical database
db = AromachemicalDB()
chemicals = db.get_all()

# Create matcher and formulator
matcher = AromachemicalMatcher(chemicals)
engine = FormulatorEngine(matcher, FormulationConfig(
    min_peak_percent=0.1,
    ifra_compliant=True,
    max_cost_per_kg=500.0,
))

# Create a profile from GC-MS data
profile = NaturalProfile(
    name="Bulgarian Rose Otto",
    botanical_name="Rosa damascena",
    origin="Bulgaria",
    peaks=[
        GCMSPeak(retention_time=12.5, area_percent=35.0, cas_number="106-22-9", compound_name="Citronellol"),
        GCMSPeak(retention_time=14.2, area_percent=22.0, cas_number="106-24-1", compound_name="Geraniol"),
        GCMSPeak(retention_time=16.8, area_percent=8.0, cas_number="141-12-8", compound_name="Nerol"),
        # ... more peaks
    ]
)

# Generate formula
formula = engine.formulate(profile, name="Rose Recreation")

print(f"Formula: {formula.name}")
print(f"Fidelity: {formula.fidelity_score:.1f}%")
print(f"Cost: ${formula.total_cost_per_kg}/kg")

for ingredient in formula.ingredients:
    print(f"  {ingredient.percentage:.1f}% {ingredient.aromachemical.name}")
```

### REST API

```bash
# Start the API server
uvicorn api.main:app --reload

# Open http://localhost:8000 for the web UI
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/aromachemicals` | GET | List aromachemicals (filter by family, volatility, search) |
| `/api/aromachemicals/{cas}` | GET | Get aromachemical by CAS number |
| `/api/odor-families` | GET | List all odor families |
| `/api/formulas` | GET/POST | List or create formulas |
| `/api/formulas/{id}` | GET/PUT/DELETE | Manage a specific formula |
| `/api/formulas/{id}/ifra-check` | GET | Check IFRA compliance |
| `/api/formulas/{id}/optimize-cost` | POST | Optimize for cost target |
| `/api/formulas/{id}/volatility-analysis` | GET | Analyze note distribution |
| `/api/formulas/{id}/longevity-estimate` | GET | Estimate longevity/sillage |
| `/api/formulas/{id}/suggestions` | GET | Get modification suggestions |
| `/api/pyramid/{id}` | GET | Get odor pyramid visualization data |
| `/api/upload/gcms` | POST | Upload and parse GC-MS file |

## Project Structure

```
aroma-lab/
├── src/
│   ├── cli.py              # Command-line interface
│   ├── models.py           # Core data models
│   ├── database/           # Aromachemical database
│   │   ├── manager.py      # Database operations
│   │   ├── loader.py       # CSV/JSON loading
│   │   └── updater.py      # PubChem data enrichment
│   ├── formulator/         # Formula generation
│   │   ├── engine.py       # Core formulation logic
│   │   └── optimizer.py    # Cost/compliance optimization
│   ├── matching/           # Compound matching
│   │   ├── matcher.py      # Peak-to-chemical matching
│   │   └── identifier.py   # Unknown compound identification
│   ├── parsers/            # GC-MS file parsers
│   │   ├── agilent_parser.py
│   │   ├── shimadzu_parser.py
│   │   ├── nist_parser.py
│   │   ├── mzml_parser.py
│   │   └── csv_parser.py
│   ├── literature/         # External data sources
│   │   ├── ifra_data.py    # IFRA restrictions
│   │   ├── pubchem_client.py
│   │   └── gcms_literature.py
│   └── variations/         # Natural material variations
├── api/                    # FastAPI backend
│   └── main.py
├── ui/                     # Web interface
├── data/
│   ├── aromachemicals/     # Aromachemical database (JSON)
│   ├── gcms_profiles/      # Sample GC-MS profiles
│   └── literature/         # IFRA data, compositions
└── tests/
```

## Core Models

### Aromachemical
```python
@dataclass
class Aromachemical:
    cas_number: str
    name: str
    odor_description: str
    odor_families: list[OdorFamily]  # floral, woody, citrus, etc.
    volatility: Volatility           # top, heart, base
    boiling_point_c: float
    cost_per_kg_usd: float
    ifra_restricted: bool
    max_usage_percent: float
```

### Formula
```python
@dataclass
class Formula:
    name: str
    ingredients: list[FormulaIngredient]
    target_natural: NaturalProfile  # Original material being reconstructed
    total_cost_per_kg: float
    fidelity_score: float           # 0-100% match to target
```

### GCMSPeak
```python
@dataclass
class GCMSPeak:
    retention_time: float
    area_percent: float
    cas_number: str
    compound_name: str
    match_quality: float  # Library match score 0-100
```

## Odor Families

The system classifies aromachemicals into these odor families:
- Floral, Woody, Citrus, Spicy, Herbaceous
- Balsamic, Musk, Amber, Green, Fruity
- Animalic, Marine, Earthy

## GC-MS Parser Support

| Format | Parser | Status |
|--------|--------|--------|
| Agilent ChemStation | `agilent_parser.py` | Full support |
| Shimadzu LabSolutions | `shimadzu_parser.py` | Full support |
| NIST MS Search | `nist_parser.py` | Full support |
| mzML (Open format) | `mzml_parser.py` | Full support |
| CSV (Generic) | `csv_parser.py` | Basic support |

## Formula Optimization

The optimizer can adjust formulas for:

1. **Cost Optimization** - Find cheaper substitutes while maintaining character
2. **IFRA Compliance** - Ensure all ingredients are within regulatory limits
3. **Volatility Balance** - Achieve desired top/heart/base distribution
4. **Longevity Enhancement** - Improve lasting power and sillage

```python
from src.formulator.optimizer import FormulaOptimizer, ApplicationType

optimizer = FormulaOptimizer(aromachemical_db)

# Check IFRA compliance
is_compliant, issues, adjusted = optimizer.check_ifra_compliance(
    formula,
    ApplicationType.FINE_FRAGRANCE
)

# Optimize cost
result = optimizer.optimize_cost(formula, target_cost=200.0, min_fidelity=80.0)

# Analyze volatility
analysis = optimizer.analyze_volatility(formula)
print(f"Top: {analysis.top_note_percent}%")
print(f"Heart: {analysis.heart_note_percent}%")
print(f"Base: {analysis.base_note_percent}%")
```

## Testing

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest --cov=src tests/

# Run specific test file
pytest tests/test_optimizer.py -v
```

## Related Projects

- **smell-reg** - Regulatory compliance application that imports IFRA data and models from this project

## Data Sources

- **PubChem** - Chemical properties via `pubchem_client.py`
- **IFRA** - Restriction limits via `ifra_data.py`
- **Literature** - GC-MS compositions from scientific papers

## License

Internal use only.

## Contributing

1. Add aromachemicals to `data/aromachemicals/`
2. Add GC-MS profiles to `data/gcms_profiles/`
3. Run tests before committing
