"""Fair, oldest-first rotation; no historical score or preferred ticker influences priority."""
import pandas as pd

def choose(catalog, existing, state, batch_size, rotation_fn=None, revisit_limit=0):
    from qp_universe_r18 import eligible
    cat=eligible(catalog).drop_duplicates('ticker',keep='last').copy()
    n=min(max(1,int(batch_size)),len(cat))
    if not n:
        return cat,{}, {'균등 최신성 순환':0,'기존 우수 후보':0}
    old=existing[['ticker','scanned_at_utc']].drop_duplicates('ticker',keep='last') if not existing.empty and {'ticker','scanned_at_utc'}.issubset(existing.columns) else pd.DataFrame(columns=['ticker','scanned_at_utc'])
    cat=cat.merge(old,on='ticker',how='left')
    cat['_stamp']=pd.to_datetime(cat.scanned_at_utc,utc=True,errors='coerce')
    # Unscanned and oldest symbols first, independently within each market.
    groups={m:g.sort_values(['_stamp','ticker'],na_position='first').reset_index(drop=True) for m,g in cat.groupby('market',sort=True)}
    picked=[]
    while len(picked)<n:
        progress=False
        for m in groups:
            if len(picked)>=n: break
            if len(groups[m]):
                picked.append(groups[m].iloc[0]); groups[m]=groups[m].iloc[1:]; progress=True
        if not progress: break
    out=pd.DataFrame(picked).drop(columns=['_stamp','scanned_at_utc'],errors='ignore').reset_index(drop=True)
    out['selection_group']='균등 최신성 순환'
    return out, state.get('market_cursors',{}), {'균등 최신성 순환':len(out),'신규 순환 발굴':len(out),'기존 우수 후보':0}
