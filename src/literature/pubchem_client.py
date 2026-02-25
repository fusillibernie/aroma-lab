"""PubChem API client for fetching compound data.

This module provides functions to fetch compound information from the
PubChem database, including CAS numbers, molecular formulas, synonyms,
and physical properties.
"""

import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .data_models import PubChemCompound

logger = logging.getLogger(__name__)

# PubChem API base URL
PUBCHEM_BASE_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"

# Default cache directory
DEFAULT_CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "literature" / "pubchem_cache"

# Rate limiting: PubChem allows 5 requests per second
REQUEST_DELAY = 0.2  # 200ms between requests


class PubChemError(Exception):
    """Exception raised for PubChem API errors."""
    pass


class PubChemClient:
    """Client for fetching compound data from PubChem API.

    Provides caching to avoid repeated API calls and respects rate limits.
    """

    def __init__(self, cache_dir: Optional[Path] = None, cache_enabled: bool = True):
        """Initialize the PubChem client.

        Args:
            cache_dir: Directory for caching API responses. Defaults to data/literature/pubchem_cache.
            cache_enabled: Whether to use caching. Defaults to True.
        """
        self.cache_dir = cache_dir or DEFAULT_CACHE_DIR
        self.cache_enabled = cache_enabled
        self._last_request_time = 0.0

        if self.cache_enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < REQUEST_DELAY:
            time.sleep(REQUEST_DELAY - elapsed)
        self._last_request_time = time.time()

    def _make_request(self, url: str, timeout: int = 30) -> dict:
        """Make an HTTP request to PubChem API.

        Args:
            url: The full URL to request.
            timeout: Request timeout in seconds.

        Returns:
            Parsed JSON response as dictionary.

        Raises:
            PubChemError: If the request fails or returns an error.
        """
        self._rate_limit()

        try:
            request = Request(
                url,
                headers={"Accept": "application/json", "User-Agent": "AromaLab/1.0"}
            )
            with urlopen(request, timeout=timeout) as response:
                data = response.read().decode("utf-8")
                return json.loads(data)
        except HTTPError as e:
            if e.code == 404:
                raise PubChemError(f"Compound not found: {url}")
            raise PubChemError(f"HTTP error {e.code}: {e.reason}")
        except URLError as e:
            raise PubChemError(f"URL error: {e.reason}")
        except json.JSONDecodeError as e:
            raise PubChemError(f"Invalid JSON response: {e}")

    def _get_cache_path(self, identifier: str, id_type: str) -> Path:
        """Get the cache file path for a compound."""
        safe_id = re.sub(r'[^\w\-]', '_', identifier)
        return self.cache_dir / f"{id_type}_{safe_id}.json"

    def _load_from_cache(self, identifier: str, id_type: str) -> Optional[PubChemCompound]:
        """Load compound data from cache.

        Args:
            identifier: The compound identifier.
            id_type: Type of identifier ('cas', 'cid', 'name').

        Returns:
            PubChemCompound if found in cache, None otherwise.
        """
        if not self.cache_enabled:
            return None

        cache_path = self._get_cache_path(identifier, id_type)
        if cache_path.exists():
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    logger.debug(f"Loaded from cache: {identifier}")
                    return PubChemCompound.from_dict(data)
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Cache read error for {identifier}: {e}")
                return None
        return None

    def _save_to_cache(self, compound: PubChemCompound, identifier: str, id_type: str) -> None:
        """Save compound data to cache.

        Args:
            compound: The compound data to cache.
            identifier: The original identifier used.
            id_type: Type of identifier ('cas', 'cid', 'name').
        """
        if not self.cache_enabled:
            return

        cache_path = self._get_cache_path(identifier, id_type)
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(compound.to_dict(), f, indent=2)
            logger.debug(f"Saved to cache: {identifier}")
        except IOError as e:
            logger.warning(f"Cache write error for {identifier}: {e}")

    def get_cid_by_cas(self, cas_number: str) -> Optional[int]:
        """Get PubChem CID for a CAS number.

        Args:
            cas_number: CAS registry number (e.g., "106-24-1").

        Returns:
            PubChem CID if found, None otherwise.
        """
        url = f"{PUBCHEM_BASE_URL}/compound/name/{cas_number}/cids/JSON"
        try:
            data = self._make_request(url)
            cids = data.get("IdentifierList", {}).get("CID", [])
            return cids[0] if cids else None
        except PubChemError as e:
            logger.debug(f"CID lookup failed for CAS {cas_number}: {e}")
            return None

    def get_cid_by_name(self, name: str) -> Optional[int]:
        """Get PubChem CID for a compound name.

        Args:
            name: Compound name or synonym.

        Returns:
            PubChem CID if found, None otherwise.
        """
        url = f"{PUBCHEM_BASE_URL}/compound/name/{name}/cids/JSON"
        try:
            data = self._make_request(url)
            cids = data.get("IdentifierList", {}).get("CID", [])
            return cids[0] if cids else None
        except PubChemError as e:
            logger.debug(f"CID lookup failed for name {name}: {e}")
            return None

    def get_compound_properties(self, cid: int) -> dict:
        """Fetch basic compound properties by CID.

        Args:
            cid: PubChem Compound ID.

        Returns:
            Dictionary of compound properties.
        """
        properties = [
            "MolecularFormula",
            "MolecularWeight",
            "IUPACName",
            "InChI",
            "InChIKey",
            "CanonicalSMILES"
        ]
        props_str = ",".join(properties)
        url = f"{PUBCHEM_BASE_URL}/compound/cid/{cid}/property/{props_str}/JSON"

        data = self._make_request(url)
        props_list = data.get("PropertyTable", {}).get("Properties", [])
        return props_list[0] if props_list else {}

    def get_compound_synonyms(self, cid: int, max_synonyms: int = 50) -> list[str]:
        """Fetch compound synonyms by CID.

        Args:
            cid: PubChem Compound ID.
            max_synonyms: Maximum number of synonyms to return.

        Returns:
            List of compound synonyms.
        """
        url = f"{PUBCHEM_BASE_URL}/compound/cid/{cid}/synonyms/JSON"

        try:
            data = self._make_request(url)
            info_list = data.get("InformationList", {}).get("Information", [])
            if info_list:
                synonyms = info_list[0].get("Synonym", [])
                return synonyms[:max_synonyms]
            return []
        except PubChemError:
            return []

    def get_experimental_properties(self, cid: int) -> dict:
        """Fetch experimental physical properties by CID.

        This retrieves properties from the full compound record including
        boiling point, vapor pressure, density, etc.

        Args:
            cid: PubChem Compound ID.

        Returns:
            Dictionary of experimental properties.
        """
        url = f"{PUBCHEM_BASE_URL}/compound/cid/{cid}/JSON"

        try:
            data = self._make_request(url)
            record = data.get("PC_Compounds", [{}])[0]
            props = record.get("props", [])

            result = {}
            for prop in props:
                urn = prop.get("urn", {})
                label = urn.get("label", "")
                name = urn.get("name", "")
                value = prop.get("value", {})

                # Extract various property types
                if label == "Boiling Point":
                    result["boiling_point"] = self._extract_numeric_value(value)
                elif label == "Melting Point":
                    result["melting_point"] = self._extract_numeric_value(value)
                elif label == "Density":
                    result["density"] = self._extract_numeric_value(value)
                elif label == "Vapor Pressure":
                    result["vapor_pressure"] = self._extract_numeric_value(value)
                elif label == "Log P":
                    result["log_p"] = self._extract_numeric_value(value)
                elif label == "Solubility":
                    result["solubility"] = self._extract_numeric_value(value)

            return result
        except PubChemError as e:
            logger.debug(f"Experimental properties fetch failed for CID {cid}: {e}")
            return {}

    def _extract_numeric_value(self, value_dict: dict) -> Optional[float]:
        """Extract a numeric value from PubChem value dictionary."""
        if "fval" in value_dict:
            return float(value_dict["fval"])
        if "ival" in value_dict:
            return float(value_dict["ival"])
        if "sval" in value_dict:
            # Try to parse numeric from string
            try:
                return float(value_dict["sval"].split()[0])
            except (ValueError, IndexError):
                pass
        return None

    def _extract_cas_from_synonyms(self, synonyms: list[str]) -> Optional[str]:
        """Extract CAS number from list of synonyms.

        Args:
            synonyms: List of compound synonyms.

        Returns:
            CAS number if found, None otherwise.
        """
        cas_pattern = re.compile(r'^\d{2,7}-\d{2}-\d$')
        for syn in synonyms:
            if cas_pattern.match(syn):
                return syn
        return None

    def fetch_by_cas(self, cas_number: str) -> Optional[PubChemCompound]:
        """Fetch complete compound data by CAS number.

        Args:
            cas_number: CAS registry number.

        Returns:
            PubChemCompound with all available data, or None if not found.
        """
        # Check cache first
        cached = self._load_from_cache(cas_number, "cas")
        if cached:
            return cached

        # Get CID
        cid = self.get_cid_by_cas(cas_number)
        if not cid:
            logger.warning(f"No PubChem entry found for CAS {cas_number}")
            return None

        # Fetch all data
        compound = self._fetch_compound_data(cid, cas_number)
        if compound:
            self._save_to_cache(compound, cas_number, "cas")
        return compound

    def fetch_by_cid(self, cid: int) -> Optional[PubChemCompound]:
        """Fetch complete compound data by PubChem CID.

        Args:
            cid: PubChem Compound ID.

        Returns:
            PubChemCompound with all available data, or None if not found.
        """
        # Check cache first
        cached = self._load_from_cache(str(cid), "cid")
        if cached:
            return cached

        compound = self._fetch_compound_data(cid)
        if compound:
            self._save_to_cache(compound, str(cid), "cid")
        return compound

    def fetch_by_name(self, name: str) -> Optional[PubChemCompound]:
        """Fetch complete compound data by name.

        Args:
            name: Compound name or synonym.

        Returns:
            PubChemCompound with all available data, or None if not found.
        """
        # Check cache first
        cached = self._load_from_cache(name, "name")
        if cached:
            return cached

        # Get CID
        cid = self.get_cid_by_name(name)
        if not cid:
            logger.warning(f"No PubChem entry found for name '{name}'")
            return None

        compound = self._fetch_compound_data(cid)
        if compound:
            self._save_to_cache(compound, name, "name")
        return compound

    def _fetch_compound_data(self, cid: int, cas_number: Optional[str] = None) -> Optional[PubChemCompound]:
        """Fetch complete compound data for a CID.

        Args:
            cid: PubChem Compound ID.
            cas_number: Known CAS number (optional).

        Returns:
            PubChemCompound with all available data.
        """
        try:
            # Get basic properties
            props = self.get_compound_properties(cid)
            if not props:
                return None

            # Get synonyms
            synonyms = self.get_compound_synonyms(cid)

            # Try to get CAS from synonyms if not provided
            if not cas_number:
                cas_number = self._extract_cas_from_synonyms(synonyms)

            # Get name from synonyms or IUPAC name
            name = synonyms[0] if synonyms else props.get("IUPACName", "")

            # Get experimental properties
            exp_props = self.get_experimental_properties(cid)

            return PubChemCompound(
                cid=cid,
                cas_number=cas_number,
                name=name,
                iupac_name=props.get("IUPACName"),
                molecular_formula=props.get("MolecularFormula"),
                molecular_weight=props.get("MolecularWeight"),
                synonyms=synonyms,
                boiling_point_c=exp_props.get("boiling_point"),
                melting_point_c=exp_props.get("melting_point"),
                density_g_ml=exp_props.get("density"),
                vapor_pressure_mmhg=exp_props.get("vapor_pressure"),
                log_p=exp_props.get("log_p"),
                solubility_mg_ml=exp_props.get("solubility"),
                inchi=props.get("InChI"),
                inchi_key=props.get("InChIKey"),
                smiles=props.get("CanonicalSMILES"),
                fetched_date=datetime.now().isoformat()
            )
        except PubChemError as e:
            logger.error(f"Failed to fetch compound data for CID {cid}: {e}")
            return None

    def clear_cache(self) -> int:
        """Clear all cached data.

        Returns:
            Number of cache files removed.
        """
        if not self.cache_dir.exists():
            return 0

        count = 0
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                cache_file.unlink()
                count += 1
            except IOError:
                pass
        return count


# Convenience functions for quick lookups

_default_client: Optional[PubChemClient] = None


def get_client() -> PubChemClient:
    """Get or create the default PubChem client."""
    global _default_client
    if _default_client is None:
        _default_client = PubChemClient()
    return _default_client


def fetch_compound(cas_number: str) -> Optional[PubChemCompound]:
    """Fetch compound data by CAS number using the default client.

    Args:
        cas_number: CAS registry number.

    Returns:
        PubChemCompound if found, None otherwise.
    """
    return get_client().fetch_by_cas(cas_number)


def fetch_compound_by_name(name: str) -> Optional[PubChemCompound]:
    """Fetch compound data by name using the default client.

    Args:
        name: Compound name or synonym.

    Returns:
        PubChemCompound if found, None otherwise.
    """
    return get_client().fetch_by_name(name)


def get_cas_number(name: str) -> Optional[str]:
    """Look up CAS number for a compound name.

    Args:
        name: Compound name or synonym.

    Returns:
        CAS number if found, None otherwise.
    """
    compound = fetch_compound_by_name(name)
    return compound.cas_number if compound else None


def get_molecular_formula(cas_number: str) -> Optional[str]:
    """Look up molecular formula for a CAS number.

    Args:
        cas_number: CAS registry number.

    Returns:
        Molecular formula if found, None otherwise.
    """
    compound = fetch_compound(cas_number)
    return compound.molecular_formula if compound else None


def get_physical_properties(cas_number: str) -> dict:
    """Get physical properties for a compound.

    Args:
        cas_number: CAS registry number.

    Returns:
        Dictionary with available physical properties.
    """
    compound = fetch_compound(cas_number)
    if not compound:
        return {}

    return {
        "boiling_point_c": compound.boiling_point_c,
        "melting_point_c": compound.melting_point_c,
        "density_g_ml": compound.density_g_ml,
        "vapor_pressure_mmhg": compound.vapor_pressure_mmhg,
        "log_p": compound.log_p
    }
