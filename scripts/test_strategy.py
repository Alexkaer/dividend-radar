import copy
import unittest
from strategy_screen import evaluate, bars_from_tables


def history():
    return [dict(date=f'2026-10-{i:02}',open=10,high=10.3,low=9.9,close=10,
        volume=100,amount=2e8,change=0,limit=0) for i in range(1,41)]


class StrategyTests(unittest.TestCase):
    def test_same_day_triple_and_signal_day_observe(self):
        bars=history()
        bars[-1].update(open=10,close=10.5,high=10.6,low=10,volume=300,change=5-0.1)
        result=evaluate(bars)['triple']
        self.assertEqual(result['status'],'信号日 · 仅观察')
        self.assertEqual(result['zone'],[10,10.2])
        self.assertEqual(result['invalidation'],10)

    def test_split_events_not_triple(self):
        bars=history();bars[-2].update(volume=300,close=10,change=0)
        bars[-1].update(volume=100,close=10.4,change=4)
        self.assertNotIn('triple',evaluate(bars))

    def test_shadow_is_not_breakout(self):
        bars=history();bars[-3].update(open=10,close=10.4,high=10.6,low=9.9,volume=300,change=4)
        bars[-1].update(open=10,close=10.5,high=11,low=9.95,change=4)
        self.assertEqual('等待回踩 / 实体突破',evaluate(bars)['triple']['status'])

    def test_broken_low_removes_signal(self):
        bars=history();bars[-3].update(close=10.4,high=10.6,low=9.9,volume=300,change=4)
        bars[-1].update(low=9.5,close=9.6)
        self.assertNotIn('triple',evaluate(bars))

    def test_intraday_wick_does_not_invalidate_closing_guard(self):
        bars=history();bars[-3].update(close=10.4,high=10.6,low=9.9,volume=300,change=4)
        bars[-1].update(low=9.5,close=10)
        self.assertIn('triple',evaluate(bars))

    def test_large_gain_is_observation_only(self):
        bars=history();bars[-1].update(open=10,close=11,high=11,low=10,volume=300,change=10)
        self.assertEqual(evaluate(bars)['triple']['status'],'涨幅≥5% · 仅观察不追涨')

    def test_right_breakout_defense(self):
        bars=history();bars[-3].update(close=10.4,high=10.6,low=9.9,volume=300,change=4)
        bars[-1].update(open=10.5,close=10.8,high=11,low=10.3,change=4)
        self.assertEqual(evaluate(bars)['triple']['invalidation'],10.3)

    def test_no_chasing_or_missing_history(self):
        bars=history();bars[-1]['change']=5
        self.assertEqual(evaluate(bars),{})
        self.assertEqual(evaluate(bars[:20]),{})

    def test_two_boards_volume_support_and_one_price(self):
        bars=history()
        for i in (31,32): bars[i].update(limit=1,low=9.8)
        bars[33]['volume']=300
        bars[-1].update(low=9.99,open=10,close=10.01,change=.1,volume=100)
        self.assertIn('second',evaluate(bars))
        more=copy.deepcopy(bars);more[-1]['volume']=151
        self.assertNotIn('second',evaluate(more))
        one=copy.deepcopy(bars);one[32].update(high=10,low=10)
        self.assertEqual(evaluate(one)['second']['status'],'高风险形态 · 仅观察')
        separated=copy.deepcopy(bars);separated[32]['limit']=0;separated[34]['limit']=1
        self.assertNotIn('second',evaluate(separated))

    def test_parser_adjustment_and_bool_status(self):
        block=dict(code='000001.SZ',rawTable={'headName':['2026-11-04'],'1':['10'],'2':['10.1'],'3':['9.9'],'4':['10'],'5':['100'],'6':['1'],'7':['是']},fieldSet=[])
        for ident,name in [('1','开盘价'),('2','最高价'),('3','最低价'),('4','收盘价'),('5','成交量'),('6','涨跌幅'),('7','是否涨停')]:
            block['fieldSet'].append(dict(returnCode=ident,returnName=name,fixedParamValue='AdjustFlag=1,Period=1'))
        self.assertEqual(bars_from_tables([block],'000001')[0]['limit'],1)
        bad=copy.deepcopy(block);bad['fieldSet'][0]['fixedParamValue']='AdjustFlag=0'
        self.assertEqual(bars_from_tables([bad],'000001'),[])


if __name__=='__main__': unittest.main()
