"""Parser for mzML and mzXML open standard mass spectrometry formats.

mzML and mzXML are open XML-based formats for mass spectrometry data,
developed by the HUPO-PSI (Human Proteome Organization - Proteomics
Standards Initiative). These formats store raw mass spec data including
spectra, chromatograms, and metadata.

This parser extracts:
- Chromatogram data (TIC, BPC, extracted ion chromatograms)
- Peak lists from centroided spectra
- Retention time and intensity information
- Compound identifications if present

References:
- mzML: https://www.psidev.info/mzML
- mzXML: http://tools.proteomecenter.org/wiki/index.php?title=Formats:mzXML
"""

import base64
import struct
import zlib
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Iterator

from src.models import GCMSPeak, NaturalProfile
from .base import BaseParser


class MzMLParser(BaseParser):
    """Parse mass spectrometry data from mzML and mzXML files.

    Supports both mzML and mzXML open standard formats for MS data.
    Extracts chromatographic and spectral information, converting
    them to peak data for aroma analysis.

    The parser handles:
    - Base64 encoded binary data arrays
    - Zlib compressed data
    - Both 32-bit and 64-bit float encodings
    - Multiple chromatogram types (TIC, BPC, SRM, etc.)
    """

    # XML namespaces
    MZML_NS = {
        'mzml': 'http://psi.hupo.org/ms/mzml',
        'mzml1': 'http://psi.hupo.org/schema_revision/mzML_1.1.0'
    }
    MZXML_NS = {
        'mzxml': 'http://sashimi.sourceforge.net/schema_revision/mzXML_3.2'
    }

    # CV parameter accessions (controlled vocabulary)
    CV_RETENTION_TIME = 'MS:1000016'
    CV_INTENSITY_ARRAY = 'MS:1000515'
    CV_MZ_ARRAY = 'MS:1000514'
    CV_TIME_ARRAY = 'MS:1000595'
    CV_64BIT_FLOAT = 'MS:1000523'
    CV_32BIT_FLOAT = 'MS:1000521'
    CV_ZLIB_COMPRESSION = 'MS:1000574'
    CV_NO_COMPRESSION = 'MS:1000576'
    CV_TIC = 'MS:1000235'  # Total ion current chromatogram
    CV_BPC = 'MS:1000628'  # Base peak chromatogram

    def can_parse(self, file_path: Path) -> bool:
        """Check if file is an mzML or mzXML file."""
        suffix = file_path.suffix.lower()
        if suffix not in ['.mzml', '.mzxml', '.xml']:
            return False

        try:
            # Check for mzML/mzXML root elements
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                header = f.read(1000)
                return '<mzML' in header or '<mzXML' in header or '<indexedmzML' in header
        except Exception:
            return False

    def _detect_format(self, root: ET.Element) -> str:
        """Detect if file is mzML or mzXML format."""
        tag = root.tag.lower()
        if 'mzml' in tag:
            return 'mzml'
        elif 'mzxml' in tag:
            return 'mzxml'

        # Check children
        for child in root:
            child_tag = child.tag.lower()
            if 'mzml' in child_tag:
                return 'mzml'
            elif 'msrun' in child_tag:
                return 'mzxml'

        return 'mzml'  # Default

    def _strip_namespace(self, tag: str) -> str:
        """Remove namespace from XML tag."""
        if '}' in tag:
            return tag.split('}')[1]
        return tag

    def _find_element(self, element: ET.Element, local_name: str) -> Optional[ET.Element]:
        """Find element by local name, ignoring namespace."""
        for child in element.iter():
            if self._strip_namespace(child.tag) == local_name:
                return child
        return None

    def _find_all_elements(self, element: ET.Element, local_name: str) -> Iterator[ET.Element]:
        """Find all elements by local name, ignoring namespace."""
        for child in element.iter():
            if self._strip_namespace(child.tag) == local_name:
                yield child

    def _get_cv_param(self, element: ET.Element, accession: str) -> Optional[ET.Element]:
        """Get CV parameter by accession number."""
        for cvParam in self._find_all_elements(element, 'cvParam'):
            if cvParam.get('accession') == accession:
                return cvParam
        return None

    def _get_cv_value(self, element: ET.Element, accession: str) -> Optional[str]:
        """Get CV parameter value by accession number."""
        param = self._get_cv_param(element, accession)
        if param is not None:
            return param.get('value')
        return None

    def _has_cv_param(self, element: ET.Element, accession: str) -> bool:
        """Check if element has CV parameter."""
        return self._get_cv_param(element, accession) is not None

    def _decode_binary_data(
        self,
        encoded_data: str,
        is_64bit: bool = True,
        is_compressed: bool = False
    ) -> list[float]:
        """Decode base64-encoded binary array data.

        Args:
            encoded_data: Base64-encoded string
            is_64bit: True for 64-bit floats, False for 32-bit
            is_compressed: True if zlib compressed

        Returns:
            List of decoded float values
        """
        if not encoded_data or not encoded_data.strip():
            return []

        try:
            # Decode base64
            binary_data = base64.b64decode(encoded_data.strip())

            # Decompress if needed
            if is_compressed:
                binary_data = zlib.decompress(binary_data)

            # Unpack floats
            fmt = 'd' if is_64bit else 'f'
            size = 8 if is_64bit else 4
            count = len(binary_data) // size

            values = struct.unpack(f'<{count}{fmt}', binary_data)
            return list(values)
        except Exception:
            return []

    def _parse_binary_data_array(self, array_element: ET.Element) -> tuple[list[float], str]:
        """Parse a binary data array element.

        Returns:
            Tuple of (values list, array type: 'mz', 'intensity', or 'time')
        """
        # Determine array type
        array_type = 'unknown'
        if self._has_cv_param(array_element, self.CV_MZ_ARRAY):
            array_type = 'mz'
        elif self._has_cv_param(array_element, self.CV_INTENSITY_ARRAY):
            array_type = 'intensity'
        elif self._has_cv_param(array_element, self.CV_TIME_ARRAY):
            array_type = 'time'

        # Determine encoding
        is_64bit = self._has_cv_param(array_element, self.CV_64BIT_FLOAT)
        is_compressed = self._has_cv_param(array_element, self.CV_ZLIB_COMPRESSION)

        # Find binary element
        binary_elem = self._find_element(array_element, 'binary')
        if binary_elem is None or binary_elem.text is None:
            return [], array_type

        values = self._decode_binary_data(binary_elem.text, is_64bit, is_compressed)
        return values, array_type

    def _parse_mzml_chromatogram(self, chrom_element: ET.Element) -> dict:
        """Parse a chromatogram element from mzML."""
        chrom_data = {
            'id': chrom_element.get('id', ''),
            'times': [],
            'intensities': [],
            'type': 'unknown'
        }

        # Determine chromatogram type
        if self._has_cv_param(chrom_element, self.CV_TIC):
            chrom_data['type'] = 'TIC'
        elif self._has_cv_param(chrom_element, self.CV_BPC):
            chrom_data['type'] = 'BPC'

        # Parse binary data arrays
        for array in self._find_all_elements(chrom_element, 'binaryDataArray'):
            values, array_type = self._parse_binary_data_array(array)

            if array_type == 'time':
                chrom_data['times'] = values
            elif array_type == 'intensity':
                chrom_data['intensities'] = values

        return chrom_data

    def _parse_mzml_spectrum(self, spectrum_element: ET.Element) -> dict:
        """Parse a spectrum element from mzML."""
        spectrum_data = {
            'id': spectrum_element.get('id', ''),
            'index': spectrum_element.get('index'),
            'rt': None,
            'mz_values': [],
            'intensities': []
        }

        # Get retention time from scan element
        scan = self._find_element(spectrum_element, 'scan')
        if scan is not None:
            rt_value = self._get_cv_value(scan, self.CV_RETENTION_TIME)
            if rt_value:
                spectrum_data['rt'] = float(rt_value)

        # Also check directly on spectrum element
        if spectrum_data['rt'] is None:
            rt_value = self._get_cv_value(spectrum_element, self.CV_RETENTION_TIME)
            if rt_value:
                spectrum_data['rt'] = float(rt_value)

        # Parse binary data arrays
        for array in self._find_all_elements(spectrum_element, 'binaryDataArray'):
            values, array_type = self._parse_binary_data_array(array)

            if array_type == 'mz':
                spectrum_data['mz_values'] = values
            elif array_type == 'intensity':
                spectrum_data['intensities'] = values

        return spectrum_data

    def _parse_mzxml_scan(self, scan_element: ET.Element) -> dict:
        """Parse a scan element from mzXML."""
        scan_data = {
            'num': scan_element.get('num'),
            'rt': None,
            'mz_values': [],
            'intensities': [],
            'base_peak_mz': None,
            'base_peak_intensity': None,
            'total_ion_current': None
        }

        # Get retention time (in seconds or minutes)
        rt_str = scan_element.get('retentionTime', '')
        if rt_str:
            # Handle PT##.##S format (seconds)
            match = re.match(r'PT?(\d+\.?\d*)S?', rt_str, re.IGNORECASE)
            if match:
                rt_seconds = float(match.group(1))
                scan_data['rt'] = rt_seconds / 60.0  # Convert to minutes

        # Get other attributes
        scan_data['base_peak_mz'] = self._parse_float(scan_element.get('basePeakMz'))
        scan_data['base_peak_intensity'] = self._parse_float(scan_element.get('basePeakIntensity'))
        scan_data['total_ion_current'] = self._parse_float(scan_element.get('totIonCurrent'))

        # Parse peaks data
        peaks_elem = self._find_element(scan_element, 'peaks')
        if peaks_elem is not None and peaks_elem.text:
            precision = int(peaks_elem.get('precision', '32'))
            compression = peaks_elem.get('compressionType', 'none')

            is_64bit = precision == 64
            is_compressed = compression.lower() == 'zlib'

            # mzXML stores m/z and intensity interleaved
            values = self._decode_binary_data(peaks_elem.text, is_64bit, is_compressed)

            # Deinterleave
            scan_data['mz_values'] = values[0::2]
            scan_data['intensities'] = values[1::2]

        return scan_data

    def _parse_float(self, value: Optional[str]) -> Optional[float]:
        """Parse a float value safely."""
        if value is None:
            return None
        try:
            return float(value)
        except ValueError:
            return None

    def _extract_peaks_from_chromatogram(self, chrom_data: dict, min_intensity_pct: float = 0.5) -> list[dict]:
        """Extract peaks from chromatogram data using simple peak detection.

        Args:
            chrom_data: Chromatogram data with times and intensities
            min_intensity_pct: Minimum intensity as percentage of max

        Returns:
            List of detected peaks with RT and relative intensity
        """
        times = chrom_data.get('times', [])
        intensities = chrom_data.get('intensities', [])

        if not times or not intensities or len(times) != len(intensities):
            return []

        peaks = []
        max_intensity = max(intensities) if intensities else 0

        if max_intensity == 0:
            return []

        min_intensity = max_intensity * (min_intensity_pct / 100)

        # Simple peak detection: find local maxima
        for i in range(1, len(intensities) - 1):
            if intensities[i] > intensities[i-1] and intensities[i] > intensities[i+1]:
                if intensities[i] >= min_intensity:
                    peaks.append({
                        'rt': times[i],
                        'intensity': intensities[i],
                        'intensity_pct': (intensities[i] / max_intensity) * 100
                    })

        return peaks

    def _extract_peaks_from_spectra(self, spectra: list[dict]) -> list[dict]:
        """Extract peak data from a list of spectra.

        For GC-MS data, each spectrum typically represents a scan at a
        specific retention time. We extract the base peak (highest intensity)
        information from each spectrum.
        """
        peaks = []
        total_intensity = 0

        for spectrum in spectra:
            rt = spectrum.get('rt')
            if rt is None:
                continue

            mz_values = spectrum.get('mz_values', [])
            intensities = spectrum.get('intensities', [])

            if intensities:
                max_intensity = max(intensities)
                max_idx = intensities.index(max_intensity)
                base_peak_mz = mz_values[max_idx] if mz_values and len(mz_values) > max_idx else None

                peaks.append({
                    'rt': rt,
                    'intensity': max_intensity,
                    'base_peak_mz': base_peak_mz
                })
                total_intensity += max_intensity

        # Calculate percentages
        if total_intensity > 0:
            for peak in peaks:
                peak['intensity_pct'] = (peak['intensity'] / total_intensity) * 100

        return peaks

    def parse(self, file_path: Path) -> NaturalProfile:
        """Parse mzML or mzXML file into NaturalProfile.

        The parser extracts chromatographic and spectral data from the
        open MS formats and converts them to peak data suitable for
        aroma profile analysis.

        Args:
            file_path: Path to the mzML or mzXML file.

        Returns:
            NaturalProfile containing extracted peak data.

        Raises:
            ValueError: If the file format is not recognized or parsing fails.
            FileNotFoundError: If the file does not exist.
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
        except ET.ParseError as e:
            raise ValueError(f"Failed to parse XML file {file_path}: {e}")

        # Detect format
        format_type = self._detect_format(root)

        peaks_data = []

        if format_type == 'mzml':
            peaks_data = self._parse_mzml(root)
        else:
            peaks_data = self._parse_mzxml(root)

        if not peaks_data:
            raise ValueError(
                f"No valid peak data found in {format_type.upper()} file: {file_path}"
            )

        # Convert to GCMSPeak objects
        peaks = []
        for data in peaks_data:
            peak = GCMSPeak(
                retention_time=data.get('rt', 0.0),
                area_percent=data.get('intensity_pct', 0.0),
                base_peak_mz=data.get('base_peak_mz')
            )
            peaks.append(peak)

        # Sort by area percent descending
        peaks.sort(key=lambda p: p.area_percent, reverse=True)

        return NaturalProfile(
            name=file_path.stem,
            peaks=peaks,
            notes=f"Parsed from {format_type.upper()} file: {file_path.name}"
        )

    def _parse_mzml(self, root: ET.Element) -> list[dict]:
        """Parse mzML format data."""
        peaks_data = []

        # Try chromatograms first (preferred for GC-MS)
        for chrom in self._find_all_elements(root, 'chromatogram'):
            chrom_data = self._parse_mzml_chromatogram(chrom)

            # Use TIC or BPC chromatogram for peak detection
            if chrom_data['type'] in ['TIC', 'BPC']:
                chrom_peaks = self._extract_peaks_from_chromatogram(chrom_data)
                if chrom_peaks:
                    peaks_data = chrom_peaks
                    break

        # Fall back to spectra if no chromatogram peaks found
        if not peaks_data:
            spectra = []
            for spectrum in self._find_all_elements(root, 'spectrum'):
                spec_data = self._parse_mzml_spectrum(spectrum)
                if spec_data.get('rt') is not None:
                    spectra.append(spec_data)

            if spectra:
                peaks_data = self._extract_peaks_from_spectra(spectra)

        return peaks_data

    def _parse_mzxml(self, root: ET.Element) -> list[dict]:
        """Parse mzXML format data."""
        spectra = []

        for scan in self._find_all_elements(root, 'scan'):
            scan_data = self._parse_mzxml_scan(scan)
            if scan_data.get('rt') is not None:
                spectra.append(scan_data)

        if spectra:
            return self._extract_peaks_from_spectra(spectra)

        return []


# Import re for mzXML parsing
import re
