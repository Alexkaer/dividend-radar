/* Browser-side public data requests. No GitHub credentials or scheduled jobs. */
(() => {
  let serial=0;
  const A='m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048';
  const REPORT='https://datacenter-web.eastmoney.com/api/data/v1/get';
  const n=v=>v==null||v===''||v==='-'||!Number.isFinite(Number(v))?null:Number(v);
  const day=value=>new Date(value).toLocaleDateString('sv-SE',{timeZone:'Asia/Shanghai'});
  const ago=(d,count)=>new Date(Date.parse(d+'T12:00:00Z')-count*86400000).toISOString().slice(0,10);
  const sum=a=>a.reduce((s,x)=>s+x,0);
  const avg=a=>sum(a)/a.length;
  const med=a=>{a=a.filter(x=>x!=null&&Number.isFinite(x)).sort((x,y)=>x-y);return a.length?(a.length%2?a[(a.length-1)/2]:(a[a.length/2-1]+a[a.length/2])/2):null};
  const fixed=x=>Math.round(x*10000)/10000;
  function jsonp(url,params={},key='cb',timeout=18000){
    return new Promise((resolve,reject)=>{
      const callback='_radar_'+Date.now()+'_'+(++serial),script=document.createElement('script');
      const target=new URL(url);Object.entries({...params,[key]:callback,_:Date.now()}).forEach(([k,v])=>target.searchParams.set(k,v));
      let done=false;
      const finish=(error,data)=>{if(done)return;done=true;clearTimeout(timer);script.remove();window[callback]=()=>{};setTimeout(()=>delete window[callback],60000);error?reject(error):resolve(data)};
      const timer=setTimeout(()=>finish(Error('数据接口响应超时')),timeout);
      window[callback]=data=>finish(null,data);script.onerror=()=>finish(Error('数据接口加载失败'));script.src=target.href;script.async=true;document.head.append(script);
    });
  }
  async function request(url,params,key='cb'){
    const alternatives=url.includes('https://push2.eastmoney.com')?[url,url.replace('push2.eastmoney.com','push2delay.eastmoney.com')]:[url,url];
    let last;
    for(const address of alternatives){try{return await jsonp(address,params,key)}catch(error){last=error}}
    throw last;
  }
  async function pool(items,task,parallel=4){
    const result=new Array(items.length);let cursor=0;
    await Promise.all(Array.from({length:Math.min(parallel,items.length)},async()=>{while(cursor<items.length){const i=cursor++;result[i]=await task(items[i],i)}}));return result;
  }
  async function report(name,filter,columns='ALL'){
    const params={reportName:name,columns,filter,pageSize:500,pageNumber:1,sortColumns:'SECURITY_CODE,REPORT_DATE',sortTypes:'1,-1'};
    const get=async page=>{const d=await request(REPORT,{...params,pageNumber:page},'callback');if(!d.success||!d.result)throw Error(d.message||'财报接口返回异常');return d.result};
    const first=await get(1),rest=await pool(Array.from({length:first.pages-1},(_,i)=>i+2),get);
    const rows=[...first.data,...rest.flatMap(r=>r.data)];if(rows.length!==first.count)throw Error('财报分页不完整');return rows;
  }
  async function tencentQuotes(codes){
    const symbols=codes.map(code=>(code.startsWith('6')?'sh':/^[489]/.test(code)?'bj':'sz')+code);
    const response=await fetch('https://qt.gtimg.cn/q='+symbols.join(','),{signal:AbortSignal.timeout(10000)});
    if(!response.ok)throw Error('腾讯行情暂不可用');
    const body=new TextDecoder('gbk').decode(await response.arrayBuffer());
    const rows=[];
    for(const match of body.matchAll(/v_(?:sh|sz|bj)\d{6}="([^"]*)"/g)){
      const fields=match[1].split('~'),code=fields[2],stamp=fields[30];
      if(!codes.includes(code)||!(n(fields[3])>0)||!/^\d{14}$/.test(stamp))continue;
      const time=Date.parse(stamp.replace(/^(....)(..)(..)(..)(..)(..)$/,'$1-$2-$3T$4:$5:$6+08:00'))/1000;
      rows.push({f12:code,f13:code.startsWith('6')?1:0,f14:fields[1],f2:n(fields[3]),f3:n(fields[32]),
        f6:n(fields[37])==null?null:n(fields[37])*10000,f8:n(fields[38]),f20:n(fields[45])==null?null:n(fields[45])*1e8,
        f23:n(fields[47]),f115:n(fields[39]),f124:time});
    }
    if(!rows.length)throw Error('腾讯行情为空');
    return rows;
  }
  async function sinaQuotes(){
    const base='https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/';
    const get=async path=>{
      const response=await fetch(base+path,{signal:AbortSignal.timeout(10000)});
      if(!response.ok)throw Error('新浪行情暂不可用');
      return response.json();
    };
    const [total,benchmark]=await Promise.all([get('Market_Center.getHQNodeStockCount?node=hs_a'),tencentKline('1.000001',3,0)]);
    const date=benchmark.at(-1).date;
    const pages=await pool(Array.from({length:Math.ceil(Number(total)/100)},(_,i)=>i+1),
      page=>get('Market_Center.getHQNodeData?node=hs_a&num=100&sort=symbol&asc=1&page='+page),6);
    const rows=pages.flat();
    if(!rows.length||new Set(rows.map(r=>r.code)).size!==Number(total))throw Error('新浪行情分页不完整');
    return rows.map(r=>({f12:r.code,f13:r.symbol.startsWith('sh')?1:0,f14:r.name,f2:n(r.trade),f3:n(r.changepercent),
      f20:n(r.mktcap)==null?null:n(r.mktcap)*10000,f23:n(r.pb),f115:n(r.per),
      f124:Date.parse(date+'T'+r.ticktime+'+08:00')/1000,provider:'新浪'}));
  }
  async function tencentKline(secid,count,adjust){
    const [market,code]=secid.split('.'),symbol=(market==='1'?'sh':/^[489]/.test(code)&&code!=='899050'?'bj':'sz')+code;
    const url=new URL('https://web.ifzq.gtimg.cn/appstock/app/fqkline/get');
    url.searchParams.set('param',[symbol,'day','','',count,adjust?'qfq':''].join(','));
    const response=await fetch(url,{signal:AbortSignal.timeout(10000)});
    if(!response.ok)throw Error('腾讯日K暂不可用');
    const data=(await response.json()).data?.[symbol],rows=data?.qfqday||data?.day;
    if(!rows?.length)throw Error('腾讯日K为空');
    return rows.map((r,i)=>({date:r[0],close:n(r[2]),high:n(r[3]),amount:null,change:i?(Number(r[2])/Number(rows[i-1][2])-1)*100:null}));
  }
  window.RadarTencentQuotes=tencentQuotes;
  let quotePromise=null;
  function quotes(progress){
    if(quotePromise)return quotePromise;
    quotePromise=(async()=>{
      const get=async page=>{const d=(await request('https://push2.eastmoney.com/api/qt/clist/get',{pn:page,pz:100,np:1,fltt:2,invt:2,fid:'f12',po:1,fs:A,fields:'f12,f13,f14,f2,f3,f20,f23,f115,f124'})).data;if(!d?.diff)throw Error('行情接口返回空数据');return {...d,diff:Array.isArray(d.diff)?d.diff:Object.values(d.diff)}};
      const first=await get(1);let done=1;const pages=Math.ceil(first.total/100);progress?.('获取全市场行情 1/'+pages);
      const rest=await pool(Array.from({length:pages-1},(_,i)=>i+2),async page=>{const r=await get(page);progress?.('获取全市场行情 '+(++done)+'/'+pages);return r});
      const rows=[...first.diff,...rest.flatMap(r=>r.diff)];if(new Set(rows.map(r=>r.f12)).size!==first.total)throw Error('全市场行情分页不完整');return rows;
    })().catch(sinaQuotes);
    return quotePromise.finally(()=>{quotePromise=null});
  }
  async function kline(secid,count=320,adjust=0,requireAmount=false){
    try{
    const d=(await request('https://push2his.eastmoney.com/api/qt/stock/kline/get',{secid,klt:101,fqt:adjust,lmt:count,end:20500101,fields1:'f1,f2,f3,f4,f5,f6',fields2:'f51,f52,f53,f54,f55,f56,f57,f58,f59'})).data;
    if(!d?.klines?.length)throw Error('历史行情暂不可用');
    return d.klines.map(row=>{const r=row.split(',');return {date:r[0],close:Number(r[2]),amount:Number(r[6]),change:n(r[8])}});
    }catch(error){if(requireAmount)throw error;return tencentKline(secid,count,adjust);}
  }
  function boll(bars,prefix){
    if(bars.length<21)return null;
    const v=bars.map(r=>r.close),middle=avg(v.slice(-20)),deviation=Math.sqrt(avg(v.slice(-20).map(x=>(x-middle)**2))),upper=middle+2*deviation,lower=middle-2*deviation;
    const percentB=deviation?(v.at(-1)-lower)/(upper-lower):.5,previous=avg(v.slice(-21,-1)),slope=previous?(middle/previous-1)*100:0;
    return {asOf:bars.at(-1).date,close:v.at(-1),middle:fixed(middle),upper:fixed(upper),lower:fixed(lower),percentB:fixed(percentB),position:prefix+(percentB>=.8?'上':percentB<=.2?'下':'中'),location:percentB>1?'上轨之上':percentB<0?'下轨之下':'轨道内',trend:slope>.1?'向上':slope<-.1?'向下':'走平',middleChangePct:fixed(slope)};
  }
  function technical(bars,asOf){
    bars=bars.filter(r=>r.date<=asOf).sort((a,b)=>a.date.localeCompare(b.date));const weeks=new Map();
    for(const r of bars){const d=new Date(r.date+'T12:00:00Z');d.setUTCDate(d.getUTCDate()-(d.getUTCDay()+6)%7);weeks.set(d.toISOString().slice(0,10),r)}
    const daily=boll(bars,'日'),weekly=boll([...weeks.values()],'周');return {status:daily&&weekly&&bars.at(-1)?.date===asOf?'ok':'incomplete',asOf:bars.at(-1)?.date||null,daily,weekly,weeklyPartial:new Date(asOf+'T12:00:00Z').getUTCDay()!==5,source:'东方财富前复权日K；周线自然周聚合'};
  }
  async function ownership(stocks){
    const codes=stocks.map(s=>'"'+s.code+'"').join(','),base='https://datacenter.eastmoney.com/securities/api/data/v1/get';
    const d=await request(base,{reportName:'RPT_F10_ORG_BASICINFO',columns:'SECURITY_CODE,ORG_FORM,REAL_CONTROLER,CONTROL_HOLDER',filter:`(SECURITY_CODE in (${codes}))`,pageSize:500},'callback');if(!d.result?.data)throw Error('企业性质暂不可用');
    const map=new Map(d.result.data.map(r=>[r.SECURITY_CODE,r]));
    for(const s of stocks){const r=map.get(s.code)||{},nature=r.ORG_FORM||'待核实',controller=r.REAL_CONTROLER||'未披露';let category='待核实';
      if(nature.includes('中央金融'))category='中央金融国企';else if(/中央国有|央企/.test(nature))category='央企';else if(nature.includes('地方国有'))category='地方国企';else if(nature.includes('国有'))category='国资企业';else if(/国有资产监督管理|人民政府|财政部|财政厅|财政局/.test(controller))category='国资背景';
      s.ownership={category,nature,controller,holder:r.CONTROL_HOLDER||'未披露',checkedAt:new Date().toISOString(),source:'https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/Index?type=web&code='+(s.market==='沪市'?'SH':s.market==='北交所'?'BJ':'SZ')+s.code};}
    const unknown=stocks.filter(s=>s.ownership.category==='待核实');if(!unknown.length)return;
    const h=await request(base,{reportName:'RPT_F10_EH_HOLDERS',columns:'SECURITY_CODE,END_DATE,HOLDER_NAME,HOLD_NUM_RATIO,HOLDER_RANK',filter:`(SECURITY_CODE in (${unknown.map(s=>'"'+s.code+'"').join(',')}))`,pageSize:500,sortColumns:'END_DATE,HOLDER_RANK',sortTypes:'-1,1'},'callback');
    if(!h.result?.data)throw Error('国资参股核验暂不可用');
    for(const s of unknown){const rows=h.result.data.filter(r=>r.SECURITY_CODE===s.code);if(!rows.length)continue;const date=rows.map(r=>r.END_DATE).sort().at(-1);const matched=rows.filter(r=>r.END_DATE===date&&/中央汇金|中国证券金融|国有资产监督管理|财政厅|财政局|珠海格力集团|珠海格力金融投资|中国国新控股|中国诚通控股/.test(r.HOLDER_NAME));if(matched.length)Object.assign(s.ownership,{category:'国资参股',shareholderEvidence:matched.map(r=>({name:r.HOLDER_NAME,ratio:r.HOLD_NUM_RATIO,date:r.END_DATE.slice(0,10)}))})}
  }
  function quarters(asOf){const y=Number(asOf.slice(0,4)),ends=[];for(let year=y-2;year<=y;year++)for(const md of ['03-31','06-30','09-30','12-31'])if(`${year}-${md}`<=asOf)ends.push(`${year}-${md}`);return ends.slice(-2).reverse()}
  function sectorSummary(rows,baseline){
    const revenues=rows.map(r=>n(r.TOI_RATIO)),profits=rows.filter(r=>n(r.PARENT_NETPROFIT)>0&&n(r.PARENT_NETPROFIT_RATIO)!=null&&n(r.PARENT_NETPROFIT_RATIO)>-100).map(r=>n(r.PARENT_NETPROFIT_RATIO));
    const valid=rows.map(r=>n(r.PARENT_NETPROFIT)).filter(x=>x!=null),share=valid.length?valid.filter(x=>x>0).length/valid.length:null,rg=med(revenues),pg=med(profits),coverage=baseline?rows.length/baseline:1;let label='样本不足';
    if(rows.length>=3&&coverage>=.7&&profits.length>=Math.max(2,rows.length*.3)&&rg!=null&&pg!=null)label=rg>=5&&pg>=10&&share>=.7?'向好':(rg<0&&pg<0)||pg<=-10||share<.6?'承压':'分化';
    return {label,samples:rows.length,baselineSamples:baseline,coverage,revenueGrowthMedian:rg,profitGrowthMedian:pg,profitGrowthSamples:profits.length,profitableShare:share};
  }
  function company(row,prior,cash){
    const revenue=n(row.TOTAL_OPERATE_INCOME)??n(row.OPERATE_INCOME),profit=n(row.PARENT_NETPROFIT),deduct=n(row.DEDUCT_PARENT_NETPROFIT),rg=n(row.TOI_RATIO),pg=n(row.PARENT_NETPROFIT_RATIO),dg=n(row.DPN_RATIO),oldprofit=n(prior?.PARENT_NETPROFIT),olddeduct=n(prior?.DEDUCT_PARENT_NETPROFIT),financial=/银行|保险|证券|多元金融/.test(row.INDUSTRY_NAME||''),ocf=n(cash?.NETCASH_OPERATE);let label='数据不足',ratio=null;const analysis=[],risks=[];
    if(profit!=null){if(profit<0){label='亏损';risks.push('本期归母净利润为负，需关注盈利修复与分红持续性。')}else if(oldprofit!=null&&oldprofit<0){label='扭亏';analysis.push('归母净利润由上年同期亏损转为盈利，低基数同比不宜直接比较。')}else if(pg!=null&&rg!=null)label=pg<=-10||(dg!=null&&dg<=-10)||rg<=-10?'承压':rg>=5&&pg>=10&&dg!=null&&dg>=0&&(olddeduct==null||olddeduct>0)?'向好':'平稳'}
    if(rg!=null)analysis.push(`累计营收同比${rg>=0?'+':''}${rg.toFixed(2)}%，${rg>0?'收入规模扩张。':rg<0?'收入规模收缩。':'收入基本持平。'}`);
    if(pg!=null&&label!=='扭亏')analysis.push(`累计归母净利润同比${pg>=0?'+':''}${pg.toFixed(2)}%。`);
    if(dg!=null)analysis.push(`扣非归母净利润同比${dg>=0?'+':''}${dg.toFixed(2)}%。`);
    if(pg>=100)risks.push('同比利润增速较高，需核对上年同期基数，不宜直接外推。');
    if(profit>0&&deduct!=null&&(profit-deduct)/profit>.2)risks.push(`归母与扣非利润差额占归母利润${((profit-deduct)/profit*100).toFixed(1)}%，需核对非经常性损益。`);
    if(financial)analysis.push('金融行业现金流结构特殊，不采用经营现金流/归母利润评价盈利质量。');else if(ocf!=null&&profit>0){ratio=ocf/profit;analysis.push(`经营现金流净额/归母净利润约${ratio.toFixed(2)}倍，合并与归母口径存在差异。`);if(ratio<0)risks.push('利润为正但经营现金流为负，需关注回款和营运资金占用。');else if(ratio<.8)risks.push('经营现金流低于归母利润的0.8倍，建议核对季节性与回款节奏。')}else analysis.push('同报告期现金流或利润数据不足，暂不判断现金支撑。');
    if(!risks.length)risks.push('本规则未触发额外风险项，仍需核对一次性收益、债务与分红安排。');
    return {status:label==='数据不足'?'incomplete':'ok',label,reportDate:row.REPORT_DATE.slice(0,10),noticeDate:(row.NOTICE_DATE||'').slice(0,10),industry:row.INDUSTRY_NAME||'未分类',revenue,profit,deductProfit:deduct,revenueGrowth:rg,profitGrowth:pg,deductGrowth:dg,operatingCashFlow:ocf,cashProfitRatio:ratio,financialSector:financial,analysis,risks};
  }
  async function fundamentals(stocks,progress){
    const asOf=day(Date.now()),[latest,previous]=quarters(asOf),known=`(NOTICE_DATE<='${asOf} 23:59:59')(REPORT_DATE<='${asOf}')(SECURITY_TYPE_CODE="058001001")`,columns='SECURITY_CODE,INDUSTRY_NAME,REPORT_DATE,NOTICE_DATE,TOTAL_OPERATE_INCOME,OPERATE_INCOME,PARENT_NETPROFIT,DEDUCT_PARENT_NETPROFIT,TOI_RATIO,PARENT_NETPROFIT_RATIO,DPN_RATIO',codes=stocks.map(s=>'"'+s.code+'"').join(',');
    progress?.('正在刷新财报与全市场同行样本…');
    const [recent,old,companies,cashes]=await Promise.all([report('RPT_DMSK_FN_INCOME',`(REPORT_DATE='${latest}')`+known,columns),report('RPT_DMSK_FN_INCOME',`(REPORT_DATE='${previous}')`+known,columns),report('RPT_DMSK_FN_INCOME',`(SECURITY_CODE in (${codes}))(REPORT_DATE>='${ago(previous,370)}')`+known,columns),report('RPT_DMSK_FN_CASHFLOW',`(SECURITY_CODE in (${codes}))(REPORT_DATE>='${previous}')`+known,'SECURITY_CODE,REPORT_DATE,NETCASH_OPERATE')]);
    for(const s of stocks){const rows=companies.filter(r=>r.SECURITY_CODE===s.code).sort((a,b)=>b.REPORT_DATE.localeCompare(a.REPORT_DATE));if(!rows.length){s.fundamentals={status:'unavailable',label:'待更新',industry:'未分类'};continue}const row=rows[0],p=row.REPORT_DATE.slice(0,10),prior=rows.find(r=>r.REPORT_DATE.slice(0,10)===String(Number(p.slice(0,4))-1)+p.slice(4)),cash=cashes.find(r=>r.SECURITY_CODE===s.code&&r.REPORT_DATE.slice(0,10)===p),f=company(row,prior,cash),newPeers=recent.filter(r=>r.INDUSTRY_NAME===f.industry),oldPeers=old.filter(r=>r.INDUSTRY_NAME===f.industry);let sector=sectorSummary(newPeers,oldPeers.length),period=latest;if(sector.label==='样本不足'&&oldPeers.length){sector=sectorSummary(oldPeers,oldPeers.length);period=previous}f.sector={...sector,reportDate:period,industry:f.industry,periodFallback:period!==latest};Object.assign(f,{checkedAt:asOf,source:'https://data.eastmoney.com/bbsj/'+s.code+'.html',method:'累计财报同比规则分析，非投资评级；同行取全A股同分类、同报告期。'});s.fundamentals=f;}
  }
  async function refreshStocks(seed,progress){
    try{return await refreshFullStocks(seed,progress);}
    catch(error){
      if(!seed?.stocks?.length)throw error;
      progress?.('正在用腾讯行情更新已有红利名单…');
      const codes=seed.stocks.map(stock=>stock.code),batches=[];
      for(let i=0;i<codes.length;i+=50)batches.push(codes.slice(i,i+50));
      const rows=(await pool(batches,async batch=>tencentQuotes(batch).catch(()=>[]))).flat();
      const latest=new Map(rows.map(row=>[row.f12,row]));
      let updated=0;
      const stocks=seed.stocks.map(stock=>{
        const quote=latest.get(stock.code);
        if(!quote||quote.f124<(stock.quoteTime||0)||!Number.isFinite(stock.cash))return stock;
        updated++;
        return {...stock,price:quote.f2,change:quote.f3,quoteTime:quote.f124,
          yieldRate:fixed(stock.cash/quote.f2*100),pe:quote.f115??stock.pe,
          pb:quote.f23??stock.pb,cap:quote.f20??stock.cap};
      });
      if(!updated)throw Error('暂未取得可用的腾讯行情');
      return {...seed,stocks,quoteAt:Math.max(...stocks.map(stock=>stock.quoteTime||0)),source:'腾讯公开行情',
        warnings:[`腾讯已更新 ${updated}/${stocks.length} 只；分红统计截至 ${seed.windowEnd||'原快照日期'}，沿用原名单`]};
    }
  }
  async function refreshFullStocks(seed,progress){
    const all=await quotes(progress),valid=all.filter(q=>n(q.f2)>0&&n(q.f20)>50e9),stamp=Math.max(...valid.map(q=>n(q.f124)||0));if(!stamp)throw Error('行情时间无效');
    const asOf=day(stamp*1000),start=ago(asOf,365);progress?.('正在刷新近一年现金分红…');
    const dividends=await report('RPT_SHAREBONUS_DET',`(EX_DIVIDEND_DATE>'${start}')(EX_DIVIDEND_DATE<='${asOf}')(ASSIGN_PROGRESS="实施分配")`);
    const sums=new Map();for(const r of dividends){if(n(r.PRETAX_BONUS_RMB)>0){if(!sums.has(r.SECURITY_CODE))sums.set(r.SECURITY_CODE,[]);sums.get(r.SECURITY_CODE).push({date:r.EX_DIVIDEND_DATE.slice(0,10),cash:r.PRETAX_BONUS_RMB/10,plan:r.IMPL_PLAN_PROFILE})}}
    const stocks=[];for(const q of valid){const records=sums.get(q.f12)||[],cash=sum(records.map(r=>r.cash)),rate=cash/q.f2*100;if(rate>5)stocks.push({code:q.f12,name:q.f14,market:q.f13===1?'沪市':/^[489]/.test(q.f12)?'北交所':'深市',price:q.f2,change:n(q.f3),yieldRate:fixed(rate),cash:fixed(cash),pe:n(q.f115),pb:n(q.f23),cap:n(q.f20),quoteTime:n(q.f124),dividends:records})}
    if(!stocks.length)throw Error('筛选结果异常为空，保留原快照');stocks.sort((a,b)=>b.yieldRate-a.yieldRate);
    const warnings=[];let done=0;
    await Promise.all([
      ownership(stocks).catch(()=>warnings.push('国资资料刷新失败')),
      fundamentals(stocks,progress).catch(()=>warnings.push('财报刷新失败')),
      pool(stocks,async s=>{try{s.technical=technical(await kline((s.market==='沪市'?'1.':s.market==='北交所'?'0.':'0.')+s.code,320,1),asOf)}catch{s.technical={status:'unavailable',asOf:null,daily:null,weekly:null};warnings.push(s.name+' BOLL暂不可用')}progress?.('历史指标 '+(++done)+'/'+stocks.length);})
    ]);
    const prior=new Map((seed?.stocks||[]).map(s=>[s.code,s]));for(const s of stocks){if(!s.fundamentals){s.fundamentals=prior.get(s.code)?.fundamentals||{status:'unavailable',label:'待更新',industry:'待更新'};s.fundamentals={...s.fundamentals,cached:true}}if(!s.ownership){s.ownership=prior.get(s.code)?.ownership||{category:'待核实'};s.ownership={...s.ownership,cached:true}}}
    return {updatedAt:new Date().toISOString(),windowStart:start,windowEnd:asOf,quoteAt:stamp,universe:all.length,dividendRecords:dividends.length,source:all.some(q=>q.provider==='新浪')?'新浪行情 · 东方财富分红及财报':'东方财富浏览器直连行情、历史K线及财报',method:seed?.method||'近365天已除息税前每股派息之和÷最新价；未对期间股本变动调整，特殊公司须复核。',stocks,warnings:[...new Set(warnings)],live:true};
  }
  const INDEX=[['1.000001','上证指数'],['0.399001','深证成指'],['0.399006','创业板指'],['1.000688','科创50'],['1.000300','沪深300'],['0.899050','北证50'],['1.000016','上证50'],['1.000905','中证500']];
  async function limits(asOf){const result={};for(const [key,endpoint] of [['up','getTopicZTPool'],['down','getTopicDTPool']]){const d=(await request('https://push2ex.eastmoney.com/'+endpoint,{ut:'7eea3edcaed734bea9cbfc24409ed989',dpt:'wz.ztzt',Pageindex:0,pagesize:1000,sort:key==='up'?'fbt:asc':'fund:asc',date:asOf.replaceAll('-','')})).data;if(!d||String(d.qdate)!==asOf.replaceAll('-',''))throw Error('涨跌停股池日期不匹配');result[key]=d.tc}return {...result,scope:'东方财富涨跌停股池收录数，并非全A股统一口径，ST、北交所等范围可能与软件不同。'}}
  async function sectors(asOf){
    const get=async page=>{const d=(await request('https://push2.eastmoney.com/api/qt/clist/get',{pn:page,pz:100,np:1,fltt:2,fid:'f109',po:1,fs:'m:90+t:2',fields:'f12,f14,f3,f109,f124'})).data;if(!d?.diff)throw Error('板块行情暂不可用');return {...d,diff:Array.isArray(d.diff)?d.diff:Object.values(d.diff)}};
    const first=await get(1),rest=await pool(Array.from({length:Math.ceil(first.total/100)-1},(_,i)=>i+2),get),rows=[...first.diff,...rest.flatMap(x=>x.diff)];if(new Set(rows.map(r=>r.f12)).size!==first.total)throw Error('板块分页不完整');
    const history=new Map();const getBars=code=>{if(!history.has(code))history.set(code,kline('90.'+code,8));return history.get(code)};
    const top=rows.filter(r=>n(r.f109)!=null).sort((a,b)=>b.f109-a.f109).slice(0,15),daily=rows.filter(r=>n(r.f3)!=null).sort((a,b)=>b.f3-a.f3).slice(0,15);
    const verify=async(r,period)=>{const bars=(await getBars(r.f12)).filter(b=>b.date<=asOf);if(bars.length<period+1||bars.at(-1).date!==asOf)throw Error('板块历史日期不匹配');const value=(bars.at(-1).close/bars.at(-period-1).close-1)*100,reference=period===1?r.f3:r.f109;if(Math.abs(value-reference)>.08)throw Error('板块涨幅核验不符');return {code:r.f12,name:r.f14,change:period===1?fixed(value):n(r.f3),fiveDayChange:period===5?fixed(value):null,startDate:bars.at(-period-1).date,endDate:bars.at(-1).date}};
    const [items,todayItems]=await Promise.all([pool(top,r=>verify(r,5)),pool(daily,r=>verify(r,1))]);
    return {items,todayItems,universe:first.total,scope:'东方财富全部行业层级，存在成分重叠；当日与最近5个交易日榜各取前15，均已用日K核对。'};
  }

  async function refreshMarket(seed,progress){
    try{return await refreshFullMarket(seed,progress);}
    catch(error){
      if(!seed)throw error;
      const [all,histories]=await Promise.all([sinaQuotes(),Promise.allSettled(INDEX.map(async ([secid,name])=>{
        const bar=(await tencentKline(secid,3,0)).at(-1);
        return {...bar,code:secid.split('.')[1],name};
      }))]);
      const indices=histories.flatMap(r=>r.status==='fulfilled'?[r.value]:[]);
      const asOf=indices.find(r=>r.code==='000001')?.date;
      if(!asOf||asOf<seed.asOf)throw error;
      const changes=all.filter(q=>q.f2>0&&q.f3!=null&&q.f124&&day(q.f124*1000)===asOf).map(q=>q.f3);
      if(changes.length<4500)throw error;
      const up=changes.filter(v=>v>0).length,down=changes.filter(v=>v<0).length;
      return {...seed,asOf,updatedAt:new Date().toISOString(),session:'公开行情快照',
        indices:indices.filter(r=>r.date===asOf),
        breadth:{up,down,flat:changes.length-up-down,total:changes.length,advanceShare:up+down?up/(up+down):null},
        limits:{up:null,down:null,scope:'涨跌停池暂未核验'},
        sentiment:{label:'待判断',score:null,method:'涨跌停池暂未核验'},
        partialSource:'腾讯指数 · 新浪市场广度。成交额与行业榜沿用各自标注日期。'};
    }
  }
  async function refreshFullMarket(seed,progress){
    progress?.('正在获取指数和市场广度…');
    const [all,histories,sh,sz]=await Promise.all([quotes(progress),pool(INDEX,async item=>({item,bars:await kline(item[0],3)})),kline('1.000001',20,0,true),kline('0.399001',20,0,true)]);
    const asOf=sh.at(-1).date;if(sz.at(-1).date!==asOf)throw Error('沪深量能日期不匹配');
    const indices=histories.map(({item,bars})=>{const r=bars.filter(b=>b.date<=asOf).at(-1);if(r?.date!==asOf)throw Error('指数日期不匹配');return {code:item[0].split('.')[1],name:item[1],...r}});
    const changes=all.filter(q=>n(q.f2)>0&&n(q.f3)!=null&&day((n(q.f124)||0)*1000)===asOf).map(q=>q.f3);if(changes.length<4500)throw Error('同日广度行情覆盖不足');const up=changes.filter(v=>v>0).length,down=changes.filter(v=>v<0).length,breadth={up,down,flat:changes.length-up-down,total:changes.length,universe:all.length,advanceShare:up+down?up/(up+down):null};
    progress?.('正在核对涨跌停和行业当日、五日涨幅…');const [l,s]=await Promise.all([limits(asOf),sectors(asOf)]),days=sh.filter(r=>r.date<=asOf&&sz.some(b=>b.date===r.date)).slice(-10).map(r=>({date:r.date,shanghai:r.amount,shenzhen:sz.find(b=>b.date===r.date).amount,amount:r.amount+sz.find(b=>b.date===r.date).amount}));if(days.length!==10)throw Error('成交额窗口不足10个交易日');
    const recent=sum(days.slice(-5).map(r=>r.amount)),previous=sum(days.slice(0,5).map(r=>r.amount)),turnover={days,today:days.at(-1).amount,dayChangePct:(days.at(-1).amount/days.at(-2).amount-1)*100,fiveDayChangePct:(recent/previous-1)*100,recentFiveDayAverage:recent/5,previousFiveDayAverage:previous/5,scope:'沪深主指数成交额合计，不含北交所；盘中为截至抓取时的累计成交额，不能与完整交易日直接比较。'};
    const main=indices.filter(r=>['000001','399001'].includes(r.code)),score=breadth.advanceShare==null||!l.up&&!l.down?null:Math.round(100*(.6*breadth.advanceShare+.25*l.up/(l.up+l.down)+.15*Math.max(0,Math.min(1,.5+avg(main.map(r=>r.change))/6))));
    const label=score==null?'待判断':score>=75?'活跃':score>=55?'偏强':score>=45?'分歧':score>=25?'偏弱':'低迷',hour=Number(new Date().toLocaleTimeString('en-GB',{timeZone:'Asia/Shanghai',hour:'2-digit',hour12:false}));
    return {updatedAt:new Date().toISOString(),asOf,session:asOf===day(Date.now())&&hour<15?'盘中快照':'收盘快照',indices,breadth,limits:l,sentiment:{label,score,method:seed?.sentiment?.method||'60%上涨占比+25%涨停池占比+15%指数强弱分；规则描述，不预测未来。'},turnover,sectors:s,source:all.some(q=>q.provider==='新浪')?'新浪市场广度 · 东方财富市场统计':'东方财富浏览器直连行情与历史K线',live:true};
  }
  async function refreshHardware(definitions,progress){
    if(!definitions.length)return {updatedAt:new Date().toISOString(),stocks:[],warnings:[]};
    if(definitions.some(s=>!/^\d{6}$/.test(s.code)))throw Error('股票代码必须为6位数字');
    progress?.('正在刷新硬件AI行情…');
    const chunks=[];for(let i=0;i<definitions.length;i+=80)chunks.push(definitions.slice(i,i+80));
    let usedTencent=false;
    const batches=await pool(chunks,async list=>{try{const secids=list.map(s=>(s.code.startsWith('6')?'1.':'0.')+s.code).join(',');const d=(await request('https://push2.eastmoney.com/api/qt/ulist.np/get',{secids,fltt:2,fields:'f2,f3,f6,f8,f12,f13,f14,f20,f23,f115,f124'})).data;if(!d?.diff)throw Error('标的行情暂不可用');return Array.isArray(d.diff)?d.diff:Object.values(d.diff)}catch{usedTencent=true;return tencentQuotes(list.map(item=>item.code)).catch(()=>[]);}});
    const quotes=new Map(batches.flat().map(q=>[q.f12,q]));let profiles=[],warnings=[];
    try{const d=await request('https://datacenter.eastmoney.com/securities/api/data/v1/get',{reportName:'RPT_F10_ORG_BASICINFO',columns:'SECURITY_CODE,SECURITY_NAME_ABBR,MAIN_BUSINESS,ORG_PROFILE,BOARD_NAME_1LEVEL,BOARD_NAME_2LEVEL',filter:`(SECURITY_CODE in (${definitions.map(s=>'"'+s.code+'"').join(',')}))`,pageSize:500},'callback');if(!d.result?.data)throw Error();profiles=d.result.data}catch{warnings.push('公司主营资料暂不可用')}
    const byCode=new Map(profiles.map(p=>[p.SECURITY_CODE,p]));
    const stocks=definitions.map(item=>{const q=quotes.get(item.code),p=byCode.get(item.code);return {...item,nameVerified:q?.f14||item.name||item.code,market:item.code.startsWith('6')?'沪市':/^[489]/.test(item.code)?'北交所':'深市',price:n(q?.f2),change:n(q?.f3),amount:n(q?.f6),turnover:n(q?.f8),cap:n(q?.f20),pe:n(q?.f115),pb:n(q?.f23),quoteTime:n(q?.f124),industry:p?.BOARD_NAME_2LEVEL||p?.BOARD_NAME_1LEVEL||null,business:p?.MAIN_BUSINESS||p?.ORG_PROFILE||null,source:'https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/Index?type=web&code='+(item.code.startsWith('6')?'SH':/^[489]/.test(item.code)?'BJ':'SZ')+item.code,companyVerified:Boolean(p),available:Boolean(q?.f14)&&n(q?.f2)>0}});
    if(!stocks.some(s=>s.available))throw Error('未取得有效A股行情，请核对代码或稍后重试');
    return {updatedAt:new Date().toISOString(),source:usedTencent?'公开行情回退 · 腾讯行情与东方财富公司资料':'东方财富浏览器直连行情与公司资料',stocks,warnings,live:true};
  }
  async function hardwareOrders(stock){
    const announcement=async(url,params)=>{const target=new URL(url);Object.entries(params).forEach(([k,v])=>target.searchParams.set(k,v));const response=await fetch(target,{signal:AbortSignal.timeout(18000)});if(!response.ok)throw Error('公告服务响应 '+response.status);return response.json()};
    const d=await announcement('https://np-anotice-stock.eastmoney.com/api/security/ann',{sr:-1,page_size:60,page_index:1,ann_type:'A',client_source:'web',stock_list:stock.code,f_node:0,s_node:0});
    if(!d.success||!Array.isArray(d.data?.list))throw Error('公告接口暂不可用');
    const cutoff=ago(day(Date.now()),180),all=d.data.list.filter(r=>r.notice_date?.slice(0,10)>=cutoff),candidates=all.filter(r=>/重大合同|销售合同|经营合同|中标|订单|投资者关系活动|调研/.test(r.title)).slice(0,3),items=[];
    for(const row of candidates){try{const body=(await announcement('https://np-cnotice-stock.eastmoney.com/api/content/ann',{art_code:row.art_code,client_source:'web',page_index:1})).data;if(!body?.notice_content)continue;const excerpt=window.HardwareMetrics.orderExcerpt(body.notice_content);if(excerpt)items.push({title:row.title,date:row.notice_date.slice(0,10),excerpt,kind:/重大合同|销售合同|经营合同|中标/.test(row.title)?'合同类公告':'交流记录',url:'https://data.eastmoney.com/notices/detail/'+stock.code+'/'+row.art_code+'.html'});if(items.length>=2)break}catch{}}
    return {status:items.length?'found':'not-found',items,checkedAt:new Date().toISOString(),searched:all.length,scope:'最近180天内、最新60条公告，最多核对3份合同或交流记录；不代表已穷尽所有订单披露。',summary:items.length?(items.some(i=>i.kind==='合同类公告')?'发现合同类披露':'发现定性订单描述'):'本次检索未找到可引用订单描述'};
  }
  async function enrichHardwareLeaders(stocks,progress){
    const selected=stocks;if(!selected.length)return stocks;let done=0;
    const asOf=day(Date.now()),codes=selected.map(s=>'"'+s.code+'"').join(','),[latest,previous]=quarters(asOf),known=`(NOTICE_DATE<='${asOf} 23:59:59')(REPORT_DATE<='${asOf}')(SECURITY_TYPE_CODE="058001001")`,fields='SECURITY_CODE,INDUSTRY_NAME,REPORT_DATE,NOTICE_DATE,TOTAL_OPERATE_INCOME,OPERATE_INCOME,PARENT_NETPROFIT,DEDUCT_PARENT_NETPROFIT,TOI_RATIO,PARENT_NETPROFIT_RATIO,DPN_RATIO';
    const signalSession=kline('1.000001',5).then(bars=>window.HardwareMetrics.completedSession(bars)).catch(()=>null);
    const earnings=(async()=>{const [income,cash]=await Promise.all([report('RPT_DMSK_FN_INCOME',`(SECURITY_CODE in (${codes}))(REPORT_DATE>='${ago(previous,370)}')`+known,fields),report('RPT_DMSK_FN_CASHFLOW',`(SECURITY_CODE in (${codes}))(REPORT_DATE>='${previous}')`+known,'SECURITY_CODE,REPORT_DATE,NETCASH_OPERATE')]);for(const s of selected){const rows=income.filter(r=>r.SECURITY_CODE===s.code).sort((a,b)=>b.REPORT_DATE.localeCompare(a.REPORT_DATE));if(!rows.length){s.fundamentals={status:'unavailable',label:'待更新'};continue}const row=rows[0],period=row.REPORT_DATE.slice(0,10),prior=rows.find(r=>r.REPORT_DATE.slice(0,10)===String(Number(period.slice(0,4))-1)+period.slice(4));s.fundamentals={...company(row,prior,cash.find(r=>r.SECURITY_CODE===s.code&&r.REPORT_DATE.slice(0,10)===period)),checkedAt:asOf,source:'https://data.eastmoney.com/bbsj/'+s.code+'.html'}}})().catch(()=>{for(const s of selected)s.fundamentals={status:'unavailable',label:'待更新'}});
    await Promise.all([earnings,pool(selected,async s=>{const date=s.quoteTime?day(s.quoteTime*1000):asOf;try{const raw=(await request('https://push2his.eastmoney.com/api/qt/stock/kline/get',{secid:(s.code.startsWith('6')?'1.':'0.')+s.code,klt:101,fqt:1,lmt:100000,end:20500101,fields1:'f1,f2,f3,f4,f5,f6',fields2:'f51,f52,f53,f54,f55,f56,f57'})).data;s.history=window.HardwareMetrics.historicalHigh(raw,s.price,date);s.dailySignal=window.HardwareMetrics.dailySignal(raw,await signalSession)}catch{
      try{
        const rows=await tencentKline((s.code.startsWith('6')?'1.':'0.')+s.code,320,1);
        const raw={klines:rows.map(r=>[r.date,'',r.close,r.high].join(','))};
        s.history=window.HardwareMetrics.historicalHigh(raw,s.price,date);
        s.dailySignal=window.HardwareMetrics.dailySignal(raw,await signalSession);
      }catch{s.history={status:'unavailable'};s.dailySignal={status:'unavailable',matches:null,reason:'日K暂不可用'};}
    }try{s.orders=await hardwareOrders(s)}catch(error){s.orders=s.orders?.checkedAt?{...s.orders,cached:true}:{status:'unavailable',summary:'订单公告暂不可用',items:[]}}progress?.('高点、领涨与经营数据核验 '+(++done)+'/'+selected.length);},3)]);
    const ranks=window.HardwareMetrics.leaders(stocks);for(const s of stocks)s.leaderRank=ranks.get(s.code)||null;return stocks;
  }
  const cache={get(key){try{const v=JSON.parse(localStorage.getItem('radar-live-'+key));return v?.version===1?v.data:null}catch{return null}},put(key,data){try{localStorage.setItem('radar-live-'+key,JSON.stringify({version:1,data}))}catch{}}};
  window.RadarLive={refreshStocks,refreshMarket,refreshHardware,enrichHardwareLeaders,cache};
})();
