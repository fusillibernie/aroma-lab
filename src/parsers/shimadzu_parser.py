"""Parser for Shimadzu LabSolutions GC-MS text exports.

Shimadzu LabSolutions exports GC-MS data in a structured text format
with distinct sections for sample information, peak table, and library
search results. This parser handles the standard ASCII report format.

Typical LabSolutions report structure:
- Header section with sample info, method, and instrument details
- [Peak Table] section with integration results
- [MS Spectrum] section (optional)
- [Library Search] section with compound identifications
"""

import re
from pathlib import Path
from typing import Optional

from src.models import GCMSPeak, NaturalProfile
from .base import BaseParser


class ShimadzuParser(BaseParser):
    """Parse GC-MS data from Shimadzu LabSolutions text exports.

    Supports LabSolutions ASCII report formats including:
    - Standard peak reports
    - Library search reports
    - Combined analysis reports

    The parser handles section-based file structure and merges
    peak data from multiple sections when available.
    """

    # Section markers in LabSolutions reports
    PEAK_TABLE_MARKERS = [
        "[peak table]",
        "[peak table(detector",
        "peak#",
        "peaktable"
    ]
    LIBRARY_SECTION_MARKERS = [
        "[library search",
        "[ms library",
        "[library hit",
        "[similarity search"
    ]

    def can_parse(self, file_path: Path) -> bool:
        """Check if file is a Shimadzu LabSolutions text export.

        Identifies LabSolutions exports by checking for characteristic
        section markers and formatting patterns.
        """
        if file_path.suffix.lower() not in ['.txt', '.asc', '.rep']:
            return False

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(2000).lower()

                # Check for Shimadzu-specific markers
                shimadzu_markers = [
                    "labsolutions",
                    "shimadzu",
                    "[peak table",
                    "gcmssolution",
                    "[ms spectrum",
                    "detector a"
                ]

                return any(marker in content for marker in shimadzu_markers)
        except Exception:
            return False

    def _parse_numeric(self, value: str) -> Optional[float]:
        """Parse a numeric value, handling various formats."""
        if not value or value.strip() == '':
            return None

        # Remove common non-numeric characters
        cleaned = value.strip().replace(',', '').replace(' ', '')
        cleaned = cleaned.rstrip('%')

        # Handle scientific notation
        cleaned = cleaned.replace('E', 'e')

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
        if name.lower() in ['', 'unknown', 'not identified', 'n/a', '-', '--', 'none']:
            return None

        # Remove trailing hit number like "(1)" or "#1"
        name = re.sub(r'\s*[\(\#]\d+[\)]?\s*$', '', name)

        return name if name else None

    def _clean_cas(self, cas: str) -> Optional[str]:
        """Clean and validate CAS number."""
        if not cas:
            return None

        cas = cas.strip()

        if cas.lower() in ['', 'n/a', '-', '--', 'none', '0-00-0']:
            return None

        # Validate CAS format
        if re.match(r'^\d{2,7}-\d{2}-\d$', cas):
            return cas

        # Try to extract CAS from string
        match = re.search(r'(\d{2,7}-\d{2}-\d)', cas)
        if match:
            return match.group(1)

        return None

    def _find_section(self, lines: list[str], markers: list[str]) -> int:
        """Find the start index of a section by its markers."""
        for i, line in enumerate(lines):
            line_lower = line.lower().strip()
            for marker in markers:
                if marker in line_lower:
                    return i
        return -1

    def _parse_peak_table_line(self, line: str, headers: list[str]) -> Optional[dict]:
        """Parse a single line from the peak table.

        LabSolutions peak tables can be either:
        - Tab-delimited
        - Fixed-width columns
        - Space-delimited with quoted strings
        """
        # Try tab-delimited first
        if '\t' in line:
            values = line.split('\t')
        else:
            # Try to split by multiple spaces (fixed width)
            values = re.split(r'\s{2,}', line.strip())

        if len(values) < 2:
            return None

        # Try to identify column positions
        result = {}
        headers_lower = [h.lower() for h in headers]

        for i, value in enumerate(values):
            if i >= len(headers):
                break

            header = headers_lower[i]

            if any(rt in header for rt in ['r.t', 'ret', 'time']):
                result['rt'] = self._parse_numeric(value)
            elif any(area in header for area in ['area%', 'conc', 'percent', '%']):
                result['area_pct'] = self._parse_numeric(value)
            elif 'area' in header and '%' not in header and 'percent' not in header:
                result['area'] = self._parse_numeric(value)
            elif any(name in header for name in ['name', 'compound', 'id']):
                result['name'] = self._clean_compound_name(value)
            elif any(cas in header for cas in ['cas', 'casno']):
                result['cas'] = self._clean_cas(value)
            elif any(qual in header for qual in ['si', 'similarity', 'match', 'qual']):
                result['quality'] = self._parse_numeric(value)

        return result if result.get('rt') is not None else None

    def _parse_peak_table(self, lines: list[str], start_idx: int) -> tuple[list[dict], int]:
        """Parse the peak table section.

        Returns:
            Tuple of (list of peak data dicts, end index)
        """
        peaks_data = []
        headers = []
        in_data = False
        end_idx = start_idx

        for i in range(start_idx + 1, len(lines)):
            line = lines[i].strip()
            end_idx = i

            # Check for section end
            if line.startswith('[') and ']' in line:
                break
            if line.startswith('---') or line.startswith('==='):
                if in_data:
                    break
                continue

            # Skip empty lines
            if not line:
                if in_data and peaks_data:
                    break
                continue

            # Detect header line
            line_lower = line.lower()
            if not in_data and any(h in line_lower for h in ['peak#', 'r.t', 'ret.time', 'area']):
                # This is the header line
                if '\t' in line:
                    headers = line.split('\t')
                else:
                    headers = re.split(r'\s{2,}', line)
                in_data = True
                continue

            # Parse data line
            if in_data and headers:
                # Check if line starts with a number (peak number or RT)
                if re.match(r'^\s*\d', line):
                    peak_data = self._parse_peak_table_line(line, headers)
                    if peak_data:
                        peaks_data.append(peak_data)

        return peaks_data, end_idx

    def _parse_library_section(self, lines: list[str], start_idx: int) -> dict[float, dict]:
        """Parse the library search results section.

        Returns:
            Dictionary mapping retention times to library match data.
        """
        library_data = {}
        current_rt = None

        for i in range(start_idx + 1, len(lines)):
            line = lines[i].strip()

            # Check for section end
            if line.startswith('[') and ']' in line:
                break

            if not line:
                continue

            # Look for RT indicator
            rt_match = re.search(r'(?:r\.?t\.?|ret\.?\s*time|peak\s*\d+)\s*[:\s]+(\d+\.?\d*)', line.lower())
            if rt_match:
                current_rt = float(rt_match.group(1))
                library_data[current_rt] = {'hits': []}
                continue

            # Look for hit entries
            if current_rt is not None:
                # Pattern: Hit# SI CAS CompoundName
                hit_match = re.match(
                    r'(?:hit\s*)?(\d+)\s+(\d+)\s+(\d+-\d+-\d+)?\s*(.+)?',
                    line,
                    re.IGNORECASE
                )
                if hit_match:
                    hit = {
                        'hit_num': int(hit_match.group(1)),
                        'similarity': int(hit_match.group(2)),
                        'cas': self._clean_cas(hit_match.group(3) or ''),
                        'name': self._clean_compound_name(hit_match.group(4) or '')
                    }
                    library_data[current_rt]['hits'].append(hit)

        return library_data

    def _extract_sample_info(self, lines: list[str]) -> dict:
        """Extract sample information from the header section."""
        info = {}

        for line in lines[:50]:  # Check first 50 lines
            line = line.strip()

            # Look for key-value pairs
            if ':' in line:
                key, _, value = line.partition(':')
                key = key.strip().lower()
                value = value.strip()

                if 'sample' in key and 'name' in key:
                    info['sample_name'] = value
                elif 'data file' in key or 'filename' in key:
                    info['data_file'] = value
                elif 'method' in key:
                    info['method'] = value
                elif 'date' in key:
                    info['date'] = value

        return info

    def parse(self, file_path: Path) -> NaturalProfile:
        """Parse Shimadzu LabSolutions text file into NaturalProfile.

        Args:
            file_path: Path to the LabSolutions text export file.

        Returns:
            NaturalProfile containing extracted peak data.

        Raises:
            ValueError: If the file format is not recognized or contains
                no valid peak data.
            FileNotFoundError: If the file does not exist.
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Read entire file
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        lines = content.split('\n')

        # Extract sample info
        sample_info = self._extract_sample_info(lines)

        # Find and parse peak table
        peak_table_start = self._find_section(lines, self.PEAK_TABLE_MARKERS)
        peaks_data = []

        if peak_table_start >= 0:
            peaks_data, _ = self._parse_peak_table(lines, peak_table_start)

        # Find and parse library section
        library_start = self._find_section(lines, self.LIBRARY_SECTION_MARKERS)
        library_data = {}

        if library_start >= 0:
            library_data = self._parse_library_section(lines, library_start)

        # If no peak table found, try to parse entire file as simple format
        if not peaks_data:
            peaks_data = self._parse_simple_format(lines)

        if not peaks_data:
            raise ValueError(
                f"Could not find valid peak data in Shimadzu export: {file_path}"
            )

        # Merge library data with peak data
        total_area = sum(p.get('area', 0) or 0 for p in peaks_data)
        peaks = []

        for peak_data in peaks_data:
            rt = peak_data.get('rt')
            if rt is None:
                continue

            # Calculate area percent if not provided
            if peak_data.get('area_pct') is not None:
                area_percent = peak_data['area_pct']
            elif peak_data.get('area') and total_area > 0:
                area_percent = (peak_data['area'] / total_area) * 100
            else:
                area_percent = 0.0

            # Get library match for this RT
            lib_match = self._get_best_library_match(rt, library_data)

            # Prefer library data over peak table data
            compound_name = lib_match.get('name') or peak_data.get('name')
            cas_number = lib_match.get('cas') or peak_data.get('cas')
            match_quality = lib_match.get('similarity') or peak_data.get('quality')

            peak = GCMSPeak(
                retention_time=rt,
                area_percent=area_percent,
                compound_name=compound_name,
                cas_number=cas_number,
                match_quality=match_quality
            )
            peaks.append(peak)

        # Sort by area percent descending
        peaks.sort(key=lambda p: p.area_percent, reverse=True)

        # Determine profile name
        name = sample_info.get('sample_name') or file_path.stem

        return NaturalProfile(
            name=name,
            peaks=peaks,
            analysis_date=sample_info.get('date'),
            notes=f"Parsed from Shimadzu LabSolutions export: {file_path.name}"
        )

    def _get_best_library_match(self, rt: float, library_data: dict, tolerance: float = 0.05) -> dict:
        """Get the best library match for a given retention time."""
        for lib_rt, data in library_data.items():
            if abs(lib_rt - rt) <= tolerance:
                if data.get('hits'):
                    return data['hits'][0]  # Return best hit
        return {}

    def _parse_simple_format(self, lines: list[str]) -> list[dict]:
        """Try to parse a simple tabular format without section markers."""
        peaks_data = []
        headers = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Detect header line
            line_lower = line.lower()
            if not headers and any(h in line_lower for h in ['r.t', 'ret', 'area']):
                if '\t' in line:
                    headers = line.split('\t')
                else:
                    headers = re.split(r'\s{2,}', line)
                continue

            # Parse data
            if headers and re.match(r'^\s*\d', line):
                peak_data = self._parse_peak_table_line(line, headers)
                if peak_data:
                    peaks_data.append(peak_data)

        return peaks_data
