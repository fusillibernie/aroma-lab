"""Tests for the FastAPI endpoints."""

import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


class TestAromachemicalEndpoints:
    def test_get_aromachemicals(self, client):
        """Test listing aromachemicals."""
        response = client.get("/api/aromachemicals")
        assert response.status_code == 200

        data = response.json()
        assert "chemicals" in data
        assert "count" in data
        assert data["count"] >= 0

    def test_filter_by_family(self, client):
        """Test filtering aromachemicals by odor family."""
        response = client.get("/api/aromachemicals?family=floral")
        assert response.status_code == 200

        data = response.json()
        # All returned chemicals should have floral in their families
        for chem in data["chemicals"]:
            families = [f.lower() for f in chem.get("odor_families", [])]
            assert "floral" in families

    def test_filter_by_volatility(self, client):
        """Test filtering aromachemicals by volatility."""
        response = client.get("/api/aromachemicals?volatility=base")
        assert response.status_code == 200

        data = response.json()
        for chem in data["chemicals"]:
            assert chem.get("volatility", "").lower() == "base"

    def test_search_aromachemicals(self, client):
        """Test searching aromachemicals."""
        response = client.get("/api/aromachemicals?search=rose")
        assert response.status_code == 200

        data = response.json()
        # Results should contain 'rose' in name or description
        if data["chemicals"]:
            for chem in data["chemicals"]:
                name = chem.get("name", "").lower()
                desc = chem.get("odor_description", "").lower()
                cas = chem.get("cas_number", "").lower()
                assert "rose" in name or "rose" in desc or "rose" in cas

    def test_get_odor_families(self, client):
        """Test getting list of odor families."""
        response = client.get("/api/odor-families")
        assert response.status_code == 200

        data = response.json()
        assert "families" in data
        assert isinstance(data["families"], list)


class TestFormulaEndpoints:
    def test_create_formula(self, client):
        """Test creating a formula."""
        formula_data = {
            "name": "Test Formula",
            "ingredients": [
                {"cas_number": "106-24-1", "percentage": 50.0},
                {"cas_number": "106-22-9", "percentage": 50.0},
            ],
        }

        response = client.post("/api/formulas", json=formula_data)
        assert response.status_code == 200

        data = response.json()
        assert "id" in data
        assert "formula" in data

    def test_list_formulas(self, client):
        """Test listing formulas."""
        response = client.get("/api/formulas")
        assert response.status_code == 200

        data = response.json()
        assert "formulas" in data
        assert isinstance(data["formulas"], list)

    def test_get_nonexistent_formula(self, client):
        """Test getting a formula that doesn't exist."""
        response = client.get("/api/formulas/nonexistent-id")
        assert response.status_code == 404


class TestGCMSEndpoints:
    def test_upload_gcms_csv(self, client):
        """Test uploading a GC-MS CSV file."""
        csv_content = b"""Retention Time,Area,Compound
5.23,15.5,Limonene
8.45,25.3,Linalool
"""
        files = {"file": ("test.csv", csv_content, "text/csv")}
        response = client.post("/api/upload/gcms", files=files)

        assert response.status_code == 200
        data = response.json()
        assert "peaks" in data
        assert data["peak_count"] >= 0


class TestOptimizationEndpoints:
    @pytest.fixture
    def formula_id(self, client):
        """Create a formula and return its ID."""
        formula_data = {
            "name": "Optimization Test",
            "ingredients": [
                {"cas_number": "106-24-1", "percentage": 30.0},
                {"cas_number": "106-22-9", "percentage": 30.0},
                {"cas_number": "3691-12-1", "percentage": 40.0},
            ],
        }
        response = client.post("/api/formulas", json=formula_data)
        return response.json()["id"]

    def test_volatility_analysis(self, client, formula_id):
        """Test volatility analysis endpoint."""
        response = client.get(f"/api/formulas/{formula_id}/volatility-analysis")
        assert response.status_code == 200

        data = response.json()
        assert "top_note_percent" in data
        assert "heart_note_percent" in data
        assert "base_note_percent" in data
        assert "balance_score" in data

    def test_ifra_check(self, client, formula_id):
        """Test IFRA compliance check endpoint."""
        response = client.get(
            f"/api/formulas/{formula_id}/ifra-check?application=fine_fragrance"
        )
        assert response.status_code == 200

        data = response.json()
        assert "is_compliant" in data
        assert "issues" in data

    def test_longevity_estimate(self, client, formula_id):
        """Test longevity estimation endpoint."""
        response = client.get(f"/api/formulas/{formula_id}/longevity-estimate")
        assert response.status_code == 200

        data = response.json()
        assert "initial_impact" in data
        assert "longevity_hours" in data
        assert "sillage_rating" in data

    def test_suggestions(self, client, formula_id):
        """Test suggestions endpoint."""
        response = client.get(
            f"/api/formulas/{formula_id}/suggestions?application=fine_fragrance"
        )
        assert response.status_code == 200

        data = response.json()
        assert "suggestions" in data
        assert isinstance(data["suggestions"], list)
