"""Tests for the SmellRegClient HTTP integration."""

import pytest
import respx
import httpx

from src.integrations.smell_reg_client import SmellRegClient


@pytest.fixture
def client():
    """Create a SmellRegClient with a test base URL."""
    return SmellRegClient(base_url="http://testserver:8001")


@pytest.mark.asyncio
class TestSmellRegClientHealth:
    """Tests for health check."""

    @respx.mock
    async def test_health_check_success(self, client):
        respx.get("http://testserver:8001/health").mock(
            return_value=httpx.Response(200, json={"status": "healthy"})
        )
        assert await client.check_health() is True

    @respx.mock
    async def test_health_check_failure(self, client):
        respx.get("http://testserver:8001/health").mock(
            return_value=httpx.Response(500)
        )
        assert await client.check_health() is False

    @respx.mock
    async def test_health_check_connection_error(self, client):
        respx.get("http://testserver:8001/health").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        assert await client.check_health() is False


@pytest.mark.asyncio
class TestSmellRegClientCompliance:
    """Tests for compliance check."""

    @respx.mock
    async def test_check_compliance_success(self, client):
        expected = {
            "formula_name": "Test",
            "is_compliant": True,
            "results": [],
        }
        respx.post("http://testserver:8001/api/compliance/check").mock(
            return_value=httpx.Response(200, json=expected)
        )

        formula = {
            "name": "Test",
            "ingredients": [
                {"cas_number": "78-70-6", "name": "Linalool", "percentage": 10.0}
            ],
        }
        result = await client.check_compliance(
            formula_data=formula,
            product_type="fine_fragrance",
            markets=["eu"],
        )
        assert result is not None
        assert result["is_compliant"] is True

    @respx.mock
    async def test_check_compliance_service_unavailable(self, client):
        respx.post("http://testserver:8001/api/compliance/check").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        result = await client.check_compliance(
            formula_data={"name": "Test", "ingredients": []},
            product_type="fine_fragrance",
            markets=["eu"],
        )
        assert result is None

    @respx.mock
    async def test_check_compliance_server_error(self, client):
        respx.post("http://testserver:8001/api/compliance/check").mock(
            return_value=httpx.Response(500, json={"detail": "Internal error"})
        )

        result = await client.check_compliance(
            formula_data={"name": "Test", "ingredients": []},
            product_type="fine_fragrance",
            markets=["us"],
        )
        assert result is None

    @respx.mock
    async def test_check_compliance_sends_correct_payload(self, client):
        route = respx.post("http://testserver:8001/api/compliance/check").mock(
            return_value=httpx.Response(200, json={"is_compliant": True})
        )

        formula = {
            "name": "Rose Accord",
            "ingredients": [
                {"cas_number": "106-24-1", "name": "Geraniol", "percentage": 25.0},
                {"cas_number": "78-70-6", "name": "Linalool", "percentage": 15.0},
            ],
        }
        await client.check_compliance(
            formula_data=formula,
            product_type="body_lotion",
            markets=["eu", "us"],
            fragrance_concentration=20.0,
            is_leave_on=True,
        )

        assert route.called
        body = route.calls.last.request.content
        import json
        payload = json.loads(body)
        assert payload["formula"]["name"] == "Rose Accord"
        assert len(payload["formula"]["ingredients"]) == 2
        assert payload["product_type"] == "body_lotion"
        assert payload["markets"] == ["eu", "us"]
        assert payload["fragrance_concentration"] == 20.0


@pytest.mark.asyncio
class TestSmellRegClientRegulatory:
    """Tests for regulatory info endpoint."""

    @respx.mock
    async def test_get_regulatory_info_success(self, client):
        reg_data = {
            "cas_number": "78-70-6",
            "ifra_restriction": None,
            "allergen": {"is_allergen": True, "name": "Linalool"},
        }
        respx.get("http://testserver:8001/api/materials/78-70-6/regulatory").mock(
            return_value=httpx.Response(200, json=reg_data)
        )

        result = await client.get_regulatory_info("78-70-6")
        assert result is not None
        assert result["cas_number"] == "78-70-6"

    @respx.mock
    async def test_get_regulatory_info_not_found(self, client):
        respx.get("http://testserver:8001/api/materials/999-99-9/regulatory").mock(
            return_value=httpx.Response(404)
        )

        result = await client.get_regulatory_info("999-99-9")
        assert result is None

    @respx.mock
    async def test_get_regulatory_info_connection_error(self, client):
        respx.get("http://testserver:8001/api/materials/78-70-6/regulatory").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        result = await client.get_regulatory_info("78-70-6")
        assert result is None


@pytest.mark.asyncio
class TestSmellRegClientLifecycle:
    """Tests for client lifecycle management."""

    async def test_close_client(self, client):
        # Should not raise even when no client created yet
        await client.close()

    @respx.mock
    async def test_client_reuse(self, client):
        respx.get("http://testserver:8001/health").mock(
            return_value=httpx.Response(200, json={"status": "healthy"})
        )

        await client.check_health()
        await client.check_health()
        # Should work fine with reused client
