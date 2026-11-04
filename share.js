/* Local canvas rendering: no screenshots, account details, or data uploads. */
(() => {
  const SITE='https://alexkaer.github.io/dividend-radar/';
  const COLORS={bg:'#080f16',panel:'#10212a',line:'#29434d',text:'#edf8f5',muted:'#8fa8b3',mint:'#7dfbd3',lime:'#dcff75',pink:'#ffa4b5'};
  let current=null,objectURL=null,version=0;
  const el=id=>document.getElementById(id);
  const n=(v,d=2)=>v==null||!Number.isFinite(Number(v))?'—':Number(v).toFixed(d);
  const pct=v=>v==null?'—':n(v)+'%';
  const dateText=v=>{const d=new Date(v);return Number.isNaN(d.getTime())?'待更新':d.toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false})};
  function painter(width,height){
    const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
    const c=canvas.getContext('2d');if(!c)throw Error('浏览器不支持图片生成');
    const font='"Noto Sans SC", "Microsoft YaHei", sans-serif';
    const text=(s,x,y,size=26,color=COLORS.text,bold=false,maxWidth)=>{c.font=`${bold?700:400} ${size}px ${font}`;c.fillStyle=color;c.textAlign='left';if(maxWidth==null)c.fillText(String(s??'—'),x,y);else c.fillText(String(s??'—'),x,y,maxWidth)};
    const box=(x,y,w,h,fill=COLORS.panel)=>{c.fillStyle=fill;c.fillRect(x,y,w,h);c.strokeStyle=COLORS.line;c.strokeRect(x+.5,y+.5,w-1,h-1)};
    const wrap=(s,x,y,width,size=25,color=COLORS.muted,maxLines=3)=>{c.font=`400 ${size}px ${font}`;const lines=[];let line='';for(const char of String(s??'')){if(c.measureText(line+char).width>width&&line){lines.push(line);line=char}else line+=char}if(line)lines.push(line);lines.slice(0,maxLines).forEach((l,i)=>text(i===maxLines-1&&lines.length>maxLines?l.slice(0,-1)+'…':l,x,y+i*size*1.55,size,color));return Math.min(lines.length,maxLines)*size*1.55};
    c.fillStyle=COLORS.bg;c.fillRect(0,0,width,height);
    c.strokeStyle='#162a32';for(let i=0;i<width;i+=48){c.beginPath();c.moveTo(i,0);c.lineTo(i,height);c.stroke()}for(let i=0;i<height;i+=48){c.beginPath();c.moveTo(0,i);c.lineTo(width,i);c.stroke()}
    c.fillStyle=COLORS.mint;c.fillRect(48,48,7,48);
    text('息壤  /  DIVIDEND RADAR',76,83,28,COLORS.mint,true);
    text('A-SHARE · CASH FLOW SIGNALS',76,119,17,COLORS.muted);
    return {canvas,c,text,box,wrap};
  }
  function stockPoster(stock,snapshot){
    const {canvas,c,text,box,wrap}=painter(1080,1660), f=stock.fundamentals,t=stock.technical;
    text(stock.name,64,215,64,COLORS.text,true,780);
    text(stock.code+' / '+stock.market,66,262,26,COLORS.muted);
    text(stock.ownership?.category==='待核实'?'国资背景待核实':stock.ownership?.category||'国资背景待核实',680,260,25,COLORS.lime,true,330);
    text('滚动现金股息率',66,340,25,COLORS.muted);
    text(n(stock.yieldRate,3)+'%',60,455,108,COLORS.mint,true);
    text('近365天税前派息 / 最新价 · 非预期收益',68,500,22,COLORS.muted);
    const metrics=[['最新价','¥ '+n(stock.price)],['总市值',n(stock.cap/1e8,0)+' 亿'],['每股派息','¥ '+n(stock.cash,3)],['PE / TTM',n(stock.pe)]];
    metrics.forEach(([label,value],i)=>{const x=64+i*242;box(x,540,224,120);text(label,x+18,579,21,COLORS.muted);text(value,x+18,630,32,COLORS.text,true,190)});
    ['daily','weekly'].forEach((period,i)=>{const b=t?.[period],x=64+i*486;box(x,688,468,169);text(i?'周线 BOLL':'日线 BOLL',x+22,728,22,COLORS.muted);text(b?.position||'待更新',x+22,784,37,COLORS.lime,true);text('趋势 '+(b?.trend||'待更新'),x+180,782,27,COLORS.text,true);text(b?b.location+(i&&t.weeklyPartial?' · 本周未完成':''):'历史行情不足或暂不可用',x+22,829,21,COLORS.muted, false,425)});
    text('BOLL(20,2) · 前复权 · 中轨斜率判趋势 · 截至 '+(t?.asOf||'待更新')+(t?.status!=='ok'?' / 数据不齐':''),64,896,19,COLORS.muted);
    box(64,932,952,340);text((f?.industry||'行业待更新')+' / 行业'+(f?.sector?.label||'待更新'),86,980,27,COLORS.mint,true,890);
    text('公司业绩：'+(f?.label||'待更新')+'  ·  报告期 '+(f?.reportDate||'待更新'),86,1028,27,COLORS.text,true,890);
    text('营收同比 '+pct(f?.revenueGrowth)+'    归母同比 '+pct(f?.profitGrowth),86,1078,25,COLORS.text,false,890);
    text('扣非同比 '+pct(f?.deductGrowth)+'    行业报告期 '+(f?.sector?.reportDate||'待更新'),86,1124,22,COLORS.muted,false,890);
    wrap(f?.analysis?.[0]||'财报分析暂不可用。',86,1172,888,23,COLORS.muted,2);
    wrap(f?.risks?.[0]||'财报标签为规则分析，需结合公告复核。',68,1318,944,23,COLORS.pink,2);
    text('行情 '+dateText(stock.quoteTime*1000)+' CST',64,1435,21,COLORS.text);
    text('快照生成 '+dateText(snapshot.updatedAt)+' CST',64,1474,20,COLORS.muted);
    text('数据：东方财富 / 腾讯证券 · 标签为规则分析，非投资评级',64,1528,20,COLORS.muted);
    text('股息率不代表未来收益；国资参股不等于国资控股。',64,1564,20,COLORS.muted);
    c.fillStyle=COLORS.mint;c.fillRect(64,1590,952,2);text(SITE,64,1630,22,COLORS.mint);
    return canvas;
  }
  function boardPoster(stocks,snapshot){
    const height=560+stocks.length*92,{canvas,c,text,box}=painter(1440,height);
    text('红利信号池',64,213,62,COLORS.text,true);text(stocks.length+' 只 / 当前筛选结果',900,207,29,COLORS.lime,true);
    text('股息率 > 5%  ·  总市值 > 500亿元  ·  行情 '+dateText(snapshot.quoteAt*1000)+' CST',64,276,25,COLORS.muted);
    const periods=[...new Set(stocks.map(s=>s.fundamentals?.reportDate).filter(Boolean))];
    text('公司财报期 '+(periods.length===1?periods[0]:'各股最新已披露报告期，详见看板')+'  ·  国资与业绩标签均附依据',64,318,22,COLORS.muted);
    box(64,352,1312,52);['股票 / 国资','股息率','市值/亿','日BOLL / 周BOLL','日趋势 / 周趋势','行业 / 公司业绩'].forEach((v,i)=>text(v,[82,365,515,660,867,1090][i],386,20,COLORS.mint));
    stocks.forEach((s,i)=>{const y=412+i*92;if(i%2===0){c.fillStyle='#10212ae6';c.fillRect(64,y-3,1312,89)}text(s.name,82,y+29,26,COLORS.text,true,263);text(s.code+' · '+(s.ownership?.category||'待核实'),82,y+62,18,COLORS.muted,false,263);text(pct(s.yieldRate),365,y+37,28,COLORS.mint,true);text(n(s.cap/1e8,0),515,y+37,24);text((s.technical?.daily?.position||'—')+' / '+(s.technical?.weekly?.position||'—'),660,y+37,24);text((s.technical?.daily?.trend||'—')+' / '+(s.technical?.weekly?.trend||'—'),867,y+37,23);text(s.fundamentals?.industry||'待更新',1090,y+27,20,COLORS.muted,false,260);text((s.fundamentals?.sector?.label||'—')+' / '+(s.fundamentals?.label||'—'),1090,y+61,22,COLORS.text,false,260)});
    const bottom=416+stocks.length*92;text('BOLL(20,2)前复权，周线含本周已交易日。财报标签为规则分析，非投资评级。',64,bottom+25,20,COLORS.muted);
    text('数据：东方财富 / 腾讯证券 · 股息率非预期收益 · 快照 '+dateText(snapshot.updatedAt)+' CST',64,bottom+62,19,COLORS.muted);
    text(SITE,64,bottom+108,25,COLORS.mint);return canvas;
  }
  function blob(canvas){return new Promise((resolve,reject)=>canvas.toBlob(b=>b?resolve(b):reject(Error('图片生成失败，请重试')),'image/png'))}
  function cleanup(){if(objectURL)URL.revokeObjectURL(objectURL);objectURL=null;current=null;el('shareImage').removeAttribute('src');el('downloadShare').removeAttribute('href')}
  async function generate(stocks,snapshot,single){
    if(!stocks?.length)return;
    const request=++version;cleanup();el('shareTitle').textContent=single?stocks[0].name+' · 分享图片':'当前筛选 · 分享图片';el('shareStatus').textContent='正在生成高清图片…';el('shareImage').hidden=true;el('downloadShare').hidden=true;el('nativeShare').hidden=true;
    if(!el('shareDialog').open)el('shareDialog').showModal();
    try{
      // Allow the loading state to paint before synchronous canvas work.
      await new Promise(resolve=>requestAnimationFrame(resolve));
      if(document.fonts)await Promise.race([document.fonts.ready,new Promise(resolve=>setTimeout(resolve,1200))]);
      if(request!==version)return;
      const canvas=single?stockPoster(stocks[0],snapshot):boardPoster(stocks,snapshot);
      const png=await blob(canvas);if(request!==version)return;
      const filename=`息壤-${single?stocks[0].code:'红利看板-'+stocks.length+'只'}-${snapshot.windowEnd}.png`;
      current=new File([png],filename,{type:'image/png'});objectURL=URL.createObjectURL(png);
      el('shareImage').src=objectURL;el('shareImage').alt=single?`${stocks[0].name}红利数据分享卡`:`当前筛选${stocks.length}只股票的红利看板分享图`;el('shareImage').hidden=false;
      el('downloadShare').href=objectURL;el('downloadShare').download=filename;el('downloadShare').hidden=false;
      el('nativeShare').hidden=!(navigator.canShare&&navigator.share&&navigator.canShare({files:[current]}));
      el('shareStatus').textContent='图片已生成，可保存 PNG；手机也可长按图片保存。';
    }catch(error){if(request===version)el('shareStatus').textContent='生成失败：'+error.message+'。请关闭后重试。'}
  }
  el('closeShare').onclick=()=>el('shareDialog').close();el('shareDialog').addEventListener('close',()=>{version++;cleanup()});
  el('nativeShare').onclick=async()=>{if(!current)return;try{await navigator.share({files:[current],title:el('shareTitle').textContent})}catch(error){if(error.name!=='AbortError')el('shareStatus').textContent='系统分享未完成，可改用“保存图片”。'}};
  window.dividendShare={stock:(stock,snapshot)=>generate([stock],snapshot,true),board:(stocks,snapshot)=>generate(stocks.slice(),snapshot,false)};
})();
