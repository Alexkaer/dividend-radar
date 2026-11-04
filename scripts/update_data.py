"""Fetch complete A-share quotes and implemented cash dividends; fail closed."""
import json, math, os, time, urllib.request, urllib.parse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def fetch(url, params):
    hosts = [url]
    if 'push2.eastmoney.com' in url:
        hosts += [url.replace('push2.eastmoney.com', h) for h in ['push2delay.eastmoney.com','82.push2.eastmoney.com','push2his.eastmoney.com']]
    for attempt in range(4):
        try:
            req = urllib.request.Request(hosts[attempt % len(hosts)]+'?'+urllib.parse.urlencode(params), headers={'User-Agent':'Mozilla/5.0','Referer':'https://data.eastmoney.com/'})
            with urllib.request.urlopen(req, timeout=45) as r: return json.load(r)
        except Exception:
            if attempt == 3: raise
            time.sleep(2 ** attempt)

def number(v):
    try:
        n=float(v)
        return n if math.isfinite(n) else None
    except (ValueError,TypeError): return None

def get_quotes():
    quotes={}; page=1
    while True:
        d=fetch('https://push2.eastmoney.com/api/qt/clist/get',dict(pn=page,pz=100,np=1,fltt=2,invt=2,po=1,fid='f12',fs='m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048',fields='f12,f13,f14,f2,f3,f20,f23,f115,f124'))['data']
        rows=d['diff']; rows=list(rows.values()) if isinstance(rows,dict) else rows
        if not rows: raise RuntimeError('行情分页为空')
        for r in rows: quotes[r['f12']]=r
        if page*100>=d['total']: break
        page+=1
    if len(quotes)<4500 or len(quotes)!=d['total']: raise RuntimeError('全市场行情覆盖不完整')
    return quotes

def closing_quotes():
    url='https://datacenter-web.eastmoney.com/api/data/v1/get'
    params=dict(reportName='RPT_VALUEANALYSIS_DET',columns='ALL',pageSize=500,pageNumber=1,sortColumns='TRADE_DATE,SECURITY_CODE',sortTypes='-1,1')
    latest=fetch(url,dict(params,pageSize=1,filter='(SECURITY_CODE="601988")',sortColumns='TRADE_DATE',sortTypes='-1'))['result']['data'][0]['TRADE_DATE']
    params['filter']=f'(TRADE_DATE=\'{latest[:10]}\')'
    stamp=int(datetime.fromisoformat(latest[:10]+'T15:00:00+08:00').timestamp())
    quotes={}; total=0
    while True:
        d=fetch(url,params)['result']; total+=len(d['data'])
        for r in d['data']:
            code=r['SECURITY_CODE']
            quotes[code]=dict(f12=code,f13=1 if r['SECUCODE'].endswith('.SH') else 0,f14=r['SECURITY_NAME_ABBR'],f2=r['CLOSE_PRICE'],f3=r['CHANGE_RATE'],f20=r['TOTAL_MARKET_CAP'],f23=r['PB_MRQ'],f115=r['PE_TTM'],f124=stamp)
        if params['pageNumber']>=d['pages']: break
        params['pageNumber']+=1
    if total!=d['count'] or len(quotes)!=total or total<4500: raise RuntimeError('备用收盘行情覆盖不足')
    print(f'Using closing valuation snapshot: {latest}, {total} stocks')
    return quotes

def main():
    now = datetime.now(ZoneInfo('Asia/Shanghai'))
    today=now.date(); start=today-timedelta(days=365)
    try:
        if os.environ.get('GITHUB_ACTIONS') == 'true':
            quotes=closing_quotes()
        else:
            quotes=get_quotes()
    except Exception as e:
        print(f'Primary quotes unavailable: {e}; trying closing valuation dataset')
        quotes=closing_quotes()
    # Align dividends with the quote date, including when a prior close is used.
    today=datetime.fromtimestamp(max(q['f124'] for q in quotes.values()),ZoneInfo('Asia/Shanghai')).date()
    start=today-timedelta(days=365)
    dividends={}; seen=set(); total=0; page=1
    while True:
        result=fetch('https://datacenter-web.eastmoney.com/api/data/v1/get',dict(reportName='RPT_SHAREBONUS_DET',columns='ALL',pageSize=500,pageNumber=page,sortColumns='EX_DIVIDEND_DATE,SECURITY_CODE,REPORT_DATE',sortTypes='-1,1,-1',filter=f'(EX_DIVIDEND_DATE>\'{start}\')(EX_DIVIDEND_DATE<=\'{today}\')(ASSIGN_PROGRESS="实施分配")'))
        if not result.get('success') or not result.get('result'): raise RuntimeError(str(result))
        d=result['result']; total+=len(d['data'])
        for r in d['data']:
            key=(r['SECURITY_CODE'],r['REPORT_DATE'],r['EX_DIVIDEND_DATE'])
            if key in seen: raise RuntimeError('分红记录重复')
            seen.add(key)
            cash=number(r['PRETAX_BONUS_RMB'])
            if cash and cash>0: dividends.setdefault(r['SECURITY_CODE'],[]).append({'date':r['EX_DIVIDEND_DATE'][:10],'cash':cash/10,'plan':r['IMPL_PLAN_PROFILE']})
        if page>=d['pages']: break
        page+=1
    if total!=d['count'] or total<1000: raise RuntimeError('分红覆盖不足')
    stocks=[]
    for code,q in quotes.items():
        price=number(q['f2']); records=dividends.get(code,[])
        if not price or price<=0 or not records: continue
        cap=number(q['f20'])
        if cap is None or cap<=50_000_000_000: continue
        cash=sum(x['cash'] for x in records); y=cash/price*100
        if y<=5: continue
        stocks.append(dict(code=code,name=q['f14'],market='沪市' if q['f13']==1 else ('北交所' if code[0] in '489' else '深市'),price=price,change=number(q['f3']),yieldRate=round(y,4),cash=round(cash,6),pe=number(q['f115']),pb=number(q['f23']),cap=number(q['f20']),quoteTime=q.get('f124'),dividends=records))
    stocks.sort(key=lambda x:x['yieldRate'],reverse=True)
    if not stocks: raise RuntimeError('筛选结果异常为空')
    payload=dict(updatedAt=now.isoformat(),windowStart=str(start),windowEnd=str(today),quoteAt=max(q.get('f124') or 0 for q in quotes.values()),universe=len(quotes),dividendRecords=total,source='东方财富行情 / 分红送配',method='过去365天已除息税前每股现金分红之和 ÷ 最新价 × 100%；未对期间送转、配股、拆并股调整，特殊公司须复核。',stocks=stocks)
    target=ROOT/'data/stocks.json'; temp=target.with_suffix('.tmp');temp.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8');temp.replace(target)
    print(f'Updated {len(stocks)} stocks / {len(quotes)} universe; {total} dividend records')
if __name__=='__main__': main()
