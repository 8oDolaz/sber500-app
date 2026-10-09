from decimal import Decimal

import pytest

from planner.modules.analytics.proxy_spend import parse_key_info, proxy_root


def test_parse_litellm_key_info() -> None:
    payload = {
        "key": "88dc28d0f030c55ed4ab77ed8faf098196cb1c05df778539800c9f1243fe6b4b",
        "info": {"spend": 1234.5678, "max_budget": 75000.0, "models": []},
    }
    key = parse_key_info(payload)
    assert key.spend_rub == Decimal("1234.5678")
    assert key.max_budget_rub == Decimal("75000.0")


def test_parse_key_info_without_budget() -> None:
    key = parse_key_info({"info": {"spend": 0.0, "max_budget": None}})
    assert key.spend_rub == Decimal("0.0")
    assert key.max_budget_rub is None


def test_parse_key_info_without_spend_fails() -> None:
    with pytest.raises(ValueError, match="no spend"):
        parse_key_info({"info": {"models": []}})


@pytest.mark.parametrize(
    "base_url",
    [
        "https://shared1.multitool.works:4000/v1",
        "https://shared1.multitool.works:4000/v1/",
        "https://shared1.multitool.works:4000",
    ],
)
def test_key_info_lives_at_the_proxy_root(base_url: str) -> None:
    assert proxy_root(base_url) == "https://shared1.multitool.works:4000"
