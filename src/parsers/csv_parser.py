"""CSV parser for GC-MS data exports."""

from pathlib import Path

import pandas as pd

from src.models import GCMSPeak, NaturalProfile
from .base import BaseParser


class CSVParser(BaseParser):
    """Parse GC-MS data from CSV exports.

    Expected columns (flexible naming):
    - Retention time (RT, retention_time, time)
    - Area % (area_percent, area%, pct)
    - Compound name (compound, name, compound_name)
    - CAS number (cas, cas_number, cas#) [optional]
    - Match quality (match, quality, match_quality) [optional]
    """

    # Column name mappings
    RT_COLUMNS = ["rt", "retention_time", "time", "ret_time", "retention time"]
    AREA_COLUMNS = ["area_percent", "area%", "area %", "pct", "percent", "area percent", "%"]
    NAME_COLUMNS = ["compound", "name", "compound_name", "compound name", "identification"]
    CAS_COLUMNS = ["cas", "cas_number", "cas#", "cas number"]
    MATCH_COLUMNS = ["match", "quality", "match_quality", "match quality", "si", "similarity"]

    def can_parse(self, file_path: Path) -> bool:
        """Check if file is a CSV we can parse."""
        return file_path.suffix.lower() == ".csv"

    def _find_column(self, df: pd.DataFrame, candidates: list[str]) -> str | None:
        """Find a column matching one of the candidate names."""
        df_cols_lower = {col.lower(): col for col in df.columns}
        for candidate in candidates:
            if candidate.lower() in df_cols_lower:
                return df_cols_lower[candidate.lower()]
        return None

    def parse(self, file_path: Path) -> NaturalProfile:
        """Parse CSV file into NaturalProfile."""
        df = pd.read_csv(file_path)

        # Find required columns
        rt_col = self._find_column(df, self.RT_COLUMNS)
        area_col = self._find_column(df, self.AREA_COLUMNS)
        name_col = self._find_column(df, self.NAME_COLUMNS)
        cas_col = self._find_column(df, self.CAS_COLUMNS)
        match_col = self._find_column(df, self.MATCH_COLUMNS)

        if not rt_col or not area_col:
            raise ValueError(
                f"CSV must contain retention time and area columns. "
                f"Found columns: {list(df.columns)}"
            )

        peaks = []
        for _, row in df.iterrows():
            peak = GCMSPeak(
                retention_time=float(row[rt_col]),
                area_percent=float(row[area_col]),
                compound_name=str(row[name_col]) if name_col and pd.notna(row[name_col]) else None,
                cas_number=str(row[cas_col]) if cas_col and pd.notna(row[cas_col]) else None,
                match_quality=float(row[match_col]) if match_col and pd.notna(row[match_col]) else None,
            )
            peaks.append(peak)

        # Sort by area percent descending
        peaks.sort(key=lambda p: p.area_percent, reverse=True)

        return NaturalProfile(
            name=file_path.stem,
            peaks=peaks,
        )
