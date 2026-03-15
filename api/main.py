"""
Aroma Lab API - FastAPI backend for fragrance formulation and GC-MS reconstruction
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from pathlib import Path
import json
import re
from typing import Optional
import uuid

from src.models import Aromachemical, Formula, FormulaIngredient, GCMSPeak, NaturalProfile, Volatility, OdorFamily
from src.parsers.csv_parser import CSVParser
from src.parsers.agilent_parser import AgilentParser
from src.parsers.shimadzu_parser import ShimadzuParser
from src.parsers.nist_parser import NISTParser
from src.integrations.smell_reg_client import get_smell_reg_client


def dict_to_aromachemical(d: dict) -> Aromachemical:
    """Convert a raw dict (from JSON) to an Aromachemical model object."""
    return Aromachemical(
        cas_number=d.get("cas_number", ""),
        name=d.get("name", ""),
        odor_description=d.get("odor_description", ""),
        volatility=Volatility(d["volatility"]) if d.get("volatility") else None,
        odor_families=[OdorFamily(f) for f in d.get("odor_families", []) if f in [e.value for e in OdorFamily]],
        cost_per_kg_usd=d.get("cost_per_kg_usd"),
        boiling_point_c=d.get("boiling_point_c"),
        vapor_pressure_mmhg=d.get("vapor_pressure_mmhg"),
        odor_threshold_ppm=d.get("odor_threshold_ppm"),
        ifra_restricted=d.get("ifra_restricted", False),
        max_usage_percent=d.get("max_usage_percent"),
    )


limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app):
    yield
    client = get_smell_reg_client()
    await client.close()


app = FastAPI(
    title="Aroma Lab",
    description="Fragrance reconstruction from GC-MS analysis",
    version="2.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get(
        "CORS_ORIGINS",
        "http://localhost:8000,http://127.0.0.1:8000,http://localhost:8001,http://127.0.0.1:8001"
    ).split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data paths
DATA_DIR = Path(__file__).parent.parent / "data"
AROMACHEMICALS_DIR = DATA_DIR / "aromachemicals"

# Persistence paths
USER_DATA_DIR = DATA_DIR / "user"
FORMULAS_FILE = USER_DATA_DIR / "formulas.json"
PROFILES_FILE = USER_DATA_DIR / "profiles.json"
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_json_store(path: Path) -> dict:
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def _save_json_store(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


# Persistent storage — loaded from disk on startup
formulas_db: dict[str, dict] = _load_json_store(FORMULAS_FILE)
profiles_db: dict[str, dict] = _load_json_store(PROFILES_FILE)

# Available parsers
PARSERS = [NISTParser(), ShimadzuParser(), AgilentParser(), CSVParser()]


_aromachemicals_cache: list[dict] | None = None


def load_aromachemicals() -> list[dict]:
    """Load all aromachemicals from JSON files (cached after first load)."""
    global _aromachemicals_cache
    if _aromachemicals_cache is not None:
        return _aromachemicals_cache
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
    _aromachemicals_cache = chemicals
    return _aromachemicals_cache


def build_chemical_index(chemicals: list[dict]) -> dict:
    """Build search indices for chemicals."""
    by_cas = {}
    by_name = {}
    by_name_fuzzy = {}  # lowercase, normalized

    for c in chemicals:
        cas = c.get("cas_number", "")
        name = c.get("name", "")

        if cas:
            by_cas[cas] = c
        if name:
            by_name[name] = c
            # Fuzzy: lowercase, remove common suffixes
            normalized = name.lower().strip()
            by_name_fuzzy[normalized] = c
            # Also index without common prefixes like d-, l-, dl-, etc.
            for prefix in ["d-", "l-", "dl-", "(+)-", "(-)-", "(±)-", "alpha-", "beta-", "gamma-"]:
                if normalized.startswith(prefix):
                    by_name_fuzzy[normalized[len(prefix):]] = c

    return {"by_cas": by_cas, "by_name": by_name, "by_name_fuzzy": by_name_fuzzy}


def match_peak_to_chemical(peak: dict, index: dict) -> dict:
    """Match a GC-MS peak to a chemical in the database."""
    result = {
        "peak": peak,
        "matched": False,
        "chemical": None,
        "confidence": 0.0,
        "match_type": "none",
        "alternatives": []
    }

    # 1. Try exact CAS match
    cas = peak.get("cas_number") or peak.get("cas")
    if cas and cas in index["by_cas"]:
        result["matched"] = True
        result["chemical"] = index["by_cas"][cas]
        result["confidence"] = 1.0
        result["match_type"] = "cas_exact"
        return result

    # 2. Try exact name match
    name = peak.get("compound_name") or peak.get("compound") or peak.get("name")
    if name and name in index["by_name"]:
        result["matched"] = True
        result["chemical"] = index["by_name"][name]
        result["confidence"] = 0.95
        result["match_type"] = "name_exact"
        return result

    # 3. Try fuzzy name match
    if name:
        name_lower = name.lower().strip()
        # Remove trailing annotations like "(CAS xxx)", numbers, etc.
        name_clean = re.sub(r'\s*\([^)]*\)\s*$', '', name_lower)
        name_clean = re.sub(r'\s*#\d+\s*$', '', name_clean)
        name_clean = re.sub(r',.*$', '', name_clean)  # Take first part before comma
        name_clean = name_clean.strip()

        if name_clean in index["by_name_fuzzy"]:
            result["matched"] = True
            result["chemical"] = index["by_name_fuzzy"][name_clean]
            result["confidence"] = 0.85
            result["match_type"] = "name_fuzzy"
            return result

        # 4. Try partial match (name contains)
        for db_name, chem in index["by_name_fuzzy"].items():
            if name_clean in db_name or db_name in name_clean:
                if len(name_clean) > 4 and len(db_name) > 4:  # Avoid short matches
                    result["matched"] = True
                    result["chemical"] = chem
                    result["confidence"] = 0.70
                    result["match_type"] = "name_partial"
                    return result

    # 5. Find potential alternatives based on odor description keywords
    if name:
        keywords = set(name.lower().split())
        for chem in index["by_cas"].values():
            odor = (chem.get("odor_description") or "").lower()
            if any(kw in odor for kw in keywords if len(kw) > 4):
                result["alternatives"].append({
                    "chemical": chem,
                    "reason": "similar odor keywords"
                })
                if len(result["alternatives"]) >= 3:
                    break

    return result


def parse_gcms_file(content: bytes, filename: str) -> dict:
    """Parse GC-MS file using appropriate parser."""
    import tempfile
    import os

    # Write to temp file for parsers
    suffix = Path(filename).suffix
    with tempfile.NamedTemporaryFile(mode='wb', suffix=suffix, delete=False) as f:
        f.write(content)
        temp_path = Path(f.name)

    try:
        # Find appropriate parser
        for parser in PARSERS:
            if parser.can_parse(temp_path):
                profile = parser.parse(temp_path)
                return {
                    "success": True,
                    "parser": parser.__class__.__name__,
                    "name": profile.name,
                    "peaks": [
                        {
                            "retention_time": p.retention_time,
                            "area_percent": p.area_percent,
                            "compound_name": p.compound_name,
                            "cas_number": p.cas_number,
                            "match_quality": p.match_quality,
                        }
                        for p in profile.peaks
                    ],
                    "peak_count": len(profile.peaks),
                    "notes": profile.notes,
                }

        return {"success": False, "error": "No parser could handle this file format"}
    except Exception:
        return {"success": False, "error": "Failed to parse the uploaded file"}
    finally:
        os.unlink(temp_path)


def load_reference_profiles() -> list[dict]:
    """Load reference natural profiles from JSON files."""
    profiles = []
    profiles_dir = DATA_DIR / "natural_profiles"
    if profiles_dir.exists():
        for json_file in profiles_dir.glob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    data["id"] = json_file.stem
                    profiles.append(data)
            except (json.JSONDecodeError, IOError):
                continue
    return profiles


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


# ==================== Reference Natural Profiles ====================

@app.get("/api/reference-profiles")
async def list_reference_profiles():
    """List all reference natural profiles available for reconstruction.

    These are well-documented natural materials with known GC-MS compositions.
    """
    profiles = load_reference_profiles()
    return {
        "profiles": [
            {
                "id": p.get("id"),
                "name": p.get("name"),
                "botanical_name": p.get("botanical_name"),
                "origin": p.get("origin"),
                "peak_count": len(p.get("peaks", [])),
                "olfactive_description": p.get("olfactive_description", ""),
            }
            for p in profiles
        ],
        "count": len(profiles)
    }


@app.get("/api/reference-profiles/{profile_id}")
async def get_reference_profile(profile_id: str):
    """Get a specific reference profile with full composition."""
    profiles = load_reference_profiles()
    for p in profiles:
        if p.get("id") == profile_id:
            return p
    raise HTTPException(status_code=404, detail="Reference profile not found")


@app.post("/api/reference-profiles/{profile_id}/generate-formula")
async def generate_formula_from_reference(
    profile_id: str,
    name: str = Query(default=None, description="Formula name"),
):
    """Generate a formula from a reference natural profile.

    This creates a formula using the known composition of the natural material,
    matching to available aromachemicals in your database.
    """
    profiles = load_reference_profiles()
    profile = next((p for p in profiles if p.get("id") == profile_id), None)
    if not profile:
        raise HTTPException(status_code=404, detail="Reference profile not found")

    chemicals = load_aromachemicals()
    index = build_chemical_index(chemicals)

    formula_name = name or f"{profile['name']} Recreation"
    ingredients = []
    unmatched = []
    total_matched = 0.0
    total_unmatched = 0.0

    for peak in profile.get("peaks", []):
        area = peak.get("area_percent", 0)
        match = match_peak_to_chemical(peak, index)

        if match["matched"]:
            chem = match["chemical"]
            ingredients.append({
                "cas_number": chem.get("cas_number"),
                "name": chem.get("name"),
                "percentage": round(area, 2),
                "volatility": chem.get("volatility", "heart"),
                "confidence": match["confidence"],
                "match_type": match["match_type"],
                "original_compound": peak.get("compound_name"),
                "range_min": peak.get("range_min"),
                "range_max": peak.get("range_max"),
                "odor_description": chem.get("odor_description", ""),
            })
            total_matched += area
        else:
            unmatched.append({
                "compound_name": peak.get("compound_name", "Unknown"),
                "cas_number": peak.get("cas_number"),
                "area_percent": area,
            })
            total_unmatched += area

    formula_id = str(uuid.uuid4())[:8]
    formula = {
        "id": formula_id,
        "name": formula_name,
        "source_reference_id": profile_id,
        "source_type": "reference_profile",
        "ingredients": ingredients,
        "unmatched": unmatched,
        "total_percentage": round(total_matched, 2),
        "fidelity_score": round(total_matched / (total_matched + total_unmatched) * 100, 1) if (total_matched + total_unmatched) > 0 else 0,
        "key_markers": profile.get("key_markers", {}),
        "olfactive_description": profile.get("olfactive_description"),
    }

    formulas_db[formula_id] = formula
    _save_json_store(FORMULAS_FILE, formulas_db)
    return formula


class FormulaIngredientInput(BaseModel):
    cas_number: str = ""
    name: str
    percentage: float = Field(ge=0, le=100)
    volatility: str = "heart"
    confidence: float = 0.0
    match_type: str = ""
    original_compound: Optional[str] = None
    odor_description: str = ""


class FormulaInput(BaseModel):
    name: str
    ingredients: list[FormulaIngredientInput] = []
    notes: Optional[str] = None


@app.post("/api/formulas")
async def create_formula(formula: FormulaInput):
    """Create a new formula."""
    formula_id = str(uuid.uuid4())[:8]
    formula_dict = formula.model_dump()
    formula_dict["id"] = formula_id
    formulas_db[formula_id] = formula_dict
    _save_json_store(FORMULAS_FILE, formulas_db)
    return {"id": formula_id, "formula": formula_dict}


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
async def update_formula(formula_id: str, formula: FormulaInput):
    """Update a formula."""
    if formula_id not in formulas_db:
        raise HTTPException(status_code=404, detail="Formula not found")
    formula_dict = formula.model_dump()
    formula_dict["id"] = formula_id
    formulas_db[formula_id] = formula_dict
    _save_json_store(FORMULAS_FILE, formulas_db)
    return {"id": formula_id, "formula": formula_dict}


@app.delete("/api/formulas/{formula_id}")
async def delete_formula(formula_id: str):
    """Delete a formula."""
    if formula_id not in formulas_db:
        raise HTTPException(status_code=404, detail="Formula not found")
    del formulas_db[formula_id]
    _save_json_store(FORMULAS_FILE, formulas_db)
    return {"status": "deleted"}


@app.post("/api/upload/gcms")
@limiter.limit("10/minute")
async def upload_gcms(request: Request, file: UploadFile = File(...)):
    """Upload and parse a GC-MS data file using specialized parsers.

    Supports: NIST MS Search, Shimadzu LabSolutions, Agilent ChemStation, CSV
    """
    # Validate file type
    allowed_extensions = {".csv", ".txt", ".mzml", ".xml", ".tsv"}
    filename = file.filename or "unknown"
    file_ext = Path(filename).suffix.lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed: {sorted(allowed_extensions)}",
        )

    content = await file.read()

    # Validate file size (max 10 MB)
    max_size = 10 * 1024 * 1024
    if len(content) > max_size:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 10 MB.")

    # Parse using appropriate parser
    result = parse_gcms_file(content, filename)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to parse file"))

    # Store the profile for later use
    profile_id = str(uuid.uuid4())[:8]
    safe_filename = re.sub(r'[<>&"\'/\\]', '_', Path(filename).name)
    profiles_db[profile_id] = {
        "id": profile_id,
        "filename": safe_filename,
        "parser": result["parser"],
        "name": result["name"],
        "peaks": result["peaks"],
        "peak_count": result["peak_count"],
        "notes": result.get("notes", ""),
    }
    _save_json_store(PROFILES_FILE, profiles_db)

    return {
        "profile_id": profile_id,
        "filename": filename,
        "parser_used": result["parser"],
        "peaks": result["peaks"],
        "peak_count": result["peak_count"],
    }


@app.get("/api/profiles")
async def list_profiles():
    """List all parsed GC-MS profiles."""
    return {"profiles": list(profiles_db.values())}


@app.get("/api/profiles/{profile_id}")
async def get_profile(profile_id: str):
    """Get a specific GC-MS profile."""
    if profile_id not in profiles_db:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profiles_db[profile_id]


@app.post("/api/profiles/{profile_id}/match")
async def match_profile_peaks(profile_id: str):
    """Match all peaks in a profile to chemicals in the database."""
    if profile_id not in profiles_db:
        raise HTTPException(status_code=404, detail="Profile not found")

    profile = profiles_db[profile_id]
    chemicals = load_aromachemicals()
    index = build_chemical_index(chemicals)

    matches = []
    matched_percent = 0.0
    total_percent = 0.0

    for peak in profile["peaks"]:
        area = peak.get("area_percent", 0) or 0
        total_percent += area

        match = match_peak_to_chemical(peak, index)
        if match["matched"]:
            matched_percent += area

        matches.append({
            "retention_time": peak.get("retention_time"),
            "area_percent": area,
            "compound_name": peak.get("compound_name"),
            "cas_number": peak.get("cas_number"),
            "matched": match["matched"],
            "matched_chemical": match["chemical"],
            "confidence": match["confidence"],
            "match_type": match["match_type"],
            "alternatives": match["alternatives"][:3] if match["alternatives"] else [],
        })

    fidelity = (matched_percent / total_percent * 100) if total_percent > 0 else 0

    return {
        "profile_id": profile_id,
        "matches": matches,
        "total_peaks": len(matches),
        "matched_peaks": sum(1 for m in matches if m["matched"]),
        "fidelity_percent": round(fidelity, 1),
        "matched_area_percent": round(matched_percent, 1),
        "total_area_percent": round(total_percent, 1),
    }


@app.post("/api/profiles/{profile_id}/generate-formula")
async def generate_formula_from_profile(
    profile_id: str,
    name: str = Query(default=None, description="Formula name"),
    min_percent: float = Query(default=0.5, description="Minimum area% to include"),
):
    """Generate a formula from a GC-MS profile by matching peaks to available chemicals."""
    if profile_id not in profiles_db:
        raise HTTPException(status_code=404, detail="Profile not found")

    profile = profiles_db[profile_id]
    chemicals = load_aromachemicals()
    index = build_chemical_index(chemicals)

    formula_name = name or f"{profile['name']} Recreation"
    ingredients = []
    unmatched = []
    total_matched = 0.0
    total_unmatched = 0.0

    # Sort peaks by area descending
    sorted_peaks = sorted(
        profile["peaks"],
        key=lambda p: p.get("area_percent", 0) or 0,
        reverse=True
    )

    for peak in sorted_peaks:
        area = peak.get("area_percent", 0) or 0
        if area < min_percent:
            continue

        match = match_peak_to_chemical(peak, index)

        if match["matched"]:
            chem = match["chemical"]
            ingredients.append({
                "cas_number": chem.get("cas_number"),
                "name": chem.get("name"),
                "percentage": round(area, 2),
                "volatility": chem.get("volatility", "heart"),
                "confidence": match["confidence"],
                "match_type": match["match_type"],
                "original_compound": peak.get("compound_name"),
                "odor_description": chem.get("odor_description", ""),
            })
            total_matched += area
        else:
            unmatched.append({
                "compound_name": peak.get("compound_name", "Unknown"),
                "cas_number": peak.get("cas_number"),
                "area_percent": area,
                "retention_time": peak.get("retention_time"),
                "alternatives": [
                    {"name": a["chemical"].get("name"), "reason": a["reason"]}
                    for a in match["alternatives"][:3]
                ]
            })
            total_unmatched += area

    # Create and store formula
    formula_id = str(uuid.uuid4())[:8]
    formula = {
        "id": formula_id,
        "name": formula_name,
        "source_profile_id": profile_id,
        "ingredients": ingredients,
        "unmatched": unmatched,
        "total_percentage": round(total_matched, 2),
        "fidelity_score": round(total_matched / (total_matched + total_unmatched) * 100, 1) if (total_matched + total_unmatched) > 0 else 0,
        "unmatched_percentage": round(total_unmatched, 2),
    }

    formulas_db[formula_id] = formula
    _save_json_store(FORMULAS_FILE, formulas_db)

    return formula


@app.get("/api/search/chemicals")
async def search_chemicals_inline(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(default=10, le=50),
):
    """Quick inline search for chemicals - for use in formula builder.

    Searches by name, CAS, odor description, and odor families.
    """
    chemicals = load_aromachemicals()
    q_lower = q.lower()

    results = []
    for c in chemicals:
        score = 0
        name = c.get("name", "").lower()
        cas = c.get("cas_number", "").lower()
        odor = c.get("odor_description", "").lower()
        families = " ".join(c.get("odor_families", [])).lower()

        # Exact name match
        if q_lower == name:
            score = 100
        # Name starts with
        elif name.startswith(q_lower):
            score = 90
        # Name contains
        elif q_lower in name:
            score = 70
        # CAS match
        elif q_lower in cas:
            score = 80
        # Odor description contains
        elif q_lower in odor:
            score = 50
        # Odor family match
        elif q_lower in families:
            score = 40

        if score > 0:
            results.append({"chemical": c, "score": score})

    # Sort by score descending
    results.sort(key=lambda x: x["score"], reverse=True)

    return {
        "query": q,
        "results": [r["chemical"] for r in results[:limit]],
        "count": len(results[:limit]),
    }


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
        from src.formulator.optimizer import FormulaOptimizer, ApplicationType
        from src.models import Formula, FormulaIngredient, Aromachemical, Volatility, OdorFamily
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"Optimizer not available: {e}")

    formula_data = formulas_db[formula_id]
    chemicals = load_aromachemicals()
    cas_to_chem = {c["cas_number"]: c for c in chemicals}

    # Convert to model objects
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
        from src.formulator.optimizer import FormulaOptimizer, ApplicationType
        from src.models import Formula, FormulaIngredient, Aromachemical, Volatility, OdorFamily
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"Optimizer not available: {e}")

    # Parse application type
    try:
        app_type = ApplicationType(application)
    except ValueError:
        app_type = ApplicationType.FINE_FRAGRANCE

    formula_data = formulas_db[formula_id]
    chemicals = load_aromachemicals()
    cas_to_chem = {c["cas_number"]: c for c in chemicals}

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
        from src.formulator.optimizer import FormulaOptimizer
        from src.models import Formula, FormulaIngredient, Aromachemical, Volatility, OdorFamily
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"Optimizer not available: {e}")

    formula_data = formulas_db[formula_id]
    chemicals = load_aromachemicals()
    cas_to_chem = {c["cas_number"]: c for c in chemicals}

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
        from src.formulator.optimizer import FormulaOptimizer
        from src.models import Formula, FormulaIngredient, Aromachemical, Volatility, OdorFamily
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"Optimizer not available: {e}")

    formula_data = formulas_db[formula_id]
    chemicals = load_aromachemicals()
    cas_to_chem = {c["cas_number"]: c for c in chemicals}

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
        from src.formulator.optimizer import FormulaOptimizer, ApplicationType
        from src.models import Formula, FormulaIngredient, Aromachemical, Volatility, OdorFamily
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"Optimizer not available: {e}")

    try:
        app_type = ApplicationType(application)
    except ValueError:
        app_type = ApplicationType.FINE_FRAGRANCE

    formula_data = formulas_db[formula_id]
    chemicals = load_aromachemicals()
    cas_to_chem = {c["cas_number"]: c for c in chemicals}

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


# ==================== Health & Integration Endpoints ====================

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "aroma-lab"}


@app.get("/api/integration/status")
async def integration_status():
    """Check connectivity to sibling services."""
    client = get_smell_reg_client()
    smell_reg_healthy = await client.check_health()
    return {
        "smell_reg": {
            "connected": smell_reg_healthy,
        }
    }


@app.get("/api/ifra-restrictions")
async def get_ifra_restrictions():
    """Return IFRA restriction data from local JSON.

    This endpoint allows smell-reg to fetch restrictions via HTTP
    instead of requiring filesystem access.
    """
    ifra_path = DATA_DIR / "literature" / "ifra_restrictions.json"
    if not ifra_path.exists():
        raise HTTPException(status_code=404, detail="IFRA restrictions data not found")
    with open(ifra_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ==================== Cross-Service Compliance ====================

VALID_PRODUCT_TYPES = {
    "fine_fragrance", "body_lotion", "shower_gel", "shampoo", "deodorant",
    "candle", "soap", "hand_cream", "lip_product", "air_freshener",
    "face_cream", "baby_product", "hair_styling", "mouthwash",
    "household_cleaner", "reed_diffuser",
}
VALID_MARKETS = {"us", "eu", "uk", "ca", "jp", "cn", "au", "br"}


class ComplianceCheckBody(BaseModel):
    product_type: str
    markets: list[str]
    fragrance_concentration: float = Field(default=100.0, gt=0, le=100)
    is_leave_on: bool = True


@app.post("/api/formulas/{formula_id}/compliance-check")
@limiter.limit("10/minute")
async def check_formula_compliance(request: Request, formula_id: str, body: ComplianceCheckBody):
    """Run a full regulatory compliance check on a formula via smell-reg.

    This proxies the formula to smell-reg's compliance engine for
    IFRA, allergen, VOC, and market-specific checks.
    Returns 503 if smell-reg is unavailable.
    """
    if body.product_type not in VALID_PRODUCT_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid product type: {body.product_type}")
    invalid_markets = set(body.markets) - VALID_MARKETS
    if invalid_markets:
        raise HTTPException(status_code=400, detail=f"Invalid markets: {sorted(invalid_markets)}")

    if formula_id not in formulas_db:
        raise HTTPException(status_code=404, detail="Formula not found")

    formula = formulas_db[formula_id]
    ingredients = formula.get("ingredients", [])

    # Build the payload in smell-reg's expected format
    formula_payload = {
        "name": formula.get("name", "Unnamed"),
        "ingredients": [
            {
                "cas_number": ing.get("cas_number", ""),
                "name": ing.get("name", ""),
                "percentage": ing.get("percentage", 0),
            }
            for ing in ingredients
            if ing.get("cas_number")
        ],
    }

    client = get_smell_reg_client()
    result = await client.check_compliance(
        formula_data=formula_payload,
        product_type=body.product_type,
        markets=body.markets,
        fragrance_concentration=body.fragrance_concentration,
        is_leave_on=body.is_leave_on,
    )

    if result is None:
        raise HTTPException(
            status_code=503,
            detail="Regulatory compliance service (smell-reg) is unavailable",
        )

    return result


# ==================== Enriched Chemical Data ====================

@app.get("/api/aromachemicals/{cas_number}/enriched")
@limiter.limit("30/minute")
async def get_enriched_aromachemical(request: Request, cas_number: str):
    """Get chemical data enriched with regulatory info from smell-reg.

    Returns chemical properties from aroma-lab merged with regulatory
    data from smell-reg (if available). Falls back to chemical-only
    data if smell-reg is unreachable.
    """
    if not re.match(r"^\d{1,7}-\d{2}-\d$", cas_number):
        raise HTTPException(status_code=400, detail="Invalid CAS number format")

    chemicals = load_aromachemicals()
    chemical = None
    for chem in chemicals:
        if chem.get("cas_number") == cas_number:
            chemical = chem
            break

    if chemical is None:
        raise HTTPException(status_code=404, detail="Aromachemical not found")

    result = {**chemical, "regulatory": None}

    client = get_smell_reg_client()
    reg_info = await client.get_regulatory_info(cas_number)
    if reg_info is not None:
        result["regulatory"] = reg_info

    return result


# Mount static files for UI assets
ui_dir = Path(__file__).parent.parent / "ui"
if ui_dir.exists():
    app.mount("/static", StaticFiles(directory=str(ui_dir)), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
