"""Preserve overlapping index memberships while fetching each ticker once."""

def membership_map(universe):
    memberships = {}
    for category, tickers in universe.items():
        for ticker in tickers:
            memberships.setdefault(ticker, set()).add(category)
    return memberships


def category_tickers(universe, category):
    if category not in universe:
        return set()
    return set(universe[category])


def etf_weights(base_weights):
    """Exclude unverified issuer fundamentals for ETFs, preserving total weight 100."""
    result = {}
    for horizon, weights in base_weights.items():
        clean = list(weights)
        for idx in (5, 6, 7, 8):
            clean[idx] = 0
        total = sum(clean)
        if total <= 0:
            raise ValueError('ETF weight sum must be positive')
        result[horizon] = [v * 100.0 / total for v in clean]
    return result
