import copy
import datetime as dt
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import strategy_screen as strategy
from strategy_screen import evaluate, bars_from_tables, check_quota, QuotaExceeded, reclaim_match, pullback_security_allowed, bullish_averages, apply_trade_plan


def history():
    return [dict(date=(dt.date(2026,9,1)+dt.timedelta(days=i)).isoformat(),open=10,high=10.3,low=9.9,close=10,
        volume=100,amount=2e8,change=0,limit=0) for i in range(1,41)]


class StrategyTests(unittest.TestCase):
    def reclaim_history(self,count=2):
        bars=history()
        for i,b in enumerate(bars,1): b.update(close=8+i*.1,open=8+i*.1,high=8+i*.1+.2,low=8+i*.1-.1)
        for i in range(count): bars[-20+i]['limit']=1
        bars[-3].update(open=11.3,low=11,high=11.5,close=11.4)
        bars[-2].update(open=11.5,low=11.45,high=11.8,close=11.7)
        bars[-1].update(open=11.8,low=11.7,high=12.1,close=12,change=2.56)
        return bars

    def test_at_least_two_limits_without_upper_cap(self):
        for count in (2,3,4,8):
            item=evaluate(self.reclaim_history(count))['pullback']
            self.assertEqual(item['limitCount20'],count)
            self.assertEqual({x['period'] for x in item['reclaimLines']},{5})
        for count in (0,1): self.assertNotIn('pullback',evaluate(self.reclaim_history(count)))

    def test_mainboard_only_and_st_exclusions(self):
        for code in ('000001','001359','002029','003000','600000','601000','603000','605000'):
            self.assertTrue(pullback_security_allowed(code,'测试公司'))
        for code in ('300001','301001','688001','689001','920001','830001','870001','430001','900001','200001'):
            self.assertFalse(pullback_security_allowed(code,'测试公司'))
        for name in ('ST测试','*ST测试','ＳＴ测试','测试退'):
            self.assertFalse(pullback_security_allowed('600000',name))

    def test_ma10_above_ma20_and_both_slopes_are_required(self):
        bars=self.reclaim_history()
        self.assertIsNotNone(bullish_averages(bars))
        flat=history();flat[-20]['limit']=flat[-18]['limit']=1
        flat[-1].update(low=9.8,close=10)
        self.assertIsNone(reclaim_match(flat))
        falling=self.reclaim_history();falling[-21]['close']=14.5
        self.assertIsNone(reclaim_match(falling))
        wrong=self.reclaim_history()
        for b in wrong[-20:-5]: b['close']=14
        self.assertIsNone(reclaim_match(wrong))

    def test_pullback_does_not_inherit_old_turnover_filter(self):
        bars=self.reclaim_history();bars[-1]['amount']=50000000
        self.assertIn('pullback',evaluate(bars))

    def test_limits_outside_20_days_do_not_count_and_need_no_consecutive_boards(self):
        bars=self.reclaim_history(2);bars[-19]['limit']=0;bars[-18]['limit']=1
        self.assertIsNotNone(reclaim_match(bars))
        bars[-18]['limit']=0;bars[-21]['limit']=1
        self.assertIsNone(reclaim_match(bars))

    def test_touching_or_staying_above_is_not_reclaim(self):
        bars=self.reclaim_history(2);bars[-1]['close']=9.8
        self.assertIsNone(reclaim_match(bars))
        bars=history();bars[-20]['limit']=bars[-18]['limit']=1
        bars[-1].update(low=10,close=10.2)
        self.assertIsNone(reclaim_match(bars))
        bars[-1].update(low=9.8,close=10)
        self.assertIsNone(reclaim_match(bars))

    def test_intraday_breach_and_return_is_valid(self):
        bars=self.reclaim_history()
        result=reclaim_match(bars)
        self.assertIn(bars[-3]['date'],result['lines'][0]['breakDates'])

    def test_ma5_bias_must_stay_within_five_percent(self):
        bars=self.reclaim_history(2)
        self.assertIsNotNone(reclaim_match(bars))
        bars[-1].update(close=13,high=13.1)
        self.assertIsNone(reclaim_match(bars))

    def test_unknown_limit_status_cannot_pass(self):
        bars=self.reclaim_history(2);del bars[-5]['limit']
        self.assertIsNone(reclaim_match(bars))

    def test_trade_plan_does_not_mark_price_above_rr_zone_as_buyable(self):
        item=evaluate(self.reclaim_history(2))['pullback']
        context=dict(currentPrice=item['firstTarget']*.99,vwap=item['entryRange'][0],aboveVwap=True,
            volumeSignal={'ratio':2},sector='fixture',sectorChange=2)
        apply_trade_plan(item,context,'intraday')
        self.assertEqual(item['recommendedPosition'],0)
        self.assertIn('不追',item['status'])

    def test_auction_uses_previous_session_and_preserves_other_groups(self):
        bars=self.reclaim_history(2)
        for i,b in enumerate(bars): b['date']=(dt.date(2026,11,6)-dt.timedelta(days=39-i)).isoformat()
        fixed=dt.datetime(2026,11,9,9,15,tzinfo=dt.timezone(dt.timedelta(hours=8)))
        fake_clock=SimpleNamespace(datetime=SimpleNamespace(now=lambda *args:fixed),timezone=dt.timezone,timedelta=dt.timedelta)
        preserved=dict(code='000002',name='fixture',signalDate='2026-11-04',change=1)
        previous=dict(asOf='2026-11-04',generatedAt='2026-11-04T15:45:00+08:00',verified=10,universe=12,
            groups={'pullback':[],'second':[preserved],'triple':[]},coverage={},failures=[])
        value={'searchDataResultDTO':{'dataTableDTOList':[{'rawTable':{'headName':['2026-11-09','2026-11-06']}}]}}
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);(base/'previous.json').write_text(json.dumps(previous),encoding='utf-8')
            arguments=['screen','--mode','auction','--previous',str(base/'previous.json'),'--output',str(base/'output.json')]
            with mock.patch.object(strategy,'dt',fake_clock),mock.patch.object(strategy,'api',return_value=value), \
                 mock.patch.object(strategy,'wide_screen',return_value=([{'SECURITY_CODE':'000001','SECURITY_SHORT_NAME':'fixture'}],dict(total=1,returned=1,complete=True))), \
                 mock.patch.object(strategy,'bars_from_tables',return_value=bars),mock.patch('sys.argv',arguments):
                strategy.main()
            result=json.loads((base/'output.json').read_text(encoding='utf-8'))
        self.assertEqual(result['groupAsOf']['pullback'],'2026-11-06')
        self.assertEqual(result['groupAsOf']['second'],'2026-11-04')
        self.assertEqual(result['groups']['second'],[preserved])
        self.assertEqual(result['groupStats']['second']['verified'],10)
        self.assertTrue(result['groups']['pullback'][0]['provisional'])
        self.assertEqual(result['groups']['pullback'][0]['signalDate'],'2026-11-06')

    def test_invalid_screen_response_does_not_become_empty_success(self):
        with mock.patch.object(strategy,'api',return_value={'message':'no data'}):
            with self.assertRaises(RuntimeError): strategy.screen('query','2026-11-09')
    def test_mx_quota_stops_instead_of_appearing_empty(self):
        with self.assertRaises(QuotaExceeded):
            check_quota({'message':'您今日请求的数据量已达到上限，额度将于次日恢复'})
        check_quota({'message':'ok'})
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
