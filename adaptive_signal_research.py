"""Research candidate signals only. No live ranking, orders or promotion."""
from math import isfinite
from statistics import mean, pstdev

def signals(closes, benchmark, volumes):
    """Aligned completed daily bars, oldest first, adjusted consistently.
    Scores are hypotheses, not calibrated probabilities or expected returns.
    """
    if len(closes)!=len(benchmark) or len(closes)!=len(volumes) or len(closes)<61:
        raise ValueError("need at least 61 aligned bars")
    c,b,v=([float(x) for x in a] for a in (closes,benchmark,volumes))
    if not all(isfinite(x) and x>0 for x in c+b) or not all(isfinite(x) and x>=0 for x in v):
        raise ValueError("invalid bars")
    def ret(a,n): return a[-1]/a[-1-n]-1
    daily=[c[i]/c[i-1]-1 for i in range(len(c)-20,len(c))]
    risk=max(pstdev(daily),.005)
    trend=c[-1]/mean(c[-20:])-1
    relative=ret(c,20)-ret(b,20)
    regime="up" if b[-1]>mean(b[-60:]) and ret(b,20)>.02 else "down" if b[-1]<mean(b[-60:]) and ret(b,20)<-.02 else "range"
    peak=max(c[-21:-1])
    volbase=mean(v[-21:-1])
    volume_ratio=v[-1]/volbase if volbase>0 else 0
    scores={"momentum":relative/risk,"trend":trend/risk,
            "breakout":(c[-1]/peak-1)/risk,
            "pullback":(ret(c,5)/risk if trend>0 and c[-1]<peak and c[-1]>c[-2] else 0),
            "mean_reversion":(-trend/risk if regime=="range" else 0)}
    return {"regime":regime,"scores":scores,"volume_ratio":volume_ratio,
            "research_only":True}

def candidate_score(result, horizon):
    """Predeclared challenger weights; compare on untouched chronological data."""
    if horizon not in ("short","swing","medium"): raise ValueError("unknown horizon")
    s=result["scores"]
    if result["regime"]=="down": return None
    if result["regime"]=="range":
        return .7*s["mean_reversion"]+.3*s["momentum"]
    weights={"short":(.3,.2,.4,.1),"swing":(.35,.25,.15,.25),"medium":(.55,.35,.05,.05)}[horizon]
    return sum(w*s[k] for w,k in zip(weights,("momentum","trend","breakout","pullback")))
