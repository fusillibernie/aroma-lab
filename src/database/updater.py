"""Automated database updater for aromachemicals.

Fetches data from public sources:
- PubChem (compound properties, synonyms)
- The Good Scents Company (odor descriptions) - manual import
- IFRA (restriction data) - manual import
- Scientific literature (GC-MS compositions)
"""

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

import pubchempy as pcp

from src.models import Aromachemical, OdorFamily, Volatility


@dataclass
class UpdateResult:
    """Result of a database update operation."""
    compounds_added: int = 0
    compounds_updated: int = 0
    compounds_failed: list[str] = field(default_factory=list)
    source: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class DataSource:
    """Represents a data source for aromachemicals."""
    name: str
    url: str
    last_updated: str | None = None
    update_frequency_days: int = 30
    enabled: bool = True


class AromachemicalUpdater:
    """Fetch and update aromachemical data from public sources."""

    # Known aromachemical CAS numbers to fetch (curated list)
    KNOWN_AROMACHEMICALS = [
        # Alcohols - Terpene
        ("78-70-6", "Linalool"),
        ("106-24-1", "Geraniol"),
        ("106-22-9", "Citronellol"),
        ("106-25-2", "Nerol"),
        ("98-55-5", "alpha-Terpineol"),
        ("7785-70-8", "alpha-Pinene"),  # Alternative CAS
        ("562-74-3", "Terpinen-4-ol"),
        ("470-08-6", "Borneol"),
        ("507-70-0", "Borneol (natural)"),
        ("89-78-1", "Menthol"),
        ("2216-51-5", "L-Menthol"),
        ("15356-70-4", "DL-Menthol"),
        ("7212-44-4", "Nerolidol"),
        ("4602-84-0", "Farnesol"),
        ("515-69-5", "Bisabolol"),
        ("23089-26-1", "alpha-Bisabolol"),
        ("142-30-3", "Dihydromyrcenol"),
        ("18479-58-8", "Dihydromyrcenol"),
        ("67801-20-1", "Tetrahydrolinalool"),

        # Alcohols - Aromatic
        ("100-51-6", "Benzyl Alcohol"),
        ("60-12-8", "Phenethyl Alcohol"),
        ("122-99-6", "2-Phenylethanol"),
        ("104-54-1", "Cinnamyl Alcohol"),
        ("101-85-9", "Amyl Cinnamyl Alcohol"),
        ("101-86-0", "Hexyl Cinnamaldehyde"),
        ("122-97-4", "3-Phenylpropanol"),

        # Aldehydes - Aliphatic
        ("112-31-2", "Decanal (C-10)"),
        ("112-44-7", "Undecanal (C-11)"),
        ("112-54-9", "Dodecanal (C-12)"),
        ("124-19-6", "Nonanal (C-9)"),
        ("124-13-0", "Octanal (C-8)"),
        ("66-25-1", "Hexanal (C-6)"),
        ("110-62-3", "Valeraldehyde (C-5)"),
        ("123-63-7", "Paraldehyde"),

        # Aldehydes - Terpene
        ("5392-40-5", "Citral"),
        ("106-26-3", "Neral"),
        ("141-27-5", "Geranial"),
        ("432-25-7", "beta-Cyclocitral"),
        ("116-26-7", "Safranal"),
        ("107-75-5", "Hydroxycitronellal"),

        # Aldehydes - Aromatic
        ("104-55-2", "Cinnamaldehyde"),
        ("122-78-1", "Phenylacetaldehyde"),
        ("104-87-0", "p-Tolualdehyde"),
        ("123-11-5", "Anisaldehyde"),
        ("120-57-0", "Heliotropin"),
        ("1205-17-0", "Heliotropin"),  # Piperonal alt

        # Esters
        ("115-95-7", "Linalyl Acetate"),
        ("105-87-3", "Geranyl Acetate"),
        ("141-12-8", "Neryl Acetate"),
        ("140-11-4", "Benzyl Acetate"),
        ("103-45-7", "Phenethyl Acetate"),
        ("102-22-7", "Geranyl Phenylacetate"),
        ("103-48-0", "Phenethyl Isobutyrate"),
        ("103-52-6", "Phenethyl Butyrate"),
        ("120-51-4", "Benzyl Benzoate"),
        ("118-58-1", "Benzyl Salicylate"),
        ("87-20-7", "Isoamyl Salicylate"),
        ("119-36-8", "Methyl Salicylate"),
        ("103-26-4", "Methyl Cinnamate"),
        ("103-41-3", "Benzyl Cinnamate"),
        ("122-63-4", "Benzyl Propionate"),
        ("5205-11-8", "Ethyl Linalool"),
        ("78-36-4", "Linalyl Butyrate"),
        ("150-84-5", "Citronellyl Acetate"),
        ("105-85-1", "Citronellyl Formate"),
        ("2705-87-5", "Allyl Cyclohexylpropionate"),
        ("7779-65-9", "Tricyclodecenyl Propionate"),

        # Ketones
        ("76-22-2", "Camphor"),
        ("89-82-7", "Pulegone"),
        ("99-49-0", "Carvone"),
        ("6485-40-1", "L-Carvone"),
        ("2244-16-8", "D-Carvone"),
        ("513-86-0", "Acetoin"),
        ("431-03-8", "Diacetyl"),
        ("488-10-8", "Jasmone"),
        ("542-46-1", "cis-Jasmone"),
        ("79-77-6", "beta-Ionone"),
        ("127-41-3", "alpha-Isomethyl Ionone"),
        ("79-69-6", "Methyl Ionone"),
        ("1335-46-2", "Methyl Ionone (mixed)"),
        ("24851-98-7", "Methyl Dihydrojasmonate"),
        ("141-10-6", "Pseudoionone"),
        ("7779-30-8", "Damascone"),
        ("23726-93-4", "beta-Damascone"),
        ("23696-85-7", "alpha-Damascone"),
        ("33673-71-1", "delta-Damascone"),
        ("71048-82-3", "Florhydral"),

        # Lactones
        ("104-61-0", "gamma-Nonalactone"),
        ("706-14-9", "gamma-Decalactone"),
        ("713-95-1", "delta-Decalactone"),
        ("105-21-5", "gamma-Heptalactone"),
        ("695-06-7", "gamma-Hexalactone"),
        ("698-76-0", "gamma-Octalactone"),
        ("2305-05-7", "delta-Dodecalactone"),
        ("7779-50-2", "gamma-Undecalactone"),
        ("104-67-6", "gamma-Undecalactone"),
        ("1725-02-6", "delta-Undecalactone"),
        ("91-64-5", "Coumarin"),
        ("91-44-1", "7-Methoxycoumarin"),
        ("531-59-9", "Herniarin"),

        # Musks
        ("81-14-1", "Musk Ketone"),
        ("81-15-2", "Musk Xylene"),
        ("1222-05-5", "Galaxolide"),
        ("541-91-3", "Muscone"),
        ("502-72-7", "Cyclopentadecanone"),
        ("106-02-5", "Pentadecanolide"),
        ("34902-57-3", "Habanolide"),
        ("6707-60-4", "Exaltolide"),
        ("7779-50-2", "Ambrettolide"),
        ("28645-51-4", "Ethylene Brassylate"),
        ("83-88-5", "Ambroxan"),
        ("3738-00-9", "Ambrox"),

        # Phenols
        ("97-53-0", "Eugenol"),
        ("93-15-2", "Methyl Eugenol"),
        ("97-54-1", "Isoeugenol"),
        ("120-24-1", "Isoeugenyl Acetate"),
        ("90-05-1", "Guaiacol"),
        ("93-51-6", "Creosol"),
        ("89-83-8", "Thymol"),
        ("499-75-2", "Carvacrol"),
        ("121-33-5", "Vanillin"),
        ("121-32-4", "Ethyl Vanillin"),
        ("94-86-0", "Propenyl Guaethol"),

        # Hydrocarbons - Terpenes
        ("5989-27-5", "D-Limonene"),
        ("5989-54-8", "L-Limonene"),
        ("138-86-3", "Limonene (racemic)"),
        ("80-56-8", "alpha-Pinene"),
        ("127-91-3", "beta-Pinene"),
        ("13466-78-9", "3-Carene"),
        ("99-87-6", "p-Cymene"),
        ("99-86-5", "alpha-Terpinene"),
        ("99-85-4", "gamma-Terpinene"),
        ("586-62-9", "Terpinolene"),
        ("123-35-3", "Myrcene"),
        ("79-92-5", "Camphene"),
        ("3387-41-5", "Sabinene"),
        ("555-10-2", "beta-Phellandrene"),
        ("99-83-2", "alpha-Phellandrene"),

        # Sesquiterpenes
        ("87-44-5", "beta-Caryophyllene"),
        ("6753-98-6", "alpha-Humulene"),
        ("17699-14-8", "Caryophyllene Oxide"),
        ("495-60-3", "Zingiberene"),
        ("475-20-7", "Longifolene"),
        ("469-61-4", "alpha-Cedrene"),
        ("546-28-1", "beta-Cedrene"),
        ("77-53-2", "Cedrol"),
        ("77-52-1", "Ursolic Acid"),
        ("3691-12-1", "Iso E Super"),
        ("68155-66-8", "Iso E Super (commercial)"),
        ("54464-57-2", "Cashmeran"),
        ("33704-61-9", "Javanol"),
        ("70788-30-6", "Polysantol"),

        # Oxides/Ethers
        ("470-82-6", "Eucalyptol"),
        ("470-67-7", "1,4-Cineole"),
        ("502-99-8", "Rose Oxide (cis)"),
        ("16409-43-1", "Rose Oxide (trans)"),
        ("470-82-6", "1,8-Cineole"),
        ("60-29-7", "Diethyl Ether"),
        ("100-66-3", "Anisole"),
        ("104-46-1", "trans-Anethole"),
        ("140-67-0", "Estragole"),

        # Acids
        ("79-09-4", "Propionic Acid"),
        ("107-92-6", "Butyric Acid"),
        ("109-52-4", "Valeric Acid"),
        ("142-62-1", "Hexanoic Acid"),
        ("124-07-2", "Octanoic Acid"),
        ("334-48-5", "Decanoic Acid"),
        ("65-85-0", "Benzoic Acid"),
        ("103-82-2", "Phenylacetic Acid"),
        ("501-52-0", "Cinnamic Acid"),

        # Nitrogen Compounds
        ("100-46-9", "Benzylamine"),
        ("122-39-4", "Diphenylamine"),
        ("83-34-1", "Skatole"),
        ("120-72-9", "Indole"),
        ("95-13-6", "Indene"),

        # Sulfur Compounds
        ("2179-57-9", "Diallyl Disulfide"),
        ("2050-87-5", "Dimethyl Trisulfide"),
        ("3658-80-8", "Dimethyl Trisulfide"),
        ("624-92-0", "Dimethyl Disulfide"),
        ("75-18-3", "Dimethyl Sulfide"),
        ("137-00-8", "4-Methyl-5-thiazoleethanol"),

        # Naturals/Specialties
        ("8006-64-2", "Turpentine"),
        ("8007-01-0", "Rose Oil (absolute)"),
        ("8008-57-9", "Orange Oil"),
        ("8016-85-1", "Ylang Ylang Oil"),
        ("8008-52-4", "Coriander Oil"),
        ("8014-19-5", "Patchouli Oil"),
        ("90045-36-6", "Grapefruit Oil"),
        ("90063-97-1", "Clary Sage Oil"),
        ("92128-34-2", "Bergamot Oil"),
    ]

    def __init__(self, db_path: Path):
        """Initialize updater with database path."""
        self.db_path = db_path
        self.sources_file = db_path / "sources.json"
        self.sources = self._load_sources()
        self._rate_limit_delay = 0.5  # seconds between API calls

    def _load_sources(self) -> list[DataSource]:
        """Load data sources configuration."""
        if self.sources_file.exists():
            with open(self.sources_file, "r") as f:
                data = json.load(f)
                return [DataSource(**s) for s in data]

        # Default sources
        return [
            DataSource(
                name="PubChem",
                url="https://pubchem.ncbi.nlm.nih.gov/",
                update_frequency_days=30,
            ),
            DataSource(
                name="The Good Scents Company",
                url="http://www.thegoodscentscompany.com/",
                update_frequency_days=90,
            ),
            DataSource(
                name="IFRA",
                url="https://ifrafragrance.org/",
                update_frequency_days=180,
            ),
        ]

    def _save_sources(self):
        """Save data sources configuration."""
        data = [
            {
                "name": s.name,
                "url": s.url,
                "last_updated": s.last_updated,
                "update_frequency_days": s.update_frequency_days,
                "enabled": s.enabled,
            }
            for s in self.sources
        ]
        with open(self.sources_file, "w") as f:
            json.dump(data, f, indent=2)

    def fetch_from_pubchem(
        self,
        cas_number: str,
        common_name: str | None = None,
    ) -> Aromachemical | None:
        """Fetch aromachemical data from PubChem."""
        try:
            # Try CAS number first
            compounds = pcp.get_compounds(cas_number, "name")

            if not compounds:
                return None

            compound = compounds[0]

            # Extract properties
            synonyms = compound.synonyms or []

            # Try to find a better common name from synonyms
            name = common_name or self._extract_common_name(synonyms) or cas_number

            # Determine molecular properties
            return Aromachemical(
                cas_number=cas_number,
                name=name,
                iupac_name=compound.iupac_name,
                molecular_formula=compound.molecular_formula,
                molecular_weight=compound.molecular_weight,
                odor_description="",  # PubChem doesn't have odor data
                odor_families=[],
                volatility=None,
                log_p=compound.xlogp if hasattr(compound, "xlogp") else None,
            )

        except Exception as e:
            print(f"Failed to fetch {cas_number}: {e}")
            return None

    def _extract_common_name(self, synonyms: list[str]) -> str | None:
        """Extract the most likely common name from synonyms."""
        if not synonyms:
            return None

        # Prefer shorter names without special characters
        candidates = []
        for syn in synonyms[:20]:  # Check first 20
            # Skip IUPAC-like names
            if any(c in syn for c in "[](){}"):
                continue
            # Skip very long names
            if len(syn) > 30:
                continue
            # Skip names with numbers at start
            if syn[0].isdigit():
                continue
            candidates.append(syn)

        if candidates:
            # Return shortest candidate
            return min(candidates, key=len)

        return synonyms[0] if synonyms else None

    def update_from_known_list(
        self,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> UpdateResult:
        """Update database from curated list of known aromachemicals."""
        result = UpdateResult(source="known_aromachemicals")

        total = len(self.KNOWN_AROMACHEMICALS)
        output_file = self.db_path / "pubchem_data.json"

        # Load existing data
        existing = {}
        if output_file.exists():
            with open(output_file, "r") as f:
                existing = {item["cas_number"]: item for item in json.load(f)}

        new_compounds = []

        for i, (cas, name) in enumerate(self.KNOWN_AROMACHEMICALS):
            if progress_callback:
                progress_callback(i + 1, total, name)

            # Skip if already have this CAS
            if cas in existing:
                continue

            # Rate limiting
            time.sleep(self._rate_limit_delay)

            ac = self.fetch_from_pubchem(cas, name)
            if ac:
                new_compounds.append(self._to_dict(ac))
                result.compounds_added += 1
            else:
                result.compounds_failed.append(f"{cas} ({name})")

        # Merge and save
        all_compounds = list(existing.values()) + new_compounds
        all_compounds.sort(key=lambda x: x["name"])

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(all_compounds, f, indent=2, ensure_ascii=False)

        # Update source timestamp
        for source in self.sources:
            if source.name == "PubChem":
                source.last_updated = datetime.now().isoformat()
        self._save_sources()

        return result

    def enrich_with_odor_data(
        self,
        odor_data: dict[str, dict],
    ) -> UpdateResult:
        """Enrich existing compounds with odor data.

        Args:
            odor_data: Dict mapping CAS numbers to odor info:
                {
                    "106-24-1": {
                        "odor_description": "Sweet, floral, rose",
                        "odor_families": ["floral"],
                        "volatility": "heart",
                    }
                }
        """
        result = UpdateResult(source="odor_enrichment")

        for json_file in self.db_path.glob("*.json"):
            if json_file.name == "sources.json":
                continue

            with open(json_file, "r") as f:
                compounds = json.load(f)

            updated = False
            for compound in compounds:
                cas = compound.get("cas_number")
                if cas in odor_data:
                    info = odor_data[cas]
                    if "odor_description" in info and not compound.get("odor_description"):
                        compound["odor_description"] = info["odor_description"]
                        updated = True
                    if "odor_families" in info and not compound.get("odor_families"):
                        compound["odor_families"] = info["odor_families"]
                        updated = True
                    if "volatility" in info and not compound.get("volatility"):
                        compound["volatility"] = info["volatility"]
                        updated = True
                    if updated:
                        result.compounds_updated += 1

            if updated:
                with open(json_file, "w") as f:
                    json.dump(compounds, f, indent=2, ensure_ascii=False)

        return result

    def _to_dict(self, ac: Aromachemical) -> dict:
        """Convert aromachemical to dictionary."""
        data = {
            "cas_number": ac.cas_number,
            "name": ac.name,
        }
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
        if ac.log_p is not None:
            data["log_p"] = ac.log_p
        return data

    def check_for_updates(self) -> list[DataSource]:
        """Check which sources need updating."""
        needs_update = []
        now = datetime.now()

        for source in self.sources:
            if not source.enabled:
                continue

            if source.last_updated is None:
                needs_update.append(source)
                continue

            last = datetime.fromisoformat(source.last_updated)
            days_since = (now - last).days

            if days_since >= source.update_frequency_days:
                needs_update.append(source)

        return needs_update
