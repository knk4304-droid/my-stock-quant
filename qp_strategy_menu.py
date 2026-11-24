"""Stable strategy IDs; period guidance is heuristic, not measured performance."""
LABELS={
'종합점수순':'전 기간',
'현재매수유망순':'단기·스윙 추천',
'추세·위험균형순':'스윙·중기 추천',
'반등유망순':'스윙·중기 추천',
'눌림목매수유망순':'단기·스윙 추천',
'추세돌파유망순':'단기·스윙 추천',
'최근 5일 수익률순':'단기 참고',
'최근 20일 수익률순':'스윙·중기 참고',
'낮은 변동성순':'중기·장기 참고'}
def ordered_modes(period):
    priority=next((v for k,v in {
        '단기':['현재매수유망순','추세돌파유망순','눌림목매수유망순'],
        '스윙':['추세·위험균형순','눌림목매수유망순','반등유망순'],
        '중기':['추세·위험균형순','반등유망순'],
        '장기':['추세·위험균형순','낮은 변동성순']}.items() if str(period).startswith(k)),[])
    return list(dict.fromkeys(['종합점수순',*priority,*LABELS]))
def mode_label(mode):
    return f'{mode} ({LABELS[mode]})'
