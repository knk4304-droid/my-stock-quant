"""Classic: Keep the existing ten-factor ranking as baseline; compare rule-based momentum, trend, pullback and breakout using the same universe. Research-only; no live changes."""
from math import isfinite
from statistics import mean

def review(folds, *, min_folds=12):
    """Input: chronological, nonoverlapping holdout folds, paired net returns
    and drawdown magnitudes as decimal fractions. Caller verifies provenance,
    costs, point-in-time universe and absence of leakage.
    """
    if min_folds < 12:
        raise ValueError("minimum 12 folds")
    if len(folds) < min_folds:
        return {"status": "insufficient_evidence", "eligible_for_review": False}
    deltas = []
    previous = None
    for f in folds:
        start, end = f["start"], f["end"]
        if start > end or (previous is not None and start <= previous):
            raise ValueError("overlapping or unordered folds")
        previous = end
        b, c, bd, cd = (float(f[k]) for k in ("baseline_net", "challenger_net", "baseline_mdd", "challenger_mdd"))
        if not all(map(isfinite, (b,c,bd,cd))) or not (0 <= bd <= 1 and 0 <= cd <= 1) or min(b,c) < -1:
            raise ValueError("invalid metrics")
        deltas.append(c-b)
    wins = sum(d > 0 for d in deltas)
    eligible = mean(deltas) > 0 and wins / len(deltas) >= 2/3 and max(f["challenger_mdd"] for f in folds) <= max(f["baseline_mdd"] for f in folds)
    return {"status": "manual_review_only", "eligible_for_review": eligible, "mean_paired_net_delta": mean(deltas), "positive_fold_fraction": wins/len(deltas), "folds": len(folds)}
