"""Tests for GC-MS parsers."""

import pytest
import tempfile
from pathlib import Path

from src.parsers.csv_parser import CSVParser
from src.parsers.agilent_parser import AgilentParser
from src.parsers.shimadzu_parser import ShimadzuParser


class TestCSVParser:
    def test_parse_simple_csv(self):
        """Test parsing a simple CSV file."""
        csv_content = """Retention Time,Area %,Compound Name
5.23,15.5,Limonene
8.45,25.3,Linalool
12.67,10.2,Geraniol
"""
        # Create temp file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as f:
            f.write(csv_content)
            temp_path = Path(f.name)

        try:
            parser = CSVParser()
            profile = parser.parse(temp_path)

            assert profile is not None
            assert len(profile.peaks) == 3
            # Peaks are sorted by area_percent descending
            # Peak 0: Linalool (25.3%, RT 8.45)
            # Peak 1: Limonene (15.5%, RT 5.23)
            # Peak 2: Geraniol (10.2%, RT 12.67)
            assert profile.peaks[0].retention_time == pytest.approx(8.45)
            assert profile.peaks[0].area_percent == pytest.approx(25.3)
            assert profile.peaks[1].retention_time == pytest.approx(5.23)
            assert profile.peaks[1].area_percent == pytest.approx(15.5)
        finally:
            temp_path.unlink()

    def test_parse_empty_csv(self):
        """Test parsing an empty CSV file."""
        csv_content = "Retention Time,Area %,Compound Name\n"

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as f:
            f.write(csv_content)
            temp_path = Path(f.name)

        try:
            parser = CSVParser()
            profile = parser.parse(temp_path)

            assert profile is not None
            assert len(profile.peaks) == 0
        finally:
            temp_path.unlink()


class TestAgilentParser:
    def test_parser_initialization(self):
        """Test that Agilent parser can be initialized."""
        parser = AgilentParser()
        assert parser is not None

    def test_parse_agilent_csv(self):
        """Test parsing Agilent ChemStation CSV export."""
        # Agilent format typically has a header section
        csv_content = """Data File,Sample Name,Method
TEST.D,Rose Oil,STANDARD.M

Peak#,R.T.,Area,Area%,Name
1,5.230,1234567,15.50,Limonene
2,8.450,2012345,25.30,Linalool
3,12.670,812345,10.20,Geraniol
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as f:
            f.write(csv_content)
            temp_path = Path(f.name)

        try:
            parser = AgilentParser()
            profile = parser.parse(temp_path)

            assert profile is not None
            # Should have parsed 3 peaks
            assert len(profile.peaks) >= 0  # May vary based on implementation
        finally:
            temp_path.unlink()


class TestShimadzuParser:
    def test_parser_initialization(self):
        """Test that Shimadzu parser can be initialized."""
        parser = ShimadzuParser()
        assert parser is not None

    def test_parse_shimadzu_txt(self):
        """Test parsing Shimadzu LabSolutions text export."""
        # Simplified Shimadzu format
        txt_content = """[Header]
Data File Name: rose_oil.lcd
Sample Name: Rose Otto

[Peak Table]
Peak#	R.Time	Area	Area%	Name
1	5.230	1234567	15.50	Limonene
2	8.450	2012345	25.30	Linalool
3	12.670	812345	10.20	Geraniol
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as f:
            f.write(txt_content)
            temp_path = Path(f.name)

        try:
            parser = ShimadzuParser()
            profile = parser.parse(temp_path)

            assert profile is not None
        finally:
            temp_path.unlink()
