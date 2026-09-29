from decimal import Decimal

from planner.modules.analytics.price_sync import parse_model_info


def test_parse_litellm_model_info() -> None:
    payload = {
        "data": [
            {
                "model_name": "deepseek-v4.1-flash",
                "model_info": {"input_cost_per_token": 1.25e-05, "output_cost_per_token": 5e-05},
            },
            {
                "model_name": "gigachat-3-pro",
                "model_info": {
                    "input_cost_per_token": 0.0005,
                    "output_cost_per_token": 0.0005,
                    "cache_read_input_token_cost": 0.0001,
                },
            },
            {"model_name": "no-prices", "model_info": {}},
        ]
    }
    quotes = {q.model: q for q in parse_model_info(payload)}
    assert set(quotes) == {"deepseek-v4.1-flash", "gigachat-3-pro"}
    assert quotes["deepseek-v4.1-flash"].input_per_million == Decimal("12.5")
    assert quotes["gigachat-3-pro"].cached_input_per_million == Decimal("100")
