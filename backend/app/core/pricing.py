from decimal import Decimal

# USD per 1M tokens, (input, output). Not fetched dynamically — update when
# Anthropic's pricing changes. Unknown models fall back to _DEFAULT_PRICING.
MODEL_PRICING_USD_PER_MILLION_TOKENS: dict[str, tuple[Decimal, Decimal]] = {
    "claude-opus-4-8": (Decimal("15.00"), Decimal("75.00")),
    "claude-sonnet-4-6": (Decimal("3.00"), Decimal("15.00")),
    "claude-haiku-4-5-20251001": (Decimal("0.80"), Decimal("4.00")),
    "claude-fable-5": (Decimal("3.00"), Decimal("15.00")),
}
_DEFAULT_PRICING = (Decimal("3.00"), Decimal("15.00"))
_MILLION = Decimal(1_000_000)


def calculate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    """Estimate the USD cost of one Anthropic API call from its real token usage."""
    input_price, output_price = MODEL_PRICING_USD_PER_MILLION_TOKENS.get(model, _DEFAULT_PRICING)
    return (Decimal(input_tokens) / _MILLION * input_price) + (
        Decimal(output_tokens) / _MILLION * output_price
    )
