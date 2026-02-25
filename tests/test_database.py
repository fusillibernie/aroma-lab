"""Tests for aromachemical database."""

import json
import tempfile
from pathlib import Path

import pytest

from src.database import AromachemicalDB, load_from_json, load_from_csv
from src.models import Aromachemical, OdorFamily, Volatility


class TestAromachemicalDB:
    def test_empty_init(self):
        db = AromachemicalDB()
        assert len(db) == 0

    def test_add_and_retrieve_by_cas(self):
        db = AromachemicalDB()
        geraniol = Aromachemical(
            cas_number="106-24-1",
            name="Geraniol",
            odor_description="Rose-like",
        )
        db.add(geraniol)

        assert len(db) == 1
        assert db.get_by_cas("106-24-1") == geraniol
        assert db.get_by_cas("999-99-9") is None

    def test_retrieve_by_name(self):
        db = AromachemicalDB()
        db.add(Aromachemical(
            cas_number="106-24-1",
            name="Geraniol",
        ))

        assert db.get_by_name("Geraniol") is not None
        assert db.get_by_name("geraniol") is not None  # Case insensitive
        assert db.get_by_name("GERANIOL") is not None

    def test_contains(self):
        db = AromachemicalDB()
        db.add(Aromachemical(cas_number="106-24-1", name="Geraniol"))

        assert "106-24-1" in db
        assert "999-99-9" not in db

    def test_iteration(self):
        db = AromachemicalDB()
        db.add(Aromachemical(cas_number="106-24-1", name="Geraniol"))
        db.add(Aromachemical(cas_number="78-70-6", name="Linalool"))

        chemicals = list(db)
        assert len(chemicals) == 2

    def test_search_by_query(self):
        db = AromachemicalDB()
        db.add(Aromachemical(
            cas_number="106-24-1",
            name="Geraniol",
            odor_description="Sweet, floral, rose-like",
        ))
        db.add(Aromachemical(
            cas_number="77-53-2",
            name="Cedrol",
            odor_description="Woody, cedar",
        ))

        results = db.search(query="rose")
        assert len(results) == 1
        assert results[0].name == "Geraniol"

    def test_search_by_family(self):
        db = AromachemicalDB()
        db.add(Aromachemical(
            cas_number="106-24-1",
            name="Geraniol",
            odor_families=[OdorFamily.FLORAL],
        ))
        db.add(Aromachemical(
            cas_number="77-53-2",
            name="Cedrol",
            odor_families=[OdorFamily.WOODY],
        ))

        results = db.search(odor_family=OdorFamily.FLORAL)
        assert len(results) == 1
        assert results[0].name == "Geraniol"

    def test_search_by_volatility(self):
        db = AromachemicalDB()
        db.add(Aromachemical(
            cas_number="106-24-1",
            name="Geraniol",
            volatility=Volatility.HEART,
        ))
        db.add(Aromachemical(
            cas_number="77-53-2",
            name="Cedrol",
            volatility=Volatility.BASE,
        ))

        results = db.search(volatility=Volatility.HEART)
        assert len(results) == 1
        assert results[0].name == "Geraniol"

    def test_search_by_odor(self):
        db = AromachemicalDB()
        db.add(Aromachemical(
            cas_number="106-24-1",
            name="Geraniol",
            odor_description="Sweet, floral, rose-like",
        ))
        db.add(Aromachemical(
            cas_number="121-33-5",
            name="Vanillin",
            odor_description="Sweet, vanilla, warm",
        ))

        # Both are sweet
        results = db.search_by_odor("sweet")
        assert len(results) == 2

        # Only geraniol is rose-like
        results = db.search_by_odor("rose")
        assert len(results) == 1

    def test_save_and_load(self):
        db = AromachemicalDB()
        db.add(Aromachemical(
            cas_number="106-24-1",
            name="Geraniol",
            odor_families=[OdorFamily.FLORAL],
            volatility=Volatility.HEART,
        ))

        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "test.json"
            db.save(output_file)

            # Load into new database
            new_db = AromachemicalDB(Path(tmpdir))
            assert len(new_db) == 1
            assert new_db.get_by_cas("106-24-1") is not None

    def test_stats(self):
        db = AromachemicalDB()
        db.add(Aromachemical(
            cas_number="106-24-1",
            name="Geraniol",
            odor_families=[OdorFamily.FLORAL],
            volatility=Volatility.HEART,
            cost_per_kg_usd=50.0,
            ifra_restricted=True,
        ))
        db.add(Aromachemical(
            cas_number="77-53-2",
            name="Cedrol",
            odor_families=[OdorFamily.WOODY],
            volatility=Volatility.BASE,
        ))

        stats = db.stats()
        assert stats["total_count"] == 2
        assert stats["with_cost"] == 1
        assert stats["ifra_restricted"] == 1
        assert stats["by_volatility"]["heart"] == 1
        assert stats["by_volatility"]["base"] == 1


class TestLoaders:
    def test_load_from_json(self):
        data = [
            {
                "cas_number": "106-24-1",
                "name": "Geraniol",
                "odor_families": ["floral"],
                "volatility": "heart",
            }
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()

            chemicals = load_from_json(Path(f.name))
            assert len(chemicals) == 1
            assert chemicals[0].cas_number == "106-24-1"
            assert chemicals[0].volatility == Volatility.HEART

    def test_load_from_csv(self):
        csv_content = """CAS,Name,Odor Description,Family,Volatility
106-24-1,Geraniol,Rose-like sweet,floral,heart
77-53-2,Cedrol,Woody cedar,woody,base
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            f.flush()

            chemicals = load_from_csv(Path(f.name))
            assert len(chemicals) == 2

            geraniol = next(c for c in chemicals if c.name == "Geraniol")
            assert geraniol.cas_number == "106-24-1"
            assert geraniol.volatility == Volatility.HEART
            assert OdorFamily.FLORAL in geraniol.odor_families
