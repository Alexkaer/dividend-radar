"""Private strategy builder. Never write plaintext reports inside the public repository."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
CACHE = Path(tempfile.gettempdir()) / 'dividend-strategy-private-cache'
QUERIES = {
    'pullback': 'A股，非ST，上市天数大于365天，最近20个交易日内涨停次数大于等于1，今日涨跌幅小于5%，今日成交额大于1亿元',
    'second': 'A股，非ST，上市天数大于365天，最近30个交易日内连续涨停天数大于等于2天，今日涨跌幅小于5%，今日成交额大于1亿元',
    'triple': 'A股，非ST，上市天数大于365天，最近5个交易日内成交量环比增长率大于等于200%出现次数大于0，最近5个交易日内当日涨幅大于3%出现次数大于0，今日成交额大于1亿元',
}


def api(endpoint, query, day):
    CACHE.mkdir(parents=True, exist_ok=True)
    cache = CACHE / (hashlib.sha256((day + endpoint + query).encode()).hexdigest() + '.json')
    if cache.exists():
        return json.loads(cache.read_text(encoding='utf-8'))
    for attempt in range(5):
        time.sleep(2 + attempt * 5)
        try:
            body = {'keyword' if endpoint == 'stock-screen' else 'toolQuery': query}
            req = urllib.request.Request('https://mkapi2.dfcfs.com/finskillshub/api/claw/' + endpoint,
                data=json.dumps(body).encode(), headers={'apikey': os.environ['MX_APIKEY'], 'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=180) as response:
                result = json.load(response)
            if result.get('status') not in (0, '0'):
                raise ValueError('MX outer response failed')
            data = result.get('data') or {}
            if data.get('status', 0) not in (0, '0') or data.get('code', 0) not in (0, '0', 200, '200') or not data.get('data'):
                raise ValueError('MX nested response failed')
            value = data['data']
            cache.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
            return value
        except Exception:
            if attempt == 4:
                raise RuntimeError('MX request failed after retries; retaining previous encrypted snapshot') from None


def screen(query, day):
    result = api('stock-screen', query, day)
    all_results = result.get('allResults') or {}
    table = all_results.get('result') or {}
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


def evaluate(bars):
    """Mechanical closing-bar checks only; intraday/sector acceptance remains unknown."""
    found = {}
    if len(bars) < 35:
        return found
    last = bars[-1]
    if last.get('amount', 0) <= 1e8:
        return found
    def intact(low, start):
        return min(b['low'] for b in bars[start:]) >= low - .005
    def record(kind, event, low, zone, status, evidence):
        found[kind] = dict(signalDate=event['date'], close=last['close'], change=last['change'],
            status=status, zone=[round(x, 3) for x in zone], invalidation=round(low,3), evidence=evidence,
            volumeRatio=round(last['volume']/event['volume'],4) if event['volume']>0 else None,
            confirmation='分时VWAP、板块强度与指定时段承接未查询；完成日线条件不等于买入信号',
            exit='收盘跌破防守位退出；冲高失去VWAP或量价转弱先减仓。')
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
    # 20-session limit-up, real retreat and closing bullish recovery near MA10.
    for i in range(len(bars)-3, max(-1,len(bars)-21), -1):
        event=bars[i]
        if not limits[i]: continue
        after=bars[i+1:]
        support=min(x['low'] for x in after)
        ma=sum(b['close'] for b in bars[-10:])/10
        retreat=min(x['close'] for x in after) < event['close']*.98
        recovery=last['close'] > last['open'] and last['close'] > bars[-2]['close'] and last['close'] >= ma
        if retreat and recovery and support >= event['low'] and last['close'] <= ma*1.03:
            record('pullback',event,support,[max(support,ma*.99),ma*1.01], '回调转强 · 待竞价承接',
                f"涨停日{event['date']}；回调低点{support:.2f}；收阳转强并收复MA10 {ma:.2f}")
            break
    return found


def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args=parser.parse_args()
    output=Path(args.output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise SystemExit('Plaintext output must be outside the repository')
    now=dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))
    today=now.date().isoformat()
    if (now.hour,now.minute) < (15,15):
        print('Daily closing bars are not complete; previous snapshot retained.')
        return
    index=api('query','上证指数最近5个交易日每日收盘价，返回交易日期',today)
    dates=[str(d)[:10] for b in tables(index) for d in (b.get('rawTable') or {}).get('headName',[]) if str(d)[:10]<=today]
    if not dates: raise RuntimeError('No market session date')
    session=max(dates)
    if session != today:
        print('No current trading session; previous snapshot retained.')
        return
    groups={}; coverage={}; universe={}; membership={}
    for kind, query in QUERIES.items():
        rows,coverage[kind]=wide_screen(query,today)
        for row in rows:
            code=str(row.get('SECURITY_CODE','')).zfill(6)
            if len(code)!=6 or not code.isdigit(): continue
            universe[code]=row.get('SECURITY_SHORT_NAME',code)
            membership.setdefault(code,set()).add(kind)
        groups[kind]=[]
        print(kind, 'broad candidates:',len(rows),'complete:',coverage[kind]['complete'],flush=True)
    codes=sorted(universe); failures=[]; verified=0
    for start in range(0,len(codes),5):
        batch=codes[start:start+5]
        query='、'.join(c+str(universe[c]) for c in batch)+'分别最近60个交易日每日前复权开盘价、最高价、最低价、收盘价、成交量、成交额、涨跌幅、是否涨停，返回每只股票代码和交易日期'
        try:
            blocks=tables(api('query',query,today))
        except RuntimeError:
            blocks=[]
        for code in batch:
            bars=bars_from_tables(blocks,code)
            if len(bars)<35 or not bars or bars[-1]['date']!=session or not all('limit' in b for b in bars[-35:]):
                # MX occasionally omits an entity in multi-stock queries; retry it alone.
                single=code+str(universe[code])+'最近60个交易日每日前复权开盘价、最高价、最低价、收盘价、成交量、成交额、涨跌幅、是否涨停，返回交易日期'
                try:
                    bars=bars_from_tables(tables(api('query',single,today)),code)
                except RuntimeError:
                    bars=[]
            if len(bars)<35 or bars[-1]['date']!=session or not all('limit' in b for b in bars[-35:]) or 'amount' not in bars[-1]:
                failures.append({'code':code,'name':universe[code],'reason':'日K、涨停状态或交易日期不完整，未冒充通过'})
                continue
            verified+=1
            result=evaluate(bars)
            for kind,item in result.items():
                if kind in membership[code]: groups[kind].append(dict(code=code,name=universe[code],**item))
        print('K-line progress:',min(start+5,len(codes)),'/',len(codes),flush=True)
    for values in groups.values(): values.sort(key=lambda r:(r['signalDate'],r['change']),reverse=True)
    if not verified: raise RuntimeError('No verified daily K-lines; retaining previous snapshot')
    report=dict(version=1,asOf=session,generatedAt=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),
        source='东方财富妙想 mx-xuangu + mx-data',queries=QUERIES,coverage=coverage,verified=verified,universe=len(codes),failures=failures,
        groups=groups,priceBasis='前复权日K；涨停采用妙想每日是否涨停字段确认，不用复权价格推算涨停。',
        schedule='交易日15:45（北京时间）；节假日保留上一交易日；接口失败不改写原日期。',
        ruleVersion='2026-11-04-v1',limitations='机械日线观察池，不构成买入信号。竞价9:25、承接9:40为核心检查，14:40补充；三倍量/二板回调14:45确认。未自动交易或加入自选。')
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False),encoding='utf-8')
    print('Private report ready; verified:',verified,'unavailable:',len(failures))

if __name__=='__main__': main()
