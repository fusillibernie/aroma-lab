"""
Aroma Lab API - FastAPI backend for fragrance formulation
"""
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pathlib import Path
import json
from typing import Optional
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from models import Aromachemical, Formula, FormulaIngredient

app = FastAPI(
    title="Aroma Lab",
    description="Fragrance formulation and GC-MS analysis tool",
    version="1.0.0"
)

# Data paths
DATA_DIR = Path(__file__).parent.parent / "data"
AROMACHEMICALS_DIR = DATA_DIR / "aromachemicals"

# In-memory storage for formulas (could be replaced with database)
formulas_db: dict[str, dict] = {}


def load_aromachemicals() -> list[dict]:
    """Load all aromachemicals from JSON files."""
    chemicals = []
    if AROMACHEMICALS_DIR.exists():
        for json_file in AROMACHEMICALS_DIR.glob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        chemicals.extend(data)
            except (json.JSONDecodeError, IOError):
                continue
    return chemicals


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main UI."""
    ui_path = Path(__file__).parent.parent / "ui" / "index.html"
    if ui_path.exists():
        return HTMLResponse(content=ui_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Aroma Lab</h1><p>UI not found. Please check ui/index.html</p>")


@app.get("/api/aromachemicals")
async def get_aromachemicals(
    family: Optional[str] = None,
    volatility: Optional[str] = None,
    search: Optional[str] = None
):
    """Get all aromachemicals, with optional filtering."""
    chemicals = load_aromachemicals()

    if family:
        chemicals = [c for c in chemicals if family.lower() in [f.lower() for f in c.get("odor_families", [])]]

    if volatility:
        chemicals = [c for c in chemicals if c.get("volatility", "").lower() == volatility.lower()]

    if search:
        search_lower = search.lower()
        chemicals = [c for c in chemicals if
                    search_lower in c.get("name", "").lower() or
                    search_lower in c.get("odor_description", "").lower() or
                    search_lower in c.get("cas_number", "").lower()]

    return {"chemicals": chemicals, "count": len(chemicals)}


@app.get("/api/aromachemicals/{cas_number}")
async def get_aromachemical(cas_number: str):
    """Get a specific aromachemical by CAS number."""
    chemicals = load_aromachemicals()
    for chem in chemicals:
        if chem.get("cas_number") == cas_number:
            return chem
    raise HTTPException(status_code=404, detail="Aromachemical not found")


@app.get("/api/odor-families")
async def get_odor_families():
    """Get list of all odor families."""
    families = set()
    for chem in load_aromachemicals():
        for family in chem.get("odor_families", []):
            families.add(family)
    return {"families": sorted(list(families))}


@app.post("/api/formulas")
async def create_formula(formula: dict):
    """Create a new formula."""
    import uuid
    formula_id = str(uuid.uuid4())[:8]
    formula["id"] = formula_id
    formulas_db[formula_id] = formula
    return {"id": formula_id, "formula": formula}


@app.get("/api/formulas")
async def list_formulas():
    """List all formulas."""
    return {"formulas": list(formulas_db.values())}


@app.get("/api/formulas/{formula_id}")
async def get_formula(formula_id: str):
    """Get a specific formula."""
    if formula_id not in formulas_db:
        raise HTTPException(status_code=404, detail="Formula not found")
    return formulas_db[formula_id]


@app.put("/api/formulas/{formula_id}")
async def update_formula(formula_id: str, formula: dict):
    """Update a formula."""
    if formula_id not in formulas_db:
        raise HTTPException(status_code=404, detail="Formula not found")
    formula["id"] = formula_id
    formulas_db[formula_id] = formula
    return {"id": formula_id, "formula": formula}


@app.delete("/api/formulas/{formula_id}")
async def delete_formula(formula_id: str):
    """Delete a formula."""
    if formula_id not in formulas_db:
        raise HTTPException(status_code=404, detail="Formula not found")
    del formulas_db[formula_id]
    return {"status": "deleted"}


@app.post("/api/upload/gcms")
async def upload_gcms(file: UploadFile = File(...)):
    """Upload and parse a GC-MS data file."""
    content = await file.read()
    filename = file.filename or "unknown"

    # Determine file type and parse
    if filename.endswith(".csv"):
        # Parse CSV GC-MS data
        lines = content.decode("utf-8").splitlines()
        peaks = []
        for i, line in enumerate(lines[1:], start=1):  # Skip header
            parts = line.split(",")
            if len(parts) >= 2:
                try:
                    peaks.append({
                        "retention_time": float(parts[0]),
                        "area": float(parts[1]) if len(parts) > 1 else 0,
                        "compound": parts[2] if len(parts) > 2 else f"Peak {i}"
                    })
                except ValueError:
                    continue
        return {"filename": filename, "peaks": peaks, "peak_count": len(peaks)}

    return {"filename": filename, "message": "File uploaded, parsing not implemented for this format"}


@app.get("/api/pyramid/{formula_id}")
async def get_odor_pyramid(formula_id: str):
    """Get odor pyramid visualization data for a formula."""
    if formula_id not in formulas_db:
        raise HTTPException(status_code=404, detail="Formula not found")

    formula = formulas_db[formula_id]
    chemicals = load_aromachemicals()
    cas_to_chem = {c["cas_number"]: c for c in chemicals}

    pyramid = {"top": [], "heart": [], "base": []}

    for ingredient in formula.get("ingredients", []):
        cas = ingredient.get("cas_number")
        if cas in cas_to_chem:
            chem = cas_to_chem[cas]
            volatility = chem.get("volatility", "heart")
            pyramid[volatility].append({
                "name": chem.get("name"),
                "percentage": ingredient.get("percentage", 0),
                "odor": chem.get("odor_description", "")
            })

    return pyramid


# ==================== Optimization Endpoints ====================

@app.post("/api/formulas/{formula_id}/optimize-cost")
async def optimize_formula_cost(formula_id: str, target_cost: float, min_fidelity: float = 80.0):
    """Optimize formula to meet cost target while maintaining character."""
    if formula_id not in formulas_db:
        raise HTTPException(status_code=404, detail="Formula not found")

    # Import optimizer
    try:
        from formulator.optimizer import FormulaOptimizer, ApplicationType
        from models import Formula, FormulaIngredient, Aromachemical, Volatility, OdorFamily
    except ImportError as e:
        return {"error": f"Optimizer not available: {e}"}

    formula_data = formulas_db[formula_id]
    chemicals = load_aromachemicals()
    cas_to_chem = {c["cas_number"]: c for c in chemicals}

    # Convert to model objects
    def dict_to_aromachemical(d: dict) -> Aromachemical:
        return Aromachemical(
            cas_number=d.get("cas_number", ""),
            name=d.get("name", ""),
            odor_description=d.get("odor_description", ""),
            volatility=Volatility(d["volatility"]) if d.get("volatility") else None,
            odor_families=[OdorFamily(f) for f in d.get("odor_families", []) if f in [e.value for e in OdorFamily]],
            cost_per_kg_usd=d.get("cost_per_kg_usd"),
            boiling_point_c=d.get("boiling_point_c"),
            ifra_restricted=d.get("ifra_restricted", False),
            max_usage_percent=d.get("max_usage_percent"),
        )

    ac_objects = [dict_to_aromachemical(c) for c in chemicals]
    optimizer = FormulaOptimizer(ac_objects)

    # Build formula object
    ingredients = []
    for ing in formula_data.get("ingredients", []):
        cas = ing.get("cas_number")
        if cas in cas_to_chem:
            ac = dict_to_aromachemical(cas_to_chem[cas])
            ingredients.append(FormulaIngredient(
                aromachemical=ac,
                percentage=ing.get("percentage", 0),
            ))

    formula = Formula(
        name=formula_data.get("name", "Unnamed"),
        ingredients=ingredients,
    )

    # Optimize
    result = optimizer.optimize_cost(formula, target_cost, min_fidelity)

    return {
        "original_cost": optimizer._calculate_cost(result.original_formula),
        "optimized_cost": optimizer._calculate_cost(result.optimized_formula),
        "cost_reduction_percent": result.cost_reduction_percent,
        "fidelity_change": result.fidelity_change,
        "changes": result.changes_made,
        "warnings": result.warnings,
    }


@app.get("/api/formulas/{formula_id}/ifra-check")
async def check_ifra_compliance(formula_id: str, application: str = "fine_fragrance"):
    """Check IFRA compliance for a formula."""
    if formula_id not in formulas_db:
        raise HTTPException(status_code=404, detail="Formula not found")

    try:
        from formulator.optimizer import FormulaOptimizer, ApplicationType
        from models import Formula, FormulaIngredient, Aromachemical, Volatility, OdorFamily
    except ImportError as e:
        return {"error": f"Optimizer not available: {e}"}

    # Parse application type
    try:
        app_type = ApplicationType(application)
    except ValueError:
        app_type = ApplicationType.FINE_FRAGRANCE

    formula_data = formulas_db[formula_id]
    chemicals = load_aromachemicals()
    cas_to_chem = {c["cas_number"]: c for c in chemicals}

    def dict_to_aromachemical(d: dict) -> Aromachemical:
        return Aromachemical(
            cas_number=d.get("cas_number", ""),
            name=d.get("name", ""),
            odor_description=d.get("odor_description", ""),
            volatility=Volatility(d["volatility"]) if d.get("volatility") else None,
            odor_families=[OdorFamily(f) for f in d.get("odor_families", []) if f in [e.value for e in OdorFamily]],
            ifra_restricted=d.get("ifra_restricted", False),
            max_usage_percent=d.get("max_usage_percent"),
        )

    ac_objects = [dict_to_aromachemical(c) for c in chemicals]
    optimizer = FormulaOptimizer(ac_objects)

    ingredients = []
    for ing in formula_data.get("ingredients", []):
        cas = ing.get("cas_number")
        if cas in cas_to_chem:
            ac = dict_to_aromachemical(cas_to_chem[cas])
            ingredients.append(FormulaIngredient(
                aromachemical=ac,
                percentage=ing.get("percentage", 0),
            ))

    formula = Formula(name=formula_data.get("name", ""), ingredients=ingredients)
    is_compliant, issues, adjusted = optimizer.check_ifra_compliance(formula, app_type)

    return {
        "is_compliant": is_compliant,
        "application": application,
        "issues": issues,
        "adjusted_formula": {
            "name": adjusted.name,
            "ingredients": [
                {"name": i.aromachemical.name, "percentage": i.percentage, "notes": i.notes}
                for i in adjusted.ingredients
            ]
        } if not is_compliant else None,
    }


@app.get("/api/formulas/{formula_id}/volatility-analysis")
async def analyze_volatility(formula_id: str):
    """Analyze volatility distribution of a formula."""
    if formula_id not in formulas_db:
        raise HTTPException(status_code=404, detail="Formula not found")

    try:
        from formulator.optimizer import FormulaOptimizer
        from models import Formula, FormulaIngredient, Aromachemical, Volatility, OdorFamily
    except ImportError as e:
        return {"error": f"Optimizer not available: {e}"}

    formula_data = formulas_db[formula_id]
    chemicals = load_aromachemicals()
    cas_to_chem = {c["cas_number"]: c for c in chemicals}

    def dict_to_aromachemical(d: dict) -> Aromachemical:
        return Aromachemical(
            cas_number=d.get("cas_number", ""),
            name=d.get("name", ""),
            volatility=Volatility(d["volatility"]) if d.get("volatility") else None,
            odor_families=[OdorFamily(f) for f in d.get("odor_families", []) if f in [e.value for e in OdorFamily]],
        )

    ac_objects = [dict_to_aromachemical(c) for c in chemicals]
    optimizer = FormulaOptimizer(ac_objects)

    ingredients = []
    for ing in formula_data.get("ingredients", []):
        cas = ing.get("cas_number")
        if cas in cas_to_chem:
            ac = dict_to_aromachemical(cas_to_chem[cas])
            ingredients.append(FormulaIngredient(
                aromachemical=ac,
                percentage=ing.get("percentage", 0),
            ))

    formula = Formula(name=formula_data.get("name", ""), ingredients=ingredients)
    analysis = optimizer.analyze_volatility(formula)

    return {
        "top_note_percent": analysis.top_note_percent,
        "heart_note_percent": analysis.heart_note_percent,
        "base_note_percent": analysis.base_note_percent,
        "balance_score": analysis.balance_score,
        "recommendations": analysis.recommendations,
    }


@app.get("/api/formulas/{formula_id}/longevity-estimate")
async def estimate_longevity(formula_id: str):
    """Estimate longevity and sillage for a formula."""
    if formula_id not in formulas_db:
        raise HTTPException(status_code=404, detail="Formula not found")

    try:
        from formulator.optimizer import FormulaOptimizer
        from models import Formula, FormulaIngredient, Aromachemical, Volatility, OdorFamily
    except ImportError as e:
        return {"error": f"Optimizer not available: {e}"}

    formula_data = formulas_db[formula_id]
    chemicals = load_aromachemicals()
    cas_to_chem = {c["cas_number"]: c for c in chemicals}

    def dict_to_aromachemical(d: dict) -> Aromachemical:
        return Aromachemical(
            cas_number=d.get("cas_number", ""),
            name=d.get("name", ""),
            volatility=Volatility(d["volatility"]) if d.get("volatility") else None,
            odor_families=[OdorFamily(f) for f in d.get("odor_families", []) if f in [e.value for e in OdorFamily]],
            boiling_point_c=d.get("boiling_point_c"),
            vapor_pressure_mmhg=d.get("vapor_pressure_mmhg"),
            odor_threshold_ppm=d.get("odor_threshold_ppm"),
        )

    ac_objects = [dict_to_aromachemical(c) for c in chemicals]
    optimizer = FormulaOptimizer(ac_objects)

    ingredients = []
    for ing in formula_data.get("ingredients", []):
        cas = ing.get("cas_number")
        if cas in cas_to_chem:
            ac = dict_to_aromachemical(cas_to_chem[cas])
            ingredients.append(FormulaIngredient(
                aromachemical=ac,
                percentage=ing.get("percentage", 0),
            ))

    formula = Formula(name=formula_data.get("name", ""), ingredients=ingredients)
    estimate = optimizer.estimate_longevity(formula)

    return {
        "initial_impact": estimate.initial_impact,
        "longevity_hours": estimate.longevity_hours,
        "sillage_rating": estimate.sillage_rating,
        "dry_down_quality": estimate.dry_down_quality,
        "notes": estimate.notes,
    }


@app.get("/api/formulas/{formula_id}/suggestions")
async def get_suggestions(formula_id: str, application: str = "fine_fragrance"):
    """Get modification suggestions for a formula based on application type."""
    if formula_id not in formulas_db:
        raise HTTPException(status_code=404, detail="Formula not found")

    try:
        from formulator.optimizer import FormulaOptimizer, ApplicationType
        from models import Formula, FormulaIngredient, Aromachemical, Volatility, OdorFamily
    except ImportError as e:
        return {"error": f"Optimizer not available: {e}"}

    try:
        app_type = ApplicationType(application)
    except ValueError:
        app_type = ApplicationType.FINE_FRAGRANCE

    formula_data = formulas_db[formula_id]
    chemicals = load_aromachemicals()
    cas_to_chem = {c["cas_number"]: c for c in chemicals}

    def dict_to_aromachemical(d: dict) -> Aromachemical:
        return Aromachemical(
            cas_number=d.get("cas_number", ""),
            name=d.get("name", ""),
            volatility=Volatility(d["volatility"]) if d.get("volatility") else None,
            odor_families=[OdorFamily(f) for f in d.get("odor_families", []) if f in [e.value for e in OdorFamily]],
            boiling_point_c=d.get("boiling_point_c"),
            ifra_restricted=d.get("ifra_restricted", False),
            max_usage_percent=d.get("max_usage_percent"),
        )

    ac_objects = [dict_to_aromachemical(c) for c in chemicals]
    optimizer = FormulaOptimizer(ac_objects)

    ingredients = []
    for ing in formula_data.get("ingredients", []):
        cas = ing.get("cas_number")
        if cas in cas_to_chem:
            ac = dict_to_aromachemical(cas_to_chem[cas])
            ingredients.append(FormulaIngredient(
                aromachemical=ac,
                percentage=ing.get("percentage", 0),
            ))

    formula = Formula(name=formula_data.get("name", ""), ingredients=ingredients)
    suggestions = optimizer.suggest_modifications(formula, app_type)

    return {
        "application": application,
        "suggestions": suggestions,
    }


# Mount static files for UI assets
ui_dir = Path(__file__).parent.parent / "ui"
if ui_dir.exists():
    app.mount("/static", StaticFiles(directory=str(ui_dir)), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
