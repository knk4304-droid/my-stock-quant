from trade_plan_v62 import build_trade_plan
p=build_trade_plan(10000,4,'KRW')
assert p['1차 진입 가정(-2%)']==9800
assert p['2차 목표 가정(+8%)']==10800
assert p['손실 제한 가정']==9600
assert p['가정 손익비(2차 목표 기준)']==2
print('v6.2 산술 시나리오 테스트 통과')
