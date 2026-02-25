# Aromachemical Database Schema

## Overview

Aromachemicals are stored as JSON files in the `data/aromachemicals/` directory. The database can load from a single file or multiple files (e.g., organized by odor family).

## Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `cas_number` | string | CAS Registry Number (e.g., "106-24-1") |
| `name` | string | Common/trade name (e.g., "Geraniol") |

## Optional Fields

### Chemical Properties

| Field | Type | Description |
|-------|------|-------------|
| `iupac_name` | string | IUPAC systematic name |
| `molecular_formula` | string | e.g., "C10H18O" |
| `molecular_weight` | number | g/mol |
| `boiling_point_c` | number | Boiling point in Celsius |
| `vapor_pressure_mmhg` | number | Vapor pressure at 25°C |
| `log_p` | number | Octanol-water partition coefficient |

### Olfactory Properties

| Field | Type | Description |
|-------|------|-------------|
| `odor_description` | string | Freeform description of scent |
| `odor_families` | array[string] | Primary odor categories (see values below) |
| `volatility` | string | "top", "heart", or "base" |
| `odor_threshold_ppm` | number | Detection threshold in air |

#### Valid Odor Families

- `floral`
- `woody`
- `citrus`
- `spicy`
- `herbaceous`
- `balsamic`
- `musk`
- `amber`
- `green`
- `fruity`
- `animalic`
- `marine`
- `earthy`

### Sourcing

| Field | Type | Description |
|-------|------|-------------|
| `suppliers` | array[string] | Known suppliers |
| `cost_per_kg_usd` | number | Approximate cost in USD |
| `natural_occurrence` | array[string] | Natural sources (e.g., ["rose oil", "geranium"]) |

### Regulatory

| Field | Type | Description |
|-------|------|-------------|
| `ifra_restricted` | boolean | Subject to IFRA restrictions |
| `max_usage_percent` | number | Maximum usage level (if restricted) |

## Example

```json
{
  "cas_number": "106-24-1",
  "name": "Geraniol",
  "iupac_name": "(2E)-3,7-dimethylocta-2,6-dien-1-ol",
  "molecular_formula": "C10H18O",
  "molecular_weight": 154.25,
  "odor_description": "Sweet, floral, rose-like with citrus and fruity nuances",
  "odor_families": ["floral"],
  "volatility": "heart",
  "boiling_point_c": 230,
  "natural_occurrence": ["rose oil", "palmarosa oil", "citronella oil"],
  "ifra_restricted": true,
  "max_usage_percent": 5.0
}
```

## File Organization

You can organize chemicals in multiple ways:

1. **Single file**: `common_aromachemicals.json` with all chemicals
2. **By family**: `floral.json`, `woody.json`, `citrus.json`, etc.
3. **By source**: `synthetics.json`, `natural_isolates.json`
4. **By supplier**: `sigma_catalog.json`, `bedoukian.json`

The database loader will read all `.json` files in the directory.

## Importing Data

### From CSV

```python
from src.database import AromachemicalDB, load_from_csv

chemicals = load_from_csv("supplier_catalog.csv")
db = AromachemicalDB()
for chem in chemicals:
    db.add(chem)
db.save(Path("data/aromachemicals/imported.json"))
```

### CSV Column Mapping

The loader recognizes these common column names (case-insensitive):

- CAS: `cas`, `cas_number`, `cas#`, `cas #`
- Name: `name`, `product`, `product name`, `chemical name`
- Odor: `odor`, `odor description`, `description`, `scent`
- Price: `price`, `cost`, `cost_per_kg`, `$/kg`
- Family: `family`, `category`, `odor family`
- Volatility: `volatility`, `note`, `top/heart/base`
