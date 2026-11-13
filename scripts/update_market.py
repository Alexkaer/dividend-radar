"""Closing market dashboard with date-aligned source data; fail closed."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor
try:
    from .update_data import fetch, closing_quotes, ROOT, number
    from .strategy_screen import tencent_daily
except ImportError:
    from update_data import fetch, closing_quotes, ROOT, number
    from strategy_screen import tencent_daily

INDICES=[('1.000001','上证指数'),('0.399001','深证成指'),('0.399006','创业板指'),('1.000688','科创50'),('1.000300','沪深300'),('0.899050','北证50'),('1.000016','上证50'),('1.000905','中证500')]

def kline(secid,limit=20):
    data=fetch('https://push2his.eastmoney.com/api/qt/stock/kline/get',dict(secid=secid,klt=101,fqt=0,lmt=limit,end=20500101,fields1='f1,f2,f3,f4,f5,f6',fields2='f51,f52,f53,f54,f55,f56,f57,f58,f59'))['data']
    if not data or not data.get('klines'): raise ValueError(f'Empty K-line {secid}')
    return [dict(date=r[0],close=float(r[2]),amount=float(r[6]),change=float(r[8]) if len(r)>8 else None) for r in (s.split(',') for s in data['klines'])]

def breadth(quotes):
    changes=[number(q['f3']) for q in quotes.values() if number(q.get('f2')) is not None and number(q['f2'])>0 and number(q.get('f3')) is not None]
    up=sum(v>0 for v in changes);down=sum(v<0 for v in changes)
    return dict(up=up,down=down,flat=len(changes)-up-down,total=len(changes),universe=len(quotes),advanceShare=round(up/(up+down),4) if up+down else None)

def turnover_summary(sh,sz,as_of):
    a={r['date']:r for r in sh};b={r['date']:r for r in sz}
    days=sorted(d for d in a.keys()&b.keys() if d<=as_of)[-10:]
    if len(days)<10 or days[-1]!=as_of: raise ValueError('Incomplete or stale turnover dates')
    rows=[dict(date=d,shanghai=a[d]['amount'],shenzhen=b[d]['amount'],amount=a[d]['amount']+b[d]['amount']) for d in days]
    if any(r['amount']<=0 for r in rows): raise ValueError('Invalid turnover amounts')
    previous=sum(r['amount'] for r in rows[:5]);recent=sum(r['amount'] for r in rows[5:])
    return dict(days=rows,today=rows[-1]['amount'],dayChangePct=round((rows[-1]['amount']/rows[-2]['amount']-1)*100,2),fiveDayChangePct=round((recent/previous-1)*100,2),recentFiveDayAverage=recent/5,previousFiveDayAverage=previous/5,scope='上证指数与深证成指成交额合计；沪深指数口径，不含北交所，不重复叠加创业板或科创50。')

def sentiment(b,limits,indices):
    if b['advanceShare'] is None or limits['up']+limits['down']==0: return dict(label='待判断',score=None)
    main=[r['change'] for r in indices if r['code'] in ['000001','399001']]
    if len(main)!=2:return dict(label='待判断',score=None)
    index_component=max(0,min(1,0.5+sum(main)/len(main)/6))
    score=round(100*(0.6*b['advanceShare']+0.25*limits['up']/(limits['up']+limits['down'])+0.15*index_component))
    label='活跃' if score>=75 else '偏强' if score>=55 else '分歧' if score>=45 else '偏弱' if score>=25 else '低迷'
    return dict(label=label,score=score,method='自定义情绪分：60%×上涨占比（上涨/涨跌家数）+25%×涨停池占比（涨停/涨跌停池总数）+15%×指数强弱分。指数强弱分=截断至0~1的(0.5+沪深主指数平均涨幅/6)。≥75活跃、55~74偏强、45~54分歧、25~44偏弱、<25低迷；为当日描述，不是买卖预测。')

def pools(as_of):
    counts={}
    for kind,endpoint in [('up','getTopicZTPool'),('down','getTopicDTPool')]:
        data=fetch('https://push2ex.eastmoney.com/'+endpoint,dict(ut='7eea3edcaed734bea9cbfc24409ed989',dpt='wz.ztzt',Pageindex=0,pagesize=1000,sort='fbt:asc' if kind=='up' else 'fund:asc',date=as_of.replace('-','')))['data']
        if data is None or str(data.get('qdate'))!=as_of.replace('-',''): raise ValueError('Stale limit pool')
        # tc is the full source pool count; it may exceed the returned page length.
        counts[kind]=int(data['tc'])
    counts['scope']='东方财富涨停/跌停股池收录数；并非全A股严格涨跌停总数，可能与交易软件在ST、北交所等范围上不同。'
    return counts

def sector_ranking(as_of):
    rows=[];page=1
    while True:
        d=fetch('https://push2.eastmoney.com/api/qt/clist/get',dict(pn=page,pz=100,np=1,fltt=2,fid='f109',po=1,fs='m:90+t:2',fields='f12,f14,f3,f109,f124'))['data']
        part=d['diff'];part=list(part.values()) if isinstance(part,dict) else part
        if not part:raise ValueError('Sector page empty')
        rows.extend(part)
        if page*100>=d['total']:break
        page+=1
    if len({r['f12'] for r in rows})!=d['total']:raise ValueError('Sector universe incomplete')
    ranked=sorted([r for r in rows if number(r.get('f109')) is not None],key=lambda r:r['f109'],reverse=True)[:15]
    if len(ranked)<15:raise ValueError('Insufficient sector ranking')
    def verify(row):
        bars=[r for r in kline('90.'+row['f12'],8) if r['date']<=as_of]
        if len(bars)<6 or bars[-1]['date']!=as_of:raise ValueError('Sector history stale')
        value=(bars[-1]['close']/bars[-6]['close']-1)*100
        if abs(value-row['f109'])>0.08:raise ValueError('Sector five-session field mismatch')
        return dict(code=row['f12'],name=row['f14'],change=number(row.get('f3')),fiveDayChange=round(value,2),startDate=bars[-6]['date'],endDate=bars[-1]['date'])
    with ThreadPoolExecutor(max_workers=4) as pool: top=list(pool.map(verify,ranked))
    def daily_verify(row):
        bars=[r for r in kline('90.'+row['f12'],3) if r['date']<=as_of]
        if len(bars)<2 or bars[-1]['date']!=as_of:raise ValueError('Daily sector date mismatch')
        value=(bars[-1]['close']/bars[-2]['close']-1)*100
        if abs(value-row['f3'])>0.08:raise ValueError('Daily sector field mismatch')
        return dict(code=row['f12'],name=row['f14'],change=round(value,2),startDate=bars[-2]['date'],endDate=bars[-1]['date'])
    with ThreadPoolExecutor(max_workers=4) as pool: today=list(pool.map(daily_verify,sorted([r for r in rows if number(r.get('f3')) is not None],key=lambda r:r['f3'],reverse=True)[:15]))
    return dict(items=top,todayItems=today,universe=d['total'],scope='东方财富行业板块（含不同层级，可能存在重叠），不含概念板块；当日与5日榜各前15，分别用日K核对。')

def public_turnover(as_of):
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen
    year=int(as_of[:4])
    def history(symbol):
        rows={}
        for start in ({year-1,year} if as_of[5:7]=='01' else {year}):
            query=urlencode(dict(_var='kline_dayqfq',param=f'{symbol},day,{start}-01-01,{start+1}-12-31,640,qfq',
                r='0.8205512681390605'))
            url='https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get?'+query
            with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=15) as response:
                body=response.read().decode()
            payload=json.loads(body.split('=',1)[-1].rstrip(';\r\n'))['data'][symbol]
            for row in payload.get('day') or payload['qfqday']:
                amount=number(row[8]) if len(row)>8 else None
                if row[0]<=as_of and amount is not None and amount>0:
                    rows[row[0]]=dict(date=row[0],amount=amount*10000)
        return list(rows.values())
    with ThreadPoolExecutor(max_workers=2) as pool:
        sh,sz=pool.map(history,('sh000001','sz399001'))
    result=turnover_summary(sh,sz,as_of)
    result['scope']+=' 数据来源：腾讯证券日K成交额。'
    return result


def public_sectors(as_of):
    import akshare as ak
    universe=ak.index_realtime_sw('一级行业').drop_duplicates(subset='指数代码')
    if len(universe)<31:
        raise ValueError('Incomplete Shenwan first-level industry universe')
    def rank(row):
        code,name=row
        history=ak.index_hist_sw(symbol=str(code))
        bars=history.assign(session=history['日期'].astype(str))
        bars=bars[bars.session<=as_of].sort_values('session').tail(6)
        if len(bars)!=6 or bars.session.iloc[-1]!=as_of:
            raise ValueError(f'Shenwan history not current: {code}')
        closes=bars['收盘'].tolist()
        if any(not (value>0) for value in closes):
            raise ValueError(f'Invalid Shenwan close: {code}')
        return dict(code=str(code),name=name,change=(closes[-1]/closes[-2]-1)*100,
            fiveDayChange=(closes[-1]/closes[0]-1)*100,startDate=bars.session.iloc[0],
            priorDate=bars.session.iloc[-2],endDate=as_of)
    with ThreadPoolExecutor(max_workers=8) as pool:
        rows=list(pool.map(rank,universe[['指数代码','指数名称']].itertuples(index=False,name=None)))
    five=sorted(rows,key=lambda row:-row['fiveDayChange'])[:15]
    daily=sorted(rows,key=lambda row:-row['change'])[:15]
    return dict(items=five,todayItems=[{**row,'startDate':row['priorDate']} for row in daily],
        universe=len(rows),provider='shenwan',scope='申万一级行业指数，按收盘日K计算当日与近5交易日涨幅。')


def full_snapshot():
    now=datetime.now(ZoneInfo('Asia/Shanghai'));quotes=closing_quotes()
    as_of=datetime.fromtimestamp(max(q['f124'] for q in quotes.values()),ZoneInfo('Asia/Shanghai')).date().isoformat()
    with ThreadPoolExecutor(max_workers=4) as pool:
        sh_future=pool.submit(kline,'1.000001',20);sz_future=pool.submit(kline,'0.399001',20)
        limit_future=pool.submit(pools,as_of);sector_future=pool.submit(sector_ranking,as_of)
        histories=list(pool.map(lambda item:kline(item[0],3),INDICES))
        indices=[]
        for (secid,name),bars in zip(INDICES,histories):
            bars=[r for r in bars if r['date']<=as_of]
            if not bars or bars[-1]['date']!=as_of:raise ValueError('Index date mismatch: '+name)
            r=bars[-1];indices.append(dict(code=secid.split('.')[1],name=name,close=r['close'],change=r['change'],amount=r['amount'],date=r['date']))
        volumes=turnover_summary(sh_future.result(),sz_future.result(),as_of);limits=limit_future.result();sectors=sector_future.result()
    b=breadth(quotes)
    data=dict(updatedAt=now.isoformat(),asOf=as_of,session='收盘快照',indices=indices,breadth=b,limits=limits,sentiment=sentiment(b,limits,indices),turnover=volumes,sectors=sectors,source='东方财富指数行情、全A股估值行情、涨跌停股池及行业指数')
    return data


def public_snapshot(previous):
    now=datetime.now(ZoneInfo('Asia/Shanghai'))
    day=now.date().isoformat()
    if now.hour<15:
        return previous
    def public_index(item):
        secid,name=item
        market,code=secid.split('.')
        symbol=('sh' if market=='1' else 'sz')+code
        rows=sorted(tencent_daily(symbol,day,5).items())
        if len(rows)<2:return None
        (prior,previous_close),(date,close)=rows[-2:]
        return dict(code=code,name=name,date=date,close=float(close),change=float((close/previous_close-1)*100))
    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs=[pool.submit(public_index,item) for item in INDICES]
    indices=[]
    for job in jobs:
        try:
            row=job.result()
            if row:indices.append(row)
        except (OSError,ValueError,KeyError,ArithmeticError,TypeError): pass
    as_of=next((row['date'] for row in indices if row['code']=='000001'),None)
    if as_of!=day or not any(row['code']=='399001' and row['date']==day for row in indices):
        if previous['asOf']!=day:
            raise ValueError('Public index closing date could not be verified')
        as_of=day
        indices=previous['indices']
    if previous['asOf']>as_of:return previous
    data={**previous,'asOf':as_of,'updatedAt':now.isoformat(),'session':'公开收盘快照',
        'indices':[row for row in indices if row['date']==as_of]}
    notes=['指数来自腾讯公开日K']
    try:
        base='https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/'
        total=int(fetch(base+'Market_Center.getHQNodeStockCount',dict(node='hs_a')))
        def page(i):
            return fetch(base+'Market_Center.getHQNodeData',dict(node='hs_a',num=100,page=i,sort='symbol',asc=1))
        with ThreadPoolExecutor(max_workers=8) as pool:
            rows={r['code']:dict(f2=r['trade'],f3=r['changepercent']) for part in pool.map(page,range(1,(total+99)//100+1)) for r in part}
        if len(rows)!=total or total<4500:raise ValueError('Sina market coverage incomplete')
        data['breadth']=breadth(rows)
        notes.append('市场广度来自新浪')
    except (OSError,ValueError,KeyError,TypeError,RuntimeError):
        data['breadth']=dict(up=None,down=None,flat=None,total=0,advanceShare=None)
        notes.append('市场广度暂不可用')
    try:
        data['limits']=pools(as_of)
        data['sentiment']=sentiment(data['breadth'],data['limits'],data['indices'])
    except (OSError,ValueError,KeyError,TypeError,RuntimeError):
        data['limits']=dict(up=None,down=None,scope='当日涨跌停池暂不可用')
        data['sentiment']=dict(label='待判断',score=None)
    with ThreadPoolExecutor(max_workers=3) as pool:
        turnover=pool.submit(public_turnover,as_of)
        sectors=pool.submit(public_sectors,as_of)
        try:
            data['turnover']=turnover.result()
            notes.append('成交额来自腾讯证券')
        except Exception as error:
            print('Public turnover unavailable:',error)
            notes.append('成交额保留原日期')
        try:
            data['sectors']=sectors.result()
            notes.append('行业榜来自申万一级行业指数')
        except Exception as error:
            print('Public sectors unavailable:',error)
            notes.append('行业榜保留原日期')
    data['partialSource']='。'.join(notes)+'。'
    return data


def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--public-only',action='store_true')
    args=parser.parse_args()
    target=ROOT/'data/market.json'
    previous=json.loads(target.read_text(encoding='utf-8'))
    try:
        data=public_snapshot(previous) if args.public_only else full_snapshot()
        today=datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
        if data['asOf']!=today: data=public_snapshot(previous)
    except Exception:
        if args.public_only:raise
        data=public_snapshot(previous)
    tmp=target.with_suffix('.tmp')
    tmp.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    tmp.replace(target)
    print(f'Market {data["asOf"]}: {len(data["indices"])} indices; {data.get("partialSource","full snapshot")}')

if __name__=='__main__': main()
