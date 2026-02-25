"""Parser for NIST MS Search library search results.

NIST MS Search exports compound identification results in various formats
including text reports, hit lists, and spectrum match data. This parser
handles the common export formats from NIST MS Search software.

NIST MS Search result formats supported:
- Hit list text exports (.txt)
- Spectrum search reports
- Library search results with similarity indices
- NIST mainlib and replicate library matches
"""

import re
from pathlib import Path
from typing import Optional

from src.models import GCMSPeak, NaturalProfile
from .base import BaseParser


class NISTParser(BaseParser):
    """Parse NIST MS Search library search results.

    Handles various NIST MS Search export formats:
    - Standard hit list exports
    - Detailed spectrum match reports
    - Batch search results

    The parser extracts compound identifications, similarity scores,
    CAS numbers, and molecular formula information from NIST searches.
    """

    # Common NIST-specific markers
    NIST_MARKERS = [
        "nist",
        "mainlib",
        "replib",
        "similarity",
        "match factor",
        "reverse match",
        "hit",
        "spec#"
    ]

    def can_parse(self, file_path: Path) -> bool:
        """Check if file is a NIST MS Search results file.

        Identifies NIST exports by checking for characteristic
        markers and formatting patterns.
        """
        if file_path.suffix.lower() not in ['.txt', '.msp', '.nist']:
            return False

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(3000).lower()

                return any(marker in content for marker in self.NIST_MARKERS)
        except Exception:
            return False

    def _parse_numeric(self, value: str) -> Optional[float]:
        """Parse a numeric value from various formats."""
        if not value or value.strip() == '':
            return None

        cleaned = value.strip().replace(',', '').replace(' ', '')

        try:
            return float(cleaned)
        except ValueError:
            return None

    def _parse_integer(self, value: str) -> Optional[int]:
        """Parse an integer value."""
        num = self._parse_numeric(value)
        return int(num) if num is not None else None

    def _clean_compound_name(self, name: str) -> Optional[str]:
        """Clean and validate compound name from NIST results."""
        if not name:
            return None

        name = name.strip()

        # Skip invalid values
        if name.lower() in ['', 'unknown', 'n/a', '-', '--', 'none', 'no match']:
            return None

        # Remove NIST-specific prefixes like numbering
        name = re.sub(r'^[\d\.\)]+\s*', '', name)

        # Remove trailing annotations
        name = re.sub(r'\s*\$\$.*$', '', name)  # Remove $$ synonyms
        name = re.sub(r'\s*\([^)]*nist[^)]*\)\s*$', '', name, flags=re.IGNORECASE)

        return name.strip() if name.strip() else None

    def _clean_cas(self, cas: str) -> Optional[str]:
        """Clean and validate CAS number."""
        if not cas:
            return None

        cas = cas.strip()

        if cas.lower() in ['', 'n/a', '-', '--', 'none', '0-00-0', '0']:
            return None

        # Validate CAS format
        if re.match(r'^\d{2,7}-\d{2}-\d$', cas):
            return cas

        # Try to extract CAS from string
        match = re.search(r'(\d{2,7}-\d{2}-\d)', cas)
        if match:
            return match.group(1)

        return None

    def _parse_hit_entry(self, lines: list[str], start_idx: int) -> tuple[Optional[dict], int]:
        """Parse a single hit entry from NIST search results.

        NIST hit entries can span multiple lines with various formats:
        - Single line: Hit# SI RSI Name CAS MW Formula
        - Multi-line with labeled fields

        Returns:
            Tuple of (hit data dict or None, next line index)
        """
        hit_data = {}
        idx = start_idx

        while idx < len(lines):
            line = lines[idx].strip()

            if not line:
                idx += 1
                break

            # Check for new hit entry (starts with number or "Hit")
            if idx > start_idx and (
                re.match(r'^Hit\s*\d+', line, re.IGNORECASE) or
                re.match(r'^\d+[\.\):]', line)
            ):
                break

            line_lower = line.lower()

            # Extract similarity/match factor
            si_match = re.search(r'(?:si|similarity|mf|match\s*factor)[:\s]+(\d+)', line_lower)
            if si_match:
                hit_data['similarity'] = self._parse_integer(si_match.group(1))

            # Extract reverse match factor
            rsi_match = re.search(r'(?:rsi|rsim|reverse|r\.match|rmf)[:\s]+(\d+)', line_lower)
            if rsi_match:
                hit_data['reverse_match'] = self._parse_integer(rsi_match.group(1))

            # Extract CAS number
            cas_match = re.search(r'(?:cas|cas#|cas\s*no\.?)[:\s]*(\d+-\d+-\d+)', line_lower)
            if cas_match:
                hit_data['cas'] = self._clean_cas(cas_match.group(1))
            elif not hit_data.get('cas'):
                # Try standalone CAS pattern
                standalone_cas = re.search(r'\b(\d{2,7}-\d{2}-\d)\b', line)
                if standalone_cas:
                    hit_data['cas'] = self._clean_cas(standalone_cas.group(1))

            # Extract molecular weight
            mw_match = re.search(r'(?:mw|mol\.?\s*wt\.?|molecular\s*weight)[:\s]+(\d+)', line_lower)
            if mw_match:
                hit_data['mw'] = self._parse_integer(mw_match.group(1))

            # Extract molecular formula
            formula_match = re.search(r'(?:formula|mf)[:\s]+([A-Z][A-Za-z0-9]+)', line)
            if formula_match:
                hit_data['formula'] = formula_match.group(1)

            # Extract compound name - often on its own line
            name_match = re.search(r'(?:name|compound|id)[:\s]+(.+)$', line_lower)
            if name_match:
                hit_data['name'] = self._clean_compound_name(name_match.group(1))
            elif not hit_data.get('name') and not any(k in line_lower for k in ['si:', 'cas:', 'mw:', 'formula:']):
                # Might be a name-only line
                potential_name = self._clean_compound_name(line)
                if potential_name and len(potential_name) > 3:
                    hit_data['name'] = potential_name

            idx += 1

        return (hit_data if hit_data else None), idx

    def _parse_tabular_format(self, lines: list[str]) -> list[dict]:
        """Parse NIST results in tabular format.

        Common tabular format:
        Hit# SI RSI Compound CAS MW Formula Library
        """
        results = []
        headers = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            line_lower = line.lower()

            # Detect header line
            if not headers and any(h in line_lower for h in ['hit#', 'hit', 'compound', 'si', 'similarity']):
                if '\t' in line:
                    headers = line.split('\t')
                else:
                    headers = re.split(r'\s{2,}', line)
                continue

            # Parse data lines
            if headers and (re.match(r'^\d', line) or line_lower.startswith('hit')):
                if '\t' in line:
                    values = line.split('\t')
                else:
                    values = re.split(r'\s{2,}', line)

                hit_data = self._map_values_to_headers(values, headers)
                if hit_data:
                    results.append(hit_data)

        return results

    def _map_values_to_headers(self, values: list[str], headers: list[str]) -> Optional[dict]:
        """Map values to headers for tabular data."""
        hit_data = {}
        headers_lower = [h.lower() for h in headers]

        for i, value in enumerate(values):
            if i >= len(headers):
                break

            header = headers_lower[i]

            if any(s in header for s in ['si', 'similarity', 'mf', 'match']):
                if 'reverse' in header or 'rsi' in header or 'rsim' in header:
                    hit_data['reverse_match'] = self._parse_integer(value)
                elif not hit_data.get('similarity'):
                    hit_data['similarity'] = self._parse_integer(value)
            elif any(n in header for n in ['name', 'compound', 'id']):
                hit_data['name'] = self._clean_compound_name(value)
            elif 'cas' in header:
                hit_data['cas'] = self._clean_cas(value)
            elif any(m in header for m in ['mw', 'mol', 'weight']):
                hit_data['mw'] = self._parse_integer(value)
            elif 'formula' in header:
                hit_data['formula'] = value.strip()
            elif any(r in header for r in ['rt', 'ret', 'time']):
                hit_data['rt'] = self._parse_numeric(value)
            elif any(a in header for a in ['area', 'pct', '%']):
                hit_data['area_pct'] = self._parse_numeric(value)

        return hit_data if hit_data.get('name') or hit_data.get('similarity') else None

    def _parse_spectrum_blocks(self, content: str) -> list[dict]:
        """Parse spectrum-organized NIST results.

        Format with spectrum headers:
        Spec# RT Area% ...
        Hit 1: Name (SI: XX, RSI: XX)
        """
        results = []

        # Split by spectrum blocks
        spectrum_pattern = r'(?:spec(?:trum)?(?:#|:|\s+)?\s*(\d+)|pk(?:#|:|\s+)?\s*(\d+))'

        blocks = re.split(spectrum_pattern, content, flags=re.IGNORECASE)

        current_rt = None
        current_area = None

        for block in blocks:
            if not block:
                continue

            # Look for RT and Area in block
            rt_match = re.search(r'(?:r\.?t\.?|ret\.?\s*time)[:\s]*(\d+\.?\d*)', block, re.IGNORECASE)
            if rt_match:
                current_rt = self._parse_numeric(rt_match.group(1))

            area_match = re.search(r'(?:area\s*%?|pct)[:\s]*(\d+\.?\d*)', block, re.IGNORECASE)
            if area_match:
                current_area = self._parse_numeric(area_match.group(1))

            # Find hits in this block
            hit_pattern = r'hit\s*(\d+)[:\s]*([^\n]+)'
            hits = re.findall(hit_pattern, block, re.IGNORECASE)

            for hit_num, hit_text in hits:
                hit_data = {
                    'hit_num': int(hit_num),
                    'rt': current_rt,
                    'area_pct': current_area
                }

                # Parse hit text for name and scores
                si_match = re.search(r'(?:si|sim)[:\s]*(\d+)', hit_text, re.IGNORECASE)
                if si_match:
                    hit_data['similarity'] = self._parse_integer(si_match.group(1))

                rsi_match = re.search(r'(?:rsi|rsim)[:\s]*(\d+)', hit_text, re.IGNORECASE)
                if rsi_match:
                    hit_data['reverse_match'] = self._parse_integer(rsi_match.group(1))

                cas_match = re.search(r'(\d{2,7}-\d{2}-\d)', hit_text)
                if cas_match:
                    hit_data['cas'] = self._clean_cas(cas_match.group(1))

                # Name is usually before the parenthetical scores
                name_match = re.match(r'^([^(]+)', hit_text)
                if name_match:
                    hit_data['name'] = self._clean_compound_name(name_match.group(1))

                if hit_data.get('name') or hit_data.get('similarity'):
                    results.append(hit_data)

        return results

    def parse(self, file_path: Path) -> NaturalProfile:
        """Parse NIST MS Search results file into NaturalProfile.

        Args:
            file_path: Path to the NIST MS Search results file.

        Returns:
            NaturalProfile containing extracted peak and match data.

        Raises:
            ValueError: If the file format is not recognized or contains
                no valid match data.
            FileNotFoundError: If the file does not exist.
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        lines = content.split('\n')

        # Try different parsing strategies
        results = []

        # Strategy 1: Tabular format
        results = self._parse_tabular_format(lines)

        # Strategy 2: Spectrum blocks
        if not results:
            results = self._parse_spectrum_blocks(content)

        # Strategy 3: Sequential hit entries
        if not results:
            results = self._parse_sequential_hits(lines)

        if not results:
            raise ValueError(
                f"Could not find valid NIST search results in: {file_path}"
            )

        # Convert to peaks, taking best hit per RT
        peaks_by_rt = {}

        for result in results:
            rt = result.get('rt', 0.0) or 0.0

            # Use rounded RT as key for grouping
            rt_key = round(rt, 2)

            # Keep best hit (highest similarity)
            if rt_key not in peaks_by_rt or (
                result.get('similarity', 0) > peaks_by_rt[rt_key].get('similarity', 0)
            ):
                peaks_by_rt[rt_key] = result

        peaks = []
        for rt_key, data in sorted(peaks_by_rt.items()):
            peak = GCMSPeak(
                retention_time=data.get('rt', rt_key),
                area_percent=data.get('area_pct', 0.0) or 0.0,
                compound_name=data.get('name'),
                cas_number=data.get('cas'),
                match_quality=data.get('similarity')
            )
            peaks.append(peak)

        # Sort by similarity score descending (NIST results typically emphasize match quality)
        peaks.sort(key=lambda p: p.match_quality or 0, reverse=True)

        return NaturalProfile(
            name=file_path.stem,
            peaks=peaks,
            notes=f"Parsed from NIST MS Search results: {file_path.name}"
        )

    def _parse_sequential_hits(self, lines: list[str]) -> list[dict]:
        """Parse sequentially listed hit entries."""
        results = []
        current_rt = None
        current_area = None

        idx = 0
        while idx < len(lines):
            line = lines[idx].strip()

            # Look for spectrum/peak RT info
            rt_match = re.search(r'(?:r\.?t\.?|ret\.?\s*time|scan)[:\s]*(\d+\.?\d*)', line, re.IGNORECASE)
            if rt_match:
                current_rt = self._parse_numeric(rt_match.group(1))

            area_match = re.search(r'(?:area\s*%?|pct)[:\s]*(\d+\.?\d*)', line, re.IGNORECASE)
            if area_match:
                current_area = self._parse_numeric(area_match.group(1))

            # Check for hit entry start
            if re.match(r'^(?:hit\s*)?\d+[\.\):\s]', line, re.IGNORECASE):
                hit_data, idx = self._parse_hit_entry(lines, idx)
                if hit_data:
                    hit_data['rt'] = hit_data.get('rt') or current_rt
                    hit_data['area_pct'] = hit_data.get('area_pct') or current_area
                    results.append(hit_data)
                continue

            idx += 1

        return results
