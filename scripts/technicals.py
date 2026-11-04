"""BOLL(20, 2), population standard deviation, on forward-adjusted closes."""
import json
import math
import statistics
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date


def weekly_closes(bars):
    weeks = {}
    for day, close in bars:
        weeks[date.fromisoformat(day).isocalendar()[:2]] = (day, close)
    return list(weeks.values())


def boll(bars, prefix):
    if len(bars) < 21:
        return None
    values = [v for _, v in bars]
    middle = statistics.mean(values[-20:])
    deviation = statistics.pstdev(values[-20:])
    upper, lower = middle + 2 * deviation, middle - 2 * deviation
    percent_b = (values[-1] - lower) / (upper - lower) if deviation else 0.5
    previous = statistics.mean(values[-21:-1])
    slope = (middle / previous - 1) * 100 if previous else 0
    trend = '向上' if slope > 0.1 else '向下' if slope < -0.1 else '走平'
    zone = prefix + ('上' if percent_b >= 0.8 else '下' if percent_b <= 0.2 else '中')
    location = '上轨之上' if percent_b > 1 else '下轨之下' if percent_b < 0 else '轨道内'
    return dict(asOf=bars[-1][0], close=values[-1], middle=round(middle, 4), upper=round(upper, 4), lower=round(lower, 4), percentB=round(percent_b, 4), position=zone, location=location, trend=trend, middleChangePct=round(slope, 4))


def calculate(bars, as_of):
    bars = sorted((d, float(v)) for d, v in bars if d <= as_of)
    if len({d for d, _ in bars}) != len(bars) or any(not math.isfinite(v) or v <= 0 for _, v in bars):
        raise ValueError('Invalid or duplicate history')
    daily, weekly = boll(bars, '日'), boll(weekly_closes(bars), '周')
    return dict(status='ok' if daily and weekly and bars[-1][0] == as_of else 'incomplete', asOf=bars[-1][0] if bars else None, daily=daily, weekly=weekly, weeklyPartial=bool(bars and date.fromisoformat(bars[-1][0]).weekday() < 4))


def history(stock, as_of):
    symbol = ('sh' if stock['market'] == '沪市' else 'bj' if stock['market'] == '北交所' else 'sz') + stock['code']
    query = urllib.parse.urlencode({'param': f'{symbol},day,,{as_of},320,qfq'})
    errors = []
    for base in ['https://web.ifzq.gtimg.cn/appstock/app/fqkline/get', 'https://proxy.finance.qq.com/ifzqgtimg/appstock/app/fqkline/get']:
        try:
            request = urllib.request.Request(base + '?' + query, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://gu.qq.com/'})
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.load(response)
            series = payload['data'][symbol]
            rows = series.get('qfqday') or series.get('day')
            if not rows:
                raise ValueError('Empty K-line history')
            result = calculate([(r[0], r[2]) for r in rows], as_of)
            result['source'] = '腾讯证券前复权日K；周K按ISO自然周聚合'
            stock['technical'] = result
            return
        except Exception as error:
            errors.append(str(error))
    stock['technical'] = dict(status='unavailable', asOf=None, daily=None, weekly=None, reason='历史行情暂不可用')
    print(f'BOLL unavailable {symbol}: {errors}')


def enrich_technicals(stocks, as_of):
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda stock: history(stock, as_of), stocks))
    print(f'BOLL coverage: {sum(s["technical"]["status"] == "ok" for s in stocks)}/{len(stocks)}')
