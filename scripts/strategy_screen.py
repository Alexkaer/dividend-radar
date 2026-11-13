"""Private strategy builder. Never write plaintext reports inside the public repository."""
import datetime as dt
import concurrent.futures
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import urllib.parse
import urllib.request

_SECTOR_CHANGES = None
_INTRADAY_CONTEXT = {}

ROOT = Path(__file__).resolve().parents[1]
CACHE = Path(tempfile.gettempdir()) / 'dividend-strategy-private-cache'
PULLBACK_RULE_VERSION = '2026-11-10-mainboard-reclaim-v4'
QUERIES = {
    'pullback': '沪深主板A股，非ST，非创业板，非科创板，非北交所，上市天数大于365天，最近20个交易日内涨停次数大于等于2次',
    'maPullback': 'A股，最近20个交易日内涨停次数大于等于2次',
    'second': 'A股，非ST，上市天数大于365天，最近30个交易日内连续涨停天数大于等于2天，今日涨跌幅小于5%，今日成交额大于1亿元',
    'triple': 'A股，非ST，上市天数大于365天，最近5个交易日内成交量环比增长率大于等于200%出现次数大于0，最近5个交易日内当日涨幅大于3%出现次数大于0，今日成交额大于1亿元',
}


class QuotaExceeded(RuntimeError):
    pass


def check_quota(value):
    message=str(value.get('message') or value.get('msg') or '') if isinstance(value,dict) else ''
    if ('额度' in message or '数据量' in message) and ('上限' in message or '用尽' in message or '耗尽' in message):
        raise QuotaExceeded('MX daily data quota exhausted; previous encrypted snapshot retained. Quota resets next day.')


def api(endpoint, query, day):
    CACHE.mkdir(parents=True, exist_ok=True)
    cache = CACHE / (hashlib.sha256((day + endpoint + query).encode()).hexdigest() + '.json')
    if cache.exists():
        value=json.loads(cache.read_text(encoding='utf-8'))
        check_quota(value)
        return value
    for attempt in range(5):
        time.sleep(2 + attempt * 5)
        try:
            body = {'keyword' if endpoint == 'stock-screen' else 'toolQuery': query}
            req = urllib.request.Request('https://mkapi2.dfcfs.com/finskillshub/api/claw/' + endpoint,
                data=json.dumps(body).encode(), headers={'apikey': os.environ['MX_APIKEY'], 'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=180) as response:
                result = json.load(response)
            check_quota(result)
            if result.get('status') not in (0, '0'):
                raise ValueError('MX outer response failed')
            data = result.get('data') or {}
            check_quota(data)
            if data.get('status', 0) not in (0, '0') or data.get('code', 0) not in (0, '0', 200, '200') or not data.get('data'):
                raise ValueError('MX nested response failed')
            value = data['data']
            check_quota(value)
            cache.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
            return value
        except QuotaExceeded:
            raise
        except Exception:
            if attempt == 4:
                raise RuntimeError('MX request failed after retries; retaining previous encrypted snapshot') from None


def public_json(url):
    request=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Referer':'https://quote.eastmoney.com/'})
    with urllib.request.urlopen(request,timeout=20) as response:
        return json.load(response)


def official_limit_count(row):
    for key,value in row.items():
        if 'DURATION_LIMIT_UP' in str(key):
            return int(float(value))
    return None


def public_daily_bars(code,session):
    secid=('1.' if code.startswith('6') else '0.')+code
    url=('https://push2his.eastmoney.com/api/qt/stock/kline/get?secid='+secid+
        '&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59&klt=101&fqt=1&lmt=60&end='+session.replace('-',''))
    rows=((public_json(url).get('data') or {}).get('klines') or [])
    bars=[]
    for raw in rows:
        value=raw.split(',')
        bars.append(dict(date=value[0],open=float(value[1]),close=float(value[2]),high=float(value[3]),low=float(value[4]),
            volume=float(value[5]),amount=float(value[6]),change=float(value[8]),limit=0))
    for i in range(1,len(bars)):
        bars[i]['limit']=1 if bars[i]['close']/bars[i-1]['close']-1>=.095 else 0
    return bars


def public_trading_session(day):
    data=(public_json('https://push2his.eastmoney.com/api/qt/stock/trends2/get?secid=1.000001&'
        'fields1=f1,f2,f3,f4,f5,f6,f7,f8&fields2=f51,f52,f53,f54,f55,f56,f57,f58&ndays=1&iscr=0&iscca=0').get('data') or {})
    trends=data.get('trends') or []
    return bool(trends and str(trends[-1]).startswith(day))


def sector_changes():
    global _SECTOR_CHANGES
    if _SECTOR_CHANGES is None:
        url=('https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=500&po=1&np=1&fltt=2&invt=2'
             '&fid=f3&fs=m:90+t:2&fields=f12,f14,f3')
        rows=((public_json(url).get('data') or {}).get('diff') or [])
        _SECTOR_CHANGES={str(row.get('f14','')):float(row['f3']) for row in rows if row.get('f14') and row.get('f3') is not None}
    return _SECTOR_CHANGES


def intraday_context(code,cutoff=None):
    cache_key=(code,cutoff)
    if cache_key in _INTRADAY_CONTEXT: return _INTRADAY_CONTEXT[cache_key]
    secid=('1.' if code.startswith('6') else '0.')+code
    quote=(public_json('https://push2.eastmoney.com/api/qt/stock/get?secid='+secid+
        '&fields=f57,f58,f43,f170,f127').get('data') or {})
    sector=str(quote.get('f127') or '未知行业')
    change=sector_changes().get(sector)
    data=(public_json('https://push2his.eastmoney.com/api/qt/stock/trends2/get?secid='+secid+
        '&fields1=f1,f2,f3,f4,f5,f6,f7,f8&fields2=f51,f52,f53,f54,f55,f56,f57,f58&ndays=1&iscr=0&iscca=0').get('data') or {})
    minutes=[]
    for raw in data.get('trends') or []:
        value=raw.split(',')
        if cutoff and value[0][11:16]>cutoff: continue
        minutes.append(dict(time=value[0],open=float(value[1]),close=float(value[2]),high=float(value[3]),
            low=float(value[4]),volume=float(value[5]),vwap=float(value[7])))
    if not minutes:
        result=dict(sector=sector,sectorChange=change);_INTRADAY_CONTEXT[cache_key]=result;return result
    bars=[]
    for start in range(0,len(minutes),5):
        part=minutes[start:start+5]
        if len(part)!=5: continue
        bars.append(dict(time=part[-1]['time'],open=part[0]['open'],close=part[-1]['close'],
            high=max(x['high'] for x in part),low=min(x['low'] for x in part),
            volume=sum(x['volume'] for x in part),vwap=part[-1]['vwap']))
    signal=None; previous_close=float(data.get('preClose') or 0)
    for i in range(5,len(bars)):
        bar=bars[i]; base=sum(x['volume'] for x in bars[i-5:i])/5
        ratio=bar['volume']/base if base else 0
        underwater=bar['low']<previous_close and bar['close']>previous_close
        breakout=bar['open']>=previous_close and bar['close']>max(x['high'] for x in bars[i-3:i])
        if ratio>=1.5 and bar['close']>bar['open'] and bar['close']>bar['vwap'] and (underwater or breakout):
            signal=dict(time=bar['time'],ratio=round(ratio,2),kind='水下收复' if underwater else '水上突破')
    last=minutes[-1]
    result=dict(currentPrice=last['close'],quoteTime=last['time'],vwap=last['vwap'],aboveVwap=last['close']>last['vwap'],
        sessionOpen=minutes[0]['open'],sessionHigh=max(x['high'] for x in minutes),sessionLow=min(x['low'] for x in minutes),
        sessionVolume=sum(x['volume'] for x in minutes),volumeSignal=signal,sector=sector,sectorChange=change)
    _INTRADAY_CONTEXT[cache_key]=result
    return result


def apply_trade_plan(item,context,mode):
    item['intraday']=context
    ma5=item['bullishAverages']['current'][5]
    price=context.get('currentPrice',item['close'])
    lower=max(ma5,context.get('vwap',ma5))
    stop=ma5*.99; target=item['firstTarget']
    rr_ceiling=(target+2*stop)/3
    upper=min(price,ma5*1.05,rr_ceiling)
    executable=upper>=lower
    if not executable: upper=lower
    entry=(lower+upper)/2
    rr=(target-entry)/(entry-stop) if entry>stop else 0
    sector_change=context.get('sectorChange')
    confirmed=(mode=='intraday' and context.get('aboveVwap') and context.get('volumeSignal') and
        sector_change is not None and sector_change>0 and executable and lower<=price<=upper and rr>=2)
    position=10 if confirmed and sector_change>=1.5 else 5 if confirmed else 0
    item.update(entryRange=[round(lower,3),round(upper,3)],invalidation=round(stop,3),stopPrice=round(stop,3),
        rewardRisk=round(rr,2),recommendedPosition=position,
        action='A+可上车' if position==10 else 'A类可上车' if position==5 else '观察/等条件',
        status=('盘中确认 · 可按区间低吸' if position else
            '价格高于满足2:1盈亏比的区间 · 不追' if price>upper else '日线满足 · 分时/板块/盈亏比未全部确认'))
    item['confirmation']=(f"行业{context.get('sector','未知')}"
        +(f" {sector_change:+.2f}%" if sector_change is not None else '涨幅未知')+
        ('；价格在VWAP上方' if context.get('aboveVwap') else '；价格未站稳VWAP')+
        ('；5分钟放量确认' if context.get('volumeSignal') else '；未见合格5分钟放量')+
        f"；计划盈亏比{rr:.2f}:1")


def enforce_portfolio_cap(items):
    eligible=[item for item in items if item.get('recommendedPosition',0)>0]
    def score(item):
        context=item.get('intraday') or {}; signal=context.get('volumeSignal') or {}
        return (float(context.get('sectorChange') or 0)+min(float(item.get('rewardRisk') or 0),4)+
            min(float(signal.get('ratio') or 0),3),float(item.get('rewardRisk') or 0))
    eligible.sort(key=score,reverse=True)
    selected={item['code']:(10 if index==0 else 5) for index,item in enumerate(eligible[:3])}
    for item in items:
        if item.get('recommendedPosition',0)<=0: continue
        allocation=selected.get(item['code'],0)
        item['recommendedPosition']=allocation
        item['action']='A+可上车' if allocation==10 else 'A类可上车' if allocation==5 else '观察/等总仓位名额'
        if not allocation: item['status']='个股条件满足，但当日新增仓位上限20%，不再新增'


def screen(query, day):
    result = api('stock-screen', query, day)
    all_results = result.get('allResults') or {}
    table = all_results.get('result') or {}
    if not all_results or 'dataList' not in table:
        raise RuntimeError('MX did not return a validated screening table; previous snapshot retained')
    rows = table.get('dataList') or []
    total = int(table.get('totalRecordCount', table.get('total', len(rows))))
    return rows, total, all_results.get('totalCondition')


def wide_screen(query, day):
    rows, total, condition = screen(query, day)
    conditions = [condition]
    if total <= len(rows):
        return rows, {'total': total, 'returned': len(rows), 'complete': True, 'conditions': conditions}
    # API returns at most 200 rows. Disjoint code prefixes preserve the base conditions.
    collected = {}
    complete = True
    for prefix in ('60', '00', '30', '68', '8', '4', '9'):
        part, count, parsed = screen(query + '，股票代码以' + prefix + '开头', day)
        conditions.append(parsed)
        complete = complete and count <= len(part)
        for row in part:
            code = str(row.get('SECURITY_CODE', '')).zfill(6)
            if not code.startswith(prefix):
                complete = False
                continue
            collected[code] = row
    complete = complete and len(collected) == total
    return list(collected.values()), {'total': total, 'returned': len(collected), 'complete': complete, 'conditions': conditions}


def tables(value):
    return (value.get('searchDataResultDTO') or {}).get('dataTableDTOList') or []


def bars_from_tables(blocks, code):
    series = {}
    for block in blocks:
        if str(block.get('code', '')).split('.')[0] != code:
            continue
        raw = block.get('rawTable') or {}
        dates = raw.get('headName') or []
        for field in block.get('fieldSet') or []:
            ident = str(field.get('returnCode', ''))
            name = field.get('returnName') or (block.get('nameMap') or {}).get(ident, '')
            # Reject live quote aliases masquerading as historical fields.
            if not ident.isdigit() or ident not in raw:
                continue
            params = str(field.get('fixedParamValue') or '')
            key = {'开盘价': 'open', '最高价': 'high', '最低价': 'low', '收盘价': 'close',
                   '成交量': 'volume', '成交额': 'amount', '涨跌幅': 'change', '是否涨停': 'limit'}.get(name)
            if not key:
                continue
            if key in ('open', 'high', 'low', 'close'):
                if 'AdjustFlag=1' not in params:
                    continue
            for date, val in zip(dates, raw[ident]):
                try:
                    number = (1.0 if str(val) in ('是','1','true') else 0.0 if str(val) in ('否','0','false') else float('nan')) if key == 'limit' else float(str(val).replace(',', ''))
                    if not __import__('math').isfinite(number):
                        continue
                    series.setdefault(str(date)[:10], {})[key] = number
                except (ValueError, TypeError):
                    pass
    return [dict(date=d, **row) for d, row in sorted(series.items()) if all(k in row for k in ('open','high','low','close','volume','change'))]


def pullback_security_allowed(code, name):
    import re
    import unicodedata
    normalized=unicodedata.normalize('NFKC',str(name)).upper()
    return bool(normalized.strip()) and bool(re.fullmatch(r'(?:60|00)\d{4}',str(code))) and not re.search(r'ST|退',normalized)


def bullish_averages(bars):
    from math import fsum
    if len(bars)<21: return None
    current={n:round(fsum(b['close'] for b in bars[-n:])/n,10) for n in (5,10,20)}
    previous={n:round(fsum(b['close'] for b in bars[-n-1:-1])/n,10) for n in (5,10,20)}
    if not current[10]>current[20]: return None
    if not all(current[n]>previous[n] for n in (10,20)): return None
    return dict(current=current,previous=previous)


def reclaim_match(bars):
    """Final pullback rule: MA20 hold, rising K centers/MA10/20, MA5 recovery."""
    if len(bars)<21 or any(b.get('limit') not in (0,1) for b in bars[-20:]):
        return None
    count=sum(b['limit']==1 for b in bars[-20:])
    if count<2: return None
    trend=bullish_averages(bars)
    if not trend: return None
    last=bars[-1]
    latest_limit=max(i for i,b in enumerate(bars[-20:],start=len(bars)-20) if b.get('limit')==1)
    if latest_limit>=len(bars)-1 or last['close']<=trend['current'][20]: return None
    if any(bars[i]['close']<sum(x['close'] for x in bars[i-19:i+1])/20 for i in range(latest_limit+1,len(bars))): return None
    center_bars=bars[-4:-1] if bars[-1].get('partial') else bars[-3:]
    centers=[(b['high']+b['low']+b['close'])/3 for b in center_bars]
    if not centers[0]<centers[1]<centers[2]: return None
    breaks=[]
    for i in range(latest_limit+1,len(bars)):
        if i<4: continue
        dynamic_low_ma=round(__import__('math').fsum([*(b['close'] for b in bars[i-4:i]),bars[i]['low']])/5,10)
        daily_ma5=sum(b['close'] for b in bars[i-4:i+1])/5
        if bars[i]['low']<dynamic_low_ma or bars[i]['close']<daily_ma5:
            breaks.append(i)
    bias=(last['close']/trend['current'][5]-1)*100
    reclaimed=any(any(bars[j]['close']>sum(b['close'] for b in bars[j-4:j+1])/5 for j in range(i,len(bars))) for i in breaks)
    if not breaks or not reclaimed or not (last['close']>trend['current'][5] and 0<=bias<=5): return None
    line=dict(period=5,ma=trend['current'][5],previousMA=trend['previous'][5],
        breakDates=[bars[i]['date'] for i in breaks],bias=round(bias,4))
    return dict(count=count,lines=[line],trend=trend,centers=centers,latestLimit=bars[latest_limit]['date'])


def ma_pullback_plan(bars):
    window = bars[-20:]
    if len(window) < 20 or any(b.get('limit') not in (0, 1) for b in window):
        return None
    limits = [b for b in window if b['limit'] == 1]
    last = window[-1]
    if len(limits) < 2 or last['limit'] == 1 or last['close'] >= limits[-1]['close']:
        return None

    closes = [Decimal(str(b['close'])) for b in window]
    ma20 = sum(closes) / 20
    stop = int((ma20 * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    target = int((sum(closes[-5:]) / 5 * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    price = closes[-1] * 100
    entry_min = max(stop, int(ma20 * 100)) + 1
    pullback_ceiling = int((Decimal(str(limits[-1]['close'])) * 100).to_integral_value(rounding=ROUND_CEILING)) - 1
    entry_max = min((target + 2 * stop) // 3, pullback_ceiling)
    if not (entry_min <= price <= entry_max):
        return None
    ratio = (target - price) / (price - stop)
    return limits[-1], dict(
        limitCount20=len(limits), latestLimitClose=limits[-1]['close'],
        stopPrice=stop / 100, firstTarget=target / 100, rewardRisk=float(ratio),
        entryRange=[entry_min / 100, entry_max / 100],
    )


def evaluate(bars):
    """Mechanical closing-bar checks only; intraday/sector acceptance remains unknown."""
    found = {}
    if not bars:
        return found
    last = bars[-1]
    def intact(low, start):
        return min(b['low'] for b in bars[start:]) >= low - .005
    def record(kind, event, low, zone, status, evidence):
        found[kind] = dict(signalDate=event['date'], close=last['close'], change=last['change'],
            status=status, zone=[round(x, 3) for x in zone], invalidation=round(low,3), evidence=evidence,
            volumeRatio=round(last['volume']/event['volume'],4) if event['volume']>0 else None,
            confirmation='分时VWAP、板块强度与指定时段承接未查询；完成日线条件不等于买入信号',
            exit='收盘跌破防守位退出；冲高失去VWAP或量价转弱先减仓。')
    plan = ma_pullback_plan(bars)
    if plan:
        event, levels = plan
        record('maPullback', event, levels['stopPrice'], levels['entryRange'],
            '回调观察 · 快照盈亏比达标',
            f"近20日{levels['limitCount20']}次涨停；低于最近涨停日收盘价 {event['close']:.2f}")
        found['maPullback'].update(levels, exit='触及MA20参考价止损；MA5参考价为初步止盈位。')
    reclaim=reclaim_match(bars)
    if reclaim:
        support=reclaim['trend']['current'][5]
        event=next(b for b in reversed(bars[-20:]) if b.get('limit')==1)
        zone=[support,max(support,min(last['close'],support*1.025))]
        stop=support*.99
        prior_high=max(b['high'] for b in bars[-21:-1])
        mean=reclaim['trend']['current'][20]
        variance=sum((b['close']-mean)**2 for b in bars[-20:])/20
        boll_upper=mean+2*variance**.5
        targets=[x for x in (prior_high,boll_upper) if x>sum(zone)/2]
        target=min(targets) if targets else max(prior_high,boll_upper,last['high'])
        entry=sum(zone)/2
        rr=(target-entry)/(entry-stop) if entry>stop else 0
        record('pullback',event,stop,zone,
            '日线满足 · 待分时与板块确认',
            f"近20交易日累计{reclaim['count']}次涨停；回调收盘守住MA20；近3根K线重心上移；MA10>MA20且两线向上；回调曾破MA5后重新站回，当前MA5乖离{reclaim['lines'][0]['bias']:.2f}%")
        found['pullback'].update(limitCount20=reclaim['count'],reclaimLines=reclaim['lines'],
            ruleVersion=PULLBACK_RULE_VERSION,signalDate=last['date'],bullishAverages=reclaim['trend'],
            kCenters=[round(x,4) for x in reclaim['centers']],latestLimitDate=reclaim['latestLimit'],
            entryRange=[round(x,3) for x in zone],stopPrice=round(stop,3),firstTarget=round(target,3),
            rewardRisk=round(rr,2),recommendedPosition=0,action='观察')
    if len(bars)<35 or last.get('amount',0)<=1e8:
        return found
    # Historical official limit status is independent of price adjustment.
    limits = [b.get('limit') == 1 for b in bars]
    for i in range(len(bars)-1, max(0,len(bars)-6), -1):
        b, previous = bars[i], bars[i-1]
        if previous['volume'] > 0 and b['volume']/previous['volume'] >= 3 and b['close'] > b['open'] and b['change'] > 3 and b['close'] >= (b['high']+b['low'])/2 and min(x['close'] for x in bars[i:]) >= b['low']:
            upper = min(b['low']+(b['high']-b['low'])/3, b['low']*1.03)
            later = bars[i+1:]
            breaks = [x for x in later if x['close'] > b['high'] and x['close'] > x['open']]
            if breaks:
                breakout=breaks[-1]
                if last['close'] < breakout['low']:
                    continue
                status='实体突破 · 待分时确认' if breakout['open'] <= b['high'] else '跳空突破 · 待回踩确认'
                record('triple', b, breakout['low'], [b['high'], b['high']*1.01], status,
                    f"同日量比{b['volume']/previous['volume']:.2f}倍；阳线涨{b['change']:.2f}%；突破日{breakout['date']}")
            else:
                status='信号日 · 仅观察' if i == len(bars)-1 else '底部区间 · 等承接' if b['low'] <= last['close'] <= upper else '等待回踩 / 实体突破'
                record('triple', b, b['low'], [b['low'],upper], status,
                    f"同日量比{b['volume']/previous['volume']:.2f}倍；阳线涨{b['change']:.2f}%；右侧需收阳且收盘>{b['high']:.2f}")
            break
    if last['change'] >= 5:
        if 'triple' in found:
            found['triple']['status']='涨幅≥5% · 仅观察不追涨'
        if 'pullback' in found:
            found['pullback']['status']='涨幅≥5% · 仅观察不追涨'
        return found
    # First break after consecutive official limits; prefer 3–10 full sessions afterwards.
    for end in range(len(bars)-2, max(0,len(bars)-31), -1):
        if not limits[end] or limits[end+1]:
            continue
        start=end
        while start > 0 and limits[start-1]: start-=1
        count=end-start+1
        age=len(bars)-1-(end+1)
        broken=bars[end+1]
        if count < 2 or not 3 <= age <= 10 or broken['volume'] <= 0 or last['volume']/broken['volume'] > .5 or not intact(bars[start]['low'], start):
            continue
        ma=sum(b['close'] for b in bars[-10:])/10
        if not (last['low'] <= ma*1.01 and last['close'] >= ma and last['close'] <= ma*1.03):
            continue
        guard=max(bars[start]['low'], min(last['low'],ma*.99))
        one_price=any(abs(bars[k]['high']-bars[k]['low'])<.005 for k in range(start,end+1))
        record('second', bars[end], guard,[ma*.99,ma*1.01], '缩量回踩 · 待承接' if count==2 and not one_price else '高风险形态 · 仅观察',
            f"真实连续{count}板 {bars[start]['date']}~{bars[end]['date']}；断板后{age}日；量/断板量={last['volume']/broken['volume']:.2f}；MA10={ma:.2f}" + ('；含一字板' if one_price else ''))
        found['second']['volumeRatio']=round(last['volume']/broken['volume'],4)
        break
    return found


def tencent_daily(symbol, end, count, adjust='', *, full=False):
    next_day=(dt.date.fromisoformat(end)+dt.timedelta(days=1)).isoformat()
    url='https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?'+urllib.parse.urlencode(
        {'param':f'{symbol},day,,{next_day},{count},{adjust}'})
    payload=public_json(url)['data'][symbol]
    return {row[0]:row if full else Decimal(row[2])
        for row in payload.get('qfqday',payload.get('day',[])) if row[0]<=end}


def public_ma_pullback(previous, mode, selected=('maPullback',)):
    """Build independently verified strategy groups from public market data."""
    today=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()
    end=(today-dt.timedelta(days=1)).isoformat() if mode=='auction' else today.isoformat()
    history=36 if 'second' in selected else 21
    window=30 if 'second' in selected else 20
    dates=sorted(tencent_daily('sh000001',end,history))[-window:]
    if len(dates)!=window:
        raise RuntimeError('Public trading calendar incomplete')
    session=dates[-1]
    if mode!='auction' and session!=today.isoformat():
        raise RuntimeError('Public data has no current trading session')
    def pool(day):
        url='https://push2ex.eastmoney.com/getTopicZTPool?'+urllib.parse.urlencode(dict(
            ut='7eea3edcaed734bea9cbfc24409ed989',dpt='wz.ztzt',Pageindex=0,pagesize=500,sort='fbt:asc',
            date=day.replace('-','')))
        data=public_json(url).get('data') or {}
        rows=data.get('pool') or []
        return (day,rows) if rows and data.get('tc')==len(rows) else (day,[])

    def safe_pool(day):
        try: return pool(day)
        except (OSError, ValueError, KeyError): return day,[]

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        pools=dict(executor.map(safe_pool,dates))
    available={day for day,rows in pools.items() if rows}
    universe={}
    flags={}
    for day,rows in pools.items():
        for row in rows:
            code=str(row['c'])
            universe[code]=row['n']
            flags.setdefault(code,{})[day]=Decimal(str(row['p']))/1000

    triple_codes={}
    if 'triple' in selected:
        try:
            if session==today.isoformat() and mode=='close':
                base='https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/'
                total=int(public_json(base+'Market_Center.getHQNodeStockCount?node=hs_a'))
                def quote_page(page):
                    return public_json(base+'Market_Center.getHQNodeData?'+urllib.parse.urlencode(dict(
                        node='hs_a',page=page,num=100,sort='symbol',asc=1)))
                with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                    quotes=[row for page in executor.map(quote_page,range(1,(total+99)//100+1)) for row in page]
                if len({row['code'] for row in quotes})!=total:
                    raise RuntimeError('Sina quote coverage incomplete')
                for row in quotes:
                    if 'ST' not in row['name'].upper() and float(row['amount'])>1e8:
                        triple_codes[row['code']]=float(row['amount'])
                        universe[row['code']]=row['name']
        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
            print('Public triple-volume universe unavailable:',error)

    def verify(pair):
        code,name=pair
        market='sh' if code.startswith('6') else 'bj' if code.startswith(('4','8','92')) else 'sz'
        symbol=market+code
        try:
            raw=tencent_daily(symbol,session,history,full=True)
            candles=tencent_daily(symbol,session,history,'qfq',full=True)
            adjusted={day:Decimal(row[2]) for day,row in candles.items()}
            days=sorted(adjusted)[-history:]
            if len(days)<21 or days[-1]!=session or any(day not in raw for day in days):
                raise ValueError('Missing daily history')
            raw_closes={day:Decimal(raw[day][2]) for day in days}
            limit=Decimal('1.30' if market=='bj' else '1.20' if code.startswith(('30','68'))
                else '1.05' if 'ST' in name.upper() else '1.10')
            bars=[]
            for index,day in enumerate(days):
                prior=days[max(0,index-1)]
                if raw_closes[prior]<=0 or raw_closes[day]<=0:
                    raise ValueError('Invalid close')
                # Pool records confirm known dates. On older dates use raw tick prices
                # only when the adjustment factor has not materially changed.
                stable=abs(adjusted[day]/raw_closes[day]-adjusted[prior]/raw_closes[prior])<Decimal('.0008')
                cap=(raw_closes[prior]*limit).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
                pool_close=flags.get(code,{}).get(day)
                flag=int(index>0 and (pool_close==raw_closes[day] or (stable and raw_closes[day]==cap)))
                price=float(adjusted[day])
                row=candles[day]
                bars.append(dict(date=day,close=price,limit=flag,open=float(row[1]),high=float(row[3]),
                    low=float(row[4]),volume=float(row[5]),change=float((raw_closes[day]/raw_closes[prior]-1)*100),
                    amount=triple_codes.get(code,float(raw[day][4])*float(raw[day][5])*100) if day==session
                    else 0))
            items={}
            candidates=evaluate(bars)
            eligible=(set(selected)&candidates.keys())-{'maPullback'}
            for kind in eligible:
                if 'ST' in name.upper() or '退' in name:
                    continue
                if kind=='pullback' and (code not in flags or not pullback_security_allowed(code,name)):
                    continue
                if (kind=='second' and code not in flags) or (kind=='triple' and code not in triple_codes):
                    continue
                age_limit=(dt.date.fromisoformat(session)-dt.timedelta(days=366)).isoformat()
                if tencent_daily(symbol,age_limit,5):
                    item=candidates[kind]
                    item.update(code=code,name=name,provisional=mode!='close')
                    if mode=='auction': item['status']='竞价观察 · '+item['status']
                    items[kind]=item
            plan=ma_pullback_plan(bars)
            if not plan or 'maPullback' not in selected or code not in flags: return code,items,True
            event,levels=plan
            items['maPullback']=dict(code=code,name=name,signalDate=event['date'],close=bars[-1]['close'],
                change=bars[-1]['change'],status='竞价观察 · 公开行情回退' if mode=='auction' else '公开行情回退 · 回调观察',
                zone=levels['entryRange'],invalidation=levels['stopPrice'],provisional=mode!='close',
                evidence=f"近20日核验{levels['limitCount20']}次涨停",
                confirmation='公开数据覆盖有限，盘中承接待确认',
                exit='MA20参考价止损，MA5参考价初步止盈',**levels)
            return code,items,True
        except (OSError, ValueError, ArithmeticError, KeyError, TypeError, IndexError):
            return code,{},False

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        checked=list(executor.map(verify,universe.items()))
    verified=sum(ok for _,_,ok in checked)
    if not verified:
        raise RuntimeError('No public daily histories verified')
    failures=[dict(code=code,name=universe[code],reason='公开日K不可用') for code,_,ok in checked if not ok]
    stamp=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat()
    report=dict(previous)
    report.setdefault('failures',[])
    updated=False
    for kind in selected:
        if previous.get('groupAsOf',{}).get(kind,'')>session:
            continue
        if (kind=='triple' and not triple_codes) or (kind!='triple' and len(available)<2):
            continue
        scope=triple_codes if kind=='triple' else flags
        checked_count=sum(ok for code,_,ok in checked if code in scope)
        if not checked_count:
            continue
        matches=[items[kind] for _,items,_ in checked if kind in items]
        matches.sort(key=lambda item:(-item.get('limitCount20',0),-item.get('rewardRisk',0),item['code']))
        report.setdefault('groups',{})[kind]=matches
        report.setdefault('coverage',{})[kind]=dict(total=len(scope),returned=len(scope),complete=False,
            conditions=['新浪全市场成交额宽筛'] if kind=='triple' else [f'公开涨停池覆盖 {len(available)}/{len(dates)} 个交易日'])
        report.setdefault('queries',{})[kind]='新浪成交额宽筛 + 腾讯日K' if kind=='triple' else '东方财富公开涨停池 + 腾讯不复权和前复权日K'
        report.setdefault('groupAsOf',{})[kind]=session
        report.setdefault('groupGeneratedAt',{})[kind]=stamp
        source='新浪成交额宽筛 · 腾讯日K' if kind=='triple' else f'东方财富涨停池 {len(available)}/{len(dates)} 日 · 腾讯日K'
        report['groupStats'][kind]=dict(verified=checked_count,universe=len(scope),
            failures=[item for item in failures if item['code'] in scope],mode=mode,source='公开行情回退 · '+source)
        if kind=='pullback':
            report.setdefault('ruleVersions',{})[kind]=PULLBACK_RULE_VERSION
        updated=True
        print(f'Public {kind}: {session} ({mode}); matches={len(matches)}; verified={verified}/{len(universe)}; pool days={len(available)}/{len(dates)}')
    if not updated:
        raise RuntimeError('Public snapshot would replace a newer pullback snapshot')
    return report


def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--previous')
    parser.add_argument('--mode', choices=('auto','auction','intraday','close'), default='auto')
    selection=parser.add_mutually_exclusive_group()
    selection.add_argument('--pullback-only',action='store_true')
    selection.add_argument('--ma-pullback-only',action='store_true')
    selection.add_argument('--public-ma-pullback',action='store_true')
    selection.add_argument('--public-pullback',choices=('pullback','maPullback','both','all'))
    parser.add_argument('--cutoff',help='Intraday cutoff in China time, for example 14:30')
    args=parser.parse_args()
    output=Path(args.output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise SystemExit('Plaintext output must be outside the repository')
    now=dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))
    today=now.date().isoformat()
    mode=args.mode if args.mode!='auto' else ('auction' if (now.hour,now.minute)<(9,30) else 'intraday' if (now.hour,now.minute)<(15,15) else 'close')
    cache_slot=today+'-'+mode+'-'+now.strftime('%H%M')
    previous={}
    if args.previous:
        prior_path=Path(args.previous).resolve()
        if ROOT in prior_path.parents: raise RuntimeError('Previous plaintext must remain outside repository')
        previous=json.loads(prior_path.read_text(encoding='utf-8'))
    if args.public_ma_pullback or args.public_pullback:
        if mode=='intraday':
            # Public daily candles cannot reconstruct an exact historical minute.
            mode='auction'
        public_group=args.public_pullback or 'maPullback'
        selected=tuple(QUERIES) if public_group=='all' else ('pullback','maPullback') if public_group=='both' else (public_group,)
        report=public_ma_pullback(previous,mode,selected)
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,ensure_ascii=False),encoding='utf-8')
        return
    dates=[]
    for date_query in ('上证指数最近5个交易日每日收盘价，返回交易日期',
                       '上证指数000001.SH最近10个交易日每日收盘价和成交额，返回每个交易日期',
                       '600000浦发银行最近5个交易日每日前复权收盘价，返回交易日期'):
        index=api('query',date_query,cache_slot)
        dates=[str(d)[:10] for b in tables(index) for d in (b.get('rawTable') or {}).get('headName',[])
               if __import__('re').fullmatch(r'\d{4}-\d{2}-\d{2}',str(d)[:10]) and (str(d)[:10]<today if mode=='auction' else str(d)[:10]<=today)]
        if dates: break
        print('MX date query returned no historical date table; trying explicit security query.',flush=True)
    if not dates: raise RuntimeError('No validated market session date; retaining original snapshot')
    session=max(dates)
    if mode=='intraday' and session!=today:
        try:
            if public_trading_session(today): session=today
        except Exception:
            pass
    if mode!='auction' and session != today:
        print('No current trading session; previous snapshot retained.')
        return
    partial=args.pullback_only or args.ma_pullback_only or mode!='close'
    groups=previous.get('groups',{}).copy() if partial else {}
    coverage=previous.get('coverage',{}).copy() if partial else {}
    queries=previous.get('queries',{}).copy() if partial else {}
    group_dates=previous.get('groupAsOf',{k:previous.get('asOf') for k in groups}).copy()
    group_generated=previous.get('groupGeneratedAt',{k:previous.get('generatedAt') for k in groups}).copy()
    group_stats=previous.get('groupStats',{k:dict(verified=previous.get('verified',0),universe=previous.get('universe',0),
        failures=previous.get('failures',[]),mode='close') for k in groups}).copy()
    rule_versions=previous.get('ruleVersions',{}).copy()
    universe={}; membership={}; official_counts={}
    if args.ma_pullback_only:
        selected=('maPullback',)
    elif args.pullback_only:
        selected=('pullback',)
    else:
        selected=('pullback','maPullback') if partial else tuple(QUERIES)
    for kind in selected:
        query=QUERIES[kind]
        if mode=='auction': query=query.replace('今日成交额','最近一个完整交易日成交额').replace('最近20个交易日内','截至最近一个完整交易日的最近20个交易日内')
        queries[kind]=query
        rows,coverage[kind]=wide_screen(query,cache_slot)
        for row in rows:
            code=str(row.get('SECURITY_CODE','')).zfill(6)
            if len(code)!=6 or not code.isdigit(): continue
            if kind=='pullback' and not pullback_security_allowed(code,row.get('SECURITY_SHORT_NAME','')): continue
            universe[code]=row.get('SECURITY_SHORT_NAME',code)
            membership.setdefault(code,set()).add(kind)
            if kind=='pullback': official_counts[code]=official_limit_count(row)
        groups[kind]=[]
        print(kind, 'broad candidates:',len(rows),'complete:',coverage[kind]['complete'],flush=True)
    codes=sorted(universe); failures=[]; verified=0
    verified_codes=set()
    public_bars={}
    public_codes=[code for code in codes if membership[code]=={'pullback'} and official_counts.get(code) is not None]
    if public_codes:
        def load_public(code):
            try: return code,public_daily_bars(code,session)
            except Exception: return code,[]
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
            public_bars=dict(executor.map(load_public,public_codes))
    ma_contexts={}
    if mode=='intraday' and 'maPullback' in selected:
        def load_context(code):
            try: return code,intraday_context(code,args.cutoff)
            except Exception: return code,{}
        ma_codes=[code for code in codes if 'maPullback' in membership[code]]
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
            ma_contexts=dict(executor.map(load_context,ma_codes))
    ma_missing_cutoff=set()
    for start in range(0,len(codes),5):
        batch=codes[start:start+5]
        # MX's explicit "前复权" wording can resolve to fixed-base close for only
        # one entity. Ordinary daily OHLC resolves all entities; the parser still
        # strictly requires AdjustFlag=1 metadata for every accepted price field.
        blocks=[]
        mx_batch=[code for code in batch if code not in public_bars]
        if mx_batch:
            query='、'.join(mx_batch)+'分别最近40个交易日每日开盘价、最高价、最低价、收盘价、成交量、成交额、涨跌幅、是否涨停，返回每只股票代码和交易日期'
            try:
                blocks=tables(api('query',query,cache_slot))
            except QuotaExceeded:
                raise
            except RuntimeError:
                blocks=[]
        for code in batch:
            use_public=code in public_bars
            required_bars=20 if membership[code]=={'maPullback'} else 35
            bars=public_bars[code] if use_public else bars_from_tables(blocks,code)
            bars=[b for b in bars if b['date']<=session]
            count_matches=(not use_public or (official_counts.get(code) is not None and
                sum(b.get('limit')==1 for b in bars[-20:])==official_counts[code]))
            if len(bars)<required_bars or bars[-1]['date']!=session or not all('limit' in b for b in bars[-required_bars:]) or not count_matches:
                # MX occasionally omits an entity in multi-stock queries; retry it alone.
                if not use_public:
                    single=code+str(universe[code])+'最近40个交易日每日前复权开盘价、最高价、最低价、收盘价、成交量、成交额、涨跌幅、是否涨停，返回交易日期'
                    try:
                        bars=bars_from_tables(tables(api('query',single,cache_slot)),code)
                        bars=[b for b in bars if b['date']<=session]
                    except QuotaExceeded:
                        raise
                    except RuntimeError:
                        bars=[]
            count_matches=(not use_public or (official_counts.get(code) is not None and
                sum(b.get('limit')==1 for b in bars[-20:])==official_counts[code]))
            if len(bars)<required_bars or bars[-1]['date']!=session or not all('limit' in b for b in bars[-required_bars:]) or not count_matches:
                failures.append({'code':code,'name':universe[code],'reason':'前复权日K、涨停次数或交易日期交叉校验不完整，未冒充通过'})
                continue
            context={}
            if mode=='intraday':
                try:
                    context=ma_contexts[code] if code in ma_contexts else intraday_context(code,args.cutoff)
                    quote_time=context.get('quoteTime','')
                    if quote_time[:10]==session and (not args.cutoff or quote_time[11:16]==args.cutoff):
                        bars[-1].update(open=context['sessionOpen'],high=context['sessionHigh'],low=context['sessionLow'],
                            close=context['currentPrice'],volume=context['sessionVolume'],
                            change=(context['currentPrice']/bars[-2]['close']-1)*100,partial=True)
                except Exception as error:
                    context={'error':'分时或板块数据暂缺：'+str(error)}
            verified+=1
            verified_codes.add(code)
            result=evaluate(bars)
            for kind,item in result.items():
                if kind in membership[code]:
                    if kind=='maPullback' and mode=='intraday' and args.cutoff and not bars[-1].get('partial'):
                        continue
                    if mode=='auction':
                        status='竞价观察 · 上一交易日回调，今日待确认' if kind=='maPullback' else '竞价观察 · 昨日收复，今日待确认'
                        item.update(status=status,provisional=True)
                    elif mode=='intraday':
                        item.update(status='盘中临时 · '+item['status'],provisional=True,volumeRatio=None)
                        item['confirmation']+='；盘中累计量不直接当作全天缩量'
                    if kind=='pullback':
                        apply_trade_plan(item,context,mode)
                    item['evaluatedAt']=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat()
                    groups[kind].append(dict(code=code,name=universe[code],**item))
            if code in ma_contexts and args.cutoff and not bars[-1].get('partial'):
                ma_missing_cutoff.add(code)
        print('K-line progress:',min(start+5,len(codes)),'/',len(codes),flush=True)
    for kind in selected:
        if kind == 'maPullback':
            groups[kind].sort(key=lambda r:(-r['limitCount20'],-r['rewardRisk'],r['code']))
        else:
            groups[kind].sort(key=lambda r:(r['signalDate'],r['change']),reverse=True)
    if 'pullback' in selected: enforce_portfolio_cap(groups['pullback'])
    if codes and not verified: raise RuntimeError('No verified daily K-lines; retaining previous snapshot')
    for kind in ('pullback','second','triple'):
        groups.setdefault(kind,[])
        coverage.setdefault(kind,dict(total=0,returned=0,complete=False,conditions=[]))
    for kind in selected:
        group_codes={code for code in codes if kind in membership[code]}
        group_verified=verified_codes & group_codes
        group_failures=[item for item in failures if item['code'] in group_codes]
        if kind == 'maPullback':
            group_verified-=ma_missing_cutoff
            group_failures.extend(dict(code=code,name=universe[code],reason='缺少指定截点的当日分时价')
                for code in sorted(ma_missing_cutoff))
        if kind == 'maPullback' and group_codes and not group_verified:
            raise RuntimeError('No verified MA pullback daily K-lines; retaining previous snapshot')
        group_dates[kind]=session
        group_generated[kind]=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat()
        group_stats[kind]=dict(verified=len(group_verified),universe=len(group_codes),failures=group_failures,mode=mode)
    if 'pullback' in selected: rule_versions['pullback']=PULLBACK_RULE_VERSION
    report=dict(version=1,asOf=session,generatedAt=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),
        source='东方财富妙想 mx-xuangu宽筛 + 东方财富公开前复权行情API交叉复核',queries=queries,coverage=coverage,verified=verified,universe=len(codes),failures=failures,
        groupAsOf=group_dates,groupGeneratedAt=group_generated,groupStats=group_stats,ruleVersions=rule_versions,mode=mode,
        groups=groups,priceBasis='前复权日K；涨停采用妙想每日是否涨停字段确认，不用复权价格推算涨停。',
        schedule='涨停回调策略工作日09:20竞价观察、14:30盘中查询（北京时间，后台排队可能延迟）。',
        ruleVersion=PULLBACK_RULE_VERSION,limitations='涨停回调：沪深主板非ST、上市超过365天；近20交易日至少2次涨停；回调守住MA20；近3根K线重心上移；MA10>MA20且两线向上；回调曾破MA5后重新站回，当前MA5乖离0%至5%。不再限制当日涨幅，不要求反包。09:20仅列昨日形态与竞价待确认；14:30为临时信号。未自动交易或加入自选。')
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False),encoding='utf-8')
    print('Private report ready; verified:',verified,'unavailable:',len(failures))
    if 'maPullback' in selected:
        stats=group_stats['maPullback']
        print(f"MA pullback snapshot: {session} ({mode}); matches={len(groups['maPullback'])}; "
              f"verified={stats['verified']}/{stats['universe']}; complete={coverage['maPullback']['complete']}")

if __name__=='__main__': main()
