"""Rule-based financial analysis, with report dates and comparable peer samples."""
import math
import statistics
from datetime import date, timedelta
from collections import defaultdict

URL='https://datacenter-web.eastmoney.com/api/data/v1/get'

def num(v):
    try:
        value=float(v)
        return value if math.isfinite(value) else None
    except (TypeError,ValueError): return None

def quarter_dates(as_of):
    year=date.fromisoformat(as_of).year
    ends=sorted(f'{y}-{md}' for y in range(year-2,year+1) for md in ['03-31','06-30','09-30','12-31'] if f'{y}-{md}'<=as_of)
    return ends[-1],ends[-2]

def report_rows(fetch, report, where, columns='ALL'):
    result=[];page=1
    while True:
        response=fetch(URL,dict(reportName=report,columns=columns,filter=where,pageSize=500,pageNumber=page,sortColumns='SECURITY_CODE,REPORT_DATE',sortTypes='1,-1'))
        if not response.get('success') or not response.get('result'): raise ValueError(f'Financial source failed: {response.get("message")}')
        payload=response['result'];result.extend(payload['data'])
        if page>=payload['pages']: break
        page+=1
    if len(result)!=payload['count']: raise ValueError('Incomplete financial pagination')
    return result

def median(values):
    values=[v for v in values if v is not None]
    return round(statistics.median(values),2) if values else None

def sector_summary(rows, baseline_count):
    revenues=[num(r.get('TOI_RATIO')) for r in rows]
    # Use profitable firms with non-extreme reported growth; low-base effects may remain.
    profits=[num(r.get('PARENT_NETPROFIT_RATIO')) for r in rows if (num(r.get('PARENT_NETPROFIT')) or 0)>0 and num(r.get('PARENT_NETPROFIT_RATIO')) is not None and num(r['PARENT_NETPROFIT_RATIO'])>-100]
    rev,profit=median(revenues),median(profits)
    valid=[num(r.get('PARENT_NETPROFIT')) for r in rows if num(r.get('PARENT_NETPROFIT')) is not None]
    share=sum(p>0 for p in valid)/len(valid) if valid else None
    coverage=len(rows)/baseline_count if baseline_count else 1
    reliable=len(rows)>=3 and coverage>=0.7 and len(profits)>=max(2,len(rows)*0.3) and rev is not None and profit is not None
    label='样本不足'
    if reliable:
        if rev>=5 and profit>=10 and share>=0.7: label='向好'
        elif (rev<0 and profit<0) or profit<=-10 or share<0.6: label='承压'
        else: label='分化'
    return dict(label=label,samples=len(rows),baselineSamples=baseline_count,coverage=round(coverage,4),revenueGrowthMedian=rev,profitGrowthMedian=profit,profitGrowthSamples=len(profits),profitableShare=round(share,4) if share is not None else None)

def company_analysis(row, prior=None, cash=None):
    revenue=num(row.get('TOTAL_OPERATE_INCOME'))
    if revenue is None: revenue=num(row.get('OPERATE_INCOME'))
    profit=num(row.get('PARENT_NETPROFIT'));deduct=num(row.get('DEDUCT_PARENT_NETPROFIT'))
    rg=num(row.get('TOI_RATIO'));pg=num(row.get('PARENT_NETPROFIT_RATIO'));dg=num(row.get('DPN_RATIO'))
    oldprofit=num(prior.get('PARENT_NETPROFIT')) if prior else None
    olddeduct=num(prior.get('DEDUCT_PARENT_NETPROFIT')) if prior else None
    financial=any(w in (row.get('INDUSTRY_NAME') or '') for w in ['银行','保险','证券','多元金融'])
    ocf=num(cash.get('NETCASH_OPERATE')) if cash else None
    label='数据不足';reasons=[];risks=[]
    if profit is not None:
        if profit<0: label='亏损';risks.append('本期归母净利润为负，需关注盈利修复与分红持续性。')
        elif oldprofit is not None and oldprofit<0: label='扭亏';reasons.append('归母净利润由上年同期亏损转为盈利，低基数同比不宜直接比较。')
        elif pg is not None and rg is not None:
            if pg<=-10 or (dg is not None and dg<=-10) or rg<=-10: label='承压'
            elif rg>=5 and pg>=10 and dg is not None and dg>=0 and (olddeduct is None or olddeduct>0): label='向好'
            else: label='平稳'
    if rg is not None: reasons.append(f'累计营收同比{rg:+.2f}%，'+('收入规模扩张。' if rg>0 else '收入规模收缩。' if rg<0 else '收入基本持平。'))
    if pg is not None and label!='扭亏': reasons.append(f'累计归母净利润同比{pg:+.2f}%。')
    if dg is not None: reasons.append(f'扣非归母净利润同比{dg:+.2f}%，'+('主营盈利指标增长。' if dg>0 else '主营盈利指标回落。'))
    if profit and profit>0 and deduct is not None:
        gap=(profit-deduct)/profit
        if gap>0.2: risks.append(f'归母与扣非利润差额占归母利润{gap*100:.1f}%，需核对非经常性损益影响。')
    ratio=None
    if financial: reasons.append('金融行业现金流结构特殊，不采用经营现金流/归母利润评价盈利质量。')
    elif ocf is not None and profit is not None and profit>0:
        ratio=ocf/profit
        reasons.append(f'经营现金流净额/归母净利润约{ratio:.2f}倍（合并现金流与归母利润口径存在差异）。')
        if ratio<0: risks.append('利润为正但经营现金流为负，需关注回款和营运资金占用。')
        elif ratio<0.8: risks.append('经营现金流低于归母利润的0.8倍，建议核对季节性与回款节奏。')
    elif not financial: reasons.append('同报告期现金流或利润数据不足，暂不判断现金支撑。')
    if not risks: risks.append('本规则未触发额外风险项；仍需核对公告中的一次性收益、债务与分红安排。')
    return dict(status='ok' if label!='数据不足' else 'incomplete',label=label,reportDate=row['REPORT_DATE'][:10],noticeDate=(row.get('NOTICE_DATE') or '')[:10],industry=row.get('INDUSTRY_NAME') or '未分类',revenue=revenue,profit=profit,deductProfit=deduct,revenueGrowth=rg,profitGrowth=pg,deductGrowth=dg,operatingCashFlow=ocf,cashProfitRatio=round(ratio,4) if ratio is not None else None,financialSector=financial,analysis=reasons,risks=risks)

def enrich_fundamentals(stocks, as_of, fetch):
    latest,previous=quarter_dates(as_of)
    known=f'(NOTICE_DATE<=\'{as_of} 23:59:59\')(REPORT_DATE<=\'{as_of}\')(SECURITY_TYPE_CODE="058001001")'
    columns='SECURITY_CODE,INDUSTRY_NAME,REPORT_DATE,NOTICE_DATE,TOTAL_OPERATE_INCOME,OPERATE_INCOME,PARENT_NETPROFIT,DEDUCT_PARENT_NETPROFIT,TOI_RATIO,PARENT_NETPROFIT_RATIO,DPN_RATIO'
    groups={}
    for period in [latest,previous]:
        rows=report_rows(fetch,'RPT_DMSK_FN_INCOME',f'(REPORT_DATE=\'{period}\')'+known,columns)
        groups[period]=defaultdict(list)
        for row in rows: groups[period][row.get('INDUSTRY_NAME') or '未分类'].append(row)
    codes=','.join('"'+s['code']+'"' for s in stocks)
    cutoff=str(date.fromisoformat(previous)-timedelta(days=370))
    condition=f'(SECURITY_CODE in ({codes}))(REPORT_DATE>=\'{cutoff}\')'+known
    companies=report_rows(fetch,'RPT_DMSK_FN_INCOME',condition,columns)
    cashflows=report_rows(fetch,'RPT_DMSK_FN_CASHFLOW',f'(SECURITY_CODE in ({codes}))(REPORT_DATE>=\'{previous}\')'+known,'SECURITY_CODE,REPORT_DATE,NETCASH_OPERATE')
    by_company=defaultdict(list)
    for row in companies: by_company[row['SECURITY_CODE']].append(row)
    cash_lookup={(r['SECURITY_CODE'],r['REPORT_DATE'][:10]):r for r in cashflows}
    for stock in stocks:
        rows=sorted(by_company[stock['code']],key=lambda r:r['REPORT_DATE'],reverse=True)
        if not rows:
            stock['fundamentals']=dict(status='unavailable',label='待更新',industry='未分类');continue
        row=rows[0];period=row['REPORT_DATE'][:10]
        prior_date=str(int(period[:4])-1)+period[4:]
        prior=next((r for r in rows if r['REPORT_DATE'][:10]==prior_date),None)
        result=company_analysis(row,prior,cash_lookup.get((stock['code'],period)))
        industry=result['industry'];new=groups[latest].get(industry,[]);old=groups[previous].get(industry,[])
        sector=sector_summary(new,len(old))
        sector_date=latest
        if sector['label']=='样本不足' and old:
            sector=sector_summary(old,len(old));sector_date=previous
        sector.update(reportDate=sector_date,industry=industry,periodFallback=sector_date!=latest)
        result.update(sector=sector,checkedAt=as_of,source=f'https://data.eastmoney.com/bbsj/{stock["code"]}.html',method='累计财报同比规则分析，非投资评级；行业为全A股同分类、同报告期样本，非看板内样本。')
        stock['fundamentals']=result
    print(f'Financial coverage: {sum(s.get("fundamentals",{}).get("status")=="ok" for s in stocks)}/{len(stocks)}')
