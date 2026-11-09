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
PULLBACK_RULE_VERSION = '2026-11-09-ma-reclaim-v2'
QUERIES = {
    'pullback': 'A股，非ST，上市天数大于365天，最近20个交易日内涨停次数大于等于2次且小于等于3次，今日成交额大于1亿元',
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


def reclaim_match(bars):
    """2–3 official limit-ups in 20 sessions, then a strict MA5/MA10 reclaim."""
    if len(bars)<21 or any(b.get('limit') not in (0,1) for b in bars[-20:]):
        return None
    count=sum(b['limit']==1 for b in bars[-20:])
    if count not in (2,3): return None
    last,previous=bars[-1],bars[-2]
    lines=[]
    for period in (5,10):
        ma=sum(b['close'] for b in bars[-period:])/period
        prior_ma=sum(b['close'] for b in bars[-period-1:-1])/period
        # During today's low tick, MA includes that low tick, not the later closing price.
        low_tick_ma=(sum(b['close'] for b in bars[-period:-1])+last['low'])/period
        was_below=previous['close']<prior_ma
        dipped_today=last['low']<low_tick_ma
        if last['close']>ma and (was_below or dipped_today):
            lines.append(dict(period=period,ma=ma,previousMA=prior_ma,previousClose=previous['close'],
                priorBelow=was_below,intradayBelow=dipped_today))
    return dict(count=count,lines=lines) if lines else None


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
    reclaim=reclaim_match(bars)
    if reclaim:
        support=max(line['ma'] for line in reclaim['lines'])
        labels='/'.join('MA'+str(line['period']) for line in reclaim['lines'])
        event=next(b for b in reversed(bars[-20:]) if b.get('limit')==1)
        record('pullback',event,min(last['low'],support*.99),[support*.99,support*1.01],
            '重新站回'+labels+' · 待承接确认',
            f"近20交易日累计{reclaim['count']}次涨停；"+'；'.join(
                f"MA{x['period']}={x['ma']:.3f}，"+('昨日收盘在线下' if x['priorBelow'] else '当日盘中跌破')+'后当日重新站上'
                for x in reclaim['lines']))
        found['pullback'].update(limitCount20=reclaim['count'],reclaimLines=reclaim['lines'],
            ruleVersion=PULLBACK_RULE_VERSION,signalDate=last['date'])
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


def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--previous')
    parser.add_argument('--mode', choices=('auto','auction','intraday','close'), default='auto')
    parser.add_argument('--pullback-only',action='store_true')
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
    if mode!='auction' and session != today:
        print('No current trading session; previous snapshot retained.')
        return
    partial=args.pullback_only or mode!='close'
    groups=previous.get('groups',{}).copy() if partial else {}
    coverage=previous.get('coverage',{}).copy() if partial else {}
    queries=previous.get('queries',{}).copy() if partial else {}
    group_dates=previous.get('groupAsOf',{k:previous.get('asOf') for k in groups}).copy()
    group_generated=previous.get('groupGeneratedAt',{k:previous.get('generatedAt') for k in groups}).copy()
    group_stats=previous.get('groupStats',{k:dict(verified=previous.get('verified',0),universe=previous.get('universe',0),
        failures=previous.get('failures',[]),mode='close') for k in groups}).copy()
    rule_versions=previous.get('ruleVersions',{}).copy()
    universe={}; membership={}
    selected=('pullback',) if partial else tuple(QUERIES)
    for kind in selected:
        query=QUERIES[kind]
        if mode=='auction': query=query.replace('今日成交额','最近一个完整交易日成交额').replace('最近20个交易日内','截至最近一个完整交易日的最近20个交易日内')
        queries[kind]=query
        rows,coverage[kind]=wide_screen(query,cache_slot)
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
        # MX's explicit "前复权" wording can resolve to fixed-base close for only
        # one entity. Ordinary daily OHLC resolves all entities; the parser still
        # strictly requires AdjustFlag=1 metadata for every accepted price field.
        query='、'.join(batch)+'分别最近40个交易日每日开盘价、最高价、最低价、收盘价、成交量、成交额、涨跌幅、是否涨停，返回每只股票代码和交易日期'
        try:
            blocks=tables(api('query',query,cache_slot))
        except QuotaExceeded:
            raise
        except RuntimeError:
            blocks=[]
        for code in batch:
            bars=bars_from_tables(blocks,code)
            bars=[b for b in bars if b['date']<=session]
            if len(bars)<35 or not bars or bars[-1]['date']!=session or not all('limit' in b for b in bars[-35:]):
                # MX occasionally omits an entity in multi-stock queries; retry it alone.
                single=code+str(universe[code])+'最近40个交易日每日前复权开盘价、最高价、最低价、收盘价、成交量、成交额、涨跌幅、是否涨停，返回交易日期'
                try:
                    bars=bars_from_tables(tables(api('query',single,cache_slot)),code)
                    bars=[b for b in bars if b['date']<=session]
                except QuotaExceeded:
                    raise
                except RuntimeError:
                    bars=[]
            if len(bars)<35 or bars[-1]['date']!=session or not all('limit' in b for b in bars[-35:]) or 'amount' not in bars[-1]:
                failures.append({'code':code,'name':universe[code],'reason':'日K、涨停状态或交易日期不完整，未冒充通过'})
                continue
            verified+=1
            result=evaluate(bars)
            for kind,item in result.items():
                if kind in membership[code]:
                    if mode=='auction': item.update(status='竞价观察 · 昨日收复，今日待确认',provisional=True)
                    elif mode=='intraday': item.update(status='盘中临时 · '+item['status'],provisional=True)
                    item['evaluatedAt']=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat()
                    groups[kind].append(dict(code=code,name=universe[code],**item))
        print('K-line progress:',min(start+5,len(codes)),'/',len(codes),flush=True)
    for values in groups.values(): values.sort(key=lambda r:(r['signalDate'],r['change']),reverse=True)
    if codes and not verified: raise RuntimeError('No verified daily K-lines; retaining previous snapshot')
    for kind in ('pullback','second','triple'):
        groups.setdefault(kind,[])
        coverage.setdefault(kind,dict(total=0,returned=0,complete=False,conditions=[]))
    for kind in selected:
        group_dates[kind]=session
        group_generated[kind]=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat()
        group_stats[kind]=dict(verified=verified,universe=len(codes),failures=failures,mode=mode)
    if 'pullback' in selected: rule_versions['pullback']=PULLBACK_RULE_VERSION
    report=dict(version=1,asOf=session,generatedAt=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),
        source='东方财富妙想 mx-xuangu + mx-data',queries=queries,coverage=coverage,verified=verified,universe=len(codes),failures=failures,
        groupAsOf=group_dates,groupGeneratedAt=group_generated,groupStats=group_stats,ruleVersions=rule_versions,mode=mode,
        groups=groups,priceBasis='前复权日K；涨停采用妙想每日是否涨停字段确认，不用复权价格推算涨停。',
        schedule='涨停回调策略工作日09:15竞价观察、14:40盘中查询；15:45收盘复核全策略（北京时间，后台排队可能延迟）。',
        ruleVersion=PULLBACK_RULE_VERSION,limitations='涨停回调：近20交易日累计2–3次涨停，跌破MA5或MA10后当日重新站回任一均线。09:15没有当日完整日K，只列昨日形态与竞价待确认；14:40为临时信号，收盘再复核。未自动交易或加入自选。')
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False),encoding='utf-8')
    print('Private report ready; verified:',verified,'unavailable:',len(failures))

if __name__=='__main__': main()
