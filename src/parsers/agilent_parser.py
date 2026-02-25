"""Parser for Agilent ChemStation GC-MS CSV exports.

Agilent ChemStation exports data in CSV format with specific column layouts.
This parser handles the common export formats from ChemStation software,
including integration results and library search results.

Typical ChemStation CSV columns:
- Peak#: Peak number in chromatogram
- R.T.: Retention time in minutes
- Area: Absolute peak area
- Area%: Percentage of total area
- Library/ID: Compound identification from library search
- CAS#: CAS registry number
- Qual: Library match quality (0-100)
"""

import csv
import re
from pathlib import Path
from typing import Optional

from src.models import GCMSPeak, NaturalProfile
from .base import BaseParser


class AgilentParser(BaseParser):
    """Parse GC-MS data from Agilent ChemStation CSV exports.

    Supports multiple ChemStation export formats:
    - Standard integration report exports
    - Library search result exports
    - Combined integration + library search exports

    The parser automatically detects column layouts and handles
    variations in column naming conventions used by different
    ChemStation versions.
    """

    # Column name mappings for Agilent ChemStation exports
    RT_COLUMNS = [
        "r.t.", "rt", "retention time", "ret.time", "ret time",
        "time", "r.t", "retention_time"
    ]
    AREA_PCT_COLUMNS = [
        "area%", "area %", "area percent", "area_percent",
        "pct", "%area", "% area"
    ]
    AREA_COLUMNS = [
        "area", "peak area", "peakarea", "peak_area"
    ]
    NAME_COLUMNS = [
        "library/id", "library", "compound", "name", "identification",
        "compound name", "compound_name", "id", "hit"
    ]
    CAS_COLUMNS = [
        "cas#", "cas", "cas number", "cas_number", "casno", "cas no"
    ]
    QUALITY_COLUMNS = [
        "qual", "quality", "match", "match quality", "match_quality",
        "si", "similarity", "lib match", "library match"
    ]
    PEAK_NUM_COLUMNS = [
        "peak#", "peak", "pk#", "pk", "no.", "no", "#", "peak number"
    ]
    BASE_PEAK_COLUMNS = [
        "base peak", "base peak m/z", "base_peak", "bp", "base m/z"
    ]
    MW_COLUMNS = [
        "mw", "mol. weight", "mol weight", "molecular weight", "m.w."
    ]

    def can_parse(self, file_path: Path) -> bool:
        """Check if file is an Agilent ChemStation CSV export.

        Attempts to identify ChemStation exports by checking for
        characteristic column names or header patterns.
        """
        if file_path.suffix.lower() != ".csv":
            return False

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                # Read first few lines to check format
                first_lines = [f.readline() for _ in range(10)]
                content = ''.join(first_lines).lower()

                # Check for Agilent-specific markers
                agilent_markers = [
                    "chemstation",
                    "agilent",
                    "library/id",
                    "qual",
                    "r.t."
                ]

                return any(marker in content for marker in agilent_markers)
        except Exception:
            return False

    def _find_column(self, headers: list[str], candidates: list[str]) -> Optional[int]:
        """Find column index matching one of the candidate names."""
        headers_lower = [h.lower().strip() for h in headers]
        for candidate in candidates:
            if candidate.lower() in headers_lower:
                return headers_lower.index(candidate.lower())
        return None

    def _skip_to_data(self, reader: csv.reader) -> list[str]:
        """Skip header rows and find the data header row.

        ChemStation exports often have metadata rows before the actual
        data table. This method skips to the header row containing
        column names.
        """
        for row in reader:
            if not row:
                continue

            row_lower = [cell.lower().strip() for cell in row]

            # Look for rows containing expected column headers
            if any(col in row_lower for col in ["r.t.", "rt", "retention time", "time"]):
                return row
            if any(col in row_lower for col in ["area%", "area", "peak"]):
                return row

        return []

    def _parse_numeric(self, value: str) -> Optional[float]:
        """Parse a numeric value, handling various formats."""
        if not value or value.strip() == '':
            return None

        # Remove common non-numeric characters
        cleaned = value.strip().replace(',', '').replace(' ', '')

        # Handle percentage signs
        cleaned = cleaned.rstrip('%')

        try:
            return float(cleaned)
        except ValueError:
            return None

    def _clean_compound_name(self, name: str) -> Optional[str]:
        """Clean and validate compound name."""
        if not name:
            return None

        name = name.strip()

        # Skip empty or placeholder values
        if name.lower() in ['', 'unknown', 'not found', 'n/a', '-', '--', 'none']:
            return None

        # Remove leading numbers/symbols often prepended
        name = re.sub(r'^[\d\.\-\)\(]+\s*', '', name)

        return name if name else None

    def _clean_cas(self, cas: str) -> Optional[str]:
        """Clean and validate CAS number."""
        if not cas:
            return None

        cas = cas.strip()

        # Skip invalid values
        if cas.lower() in ['', 'n/a', '-', '--', 'none', '0-00-0']:
            return None

        # Validate CAS format (digits-digits-digit)
        if re.match(r'^\d{2,7}-\d{2}-\d$', cas):
            return cas

        # Try to extract CAS from string
        match = re.search(r'(\d{2,7}-\d{2}-\d)', cas)
        if match:
            return match.group(1)

        return None

    def parse(self, file_path: Path) -> NaturalProfile:
        """Parse Agilent ChemStation CSV file into NaturalProfile.

        Args:
            file_path: Path to the ChemStation CSV export file.

        Returns:
            NaturalProfile containing extracted peak data.

        Raises:
            ValueError: If the file format is not recognized or required
                columns are missing.
            FileNotFoundError: If the file does not exist.
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        peaks = []
        total_area = 0.0

        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.reader(f)

            # Find and parse header row
            headers = self._skip_to_data(reader)

            if not headers:
                # Try reading from beginning with standard CSV
                f.seek(0)
                reader = csv.reader(f)
                try:
                    headers = next(reader)
                except StopIteration:
                    raise ValueError(f"Empty file: {file_path}")

            # Find column indices
            rt_idx = self._find_column(headers, self.RT_COLUMNS)
            area_pct_idx = self._find_column(headers, self.AREA_PCT_COLUMNS)
            area_idx = self._find_column(headers, self.AREA_COLUMNS)
            name_idx = self._find_column(headers, self.NAME_COLUMNS)
            cas_idx = self._find_column(headers, self.CAS_COLUMNS)
            qual_idx = self._find_column(headers, self.QUALITY_COLUMNS)
            base_peak_idx = self._find_column(headers, self.BASE_PEAK_COLUMNS)

            if rt_idx is None:
                raise ValueError(
                    f"Could not find retention time column in Agilent export. "
                    f"Found columns: {headers}"
                )

            if area_pct_idx is None and area_idx is None:
                raise ValueError(
                    f"Could not find area or area% column in Agilent export. "
                    f"Found columns: {headers}"
                )

            # First pass: collect all data and total area if needed
            rows_data = []
            for row in reader:
                if not row or len(row) <= rt_idx:
                    continue

                rt = self._parse_numeric(row[rt_idx])
                if rt is None:
                    continue

                # Get area value
                if area_pct_idx is not None:
                    area_pct = self._parse_numeric(row[area_pct_idx])
                    area = None
                else:
                    area_pct = None
                    area = self._parse_numeric(row[area_idx]) if area_idx is not None else None
                    if area:
                        total_area += area

                # Extract other fields
                name = None
                if name_idx is not None and len(row) > name_idx:
                    name = self._clean_compound_name(row[name_idx])

                cas = None
                if cas_idx is not None and len(row) > cas_idx:
                    cas = self._clean_cas(row[cas_idx])

                qual = None
                if qual_idx is not None and len(row) > qual_idx:
                    qual = self._parse_numeric(row[qual_idx])

                base_peak = None
                if base_peak_idx is not None and len(row) > base_peak_idx:
                    base_peak = self._parse_numeric(row[base_peak_idx])

                rows_data.append({
                    'rt': rt,
                    'area_pct': area_pct,
                    'area': area,
                    'name': name,
                    'cas': cas,
                    'qual': qual,
                    'base_peak': base_peak
                })

        # Create peaks, calculating percentages if needed
        for row_data in rows_data:
            if row_data['area_pct'] is not None:
                area_percent = row_data['area_pct']
            elif row_data['area'] is not None and total_area > 0:
                area_percent = (row_data['area'] / total_area) * 100
            else:
                area_percent = 0.0

            peak = GCMSPeak(
                retention_time=row_data['rt'],
                area_percent=area_percent,
                compound_name=row_data['name'],
                cas_number=row_data['cas'],
                match_quality=row_data['qual'],
                base_peak_mz=row_data['base_peak']
            )
            peaks.append(peak)

        # Sort by area percent descending
        peaks.sort(key=lambda p: p.area_percent, reverse=True)

        return NaturalProfile(
            name=file_path.stem,
            peaks=peaks,
            notes=f"Parsed from Agilent ChemStation export: {file_path.name}"
        )
