"""HTTP client for communicating with the smell-reg service."""

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

SMELL_REG_URL = os.environ.get("SMELL_REG_URL", "http://localhost:8001")


class SmellRegClient:
    """Async HTTP client for the smell-reg regulatory compliance service.

    All methods gracefully return None/False on connection errors,
    since smell-reg is an optional dependency.
    """

    def __init__(self, base_url: Optional[str] = None, timeout: float = 10.0):
        self.base_url = (base_url or SMELL_REG_URL).rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def check_health(self) -> bool:
        """Check if smell-reg is reachable and healthy."""
        try:
            client = await self._get_client()
            resp = await client.get("/health")
            return resp.status_code == 200
        except (httpx.HTTPError, Exception):
            return False

    async def check_compliance(
        self,
        formula_data: dict,
        product_type: str,
        markets: list[str],
        fragrance_concentration: float = 100.0,
        is_leave_on: bool = True,
    ) -> Optional[dict]:
        """Run a full compliance check via smell-reg.

        Args:
            formula_data: Dict with 'name' and 'ingredients' keys.
            product_type: Product type string (e.g. 'fine_fragrance').
            markets: List of market codes (e.g. ['us', 'eu']).
            fragrance_concentration: Fragrance concentration percentage.
            is_leave_on: Whether product is leave-on (vs rinse-off).

        Returns:
            Compliance report dict, or None if smell-reg is unavailable.
        """
        try:
            client = await self._get_client()
            payload = {
                "formula": formula_data,
                "product_type": product_type,
                "markets": markets,
                "fragrance_concentration": fragrance_concentration,
                "is_leave_on": is_leave_on,
            }
            resp = await client.post("/api/compliance/check", json=payload)
            if resp.status_code == 200:
                return resp.json()
            logger.warning("smell-reg compliance check returned %d", resp.status_code)
            return None
        except (httpx.HTTPError, Exception) as e:
            logger.debug("smell-reg compliance check failed: %s", e)
            return None

    async def get_regulatory_info(self, cas_number: str) -> Optional[dict]:
        """Get regulatory info for a CAS number from smell-reg.

        Returns:
            Regulatory data dict, or None if unavailable.
        """
        try:
            client = await self._get_client()
            resp = await client.get(f"/api/materials/{cas_number}/regulatory")
            if resp.status_code == 200:
                return resp.json()
            return None
        except (httpx.HTTPError, Exception) as e:
            logger.debug("smell-reg regulatory info failed: %s", e)
            return None


# Module-level singleton
_client: Optional[SmellRegClient] = None


def get_smell_reg_client() -> SmellRegClient:
    """Get the global SmellRegClient instance."""
    global _client
    if _client is None:
        _client = SmellRegClient()
    return _client
