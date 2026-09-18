#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Exit Radar — máy chủ nội bộ + cầu nối CoinMarketCap API.

Vì sao phải có tệp này: CMC không gửi header Access-Control-Allow-Origin,
nên trình duyệt không thể gọi thẳng pro-api.coinmarketcap.com — đã kiểm
chứng bằng thực nghiệm. Tầng dữ liệu đi qua máy chủ chạy trên chính máy
người dùng: trình duyệt gọi 127.0.0.1, máy chủ gọi CMC.

Key CMC do trình duyệt gửi kèm mỗi request qua header X-CMC-Key và chỉ
đi tới 127.0.0.1 — không rời khỏi máy người dùng, đúng như cam kết trên
giao diện.

Chạy:  python3 exit_radar_server.py            # http://127.0.0.1:8787
       python3 exit_radar_server.py --selftest # quét thử, in JSON, thoát
"""
import json, os, sys, time, threading, urllib.error, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CMC_BASE  = os.environ.get('CMC_BASE', 'https://pro-api.coinmarketcap.com')
PUBLIC    = CMC_BASE + '/public-api'
PORT      = int(os.environ.get('PORT', '8787'))
CACHE_TTL = float(os.environ.get('CACHE_TTL', '60'))
ROOT      = os.path.dirname(os.path.abspath(__file__))
WINDOW_MS = 24 * 3600 * 1000
SWAP_PAGES = int(os.environ.get('SWAP_PAGES', '3'))

_cache, _calls = {}, []
_lock = threading.Lock()
STATS = {'cache_hit': 0, 'cache_miss': 0, 'calls': 0}


# ----------------------------------------------------------------- nền tảng
def _num(x):
    if x is None or isinstance(x, bool):
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _http(url, key=None, method='GET', body=None, timeout=25):
    hdr = {'Accept': 'application/json', 'User-Agent': 'exit-radar/1.0'}
    data = None
    if body is not None:
        data = json.dumps(body).encode('utf-8')
        hdr['Content-Type'] = 'application/json'
    if key:
        hdr['X-CMC_PRO_API_KEY'] = key
    req = urllib.request.Request(url, data=data, headers=hdr, method=method)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw, st = r.read().decode('utf-8', 'replace'), r.status
    except urllib.error.HTTPError as e:
        raw, st = e.read().decode('utf-8', 'replace'), e.code
    except Exception as e:
        return {'status': 0, 'ms': int((time.time() - t0) * 1000),
                'json': None, 'error': str(e)}
    ms = int((time.time() - t0) * 1000)
    try:
        js = json.loads(raw)
    except ValueError:
        js = None
    return {'status': st, 'ms': ms, 'json': js, 'error': None}


def cmc(path, params=None, key=None, cache=True, method='GET', body=None):
    """Gọi một endpoint. Trả {'ok', 'data', 'status', 'ms', 'path'}."""
    qs = ('?' + urllib.parse.urlencode(params)) if (params and method == 'GET') else ''
    url = PUBLIC + path + qs
    ck = url + ('|k' if key else '')
    now = time.time()
    if cache:
        with _lock:
            hit = _cache.get(ck)
            if hit and now - hit[0] < CACHE_TTL:
                STATS['cache_hit'] += 1
                return hit[1]
            STATS['cache_miss'] += 1
    r = _http(url, key=key, method=method, body=body)
    js = r['json']
    err = None
    if r['status'] != 200:
        err = (js or {}).get('status', {}).get('error_message') if isinstance(js, dict) else r['error']
        err = err or ('HTTP %s' % r['status'])
    out = {'ok': r['status'] == 200, 'data': (js or {}).get('data') if isinstance(js, dict) else None,
           'status': r['status'], 'ms': r['ms'], 'path': url, 'error': err}
    with _lock:
        STATS['calls'] += 1
        _calls.append({'path': url.replace(CMC_BASE, ''), 'status': r['status'],
                       'ms': r['ms'], 'at': time.strftime('%H:%M:%S')})
        del _calls[:-80]
        if cache:
            _cache[ck] = (now, out)
    return out


# ------------------------------------- thu thập: tuần tự, giãn nhịp, thử lại
# Bộ ẩn danh của CMC 429 rất nhanh nếu bắn nhiều request cùng lúc — đo được
# bằng thực nghiệm: 11 request song song bị chặn ngay. Nên gọi tuần tự, chỉ
# gọi thứ 5 chiều thật sự cần, giãn nhịp, và thử lại khi gặp 429.

def retry(path, params, key, tries=3):
    delay, last = 2.0, None
    for _ in range(tries):
        last = cmc(path, params, key)
        if last['ok'] or last['status'] != 429:
            return last
        time.sleep(delay)
        delay *= 2
    return last


def retry2(path, params, key, method='GET', body=None, tries=3):
    delay, last = 2.0, None
    for _ in range(tries):
        last = cmc(path, params, key, method=method, body=body)
        if last['ok'] or last['status'] != 429:
            return last
        time.sleep(delay)
        delay *= 2
    return last


def fetch_swaps(platform, address, key=None, pages=None):
    """Lay NHIEU trang giao dich gan nhat.

    /v1/dex/tokens/transactions chi tra ve mot trang ~20 lenh (co lastId de
    phan trang). Lay mot trang roi goi do la "dong tien 24h" la SAI ve ban
    chat - da kiem chung bang du lieu tho: 20 lenh dau tien cong lai chi vai
    tram USD trong khi von hoa token la hang tram trieu USD.
    """
    pages = pages or SWAP_PAGES
    first = retry('/v1/dex/tokens/transactions',
                  {'platform': platform, 'address': address}, key)
    out, cur = [first], first
    for _ in range(pages - 1):
        if not cur.get('ok'):
            break
        last_id = (cur.get('data') or {}).get('lastId')
        if not last_id:
            break
        nxt = retry('/v1/dex/tokens/transactions',
                    {'platform': platform, 'address': address, 'lastId': last_id}, key)
        if not nxt.get('ok'):
            break
        out.append(nxt)
        cur = nxt
    return out


def fetch_holders_list(platform, key, address, platform_id=None):
    """Top holder - POST, va bo an dan bi chan (400 Parameter error voi moi
    bien the tham so thu duoc, GET tra 405). Nen chi chay khi co key. Ten
    tham so khong co trong tai lieu cong khai => thu lan luot vai dang, giu
    dang nao tra 200 va ghi lai da thu nhung gi."""
    shapes = [
        {'platform': platform, 'address': address},
        {'platform': platform, 'tokenAddress': address},
        {'platformId': platform_id, 'address': address},
        {'platformId': platform_id, 'tokenAddress': address},
    ]
    tried = []
    for b in shapes:
        body = {k: v for k, v in b.items() if v is not None}
        r = retry2('/v1/dex/holders/list', None, key, method='POST', body=body)
        tried.append({'body': sorted(body.keys()), 'status': r.get('status'),
                      'error': (r.get('error') or '')[:80]})
        if r.get('ok'):
            r['shape'] = body
            r['tried'] = tried
            return r
        if r.get('status') in (401, 403):
            break
        time.sleep(0.4)
    return {'ok': False, 'data': None, 'ms': 0, 'path': '/v1/dex/holders/list',
            'status': tried[-1]['status'] if tried else 0,
            'error': 'khong xac dinh duoc tham so', 'tried': tried}


def collect(platform, address, key=None):
    out = {}
    plan = [
        # tên      đường dẫn                        tham số                            cần key
        ('token',   '/v1/dex/token',                 {'platform': platform, 'address': address}, True),
        ('liqchg',  '/v1/dex/liquidity-change/list', {'platform': platform, 'address': address}, True),
        ('pools',   '/v1/dex/token/pools',           {'platform': platform, 'address': address}, True),
        ('holders', '/v1/dex/holders/count',         {'platform': platform, 'tokenAddress': address}, True),
        ('tx',      '/v1/dex/tokens/transactions',   {'platform': platform, 'address': address}, True),
        ('security','/v1/dex/security/detail',       {'platform': platform, 'address': address}, False),
        ('htrend',  '/v1/dex/holders/trend/list',    {'platform': platform, 'tokenAddress': address}, False),
    ]
    for name, path, params, keyless in plan:
        if not keyless and not key:
            out[name] = {'ok': False, 'data': None, 'status': 403, 'ms': 0, 'path': path,
                         'error': 'cần API key'}
            continue
        if name == 'tx':
            out['tx_pages'] = fetch_swaps(platform, address, key)
            out[name] = out['tx_pages'][0]
            time.sleep(0.4)
            continue
        out[name] = retry(path, params, key)
        time.sleep(0.4)

    # Top holder: POST + chi chay khi co key (bo an dan tra 400).
    if key:
        pid = _num(((out.get('token') or {}).get('data') or {}).get('pid'))
        out['hlist'] = fetch_holders_list(platform, key, address, pid)
    else:
        out['hlist'] = {'ok': False, 'data': None, 'status': 403, 'ms': 0,
                        'path': '/v1/dex/holders/list', 'error': 'can API key'}
    return out


# ------------------------------------------------------------------ chấm điểm
def band(v, table, default=0):
    """table: [(ngưỡng, điểm)] tăng dần theo v."""
    if v is None:
        return None
    for lim, pts in table:
        if v < lim:
            return pts
    return default


def score_A(liqchg, pools):
    tlu = _num((liqchg.get('data') or {}).get('tlu')) if liqchg.get('ok') else None
    lcs = ((liqchg.get('data') or {}).get('lcs') or []) if liqchg.get('ok') else []
    now = time.time() * 1000
    net24, ev = 0.0, 0
    for e in lcs:
        ts, tu = _num(e.get('ts')), _num(e.get('tu'))
        if ts is None or tu is None or now - ts > WINDOW_MS:
            continue
        tp = str(e.get('tp') or '').lower()
        sign = -1.0 if ('rem' in tp or 'sub' in tp or 'dec' in tp or 'out' in tp) else 1.0
        net24 += sign * abs(tu)
        ev += 1
    if tlu is None:
        return None
    removed = (-net24 / tlu * 100.0) if (tlu and net24 < 0) else 0.0
    a1 = band(removed, [(1, 0), (5, 3), (15, 6), (30, 10)], 12)
    a2 = band(tlu, [(5e4, 10), (5e5, 8), (5e6, 6), (5e7, 3)], 0)
    pl = (pools.get('data') or []) if pools.get('ok') else []
    tot = sum(_num(p.get('liqUsd')) or 0 for p in pl if isinstance(p, dict)) or (tlu or 0)
    top = max((_num(p.get('liqUsd')) or 0) for p in pl) if pl else 0
    share = (top / tot) if tot else None
    a3 = band(share, [(0.5, 0), (0.7, 3), (0.85, 6)], 8) if share is not None else None
    avail = [(a1, 12), (a2, 10), (a3, 8)]
    used = [x for x in avail if x[0] is not None]
    return {'score': sum(x[0] for x in used), 'max': sum(x[1] for x in used) or 30,
            'label': 'Thanh khoản', 'applicable': True,
            'endpoint': 'dex/liquidity-change/list · dex/token/pools',
            '_ev': {'tlu': tlu, 'removed_pct_24h': round(removed, 2), 'events24': ev,
                    'pools': len(pl), 'top_share': round(share, 3) if share else None,
                    'parts': [a1, a2, a3]}}


def score_B(token, holders, hlist=None):
    n = _num((holders.get('data') or {}).get('count')) if holders.get('ok') else None
    t = token.get('data') or {}
    mc, pu, tsup = _num(t.get('mcap')), _num(t.get('pu')), (_num(t.get('tsup')) or _num(t.get('ts')))
    # Top holder: chi co khi co key.
    top10, hrows = None, []
    try:
        items = (hlist or {}).get('data')
        items = items.get('holders') if isinstance(items, dict) else items
        for h in (items or []):
            if not isinstance(h, dict):
                continue
            hrows.append({'wallet': h.get('walletAddress'), 'percent': _num(h.get('percent')),
                          'balance': _num(h.get('balance')), 'buyUsd': _num(h.get('buyUsd')),
                          'sellUsd': _num(h.get('sellUsd')), 'buyCount': _num(h.get('buyCount')),
                          'sellCount': _num(h.get('sellCount')),
                          'realizedPnl': _num(h.get('realizedPnl')),
                          'realizedPnlPercent': _num(h.get('realizedPnlPercent')),
                          'name': h.get('publicName') or h.get('name'),
                          'tags': h.get('tags'), 'fundingSource': h.get('fundingSource'),
                          'firstActiveTime': _num(h.get('firstActiveTime')),
                          'lastActiveTime': _num(h.get('lastActiveTime')),
                          'flags': {k: h.get(k) for k in ('lowLiquidityFlag', 'memePumpInnerFlag',
                                                          'blackListFlag', 'riskLevelFlag')},
                          'url': h.get('addressExplorerUrl')})
        hrows.sort(key=lambda x: -(x['percent'] or 0))
        if hrows:
            top10 = sum((h['percent'] or 0) for h in hrows[:10])
            if top10 > 1.5:
                top10 = top10 / 100.0
    except Exception:
        top10 = None
    if n is None and mc is None:
        return None
    disp = (n / (mc / 1e6)) if (n is not None and mc) else None
    b1 = band(disp, [(10, 15), (50, 12), (200, 8), (500, 4)], 0) if disp is not None else None
    circ = (mc / pu) if (mc and pu) else None
    dil = (tsup / circ) if (tsup and circ) else None
    b2 = band(dil, [(1.02, 0), (1.2, 3), (2.0, 6)], 10) if dil is not None else None
    b3 = band(top10, [(0.5, 0), (0.65, 4), (0.8, 8)], 10) if top10 is not None else None
    avail = [(b1, 15), (b2, 10), (b3, 10)]
    used = [x for x in avail if x[0] is not None]
    if not used:
        return None
    return {'score': sum(x[0] for x in used), 'max': sum(x[1] for x in used),
            'label': 'Phân bố holder', 'applicable': True,
            'endpoint': 'dex/holders/count · dex/holders/list · dex/token',
            '_ev': {'holders': n, 'mcap': mc, 'holders_per_mcap_m': round(disp, 1) if disp else None,
                    'dilution': round(dil, 4) if dil else None,
                    'top10_share': round(top10, 4) if top10 else None,
                    'top_holders': hrows[:10], 'parts': [b1, b2, b3]}}


def score_E(txp):
    """Chieu E cham tren MAU giao dich gan nhat, khong phai tong 24h.

    Mot trang /tokens/transactions chi co ~20 lenh, nen phai phan trang va
    phai noi ro cua so thoi gian thuc te cua mau. Tra kem tung dong tho de
    giao dien hien thi duoc bang chung (vi nao, bao nhieu, tx nao).
    """
    pages = txp if isinstance(txp, list) else [txp]
    sw, seen = [], set()
    for pg in pages:
        for x in ((pg.get('data') or {}).get('swaps') or []):
            k = (x.get('tx'), x.get('txId'), x.get('lgid'))
            if k in seen:
                continue
            seen.add(k)
            sw.append(x)
    rows = []
    for x in sw:
        ts, v = _num(x.get('ts')), _num(x.get('v'))
        if ts is None or v is None:
            continue
        rows.append({'ts': int(ts), 'side': 'sell' if str(x.get('tp') or '').lower() == 'sell' else 'buy',
                     'usd': v, 'wallet': x.get('ma'), 'exchange': x.get('en'),
                     'tx': x.get('tx'), 'base': x.get('t0s'), 'quote': x.get('t1s'),
                     'amount': _num(x.get('a0')), 'amountQuote': _num(x.get('a1')),
                     'bundle': bool([t for t in (x.get('tags') or [])
                                     if isinstance(t, dict) and t.get('name') == 'bundle_txn'])})
    if not rows:
        return None
    rows.sort(key=lambda r: -r['ts'])
    window_min = max(0.1, (rows[0]['ts'] - rows[-1]['ts']) / 60000.0)
    buy = sum(r['usd'] for r in rows if r['side'] == 'buy')
    sell = sum(r['usd'] for r in rows if r['side'] == 'sell')
    tot = buy + sell
    # Mau qua nho thi ty le mua/ban chi la nhieu - khong cham, tra ve None
    # de giao dien noi "khong du du lieu" thay vi bia ra mot con so.
    if tot <= 0 or len(rows) < 12:
        return None
    ratio = sell / tot
    e = band(ratio, [(0.35, -10), (0.5, -3), (0.65, 4), (0.8, 9)], 15)
    wmap = {}
    for r in rows:
        w = r['wallet'] or '?'
        d = wmap.setdefault(w, {'wallet': w, 'buyUsd': 0.0, 'sellUsd': 0.0,
                                'txs': 0, 'bundle': False, 'lastTs': 0})
        if r['side'] == 'sell':
            d['sellUsd'] += r['usd']
        else:
            d['buyUsd'] += r['usd']
        d['txs'] += 1
        d['bundle'] = d['bundle'] or r['bundle']
        d['lastTs'] = max(d['lastTs'], r['ts'])
    wallets = sorted(wmap.values(), key=lambda d: -(d['sellUsd'] - d['buyUsd']))
    out_w = [w for w in wallets if w['sellUsd'] > w['buyUsd']]
    in_w = [w for w in wallets if w['buyUsd'] >= w['sellUsd']]
    top_out = wallets[0]['sellUsd'] if wallets else 0.0
    conc = (top_out / sell) if sell else 0.0
    if conc > 0.5 and sell > 0:
        e += 2
    e = max(-15, min(15, e))
    return {'score': e, 'max': 15, 'label': 'Dòng tiền ví lớn (mẫu)', 'applicable': True,
            'endpoint': 'dex/tokens/transactions',
            '_ev': {'buy_usd': round(buy, 2), 'sell_usd': round(sell, 2), 'out_ratio': round(ratio, 3),
                    'wallets_out': len(out_w), 'wallets_in': len(in_w),
                    'in_count': len(in_w), 'out_count': len(out_w),
                    'top_wallet_share_of_sells': round(conc, 3), 'swaps_sampled': len(rows),
                    'window_minutes': round(window_min, 1), 'pages': len(pages),
                    'bundles': len([r for r in rows if r['bundle']]),
                    'wallets': wallets[:12], 'rows': rows[:40]}}


EXPLORER = {
    'solana':   ('https://solscan.io/tx/', 'https://solscan.io/account/'),
    'ethereum': ('https://etherscan.io/tx/', 'https://etherscan.io/address/'),
    'bnb-chain': ('https://bscscan.com/tx/', 'https://bscscan.com/address/'),
    'base':     ('https://basescan.org/tx/', 'https://basescan.org/address/'),
    'arbitrum': ('https://arbiscan.io/tx/', 'https://arbiscan.io/address/'),
}


def _looks_hash(x):
    """txId cua CMC la so noi bo (vd 352) - KHONG phai ma giao dich. Chi coi
    la ma giao dich khi no dai va trong ky tu hex/base58."""
    if x is None:
        return False
    t = str(x)
    return len(t) >= 20 and all(c.isalnum() for c in t)


def explorer(platform, kind, value):
    pair = EXPLORER.get(str(platform or '').lower())
    if not pair or not value:
        return None
    return (pair[0] if kind == 'tx' else pair[1]) + str(value)


def build_evidence(raw, platform, address):
    """Gom so lieu THO de giao dien hien bang chung tra duoc: pool nao, su
    kien rut/them thanh khoan nao, vi nao mua ban bao nhieu, tx nao."""
    pools = []
    pl = (raw['pools'].get('data') or []) if raw['pools'].get('ok') else []
    tot = sum(_num(p.get('liqUsd')) or 0 for p in pl if isinstance(p, dict))
    for p in pl:
        if not isinstance(p, dict):
            continue
        liq = _num(p.get('liqUsd')) or 0
        pools.append({'address': p.get('addr'),
                      'exchange': p.get('exn') or p.get('en') or p.get('exchange'), 'liqUsd': liq,
                      'share': round(liq / tot, 4) if tot else None, 'v24Usd': _num(p.get('v24')),
                      'createdAt': _num(p.get('pubAt')), 'primary': bool(p.get('top')),
                      'base': (p.get('t0') or {}).get('sym'), 'quote': (p.get('t1') or {}).get('sym'),
                      'baseLiq': _num((p.get('t0') or {}).get('liqUsd')),
                      'quoteLiq': _num((p.get('t1') or {}).get('liqUsd')),
                      'url': explorer(platform, 'addr', p.get('addr'))})
    pools.sort(key=lambda x: -(x['liqUsd'] or 0))

    lcs = ((raw['liqchg'].get('data') or {}).get('lcs') or []) if raw['liqchg'].get('ok') else []
    events = []
    for e in lcs[:60]:
        if not isinstance(e, dict):
            continue
        tu = _num(e.get('tu'))
        tp = str(e.get('tp') or '').lower()
        events.append({'ts': _num(e.get('ts')),
                       'side': 'remove' if ('rem' in tp or 'sub' in tp or 'dec' in tp or 'out' in tp) else 'add',
                       'rawType': tp, 'usd': abs(tu) if tu is not None else None,
                       'pool': e.get('en') or e.get('f'), 'txId': e.get('txId'),
                       'block': _num(e.get('h')),
                       'tx': str(e.get('txn')) if _looks_hash(e.get('txn')) else None,
                       'url': explorer(platform, 'tx', e.get('txn')) if _looks_hash(e.get('txn')) else None})
    events.sort(key=lambda x: -(x['ts'] or 0))

    hl = raw.get('hlist') or {}
    htop, hmeta = [], None
    if hl.get('ok'):
        items = hl.get('data')
        items = items.get('holders') if isinstance(items, dict) else items
        for h in (items or [])[:15]:
            if not isinstance(h, dict):
                continue
            htop.append({'wallet': h.get('walletAddress'), 'percent': _num(h.get('percent')),
                         'balance': _num(h.get('balance')), 'buyUsd': _num(h.get('buyUsd')),
                         'sellUsd': _num(h.get('sellUsd')), 'buyCount': _num(h.get('buyCount')),
                         'sellCount': _num(h.get('sellCount')), 'realizedPnl': _num(h.get('realizedPnl')),
                         'realizedPnlPercent': _num(h.get('realizedPnlPercent')),
                         'name': h.get('publicName') or h.get('name'),
                         'fundingSource': h.get('fundingSource'), 'tags': h.get('tags'),
                         'url': h.get('addressExplorerUrl') or explorer(platform, 'addr', h.get('walletAddress'))})
        hmeta = {'count': len(htop), 'needsKey': False, 'shape': hl.get('shape')}
    else:
        hmeta = {'count': 0, 'needsKey': True, 'status': hl.get('status'),
                 'reason': hl.get('error'), 'tried': hl.get('tried')}
    tlu_change = _num((raw['liqchg'].get('data') or {}).get('tlu')) if raw['liqchg'].get('ok') else None
    return {'platform': platform, 'address': address, 'pools': pools,
            'liqEvents': events, 'holdersTop': htop or None, 'holdersMeta': hmeta,
            # Hai endpoint do thanh khoan theo hai dinh nghia khac nhau - phai
            # noi ro thay vi de nguoi doc tuong la mot con so.
            'totals': {'tluFromChange': tlu_change, 'poolsSum': round(tot, 2),
                       'poolsCount': len(pl),
                       'txSampleWindowMin': None}}


def _dim_unavailable(key, label, reason, maxpts, endpoint):
    return {'score': 0, 'max': maxpts, 'label': label, 'applicable': False,
            'endpoint': endpoint, '_ev': {'reason': reason}}


def build(platform, address, key=None):
    t0 = time.time()
    raw = collect(platform, address, key)
    tok = raw['token']
    if not tok['ok'] or not tok.get('data'):
        return {'error': 'token', 'detail': tok.get('error'),
                'status': tok.get('status'), 'calls': _calls[-12:]}
    t = dict(tok['data'])
    tlu = _num((raw['liqchg'].get('data') or {}).get('tlu')) if raw['liqchg'].get('ok') else None
    # /dex/token tra mcap va ts (tong cung) nhung khong tra gia. Bu bang
    # /dex/search theo ky hieu - co cache, chi goi khi con thieu.
    if _num(t.get('tsup')) is None:
        t['tsup'] = _num(t.get('ts'))
    if _num(t.get('pu')) is None:
        sym = t.get('sym') or t.get('n') or ''
        if sym:
            for it in (search(sym, key).get('items') or []):
                if it.get('address') == address:
                    t['pu'] = it.get('priceUsd'); t['v24h'] = it.get('volume24h')
                    if not t.get('tsup'): t['tsup'] = it.get('tsup')
                    break
    if tlu == 0:
        return {'error': 'nopool', 'token': t, 'calls': _calls[-12:]}

    dims, ev = {}, {}
    A = score_A(raw['liqchg'], raw['pools'])
    dims['A'] = A or _dim_unavailable('A', 'Thanh khoản', 'không lấy được số liệu thanh khoản', 30,
                                      'dex/liquidity-change/list')
    B = score_B(tok, raw['holders'], raw.get('hlist'))
    dims['B'] = B or _dim_unavailable('B', 'Phân bố holder', 'không lấy được số holder', 25,
                                      'dex/holders/count')
    dims['C'] = _dim_unavailable('C', 'An toàn hợp đồng',
                                 'dex/security/detail không nhận tham số công khai (HTTP %s)'
                                 % raw['security'].get('status'), 20, 'dex/security/detail')
    dims['D'] = _dim_unavailable('D', 'Đòn bẩy & thanh lý',
                                 'endpoint phái sinh yêu cầu API key (HTTP %s)'
                                 % (raw['htrend'].get('status') if raw['htrend'] else 0), 10,
                                 'v5/derivatives/liquidations/*')
    E = score_E(raw.get('tx_pages') or raw['tx'])
    dims['E'] = E or _dim_unavailable('E', 'Dòng tiền ví lớn', 'không có giao dịch trong 24h', 15,
                                      'dex/tokens/transactions')

    for k in ('A', 'B', 'E'):
        if dims[k].get('_ev'):
            ev[k] = dims[k]['_ev']

    # ---- 3 lý do đóng góp nhiều nhất
    cand = []
    if A:
        e = A['_ev']
        if e['removed_pct_24h'] and e['removed_pct_24h'] > 0.5:
            cand.append(('Thanh khoản đã rút %.1f%% trong 24h (còn %s USD)'
                         % (e['removed_pct_24h'], f"{e['tlu']:,.0f}".replace(',', '.')), A['score'], 30, 'A'))
        if e['pools'] and e['top_share'] and e['top_share'] > 0.5:
            cand.append(('Một pool chiếm %.0f%% thanh khoản — phụ thuộc một điểm' % (e['top_share'] * 100),
                         3, 30, 'A'))
        if A['score'] <= 4:
            cand.append(('Thanh khoản %s USD trên %d pool, chưa thấy dòng rút'
                         % (f"{e['tlu']:,.0f}".replace(',', '.'), e['pools']), A['score'], 30, 'A'))
    if B:
        e = B['_ev']
        if e.get('holders'):
            cand.append(('%s holder — %.0f holder trên mỗi triệu USD vốn hoá'
                         % (f"{e['holders']:,.0f}".replace(',', '.'), e['holders_per_mcap_m'] or 0),
                         B['score'], 25, 'B'))
        if e.get('dilution') and e['dilution'] > 1.05:
            cand.append(('Tổng cung lớn hơn cung lưu hành %.1f lần'
                         % (e['dilution'] - 1), 6, 25, 'B'))
    if E:
        e = E['_ev']
        cand.append(('Ví lớn %s: %d ví bán ròng, %d ví mua ròng trong mẫu %d lệnh (%d phút gần nhất)'
                     % ('đang rút ra' if e['out_ratio'] > 0.5 else 'đang vào',
                        e['out_count'], e['in_count'], e.get('swaps_sampled') or 0,
                        int(e.get('window_minutes') or 0)), E['score'], 15, 'E'))
        if e['top_wallet_share_of_sells'] > 0.5:
            cand.append(('Một ví chiếm %.0f%% tổng giá trị bán ra' % (e['top_wallet_share_of_sells'] * 100),
                         2, 15, 'E'))
    cand.sort(key=lambda r: -abs(r[1] / r[2]))
    reasons = [{'text': c[0], 'value': c[1], 'max': c[2], 'dim': c[3]} for c in cand[:3]]

    w = None
    if E:
        e = E['_ev']
        w = {'inCount': e['in_count'], 'inUsd': e['buy_usd'], 'outCount': e['out_count'],
             'outUsd': e['sell_usd'],
             'suspiciousPct': round((e.get('top_wallet_share_of_sells') or 0) * 100, 1),
             'verdict': 'out' if e['out_ratio'] > 0.5 else 'in',
             'wallets': e.get('wallets') or [], 'sampled': e.get('swaps_sampled'),
             'windowMinutes': e.get('window_minutes'), 'bundles': e.get('bundles') or 0,
             'rows': e.get('rows') or []}

    evd = build_evidence(raw, platform, address)
    eg = (E or {}).get('_ev') or {}
    return {
        'token': {'chain': platform, 'address': address, 'symbol': t.get('sym') or t.get('n'),
                  'name': t.get('n'), 'priceUsd': _num(t.get('pu')) or 0,
                  'liquidityUsd': tlu or 0,
                  'holders': (dims['B']['_ev'] or {}).get('holders') or 0,
                  'poolAgeDays': int((time.time() * 1000 - (_num(t.get('pubAt')) or time.time() * 1000)) / 86400000),
                  'mcap': _num(t.get('mcap')), 'tsup': _num(t.get('tsup')),
                  'volume24h': _num(t.get('v24h')), 'platformId': t.get('pid')},
        'dims': dims, 'reasons': reasons, 'whale': w, 'history': [],
        'proof': evd,
        'window': {'swapPages': len(raw.get('tx_pages') or []), 'swapSampled': eg.get('swaps_sampled'),
                   'swapMinutes': eg.get('window_minutes'), 'bundles': eg.get('bundles')},
        'holderList': {'available': bool(raw.get('hlist', {}).get('ok')),
                       'status': raw.get('hlist', {}).get('status'),
                       'reason': raw.get('hlist', {}).get('error')},
        'calls': [{'path': c['path'], 'status': c['status'], 'ms': c['ms']} for c in _calls[-14:]],
        'fetchedAt': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'elapsedMs': int((time.time() - t0) * 1000),
        'evidence': ev, 'source': 'live-cmc',
        'stats': dict(STATS), 'serverKey': bool(key)
    }


def search(q, key=None):
    r = cmc('/v1/dex/search', {'q': q}, key)
    if not r['ok']:
        return {'ok': False, 'error': r['error'], 'status': r['status'], 'items': []}
    items = []
    for x in (r['data'] or {}).get('tks', [])[:8]:
        items.append({'symbol': x.get('s') or x.get('n'), 'name': x.get('n'),
                      'chain': str(x.get('plt') or '').lower().replace(' ', '-'),
                      'platform': (x.get('plt') or '').lower(),
                      'address': x.get('addr'),
                      'liquidityUsd': _num(x.get('liq')) or 0,
                      'holders': None, 'priceUsd': _num(x.get('pu')),
                      'volume24h': _num(x.get('v24h')), 'mcap': _num(x.get('mc')),
                      'pc24h': _num(x.get('pc24h'))})
    return {'ok': True, 'items': items, 'total': (r['data'] or {}).get('total'), 'ms': r['ms']}


# --------------------------------------------------------------- HTTP server
class H(BaseHTTPRequestHandler):
    server_version = 'ExitRadar/1.0'

    def log_message(self, *a):
        pass

    def _send(self, code, payload, ctype='application/json; charset=utf-8'):
        body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-CMC-Key')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def _key(self):
        return self.headers.get('X-CMC-Key') or os.environ.get('CMC_API_KEY') or None

    def do_OPTIONS(self):
        self._send(204, b'')

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        g = lambda k, d='': (q.get(k, [d])[0] or d)
        try:
            if u.path in ('/', '/index.html'):
                p = os.path.join(ROOT, 'exit-radar-app.html')
                if os.path.exists(p):
                    return self._send(200, open(p, 'rb').read(), 'text/html; charset=utf-8')
                return self._send(404, {'error': 'không thấy exit-radar-app.html'})
            if u.path == '/api/health':
                probe = cmc('/v1/dex/search', {'q': 'BTC'}, self._key())
                return self._send(200, {'ok': True, 'server': 'exit-radar',
                                        'cmcReachable': probe['ok'], 'cmcStatus': probe['status'],
                                        'keyProvided': bool(self._key()),
                                        'cacheTtlSec': CACHE_TTL, 'stats': dict(STATS)})
            if u.path == '/api/search':
                return self._send(200, search(g('q'), self._key()))
            if u.path == '/api/scan':
                pl, ad = g('platform'), g('address')
                if not pl or not ad:
                    return self._send(400, {'error': 'thiếu platform hoặc address'})
                out = build(pl, ad, self._key())
                return self._send(200 if 'error' not in out else 502, out)
            if u.path == '/api/calls':
                return self._send(200, {'calls': _calls[-60:], 'stats': dict(STATS)})
            return self._send(404, {'error': 'không có đường dẫn này'})
        except Exception as e:
            return self._send(500, {'error': str(e)})


def selftest(platform='solana', address='DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263'):
    print('== /api/search q=BONK')
    s = search('BONK')
    print(json.dumps(s['items'][:2], ensure_ascii=False, indent=1)[:700])
    print('\n== /api/scan %s %s' % (platform, address[:14] + '…'))
    out = build(platform, address)
    if 'error' in out:
        print('LỖI:', out.get('error'), out.get('detail'))
        print(json.dumps(out.get('calls'), ensure_ascii=False, indent=1))
        return
    print(json.dumps({k: out[k] for k in ('token', 'dims', 'reasons', 'whale')},
                     ensure_ascii=False, indent=1)[:3200])
    print('\n-- bằng chứng thô --')
    print(json.dumps(out.get('evidence'), ensure_ascii=False, indent=1)[:1400])
    print('\n-- lời gọi --')
    for c in out['calls']:
        print('  %-58s %s %sms' % (c['path'][:58], c['status'], c['ms']))


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        i = sys.argv.index('--selftest')
        args = sys.argv[i + 1:i + 3]
        selftest(*args) if args else selftest()
    else:
        srv = ThreadingHTTPServer(('127.0.0.1', PORT), H)
        print('Exit Radar server → http://127.0.0.1:%d' % PORT)
        print('key CMC: %s' % ('đã có trong biến môi trường' if os.environ.get('CMC_API_KEY') else 'chưa có (chế độ công khai)'))
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print('\ndừng.')
