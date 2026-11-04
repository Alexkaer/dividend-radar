"""Maintain an optional fallback; normal updates happen in the visitor browser."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo
try:
    from .update_data import fetch,ROOT,number
except ImportError:
    from update_data import fetch,ROOT,number

def main():
    universe=json.loads((ROOT/'data/hardware-universe.json').read_text(encoding='utf-8'))
    codes=[s['code'] for s in universe['stocks']]
    secids=','.join(('1.' if c.startswith('6') else '0.')+c for c in codes)
    response=fetch('https://push2.eastmoney.com/api/qt/ulist.np/get',dict(secids=secids,fltt=2,fields='f2,f3,f6,f8,f12,f13,f14,f20,f23,f115,f124'))['data']
    rows=response['diff'];rows=list(rows.values()) if isinstance(rows,dict) else rows
    quotes={r['f12']:r for r in rows}
    quoted=','.join('"'+c+'"' for c in codes)
    profiles=fetch('https://datacenter.eastmoney.com/securities/api/data/v1/get',dict(reportName='RPT_F10_ORG_BASICINFO',columns='SECURITY_CODE,SECURITY_NAME_ABBR,MAIN_BUSINESS,ORG_PROFILE,BOARD_NAME_1LEVEL,BOARD_NAME_2LEVEL,BOARD_NAME_3LEVEL',filter=f'(SECURITY_CODE in ({quoted}))',pageSize=500))
    if not profiles.get('success') or not profiles.get('result'): raise ValueError(str(profiles.get('message')))
    by_code={r['SECURITY_CODE']:r for r in profiles['result']['data']}
    if set(codes)-quotes.keys() or set(codes)-by_code.keys():raise ValueError('Incomplete hardware quote/profile coverage')
    stocks=[]
    for item in universe['stocks']:
        c=item['code'];q=quotes[c];p=by_code[c]
        stocks.append(dict(**item,nameVerified=q['f14'],market='沪市' if c.startswith('6') else '深市',price=number(q.get('f2')),change=number(q.get('f3')),amount=number(q.get('f6')),turnover=number(q.get('f8')),cap=number(q.get('f20')),pe=number(q.get('f115')),pb=number(q.get('f23')),quoteTime=number(q.get('f124')),industry=p.get('BOARD_NAME_2LEVEL') or p.get('BOARD_NAME_1LEVEL'),business=p.get('MAIN_BUSINESS') or p.get('ORG_PROFILE'),source='https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/Index?type=web&code='+('SH' if c.startswith('6') else 'SZ')+c))
    now=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat();target=ROOT/'data/hardware.json'
    temporary=target.with_suffix('.tmp');temporary.write_text(json.dumps(dict(updatedAt=now,source='东方财富行情与公司资料',stocks=stocks),ensure_ascii=False,separators=(',',':')),encoding='utf-8');temporary.replace(target)
    print(f'Hardware snapshot: {len(stocks)} stocks; {len(by_code)} verified company profiles')

if __name__=='__main__':main()
