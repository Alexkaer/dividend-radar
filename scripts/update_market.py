"""Closing market dashboard with date-aligned source data; fail closed."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor
try:
    from .update_data import fetch, closing_quotes, ROOT, number
except ImportError:
    from update_data import fetch, closing_quotes, ROOT, number

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
    return dict(items=top,universe=d['total'],scope='东方财富行业板块（含不同层级，可能存在重叠），不含概念板块；最近5个交易日收盘涨幅，已逐一用6根日K核对前15。')

def main():
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
    target=ROOT/'data/market.json';tmp=target.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8');tmp.replace(target)
    print(f'Market {as_of}: {b["up"]} up / {b["down"]} down; limit pools {limits["up"]}/{limits["down"]}; {len(indices)} indices; 10 turnover sessions; 15 verified sectors')

if __name__=='__main__': main()
