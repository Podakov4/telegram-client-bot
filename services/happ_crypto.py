from __future__ import annotations

import json
import logging
from functools import lru_cache

import requests

HAPP_CRYPTO_API_URL = "https://crypto.happ.su/api-v2.php"

logger = logging.getLogger(__name__)


class HappCryptoError(Exception):
    pass


def _extract_happ_link(payload) -> str | None:
    if isinstance(payload, str) and payload.startswith("happ://crypt"):
        return payload

    if isinstance(payload, dict):
        preferred_keys = (
            "url",
            "link",
            "result",
            "encrypted",
            "encrypted_url",
            "data",
        )
        for key in preferred_keys:
            value = payload.get(key)
            if isinstance(value, str) and value.startswith("happ://crypt"):
                return value

        for value in payload.values():
            if isinstance(value, str) and value.startswith("happ://crypt"):
                return value

    return None


@lru_cache(maxsize=2048)
def encrypt_happ_subscription_url(plain_url: str) -> str:
    try:
        response = requests.post(
            HAPP_CRYPTO_API_URL,
            json={"url": plain_url},
            timeout=20,
        )
    except requests.RequestException as e:
        raise HappCryptoError(f"Happ crypto API request failed: {e}") from e

    if response.status_code != 200:
        raise HappCryptoError(
            f"Happ crypto API returned HTTP {response.status_code}: {response.text[:300]}"
        )

    text = response.text.strip()
    if text.startswith("happ://crypt"):
        return text

    try:
        payload = response.json()
    except json.JSONDecodeError:
        payload = None

    link = _extract_happ_link(payload)
    if link:
        return link

    raise HappCryptoError(f"Unexpected Happ crypto API response: {text[:500]}")