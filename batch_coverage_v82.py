"""Read-only comparison of saved batch universe and the current live-screen sample."""
import pandas as pd


def compare_universes(saved, live):
    if not isinstance(saved, pd.DataFrame) or '티커' not in saved:
        return pd.DataFrame(columns=['티커','종목명','시장','화면 분석 여부'])
    result = saved.copy()
    live_tickers = set()
    if isinstance(live, pd.DataFrame) and '티커' in live:
        live_tickers = set(live['티커'].dropna().astype(str).str.strip()) - {''}
    result['티커'] = result['티커'].astype('string').str.strip()
    result = result[result['티커'].notna() & result['티커'].ne('')].drop_duplicates('티커', keep='last').copy()
    result['화면 분석 여부'] = result['티커'].isin(live_tickers).map({True:'이번 화면 분석 포함', False:'저장 목록에만 있음'})
    return result.reset_index(drop=True)


def coverage_by_market(compared):
    if compared.empty or '시장' not in compared:
        return pd.DataFrame(columns=['시장','저장 종목','이번 화면 분석 포함','저장 목록에만 있음','분석 포함 비율(%)'])
    grouped = compared.groupby('시장', dropna=False)['화면 분석 여부'].agg(
        저장_종목='size', 화면_포함=lambda s: int(s.eq('이번 화면 분석 포함').sum()))
    grouped = grouped.reset_index().rename(columns={'저장_종목':'저장 종목','화면_포함':'이번 화면 분석 포함'})
    grouped['저장 목록에만 있음'] = grouped['저장 종목'] - grouped['이번 화면 분석 포함']
    grouped['분석 포함 비율(%)'] = (100 * grouped['이번 화면 분석 포함'] / grouped['저장 종목']).round(1)
    return grouped.sort_values('저장 종목', ascending=False).reset_index(drop=True)
