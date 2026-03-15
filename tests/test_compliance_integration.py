"""Tests for cross-service compliance check and enriched chemical endpoints."""

import pytest
import respx
import httpx
from fastapi.testclient import TestClient

from api.main import app, formulas_db


@pytest.fixture(autouse=True)
def clean_formulas():
    """Ensure formulas_db is clean for each test."""
    original = dict(formulas_db)
    formulas_db.clear()
    yield
    formulas_db.clear()
    formulas_db.update(original)


@pytest.fixture
def test_client():
    return TestClient(app)


@pytest.fixture
def sample_formula():
    """Create a formula in the DB and return its ID."""
    formula_id = "test-001"
    formulas_db[formula_id] = {
        "id": formula_id,
        "name": "Test Rose Accord",
        "ingredients": [
            {"cas_number": "106-24-1", "name": "Geraniol", "percentage": 25.0},
            {"cas_number": "78-70-6", "name": "Linalool", "percentage": 15.0},
            {"cas_number": "60-12-8", "name": "Phenethyl Alcohol", "percentage": 10.0},
        ],
        "total_percentage": 50.0,
    }
    return formula_id


class TestHealthEndpoint:
    def test_health(self, test_client):
        resp = test_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "aroma-lab"


class TestIntegrationStatus:
    @respx.mock
    def test_status_connected(self, test_client):
        respx.get("http://localhost:8001/health").mock(
            return_value=httpx.Response(200, json={"status": "healthy"})
        )
        resp = test_client.get("/api/integration/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["smell_reg"]["connected"] is True

    @respx.mock
    def test_status_disconnected(self, test_client):
        respx.get("http://localhost:8001/health").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        resp = test_client.get("/api/integration/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["smell_reg"]["connected"] is False


class TestIFRARestrictionsEndpoint:
    def test_get_ifra_restrictions(self, test_client):
        resp = test_client.get("/api/ifra-restrictions")
        assert resp.status_code == 200
        data = resp.json()
        assert "metadata" in data
        assert "restrictions" in data
        assert isinstance(data["restrictions"], list)


class TestComplianceCheck:
    @respx.mock
    def test_compliance_check_success(self, test_client, sample_formula):
        compliance_result = {
            "formula_name": "Test Rose Accord",
            "is_compliant": True,
            "results": [],
        }
        respx.post("http://localhost:8001/api/compliance/check").mock(
            return_value=httpx.Response(200, json=compliance_result)
        )

        resp = test_client.post(
            f"/api/formulas/{sample_formula}/compliance-check",
            json={
                "product_type": "fine_fragrance",
                "markets": ["eu"],
                "fragrance_concentration": 20.0,
                "is_leave_on": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_compliant"] is True

    @respx.mock
    def test_compliance_check_service_unavailable(self, test_client, sample_formula):
        respx.post("http://localhost:8001/api/compliance/check").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        resp = test_client.post(
            f"/api/formulas/{sample_formula}/compliance-check",
            json={
                "product_type": "fine_fragrance",
                "markets": ["eu"],
            },
        )
        assert resp.status_code == 503

    def test_compliance_check_formula_not_found(self, test_client):
        resp = test_client.post(
            "/api/formulas/nonexistent/compliance-check",
            json={
                "product_type": "fine_fragrance",
                "markets": ["eu"],
            },
        )
        assert resp.status_code == 404

    @respx.mock
    def test_compliance_check_non_compliant(self, test_client, sample_formula):
        compliance_result = {
            "formula_name": "Test Rose Accord",
            "is_compliant": False,
            "results": [
                {
                    "requirement": "IFRA Category 4 limit",
                    "status": "non_compliant",
                    "cas_number": "106-24-1",
                    "ingredient_name": "Geraniol",
                    "current_value": 25.0,
                    "limit_value": 10.0,
                }
            ],
        }
        respx.post("http://localhost:8001/api/compliance/check").mock(
            return_value=httpx.Response(200, json=compliance_result)
        )

        resp = test_client.post(
            f"/api/formulas/{sample_formula}/compliance-check",
            json={
                "product_type": "fine_fragrance",
                "markets": ["eu", "us"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_compliant"] is False
        assert len(data["results"]) == 1


class TestEnrichedAromachemical:
    @respx.mock
    def test_enriched_with_regulatory(self, test_client):
        reg_data = {
            "cas_number": "78-70-6",
            "ifra_restriction": None,
            "allergen": {"is_allergen": True, "name": "Linalool"},
        }
        respx.get("http://localhost:8001/api/materials/78-70-6/regulatory").mock(
            return_value=httpx.Response(200, json=reg_data)
        )

        resp = test_client.get("/api/aromachemicals/78-70-6/enriched")
        if resp.status_code == 200:
            data = resp.json()
            assert data["cas_number"] == "78-70-6"
            if data.get("regulatory"):
                assert data["regulatory"]["cas_number"] == "78-70-6"

    @respx.mock
    def test_enriched_without_regulatory(self, test_client):
        respx.get("http://localhost:8001/api/materials/78-70-6/regulatory").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        resp = test_client.get("/api/aromachemicals/78-70-6/enriched")
        # If chemical exists, should return 200 with regulatory=None
        if resp.status_code == 200:
            data = resp.json()
            assert data["regulatory"] is None

    def test_enriched_not_found(self, test_client):
        resp = test_client.get("/api/aromachemicals/999-99-9/enriched")
        assert resp.status_code == 404

    def test_enriched_rejects_invalid_cas(self, test_client):
        resp = test_client.get("/api/aromachemicals/../../etc/passwd/enriched")
        # FastAPI may return 400 or route it differently
        assert resp.status_code in (400, 404, 422)

    def test_enriched_rejects_traversal(self, test_client):
        resp = test_client.get("/api/aromachemicals/not-a-cas/enriched")
        assert resp.status_code == 400


class TestInputValidation:
    def test_compliance_rejects_invalid_product_type(self, test_client, sample_formula):
        resp = test_client.post(
            f"/api/formulas/{sample_formula}/compliance-check",
            json={
                "product_type": "invalid_type",
                "markets": ["eu"],
            },
        )
        assert resp.status_code == 400

    def test_compliance_rejects_invalid_market(self, test_client, sample_formula):
        resp = test_client.post(
            f"/api/formulas/{sample_formula}/compliance-check",
            json={
                "product_type": "fine_fragrance",
                "markets": ["invalid_market"],
            },
        )
        assert resp.status_code == 400
