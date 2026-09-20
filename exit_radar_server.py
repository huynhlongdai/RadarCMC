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

# --- Key CMC mac dinh cua he thong (goi 450.000 credit/thang) ---
# Thu tu uu tien: header X-CMC-Key > bien CMC_API_KEY > tep .data/cmc_key (ghi o duoi) > khong co
CMC_DEFAULT_KEY = 'c58d53184b00433cbd7327ca6c789560'
try:
    _kf = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.data', 'cmc_key')
    if not os.path.exists(_kf):
        os.makedirs(os.path.dirname(_kf), exist_ok=True)
        _fh = open(_kf, 'w', encoding='utf-8')
        _fh.write(CMC_DEFAULT_KEY)
        _fh.close()
        try:
            os.chmod(_kf, 0o600)
        except Exception:
            pass
except Exception:
    pass

def _num(x):
    if x is None or isinstance(x, bool):
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _http(url, key=None, method='GET', body=None, timeout=25, form=False):
    hdr = {'Accept': 'application/json', 'User-Agent': 'exit-radar/1.0'}
    data = None
    if body is not None:
        if form:
            data = urllib.parse.urlencode(body).encode('utf-8')
            hdr['Content-Type'] = 'application/x-www-form-urlencoded'
        else:
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


def cmc(path, params=None, key=None, cache=True, method='GET', body=None, form=False):
    """Gọi một endpoint. Trả {'ok', 'data', 'status', 'ms', 'path'}."""
    qs = ('?' + urllib.parse.urlencode(params)) if (params and method == 'GET') else ''
    # /public-api la kenh AN DANH, va no TU CHOI moi key hop le: do bang du lieu
    # that ngay 18/09 — cung mot key chay 200 tren /v1/... nhung public-api tra
    # 401/1001 "This API Key is invalid". Vi truoc day moi loi goi deu di qua
    # public-api, key DUNG bi bao sai. Co key => di duong Pro /v1.
    base = CMC_BASE if key else PUBLIC
    url = base + path + qs
    ck = url + ('|k' if key else '')
    now = time.time()
    if cache:
        with _lock:
            hit = _cache.get(ck)
            if hit and now - hit[0] < CACHE_TTL:
                STATS['cache_hit'] += 1
                return hit[1]
            STATS['cache_miss'] += 1
    r = _http(url, key=key, method=method, body=body, form=form)
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
            'error': 'không xác định được tham số (CMC trả "Parameter error")', 'tried': tried}


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


def _fng(key=None):
    """Chi so So hai & Tham lam cua CMC (/v3/fear-and-greed): 0 = so hai cuc do,
    100 = tham lam cuc do. Da kiem chung: tra 200 bang key, credit 1."""
    r = retry('/v3/fear-and-greed/latest', None, key)
    h = retry('/v3/fear-and-greed/historical', {'limit': 8}, key)
    out = {'ok': bool(r.get('ok')), 'endpoint': 'v3/fear-and-greed'}
    if r.get('ok'):
        d = r.get('data') or {}
        out.update({'value': _num(d.get('value')), 'label': d.get('value_classification'),
                    'updateTime': d.get('update_time')})
    else:
        out['status'] = r.get('status'); out['error'] = r.get('error')
    if h.get('ok'):
        out['history'] = [{'t': x.get('timestamp'), 'value': _num(x.get('value')),
                           'label': x.get('value_classification')} for x in (h.get('data') or [])]
    return out


def _altseason(key=None):
    """Chi so mua altcoin cua CMC: 75-100 = mua altcoin, 25-49 = mua BTC,
    <=24 = mua chi BTC. Da kiem chung: tra 200 bang key."""
    r = retry('/v1/altcoin-season-index/latest', None, key)
    h = retry('/v1/altcoin-season-index/historical', {'limit': 7}, key)
    out = {'ok': bool(r.get('ok')), 'endpoint': 'v1/altcoin-season-index'}
    if r.get('ok'):
        d = r.get('data') or {}
        out.update({'index': _num(d.get('altcoin_index')), 'altMcap': _num(d.get('altcoin_marketcap')),
                    'snapshotTime': d.get('snapshot_time'), 'yearlyHigh': _num(d.get('yearly_high')),
                    'yearlyHighDate': d.get('yearly_high_date'), 'yearlyLow': _num(d.get('yearly_low')),
                    'yearlyLowDate': d.get('yearly_low_date')})
    else:
        out['status'] = r.get('status'); out['error'] = r.get('error')
    if h.get('ok'):
        pts = (h.get('data') or {}).get('points') or []
        out['history'] = [{'t': x.get('timestamp'), 'index': _num(x.get('altcoin_index')),
                           'altMcap': _num(x.get('altcoin_marketcap'))} for x in pts]
    return out


def _flow(key=None, count=8):
    """Dong tien theo chuoi ngay: von hoa, khoi luong, altcoin mcap.

    DINH NGHIA phai noi ro: "dong tien vao/ra" o day la THAY DOI VON HOA theo
    ngay, khong phai dong tien rong do duoc (thi truong khong co so do dong tien
    thuan tu endpoint nay). Muc quay vong = khoi luong 24h / von hoa.
    """
    r = retry('/v1/global-metrics/quotes/historical', {'count': count, 'interval': 'daily'}, key)
    if not r.get('ok'):
        return {'ok': False, 'status': r.get('status'), 'error': r.get('error'),
                'endpoint': 'v1/global-metrics/quotes/historical'}
    rows = []
    for q in ((r.get('data') or {}).get('quotes') or []):
        u = (q.get('quote') or {}).get('USD') or {}
        rows.append({'date': q.get('timestamp'), 'mcap': _num(u.get('total_market_cap')),
                     'volume': _num(u.get('total_volume_24h')), 'altMcap': _num(u.get('altcoin_market_cap')),
                     'btcDominance': _num(u.get('btc_dominance')), 'ethDominance': _num(u.get('eth_dominance'))})
    rows.sort(key=lambda x: x.get('date') or '')
    for i, x in enumerate(rows):
        pv = rows[i - 1] if i else None
        if pv and pv.get('mcap') and x.get('mcap'):
            x['dMcap'] = x['mcap'] - pv['mcap']
            x['dMcapPct'] = x['dMcap'] / pv['mcap'] * 100
        else:
            x['dMcap'] = None; x['dMcapPct'] = None
        x['turnover'] = (x['volume'] / x['mcap']) if (x.get('volume') and x.get('mcap')) else None
        x['altShare'] = (x['altMcap'] / x['mcap'] * 100) if (x.get('altMcap') and x.get('mcap')) else None
    return {'ok': True, 'rows': rows, 'endpoint': 'v1/global-metrics/quotes/historical'}


ALLOWED_RAW = ['/v1/dex/token', '/v1/dex/liquidity-change/list', '/v1/dex/holders/count',
               '/v1/cryptocurrency/quotes/historical', '/v1/cryptocurrency/category',
               '/v1/dex/holders/list', '/v1/dex/tokens/transactions', '/v1/dex/search',
               '/v1/cryptocurrency/info', '/v1/cryptocurrency/quotes/latest',
               '/v1/global-metrics/quotes/latest', '/v3/fear-and-greed/latest',
               '/v1/altcoin-season-index/latest']


def evidence(kind, platform='', address='', cid=None, key=None, path=None, days=30, limit=16):
    """Danh sach dung sau mot con so. Tra ve DUNG nhung gi CMC tra loi, kem ma
    HTTP va thong bao loi nguyen van — de nguoi doc tu kiem chung, va de cho
    thay ro cho nao CMC khong tra duoc thi giao dien noi that."""
    out = {'ok': True, 'kind': kind, 'platform': platform, 'address': address}
    if kind == 'holders':
        c = retry('/v1/dex/holders/count', {'platform': platform, 'tokenAddress': address}, key)
        out['count'] = {'endpoint': 'v1/dex/holders/count', 'status': c.get('status'),
                        'ms': c.get('ms'), 'error': c.get('error'), 'data': c.get('data')}
        time.sleep(0.3)
        # Da do bang du lieu that: body JSON bi tu choi (400 Parameter error),
        # body form-urlencoded di duoc xa hon (500 system busy) => gui form.
        r = cmc('/v1/dex/holders/list', None, key, cache=False, method='POST',
                body={'platform': platform, 'tokenAddress': address}, form=True)
        rows = None
        d = r.get('data')
        if r.get('ok') and d:
            lst = d.get('holders') if isinstance(d, dict) else d
            rows = lst[:25] if isinstance(lst, list) else None
        out['list'] = {'endpoint': 'v1/dex/holders/list', 'status': r.get('status'),
                       'ms': r.get('ms'), 'error': r.get('error'), 'rows': rows}
    elif kind == 'price':
        # Chuoi gia theo ngay. Da do thuc te tren goi cua nguoi dung: endpoint nen
        # OHLCV (ohlcv/historical) bi tu choi 403 error_code 1006 "plan does not
        # support", con quotes/historical tra 200 voi du lieu that => dung chuoi
        # gia ngay va noi ro trong giao dien la khong phai nen OHLCV.
        if not cid:
            return {'ok': False, 'error': 'thieu cid — token chua co ho so CMC nen khong co chuoi gia'}
        r = retry('/v1/cryptocurrency/quotes/historical',
                  {'id': cid, 'count': days, 'interval': 'daily', 'convert': 'USD'}, key)
        d = r.get('data')
        obj = d[0] if (isinstance(d, list) and d) else (d if isinstance(d, dict) else {})
        pts = []
        for q_ in ((obj.get('quotes') if isinstance(obj, dict) else None) or []):
            usd = ((q_.get('quote') or {}).get('USD') or {})
            if usd.get('price') is not None:
                pts.append({'t': q_.get('timestamp'), 'price': usd.get('price')})
        out['points'] = pts
        out['cid'] = cid
        out['endpoint'] = 'v1/cryptocurrency/quotes/historical'
        out['status'] = r.get('status'); out['ms'] = r.get('ms'); out['error'] = r.get('error')
    elif kind == 'rwa':
        RWA_ID = '6400b58c1701313dc2e853a9'   # Real World Assets Protocols (CMC)
        r = retry('/v1/cryptocurrency/category',
                  {'id': RWA_ID, 'limit': limit, 'convert': 'USD'}, key)
        d = r.get('data') or {}
        coins = []
        for c_ in ((d.get('coins') if isinstance(d, dict) else None) or []):
            usd = ((c_.get('quote') or {}).get('USD') or {})
            coins.append({
                'symbol': c_.get('symbol'), 'name': c_.get('name'), 'cid': c_.get('id'),
                'price': usd.get('price') if usd.get('price') is not None else c_.get('price'),
                'chg24h': usd.get('percent_change_24h') if usd.get('percent_change_24h') is not None else c_.get('percent_change_24h'),
                'mcap': usd.get('market_cap') if usd.get('market_cap') is not None else c_.get('market_cap'),
            })
        out['tokens'] = coins
        out['category'] = (d.get('title') or d.get('name')) if isinstance(d, dict) else None
        out['endpoint'] = 'v1/cryptocurrency/category'
        out['status'] = r.get('status'); out['ms'] = r.get('ms'); out['error'] = r.get('error')
    elif kind == 'raw':
        if path not in ALLOWED_RAW:
            return {'ok': False, 'error': 'duong dan khong nam trong danh sach cho phep',
                    'allowed': ALLOWED_RAW}
        if path == '/v1/dex/holders/list':
            r = cmc(path, None, key, cache=False, method='POST',
                    body={'platform': platform, 'tokenAddress': address}, form=True)
        elif path.startswith('/v1/dex/'):
            r = retry(path, {'platform': platform, 'address': address}, key)
        elif path.startswith('/v1/cryptocurrency/info') or path.startswith('/v1/cryptocurrency/quotes'):
            r = retry(path, {'id': cid}, key)
        else:
            r = retry(path, None, key)
        out['raw'] = {'endpoint': path.lstrip('/'), 'status': r.get('status'), 'ms': r.get('ms'),
                      'error': r.get('error'), 'data': r.get('data')}
    else:
        return {'ok': False, 'error': 'kind khong ho tro: %s' % kind}
    out['calls'] = [{'path': c['path'], 'status': c['status'], 'ms': c['ms']} for c in _calls[-8:]]
    return out


def market_context(key=None):
    """Bo canh thi truong cho trang chu: so hai & tham lam, mua altcoin, dong tien."""
    t0 = time.time()
    out = {'ok': True, 'source': 'live-cmc', 'needKey': not bool(key)}
    m = markets(key)
    out['globals'] = m.get('globals'); out['top'] = m.get('top')
    time.sleep(0.3)
    out['fng'] = _fng(key) if key else {'ok': False, 'needKey': True}
    time.sleep(0.3)
    out['altSeason'] = _altseason(key) if key else {'ok': False, 'needKey': True}
    time.sleep(0.3)
    fl = _flow(key, 8) if key else {'ok': False, 'needKey': True}
    out['flow'] = fl
    rows = fl.get('rows') or []
    if rows:
        first, last = rows[0], rows[-1]
        out['flowSummary'] = {
            'days': len(rows),
            'mcapChangePct': ((last['mcap'] - first['mcap']) / first['mcap'] * 100) if (first.get('mcap') and last.get('mcap')) else None,
            'turnoverLast': last.get('turnover'), 'altShareLast': last.get('altShare'),
            'altShareFirst': first.get('altShare'), 'btcDominanceNow': last.get('btcDominance'),
            'lastDayDmcapPct': last.get('dMcapPct')}
    out['elapsedMs'] = int((time.time() - t0) * 1000)
    out['stats'] = dict(STATS)
    return out


def token_context(cid, key=None):
    """Boi canh thi truong cua rieng token: bien dong 1h/24h/7d/30d, khoi luong,
    va muc quay vong = khoi luong 24h / von hoa. Can key (endpoint Pro)."""
    if not cid:
        return None
    # KHONG truyen aux cho endpoint nay: 'aux' chi nhan cac gia tri ve so luong
    # (cmc_rank, tags, supplies...), truyen percent_change_* se bi 400. Cac truong
    # nay duoc tra MAC DINH — da doc bang du lieu that.
    r = retry('/v1/cryptocurrency/quotes/latest', {'id': cid}, key)
    if not r.get('ok') or not r.get('data'):
        return {'ok': False, 'status': r.get('status'), 'error': r.get('error'),
                'endpoint': 'v1/cryptocurrency/quotes/latest'}
    d = (r.get('data') or {}).get(str(cid)) or {}
    q = (d.get('quote') or {}).get('USD') or {}
    mcap, vol = _num(q.get('market_cap')), _num(q.get('volume_24h'))
    return {'ok': True, 'endpoint': 'v1/cryptocurrency/quotes/latest',
            'rank': _num(d.get('cmc_rank')), 'priceUsd': _num(q.get('price')),
            'mcap': mcap, 'volume24h': vol, 'volumeChange24h': _num(q.get('volume_change_24h')),
            'pc1h': _num(q.get('percent_change_1h')), 'pc24h': _num(q.get('percent_change_24h')),
            'pc7d': _num(q.get('percent_change_7d')), 'pc30d': _num(q.get('percent_change_30d')),
            'turnover': (vol / mcap) if (vol and mcap) else None,
            # CEX vs DEX: cho biet dong tien dang chay o san tap trung hay tren DEX.
            'cexVolume24h': _num(q.get('cex_volume_24h')),
            'dexVolume24h': _num(q.get('dex_volume_24h')),
            'tvl': _num(q.get('tvl')),
            'mcapDominance': _num(q.get('market_cap_dominance')),
            'pc60d': _num(q.get('percent_change_60d')), 'pc90d': _num(q.get('percent_change_90d')),
            'updatedAt': q.get('last_updated')}


def key_info(key=None):
    """Ho so key: tran tin dung thang, so credit con lai, gioi han moi phut.
    /v1/key/info chi chay khi co key. Da kiem chung: tra ve plan 15.000
    credit/thang va 50 request/phut."""
    if not key:
        return None
    r = cmc('/v1/key/info', None, key, cache=False)
    if not r['ok']:
        return {'ok': False, 'status': r.get('status'), 'error': r.get('error')}
    d = r.get('data') or {}
    p, u = d.get('plan') or {}, d.get('usage') or {}
    cm, cd = u.get('current_month') or {}, u.get('current_day') or {}
    return {'ok': True,
            'creditLimitMonthly': _num(p.get('credit_limit_monthly')),
            'rateLimitMinute': _num(p.get('rate_limit_minute')),
            'resetAt': p.get('credit_limit_monthly_reset_timestamp'),
            'creditsUsedMonth': _num(cm.get('credits_used')),
            'creditsLeftMonth': _num(cm.get('credits_left')),
            'creditsUsedDay': _num(cd.get('credits_used'))}


def token_info(cid, key=None):
    """Ho so token tren CMC: kenh lien he (website, X, Telegram, Reddit, GitHub,
    whitepaper), logo, mo ta, ngay len san, tag, va hop dong tren TUNG chain.

    /v1/cryptocurrency/info la endpoint Pro nen PHAI co key — goi khong key tra
    401 'API key missing'. Da kiem chung bang du lieu that voi BONK (cid 23095):
    tra ve 8 hop dong tren 8 chain cung day du kenh lien lac.
    """
    if not cid:
        return None
    r = retry('/v1/cryptocurrency/info', {'id': cid}, key)
    if not r['ok'] or not r.get('data'):
        return {'ok': False, 'status': r.get('status'), 'error': r.get('error')}
    d = (r.get('data') or {}).get(str(cid)) or (r.get('data') or {}).get(cid) or {}
    u = d.get('urls') or {}

    def pick(k):
        return [x for x in (u.get(k) or []) if x][:3]

    chains = []
    for c in (d.get('contract_address') or []):
        pl = c.get('platform') or {}
        chains.append({'chain': pl.get('name'), 'address': c.get('contract_address'),
                       'coinId': (pl.get('coin') or {}).get('id')})
    return {'ok': True, 'id': d.get('id'), 'name': d.get('name'), 'symbol': d.get('symbol'),
            'slug': d.get('slug'), 'category': d.get('category'), 'logo': d.get('logo'),
            'description': (d.get('description') or '')[:900],
            'website': pick('website'), 'twitter': pick('twitter'), 'chat': pick('chat'),
            'reddit': pick('reddit'), 'messageBoard': pick('message_board'),
            'facebook': pick('facebook'), 'technicalDoc': pick('technical_doc'),
            'sourceCode': pick('source_code'), 'announcement': pick('announcement'),
            'explorer': pick('explorer'), 'subreddit': d.get('subreddit'),
            'twitterUsername': d.get('twitter_username'),
            'dateAdded': d.get('date_added'), 'dateLaunched': d.get('date_launched'),
            'tags': (d.get('tags') or [])[:16], 'notice': d.get('notice'),
            'chains': chains, 'platform': (d.get('platform') or {}).get('name')}


def markets(key=None):
    """Du lieu thi truong cho trang chu. Hai endpoint nay chay KHONG can key
    (da kiem chung): /v1/global-metrics/quotes/latest va
    /v1/cryptocurrency/listings/latest. Con quotes/latest va trending/* thi 403."""
    t0 = time.time()
    out = {'ok': True, 'source': 'live-cmc', 'globals': None, 'top': []}
    g = cmc('/v1/global-metrics/quotes/latest', None, key)
    if g.get('ok'):
        d = g.get('data') or {}
        q = (d.get('quote') or {}).get('USD') or {}
        out['globals'] = {
            'btcDominance': _num(d.get('btc_dominance')),
            'ethDominance': _num(d.get('eth_dominance')),
            'totalMcap': _num(q.get('total_market_cap')),
            'totalVolume24h': _num(q.get('total_volume_24h')),
            'mcapChange24h': _num(q.get('total_market_cap_yesterday_percentage_change')),
            'activeCryptos': _num(d.get('active_cryptocurrencies')),
            'activeExchanges': _num(d.get('active_exchanges')),
            # Dong tien: stablecoin = tien mat cho, phai sinh = don bay,
            # defi = dong von trong giao thuc. Deu lay tu mot loi goi duy nhat.
            'stablecoinMcap': _num(d.get('stablecoin_market_cap')),
            'stablecoinVolume24h': _num(d.get('stablecoin_volume_24h')),
            'stablecoinChange24h': _num(d.get('stablecoin_24h_percentage_change')),
            'defiMcap': _num(d.get('defi_market_cap')),
            'defiVolume24h': _num(d.get('defi_volume_24h')),
            'defiChange24h': _num(d.get('defi_24h_percentage_change')),
            'derivativesVolume24h': _num(d.get('derivatives_volume_24h')),
            'derivativesChange24h': _num(d.get('derivatives_24h_percentage_change')),
            'todayChangePercent': _num(d.get('today_change_percent')),
            'btcDominanceChange24h': _num(d.get('btc_dominance_24h_percentage_change')),
            'ethDominanceChange24h': _num(d.get('eth_dominance_24h_percentage_change')),
            'btcDominanceYesterday': _num(d.get('btc_dominance_yesterday')),
            'updatedAt': d.get('last_updated')}
    time.sleep(0.4)
    l = cmc('/v1/cryptocurrency/listings/latest',
            {'limit': 10, 'convert': 'USD', 'sort': 'market_cap'}, key)
    if l.get('ok'):
        for x in (l.get('data') or [])[:10]:
            qq = (x.get('quote') or {}).get('USD') or {}
            out['top'].append({'rank': int(_num(x.get('cmc_rank')) or 0),
                               'symbol': x.get('symbol'), 'name': x.get('name'),
                               'priceUsd': _num(qq.get('price')),
                               'pc24h': _num(qq.get('percent_change_24h')),
                               'pc7d': _num(qq.get('percent_change_7d')),
                               'mcap': _num(qq.get('market_cap')),
                               'volume24h': _num(qq.get('volume_24h'))})
    out['elapsedMs'] = int((time.time() - t0) * 1000)
    out['stats'] = dict(STATS)
    return out


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
    sym = t.get('sym') or t.get('n') or ''
    t['cmcLookup'] = 'chua-tra'
    if sym:
        # Tra mot lan theo ky hieu (co cache 60s) de lay DUNG ma token tren CMC.
        # KHONG duoc dung pcid cua /dex/token: do la ma cua NEN TANG (Solana =
        # 5426), khong phai ma cua token — da kiem chung bang du lieu that va
        # lan dau no hien sai thanh "ho so CMC ID 5426" cho BONK.
        items = search(sym, key, enrich=False).get('items') or []
        t['cmcLookup'] = 'da-tra'
        hit = None
        for it in items:
            if it.get('address') == address:
                hit = it
                break
        if hit:
            if _num(t.get('pu')) is None and hit.get('priceUsd'):
                t['pu'] = hit.get('priceUsd')
            if not t.get('v24h'):
                t['v24h'] = hit.get('volume24h')
            if not t.get('tsup'):
                t['tsup'] = hit.get('tsup')
            t['cid'] = hit.get('cid')
            t['logo'] = hit.get('logo')
            t['website'] = hit.get('website') or t.get('web')
            t['twitter'] = hit.get('twitter') or t.get('tw')
    # Ho so lien he/social day du — chi co khi co key (endpoint Pro). Thieu key
    # thi noi ro vi sao, khong hien o trong roi de nguoi doc tuong token khong co.
    if key and t.get('cid'):
        t['contact'] = token_info(t.get('cid'), key)
    else:
        t['contact'] = None
        t['contactSkipped'] = 'can-key' if not key else 'khong-co-cid'
    t['market'] = token_context(t.get('cid'), key) if (key and t.get('cid')) else None
    if tlu == 0:
        return {'error': 'nopool', 'token': t, 'calls': _calls[-12:]}

    dims, ev = {}, {}
    A = score_A(raw['liqchg'], raw['pools'])
    dims['A'] = A or _dim_unavailable('A', 'Thanh khoản', 'không lấy được số liệu thanh khoản', 34,
                                      'dex/liquidity-change/list')
    B = score_B(tok, raw['holders'], raw.get('hlist'))
    dims['B'] = B or _dim_unavailable('B', 'Phân bố holder', 'không lấy được số holder', 28,
                                      'dex/holders/count')
    dims['C'] = _dim_unavailable('C', 'An toàn hợp đồng',
                                 'dex/security/detail không nhận tham số công khai (HTTP %s)'
                                 % raw['security'].get('status'), 20, 'dex/security/detail')
    dims['D'] = _dim_unavailable('D', 'Đòn bẩy & thanh lý',
                                 'endpoint phái sinh không trả dữ liệu kể cả khi đã có key (HTTP %s)'
                                 % (raw['htrend'].get('status') if raw['htrend'] else 0), 10,
                                 'v5/derivatives/liquidations/*')
    E = score_E(raw.get('tx_pages') or raw['tx'])
    dims['E'] = E or _dim_unavailable('E', 'Dòng tiền ví lớn', 'không có giao dịch trong 24h', 8,
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
                  'cid': (int(_num(t.get('cid'))) if _num(t.get('cid')) else None),
                  'cmcLookup': t.get('cmcLookup'),
                  'logo': t.get('logo'), 'website': t.get('website'), 'twitter': t.get('twitter'),
                  'liquidityUsd': tlu or 0,
                  'holders': (dims['B']['_ev'] or {}).get('holders') or 0,
                  'poolAgeDays': int((time.time() * 1000 - (_num(t.get('pubAt')) or time.time() * 1000)) / 86400000),
                  'mcap': _num(t.get('mcap')), 'tsup': _num(t.get('tsup')),
                  'volume24h': _num(t.get('v24h')), 'platformId': t.get('pid')},
        'dims': dims, 'reasons': reasons, 'whale': w, 'history': [],
        'proof': evd,
        'contact': t.get('contact'), 'contactSkipped': t.get('contactSkipped'),
        'market': t.get('market'),
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


def search(q, key=None, enrich=None):
    """Tim token DEX.

    Hai dieu phai noi ro vi da do bang du lieu that:
    1) /dex/search khop CA CHUOI CON — go "Ondo" tra ve ca MOONDOGE, Gondola.
       Nen phai xep hang theo nhom: khop dung ky hieu > bat dau bang > chua chuoi.
    2) /dex/search KHONG tra ve so holder. Giao dien cu hien 'holder' trong khi
       truong do luon la None, nen nguoi dung khong thay gi. Muon co so holder
       phai goi them /dex/holders/count cho tung token.
    """
    r = cmc('/v1/dex/search', {'q': q}, key)
    if not r['ok']:
        return {'ok': False, 'error': r['error'], 'status': r['status'], 'items': []}
    ql = (q or '').strip().lower()
    items = []
    for x in (r['data'] or {}).get('tks', [])[:40]:
        sym = x.get('s') or x.get('n') or ''
        sl = str(sym).lower()
        grp = 0 if sl == ql else (1 if sl.startswith(ql) else 2)
        items.append({'symbol': sym, 'name': x.get('n'),
                      'chain': str(x.get('plt') or '').lower().replace(' ', '-'),
                      'platform': (x.get('plt') or '').lower(),
                      'address': x.get('addr'),
                      'liquidityUsd': _num(x.get('liq')) or 0,
                      'holders': None, 'holdersStatus': None,
                      'priceUsd': _num(x.get('pu')),
                      'volume24h': _num(x.get('v24h')), 'mcap': _num(x.get('mc')),
                      'pc24h': _num(x.get('pc24h')),
                      'cid': int(_num(x.get('cid'))) if _num(x.get('cid')) else None,
                      'logo': x.get('l'), 'website': x.get('w'), 'twitter': x.get('x'),
                      'createdAt': _num(x.get('pt')), 'group': grp, 'exact': grp == 0})
    items.sort(key=lambda it: (it['group'], -(it['liquidityUsd'] or 0)))
    n_exact = len([i for i in items if i['exact']])
    # Bu so holder cho nhom khop dung (toi da 4 loi goi) — chi khi chuoi du dai,
    # va tan dung cache 60s cua cmc().
    do_enrich = enrich if enrich is not None else (len(ql) >= 3)
    if do_enrich and n_exact:
        for it in items[:min(n_exact, 4)]:
            hc = retry('/v1/dex/holders/count',
                       {'platform': it['platform'], 'tokenAddress': it['address']}, key)
            if hc.get('ok'):
                it['holders'] = _num((hc.get('data') or {}).get('count'))
            it['holdersStatus'] = hc.get('status')
            time.sleep(0.3)
    return {'ok': True, 'items': items[:20], 'total': (r['data'] or {}).get('total'),
            'exactCount': n_exact, 'query': q, 'ms': r['ms']}


# Vercel rewrite trong vercel.json gui '/api/index?op=<ten>' thay vi giu nguyen
# duong dan. Da kiem chung tren ban live: self.path = '/api/index?op=search' nen
# u.path khong con la '/api/search' va moi route deu roi vao 404. Doi lai theo op
# truoc khi so sanh — nho vay ca hai kieu goi deu chay.
OPMAP = {'app': '/', 'home': '/', 'health': '/api/health', 'search': '/api/search',
         'scan': '/api/scan', 'markets': '/api/markets', 'marketctx': '/api/marketctx',
         'calls': '/api/calls', 'tg': '/api/tg', 'tick': '/api/cron/tick'}


# ============================================================== BOT TELEGRAM
# Day canh bao ra khoi trinh duyet: bot Telegram nhan lenh tu nguoi dung,
# tu quet theo luat da dat va gui tin nhan. Cach lam dua tren tai lieu that:
#   - gui tin: POST https://api.telegram.org/bot<token>/sendMessage (HTML)
#   - nhan lenh: getUpdates long polling (timeout) hoac webhook; khi dat webhook
#     Telegram gui header 'X-Telegram-Bot-Api-Secret-Token' de xac thuc.
#   - gioi han gui: 30 tin/giay toan bot, ~1 tin/giay cho MOT chat, 20 tin/phut
#     cho nhom; vuot thi Telegram tra 429 kem 'parameters.retry_after' (giay).
#     => o day co gian cach 1,1s/chat + han muc 18 tin/phut/chat + doc retry_after.
#   - luu tru: tep JSON khi chay tren may (che do --bot), hoac Upstash Redis REST
#     khi chay serverless (Vercel khong ghi duoc tep). Khong co kho luu tru thi
#     endpoint bao ro chu khong gia vo da luu.
TG_DIR   = os.environ.get('ER_DATA_DIR', os.path.join(ROOT, '.data'))
TG_FILE  = os.path.join(TG_DIR, 'tg.json')
TG_URL   = 'https://api.telegram.org/bot%s/%s'
KV_URL   = (os.environ.get('UPSTASH_REDIS_REST_URL') or '').rstrip('/')
KV_TOK   = os.environ.get('UPSTASH_REDIS_REST_TOKEN') or ''
KV_KEY   = os.environ.get('ER_KV_KEY', 'exit-radar:tg')
TG_GAP   = 1.1          # giay giua hai tin lien tiep cua cung mot chat
TG_PERMIN = 18          # tran tin/phut/chat (Telegram cho 20 voi nhom)
TG_MAX_PER_TICK = int(os.environ.get('TG_MAX_PER_TICK', '5'))
TG_MSG_MAX = 3800       # Telegram cho 4096 ky tu; chua lai mot chut


def tg_token():
    return (os.environ.get('TELEGRAM_BOT_TOKEN') or '').strip()


def tg_secret():
    return (os.environ.get('TG_SECRET') or os.environ.get('CRON_SECRET') or '').strip()


def kv_on():
    return bool(KV_URL and KV_TOK)


def store_mode():
    if kv_on():
        return 'upstash'
    try:
        os.makedirs(TG_DIR, exist_ok=True)
        return 'tep' if os.access(TG_DIR, os.W_OK) else 'khong-ghi-duoc'
    except Exception:
        return 'khong-ghi-duoc'


def _kv(cmd):
    req = urllib.request.Request(KV_URL, data=json.dumps(cmd).encode('utf-8'),
                                 headers={'Authorization': 'Bearer ' + KV_TOK,
                                          'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode('utf-8'))


def tg_load():
    """Doc kho luu tru; tra ve dict rong neu chua co gi (khong nem loi)."""
    if kv_on():
        try:
            d = _kv(['GET', KV_KEY]).get('result')
            return json.loads(d) if d else {}
        except Exception:
            return {}
    try:
        with open(TG_FILE, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def tg_save(st):
    st['updatedAt'] = int(time.time() * 1000)
    if kv_on():
        try:
            _kv(['SET', KV_KEY, json.dumps(st, ensure_ascii=False)])
            return True
        except Exception:
            return False
    try:
        os.makedirs(TG_DIR, exist_ok=True)
        with open(TG_FILE, 'w', encoding='utf-8') as f:
            json.dump(st, f, ensure_ascii=False)
        return True
    except Exception:
        return False


def tg_call(method, payload, timeout=20):
    """Goi Bot API. Tra ve dict co ok/status/result/error/retry_after - khong nem loi."""
    t = tg_token()
    if not t:
        return {'ok': False, 'status': 0, 'error': 'chưa đặt TELEGRAM_BOT_TOKEN trên máy chủ',
                'result': None}
    try:
        req = urllib.request.Request(TG_URL % (t, method),
                                     data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                                     headers={'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode('utf-8'))
        return {'ok': bool(d.get('ok')), 'status': r.status, 'result': d.get('result'),
                'error': None if d.get('ok') else (d.get('description') or 'lỗi không rõ')}
    except urllib.error.HTTPError as e:
        body = ''
        try:
            body = e.read().decode('utf-8')
        except Exception:
            pass
        d = {}
        try:
            d = json.loads(body)
        except Exception:
            pass
        ra = ((d.get('parameters') or {}).get('retry_after'))
        return {'ok': False, 'status': e.code, 'error': d.get('description') or body[:180],
                'error_code': d.get('error_code'), 'retry_after': ra, 'result': None}
    except Exception as e:
        return {'ok': False, 'status': 0, 'error': str(e), 'result': None}


def tg_min_gap_ok(ch):
    """Tran gui: cach nhau >= TG_GAP giay va <= TG_PERMIN tin trong 60 giay."""
    now = time.time()
    last = float(ch.get('lastSent') or 0)
    if now - last < TG_GAP:
        return False, TG_GAP - (now - last)
    hist = [float(x) for x in (ch.get('sentHist') or []) if now - float(x) < 60]
    ch['sentHist'] = hist
    if len(hist) >= TG_PERMIN:
        return False, 60 - (now - hist[0])
    return True, 0


_TG_LAST_CARD = {}


def tg_chart_png(snap, tok):
    """Bieu do dong tien vi lon dung tu chinh du lieu vua quet - khong ton them credit."""
    try:
        import io
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except Exception:
        return None
    rows = [x for x in ((snap or {}).get('rows') or []) if isinstance(x, dict) and x.get('ts')]
    if len(rows) < 3:
        return None
    try:
        t0 = min(float(x['ts']) for x in rows)
        xb, yb, xs_, ys_ = [], [], [], []
        for x in rows:
            t = (float(x['ts']) - t0) / 60000.0
            u = float(x.get('usd') or 0)
            if (x.get('side') or '') == 'sell':
                xs_.append(t); ys_.append(-u)
            else:
                xb.append(t); yb.append(u)
        fig, ax = plt.subplots(figsize=(6.6, 3.3), dpi=140)
        fig.patch.set_facecolor('#0B1220'); ax.set_facecolor('#0B1220')
        ax.bar(xb, yb, width=0.6, color='#16C784', label='BUY')
        ax.bar(xs_, ys_, width=0.6, color='#EA3943', label='SELL')
        ax.axhline(0, color='#6B7280', linewidth=0.8)
        ax.set_xlabel('minutes from first trade', color='#9CA3AF', fontsize=8)
        ax.set_ylabel('USD', color='#9CA3AF', fontsize=8)
        ax.tick_params(colors='#9CA3AF', labelsize=7)
        for sp in ax.spines.values():
            sp.set_color('#374151')
        ax.set_title('Whale flow | ' + str((tok or {}).get('symbol') or ''),
                     color='#E5E7EB', fontsize=10)
        ax.legend(facecolor='#111827', edgecolor='#374151', labelcolor='#E5E7EB', fontsize=7)
        buf = io.BytesIO()
        fig.tight_layout()
        fig.savefig(buf, format='png', facecolor=fig.get_facecolor())
        plt.close(fig)
        return buf.getvalue()
    except Exception:
        return None


def tg_quickchart_url(snap, tok):
    """Bieu do bang URL cua dich vu ve bieu do (QuickChart - mien phi, khong can key).

    Telegram tu tai anh tu URL nay, nen may chay khong can matplotlib va khong ton credit CMC.
    Tat/doi nguon bang bien moi truong TG_CHART = auto | quickchart | local | none.
    """
    try:
        rows = [x for x in ((snap or {}).get('rows') or []) if isinstance(x, dict) and x.get('ts')]
        if len(rows) < 3:
            return None
        t0 = min(float(x['ts']) for x in rows)
        labels, buys, sells = [], [], []
        for x in rows:
            labels.append('%.1f' % ((float(x['ts']) - t0) / 60000.0))
            u = round(float(x.get('usd') or 0) / 1000.0, 2)
            if (x.get('side') or '') == 'sell':
                buys.append(0); sells.append(-u)
            else:
                buys.append(u); sells.append(0)
        cfg = {'type': 'bar',
               'data': {'labels': labels, 'datasets': [
                   {'label': 'BUY', 'data': buys, 'backgroundColor': '#16C784'},
                   {'label': 'SELL', 'data': sells, 'backgroundColor': '#EA3943'}]},
               'options': {
                   'legend': {'labels': {'fontColor': '#E5E7EB', 'fontSize': 10}},
                   'title': {'display': True, 'text': 'Whale flow (K USD) | ' + str((tok or {}).get('symbol') or ''),
                             'fontColor': '#E5E7EB', 'fontSize': 13},
                   'scales': {'xAxes': [{'ticks': {'fontColor': '#9CA3AF', 'fontSize': 8},
                                          'gridLines': {'color': '#1F2937'}}],
                              'yAxes': [{'ticks': {'fontColor': '#9CA3AF', 'fontSize': 8},
                                         'gridLines': {'color': '#1F2937'}}]}}}
        q = urllib.parse.urlencode({'w': '660', 'h': '330', 'bkg': '#0B1220',
                                    'c': json.dumps(cfg, separators=(',', ':'))})
        return 'https://quickchart.io/chart?' + q
    except Exception:
        return None


GT_NET = {'solana': 'solana', 'bsc': 'bsc', 'ethereum': 'eth', 'eth': 'eth', 'base': 'base',
          'arbitrum': 'arbitrum', 'polygon': 'polygon_pos', 'polygon-pos': 'polygon_pos',
          'avalanche': 'avax', 'optimism': 'optimism', 'tron': 'tron', 'sui': 'sui-network'}


def tg_ohlcv(platform, address, aggregate=5, limit=60):
    """Nen THAT tu GeckoTerminal: mien phi, khong can key, ~30 loi goi/phut.

    Lay pool thanh khoan lon nhat cua token roi xin nen 5 phut. Day la du lieu nen that
    (o/h/l/c) chu khong phai duong ve lai tu vai diem gia CMC.
    """
    net = GT_NET.get(str(platform or '').lower())
    if not (net and address):
        return None
    hdr = {'Accept': 'application/json;version=20230302', 'User-Agent': 'exit-radar/1.1'}
    try:
        u1 = ('https://api.geckoterminal.com/api/v2/networks/' + net + '/tokens/' +
              urllib.parse.quote(str(address)) + '/pools?page=1')
        with urllib.request.urlopen(urllib.request.Request(u1, headers=hdr), timeout=20) as r:
            j = json.loads(r.read().decode('utf-8', 'replace'))
        pools = (j.get('data') or []) if isinstance(j, dict) else []
        best, br = None, -1.0
        for pp in pools:
            a = pp.get('attributes') or {}
            addr = a.get('address') or (pp.get('id') or '').split('_')[-1]
            try:
                rv = float(a.get('reserve_in_usd') or 0)
            except Exception:
                rv = 0.0
            if addr and rv > br:
                best, br = addr, rv
        if not best:
            return None
        u2 = ('https://api.geckoterminal.com/api/v2/networks/' + net + '/pools/' + str(best) +
              '/ohlcv/minute?aggregate=' + str(aggregate) + '&limit=' + str(limit))
        with urllib.request.urlopen(urllib.request.Request(u2, headers=hdr), timeout=20) as r2:
            j2 = json.loads(r2.read().decode('utf-8', 'replace'))
        lst = (((j2.get('data') or {}).get('attributes') or {}).get('ohlcv_list')) or []
        if len(lst) < 5:
            return None
        return {'pool': best, 'net': net, 'candles': lst}
    except Exception:
        return None


def tg_candle_png(data, tok, minutes=5):
    """Ve nen that (o/h/l/c) kieu san giao dich."""
    try:
        import io
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle
    except Exception:
        return None
    c = (data or {}).get('candles') or []
    if len(c) < 5:
        return None
    try:
        c = sorted(c, key=lambda x: float(x[0]))
        t0 = float(c[0][0])
        fig, ax = plt.subplots(figsize=(6.8, 3.4), dpi=140)
        fig.patch.set_facecolor('#0B1220'); ax.set_facecolor('#0B1220')
        w = max(0.5, (float(c[-1][0]) - t0) / 60.0 / max(len(c), 1) * 0.7)
        for row in c:
            try:
                ts, o, h, l, cl = (float(row[0]), float(row[1]), float(row[2]),
                                   float(row[3]), float(row[4]))
            except Exception:
                continue
            x = (ts - t0) / 60.0
            col = '#16C784' if cl >= o else '#EA3943'
            ax.plot([x, x], [l, h], color=col, linewidth=0.7, solid_capstyle='butt')
            hgt = abs(cl - o)
            if hgt <= 0:
                hgt = max((h - l) * 0.002, 1e-15)
            ax.add_patch(Rectangle((x - w / 2.0, min(o, cl)), w, hgt,
                                   facecolor=col, edgecolor=col, linewidth=0.3))
        ax.set_xlabel('phut', color='#9CA3AF', fontsize=8)
        ax.set_ylabel('gia (USD)', color='#9CA3AF', fontsize=8)
        ax.tick_params(colors='#9CA3AF', labelsize=7)
        for sp in ax.spines.values():
            sp.set_color('#374151')
        ax.set_title('Nen that ' + str(minutes) + 'm | ' + str((tok or {}).get('symbol') or '') +
                     ' | pool ' + str((data or {}).get('pool') or '')[:12],
                     color='#E5E7EB', fontsize=9)
        buf = io.BytesIO()
        fig.tight_layout()
        fig.savefig(buf, format='png', facecolor=fig.get_facecolor())
        plt.close(fig)
        return buf.getvalue()
    except Exception:
        return None


def tg_multipart(fields, fname, content):
    """Dung than yeu cau multipart/form-data de gui anh cho Telegram."""
    b = '----ExitRadarBoundary7f3a'
    out = []
    for k, v in (fields or {}).items():
        if v is None:
            continue
        out.append(('--' + b + '\r\nContent-Disposition: form-data; name="' + k + '"\r\n\r\n' + str(v) + '\r\n').encode('utf-8'))
    out.append(('--' + b + '\r\nContent-Disposition: form-data; name="photo"; filename="' + fname + '"\r\n'
                'Content-Type: image/png\r\n\r\n').encode('utf-8'))
    out.append(content)
    out.append(('\r\n--' + b + '--\r\n').encode('utf-8'))
    return b''.join(out), 'multipart/form-data; boundary=' + b


def tg_call_photo(method, fields, fname, content, timeout=45):
    body, ctype = tg_multipart(fields, fname, content)
    req = urllib.request.Request(TG_URL % (tg_token(), method), data=body, headers={'Content-Type': ctype})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8', 'replace'))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode('utf-8', 'replace'))
        except Exception:
            return {'ok': False, 'error': 'HTTP ' + str(e.code)}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def tg_send(chat_id, text, markup=None, st=None, ch=None, dry=False):
    """Gui mot tin. dry=True thi KHONG goi Telegram, tra ve dung noi dung se gui."""
    text = text[:TG_MSG_MAX]
    if dry or not tg_token():
        return {'ok': False, 'dry': True, 'text': text,
                'error': None if dry else 'chưa đặt TELEGRAM_BOT_TOKEN trên máy chủ'}
    if ch is not None:
        ok, wait = tg_min_gap_ok(ch)
        if not ok:
            return {'ok': False, 'throttled': True, 'wait': round(wait, 1),
                    'error': 'chờ %.1fs cho đủ giãn cách gửi' % wait}
    body = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML',
            'disable_web_page_preview': True}
    if markup:
        body['reply_markup'] = markup
    r = None
    try:
        if not dry and _TG_LAST_CARD.get('text') == text:
            _mode = (os.environ.get('TG_CHART') or 'auto').lower()
            _card_snap, _card_tok = _TG_LAST_CARD.get('snap') or {}, _TG_LAST_CARD.get('tok') or {}
            if _mode in ('auto', 'real') and (os.environ.get('TG_CHART_DATA') or 'candles').lower() != 'bars':
                _cand = tg_ohlcv(_card_snap.get('platform'), _card_snap.get('address'))
                _png0 = tg_candle_png(_cand, _card_tok) if _cand else None
                if _png0:
                    _pf0 = {'chat_id': chat_id, 'caption': text[:1000], 'parse_mode': 'HTML'}
                    if markup:
                        _pf0['reply_markup'] = json.dumps(markup)
                    r = tg_call_photo('sendPhoto', _pf0, 'exit-radar-candles.png', _png0)
                    if not (r or {}).get('ok'):
                        r = None
            if r is None and _mode in ('auto', 'quickchart'):
                _u = tg_quickchart_url(_card_snap, _card_tok)
                if _u:
                    _pf = {'chat_id': chat_id, 'photo': _u, 'caption': text[:1000], 'parse_mode': 'HTML'}
                    if markup:
                        _pf['reply_markup'] = markup
                    r = tg_call('sendPhoto', _pf, timeout=45)
                    if not (r or {}).get('ok'):
                        r = None
            _png = None if r else (tg_chart_png(_card_snap, _card_tok) if _mode in ('auto', 'local') else None)
            if _png:
                _pf = {'chat_id': chat_id, 'caption': text[:1000], 'parse_mode': 'HTML'}
                if markup:
                    _pf['reply_markup'] = json.dumps(markup)
                r = tg_call_photo('sendPhoto', _pf, 'exit-radar.png', _png)
                if not (r or {}).get('ok'):
                    r = None
    except Exception:
        r = None
    if r is None:
        r = tg_call('sendMessage', body)
    if r.get('ok') and ch is not None:
        ch['lastSent'] = time.time()
        ch.setdefault('sentHist', []).append(time.time())
        ch['sentHist'] = ch['sentHist'][-40:]
        if st is not None:
            tg_save(st)
    return r


def tg_markup(app_url, token_key=None):
    if not app_url:
        return None
    u = app_url.rstrip('/') + '/#' + (('/scan/' + token_key.replace(':', '/')) if token_key else '/watchlist')
    return {'inline_keyboard': [[{'text': 'Mở trong Exit Radar', 'url': u}],
                              [{'text': 'Tuỳ chỉnh cảnh báo', 'url': app_url.rstrip('/') + '/#/settings'}]]}


def tg_scan(platform, address, key=None):
    """Quet mot token va rut ra dung nhung so can cho luat canh bao."""
    out = build(platform, address, key)
    if 'error' in out:
        return {'ok': False, 'error': out.get('error'), 'detail': out.get('detail')}
    tok = out.get('token') or {}
    dims = out.get('dims')
    seq = list(dims.values()) if isinstance(dims, dict) else list(dims or [])

    def by(probe):
        for d in seq:
            if probe in ((d or {}).get('_ev') or {}):
                return d
        return {}
    dE, dB = by('rows'), by('holders')
    evE, evB = (dE.get('_ev') or {}), (dB.get('_ev') or {})
    # build() khong tra ve tong diem o cap cao nhat: tong diem = tong diem cua
    # cac chieu CHAM DUOC. Chieu khong cham duoc bi loai han - neu tinh no la 0
    # thi mot token thieu du lieu se trong nhu "an toan", dung sai ve nghia.
    usable = [d for d in seq if d.get('applicable') and isinstance(d.get('score'), (int, float))]
    # Cung cong thuc voi giao dien: diem = rawSum / maxSum * 100, lam tron, san 0.
    # (Truoc do toi lay tong tho nen tin nhan ghi 6 trong khi web ghi 10 - da sua.)
    raw = sum(d['score'] for d in usable) if usable else None
    mx = sum((d.get('max') or 0) for d in usable) if usable else 0
    liq = tok.get('liquidityUsd')
    if liq is not None and float(liq or 0) <= 0:
        liq = None   # 0 o day la "khong co so", khong phai "thanh khoan bang 0"
    return {'ok': True, 'score': (max(0, int(round(raw / mx * 100))) if (raw is not None and mx) else None),
            'scoreRaw': raw, 'scoreMax': (mx or None),
            'dimsScored': len(usable), 'dimsTotal': len(seq),
            'symbol': tok.get('symbol'), 'name': tok.get('name'),
            'cid': tok.get('cid'), 'liq': liq,
            'holders': tok.get('holders'), 'price': tok.get('priceUsd'),
            'whale': ((out.get('whale') or {}).get('verdict')),
            'whaleBuyUsd': evE.get('buy_usd'), 'whaleSellUsd': evE.get('sell_usd'),
            'wallets': (evE.get('wallets') or [])[:12],
            'rows': (evE.get('rows') or [])[:40],
            'top10': evB.get('top10_share'), 'swaps': evE.get('swaps_sampled'),
            'vol24h': _num((tok or {}).get('volume24h')),
            'platform': platform, 'address': address,
            'calls': out.get('calls'), 'at': int(time.time() * 1000)}


TG_RULES = [
    ('whaleBuy',      'ví cá mập mua vào'),
    ('whaleSell',     'ví cá mập bán ra'),
    ('scoreAbove',    'điểm vượt ngưỡng'),
    ('jumpUp',        'điểm tăng thêm'),
    ('liqDropPct',    'thanh khoản giảm'),
    ('holdDropPct',   'số holder giảm'),
    ('whaleOut',      'dòng tiền ví lớn chuyển sang rút'),
    ('priceUpPct',    'giá tăng'),
    ('priceDownPct',  'giá giảm'),
]


def tg_eval(prev, snap, tg_rules, now_ms):
    """So hai lan quet va tra ve danh sach canh bao da vuot luat.

    Moi canh bao deu co so TRUOC -> so SAU. Khong doan: thieu du lieu thi bo qua
    luat do va ghi ly do, khong bao '0' hay 'an toan' khi khong biet.
    """
    r = tg_rules or {}
    out, skipped = [], []
    if not prev:
        return out, skipped
    min_buy = _num(r.get('whaleBuyMinUsd')) or 0
    min_sell = _num(r.get('whaleSellMinUsd')) or 0
    seen_ts = float(r.get('_seenTs') or 0) / 1000.0
    if r.get('whaleBuy') or r.get('whaleSell'):
        rows = [x for x in (snap.get('rows') or []) if float(x.get('ts') or 0) > seen_ts]
        if not rows:
            skipped.append('chưa có giao dịch mới kể từ lần quét trước')
        for x in rows:
            usd = float(x.get('usd') or 0)
            side = x.get('side')
            if r.get('whaleBuy') and side == 'buy' and usd >= max(min_buy, 1):
                out.append({'rk': 'whale_buy', 'rule': 'ví cá mập mua', 'side': 'buy', 'usd': usd, 'walletShort': short_w(x.get('wallet')),
                            'wallet': x.get('wallet'), 'tx': x.get('tx'),
                            'text': 'ví cá mập MUA ' + usd_txt(usd) + ' — ví ' + short_w(x.get('wallet')),
                            'from': '', 'to': usd_txt(usd)})
            if r.get('whaleSell') and side == 'sell' and usd >= max(min_sell, 1):
                out.append({'rk': 'whale_sell', 'rule': 'ví cá mập bán', 'side': 'sell', 'usd': usd, 'walletShort': short_w(x.get('wallet')),
                            'wallet': x.get('wallet'), 'tx': x.get('tx'),
                            'text': 'ví cá mập BÁN ' + usd_txt(usd) + ' — ví ' + short_w(x.get('wallet')),
                            'from': '', 'to': usd_txt(usd)})
    if r.get('scoreAbove') is not None and prev.get('score') is not None and snap.get('score') is not None:
        lim = _num(r.get('scoreAbove'))
        if prev['score'] < lim <= snap['score']:
            out.append({'rk': 'score_above', 'rule': 'điểm vượt ' + nf_txt(lim, 0), 'from': nf_txt(prev['score'], 0),
                        'to': nf_txt(snap['score'], 0),
                        'text': 'điểm vượt ' + nf_txt(lim, 0) + ' (' + nf_txt(prev['score'], 0) +
                                ' → ' + nf_txt(snap['score'], 0) + ')'})
    if r.get('jumpUp') is not None and prev.get('score') is not None and snap.get('score') is not None:
        d = snap['score'] - prev['score']
        if d >= _num(r.get('jumpUp')):
            out.append({'rk': 'jump', 'rule': 'điểm tăng thêm', 'from': nf_txt(prev['score'], 0), 'to': nf_txt(snap['score'], 0),
                        'text': 'điểm tăng ' + nf_txt(d, 0) + ' điểm (' + nf_txt(prev['score'], 0) +
                                ' → ' + nf_txt(snap['score'], 0) + ')'})
    for k, label, unit in (('liqDropPct', 'thanh khoản giảm', 'USD'),
                           ('holdDropPct', 'số holder giảm', 'người')):
        if r.get(k) is None:
            continue
        a, b = prev.get('liq' if k == 'liqDropPct' else 'holders'), snap.get('liq' if k == 'liqDropPct' else 'holders')
        if not a or not b:
            skipped.append(label + ': thiếu một trong hai mốc')
            continue
        pct = (b - a) / abs(a) * 100.0
        if pct <= -_num(r.get(k)):
            out.append({'rk': ('liq_drop' if k == 'liqDropPct' else 'hold_drop'), 'pct': nf_txt(abs(pct), 1),
                        'rule': label, 'from': usd_short(a) if unit == 'USD' else nf_txt(a, 0),
                        'to': usd_short(b) if unit == 'USD' else nf_txt(b, 0),
                        'text': label + ' ' + nf_txt(abs(pct), 1) + '% (' +
                                (usd_short(a) if unit == 'USD' else nf_txt(a, 0)) + ' → ' +
                                (usd_short(b) if unit == 'USD' else nf_txt(b, 0)) + ')'})
    if r.get('whaleOut') and prev.get('whale') != 'out' and snap.get('whale') == 'out':
        out.append({'rk': 'whale_out', 'rule': 'dòng tiền ví lớn chuyển sang rút', 'from': 'đang vào' if prev.get('whale') == 'in' else 'không rõ',
                    'to': 'đang rút', 'text': 'dòng tiền ví lớn chuyển từ ' +
                    ('đang vào' if prev.get('whale') == 'in' else 'không rõ') + ' sang ĐANG RÚT'})
    for k, label, up in (('priceUpPct', 'giá tăng', True), ('priceDownPct', 'giá giảm', False)):
        if r.get(k) is None:
            continue
        a, b = prev.get('price'), snap.get('price')
        if not a or not b:
            skipped.append(label + ': chưa có giá ở một trong hai mốc')
            continue
        pct = (b - a) / abs(a) * 100.0
        if (pct >= _num(r.get(k))) if up else (pct <= -_num(r.get(k))):
            out.append({'rk': ('price_up' if up else 'price_down'), 'pct': nf_txt(abs(pct), 2),
                        'rule': label, 'from': price_txt(a), 'to': price_txt(b),
                        'text': label + ' ' + nf_txt(abs(pct), 2) + '% (' + price_txt(a) +
                                ' → ' + price_txt(b) + ')'})
    return out, skipped


def usd_txt(v):
    v = float(v or 0)
    if v >= 1e9:
        return nf_txt(v / 1e9, 2) + ' tỷ USD'
    if v >= 1e6:
        return nf_txt(v / 1e6, 2) + ' triệu USD'
    if v >= 1e3:
        return nf_txt(v / 1e3, 1) + ' nghìn USD'
    return nf_txt(v, 0) + ' USD'


# --- Don vi tien + muc rui ro theo ngon ngu tin nhan (en/zh) ---
TG_USD_SUF = {
    'vi': (' tỷ USD', ' triệu USD', ' nghìn USD', ' USD'),
    'en': ('B USD', 'M USD', 'K USD', ' USD'),
    'zh': ('十亿美元', '百万美元', '千美元', ' 美元'),
}


def usd_txt_lang(v, lang='vi'):
    lang = lang if lang in TG_USD_SUF else 'vi'
    u = TG_USD_SUF[lang]
    v = float(v or 0)
    if v >= 1e9:
        return nf_txt(v / 1e9, 2) + u[0]
    if v >= 1e6:
        return nf_txt(v / 1e6, 2) + u[1]
    if v >= 1e3:
        return nf_txt(v / 1e3, 1) + u[2]
    return nf_txt(v, 0) + u[3]


TG_UNIT_FIX = {
    'en': [(' nghìn USD', 'K USD'), (' triệu USD', 'M USD'), (' tỷ USD', 'B USD'),
           (' USD', ' USD'), ('không rõ ví', 'unknown wallet'),
           ('ví cá mập', 'whale wallet')],
    'zh': [(' nghìn USD', '千美元'), (' triệu USD', '百万美元'),
           (' tỷ USD', '十亿美元'), (' USD', ' 美元'),
           ('không rõ ví', '未知钱包'), ('ví cá mập', '巨鲸钱包')],
}

TG_LVL = {
    'en': {'THẤP': 'LOW', 'ĐỂ MẮT': 'WATCH', 'CAO': 'HIGH', 'NGHIÊM TRỌNG': 'CRITICAL'},
    'zh': {'THẤP': '低', 'ĐỂ MẮT': '留意', 'CAO': '高', 'NGHIÊM TRỌNG': '严重'},
}


def tg_fix_units(s, lang):
    """Doi don vi tien trong cau da lap san (giu nguyen con so)."""
    if not lang or lang == 'vi':
        return s
    for a, b in TG_UNIT_FIX.get(lang, []):
        s = s.replace(a, b)
    return s


def usd_short(v):
    v = float(v or 0)
    if v >= 1e9:
        return nf_txt(v / 1e9, 2) + 'B'
    if v >= 1e6:
        return nf_txt(v / 1e6, 2) + 'M'
    if v >= 1e3:
        return nf_txt(v / 1e3, 1) + 'K'
    return nf_txt(v, 0)


def nf_txt(v, d=0):
    try:
        return ('%.' + str(d) + 'f') % float(v)
    except Exception:
        return '-'


def price_txt(v):
    v = float(v or 0)
    if v and v < 0.01:
        return '%.3e' % v
    return '$' + (nf_txt(v, 2) if v < 1000 else nf_txt(v, 0))


def short_w(w):
    w = str(w or 'không rõ ví')
    return w[:5] + '…' + w[-4:] if len(w) > 12 else w


def esc_tg(s):
    return str(s if s is not None else '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def tg_alert_text(a, lang):
    """Dung lai cau canh bao theo ngon ngu, tu so lieu goc (khong dich cau da lap so)."""
    rk = a.get('rk')
    if not rk:
        return a.get('text') or ''
    L = TGL.get(lang or 'vi') or TGL['vi']
    tpl = L.get(rk) or TGL['vi'].get(rk) or ''
    if rk in ('whale_buy', 'whale_sell'):
        return tg_fix_units(tpl % (a.get('to') or '', a.get('walletShort') or ''), lang)
    return tg_fix_units(tpl % (a.get('pct') or a.get('delta') or '', a.get('from') or '', a.get('to') or ''), lang)


def tg_message(tok, alerts, snap, note=None, lang=None):
    """Mot tin nhan cho mot token. HTML (parse_mode=HTML)."""
    L = TGL.get(lang or 'vi') or TGL['vi']
    ch = ((snap or {}).get('level') or '')
    ch = TG_LVL.get(lang or 'vi', {}).get(ch, ch)
    head = '<b>' + esc_tg(tok.get('symbol') or '?') + '</b> · ' + esc_tg(tok.get('chain') or '') + \
           (' · <i>' + esc_tg(note) + '</i>' if note else '')
    lines = ['⚠ ' + head]
    for a in alerts:
        lines.append('• ' + esc_tg(tg_alert_text(a, lang)))
    sc = (snap or {}).get('score')
    if isinstance(sc, (int, float)):
        lines.append(L['score'] + ' ' + nf_txt(sc, 0) + '/100' +
                     (' (' + esc_tg(ch) + ')' if ch else '') +
                     ' — ' + (L['dims'] % (str((snap or {}).get('dimsScored') or 0),
                                           str((snap or {}).get('dimsTotal') or 5))))
    if (snap or {}).get('liq') is not None:
        lines.append(L['liq'] + ' ' + usd_txt_lang(snap['liq'], lang))
    if (snap or {}).get('holders') is not None:
        lines.append(L['holders'] + ' ' + nf_txt(snap['holders'], 0))
    ca = ((snap or {}).get('calls') or [])
    if ca:
        lines.append('<i>' + str(len(ca)) + ' ' + L['calls'] + '</i>')
    # --- khoi so lieu kieu the canh bao (giong cac kenh whale alert) ---
    rich = []
    pr = (snap or {}).get('price')
    if pr:
        pct = None
        for a in (alerts or []):
            if a.get('rk') in ('price_up', 'price_down'):
                pct = a.get('pct')
        rich.append('\U0001F4B0 <b>' + L['price'] + ':</b> ' + price_txt(pr) +
                    ((' (' + str(pct) + '%)') if pct else ''))
    big = 0.0
    for a in (alerts or []):
        if a.get('rk') in ('whale_buy', 'whale_sell'):
            big = max(big, float(a.get('usd') or 0))
    v24 = (snap or {}).get('vol24h')
    if big:
        sline = '\U0001F6A8 <b>' + L['order'] + ':</b> ' + usd_short(big) + ' USD'
        if v24:
            try:
                sline += ' (' + nf_txt(100.0 * big / float(v24), 2) + '%)'
            except Exception:
                pass
        rich.append(sline)
    rows = [x for x in ((snap or {}).get('rows') or []) if isinstance(x, dict) and x.get('ts')]
    if len(rows) >= 2:
        try:
            ts = [float(x['ts']) for x in rows]
            rich.append('\u23F3 <b>' + L['dur'] + ':</b> ' + nf_txt((max(ts) - min(ts)) / 60000.0, 0) + ' ' + L['mins'])
        except Exception:
            pass
    if v24:
        rich.append('\U0001F4CA <b>24h Vol:</b> ' + usd_short(v24) + ' USD')
    if rich:
        lines.extend(rich)
    _TG_LAST_CARD['text'] = '\n'.join(lines)
    _TG_LAST_CARD['snap'] = snap
    _TG_LAST_CARD['tok'] = tok
    return '\n'.join(lines)


# Ngôn ngữ tin nhắn bot: chọn bằng /lang en|vi|zh. Nhãn luật vẫn dựng từ
# khoá ('rk') chứ không dịch câu đã lắp số, nên không lệch số giữa các ngôn ngữ.
TGL = {
    'en': {'score':'Score', 'liq':'Liquidity', 'holders':'Holders', 'calls':'CMC calls this scan',
           'price':'Price', 'order':'Order size', 'dur':'Duration', 'mins':'min',
           'dims':'sum of %s/%s scored dimensions', 'whale_buy':'whale wallet BOUGHT %s — wallet %s',
           'whale_sell':'whale wallet SOLD %s — wallet %s', 'score_above':'score crossed %s (%s to %s)',
           'jump':'score up %s points (%s to %s)', 'liq_drop':'liquidity down %s%% (%s to %s)',
           'hold_drop':'holders down %s%% (%s to %s)', 'whale_out':'whale flow flipped to EXITING',
           'price_up':'price up %s%% (%s to %s)', 'price_down':'price down %s%% (%s to %s)',
           'test':'Test message from Exit Radar at %s. If you can read this, the bot is linked.'},
    'vi': {'score':'Điểm', 'liq':'Thanh khoản', 'holders':'Holder', 'calls':'lời gọi CMC cho lần quét này',
           'price':'Giá', 'order':'Cỡ lệnh', 'dur':'Thời lượng', 'mins':'phút',
           'dims':'tổng của %s/%s chiều chấm được', 'whale_buy':'ví cá mập MUA %s — ví %s',
           'whale_sell':'ví cá mập BÁN %s — ví %s', 'score_above':'điểm vượt %s (%s → %s)',
           'jump':'điểm tăng %s điểm (%s → %s)', 'liq_drop':'thanh khoản giảm %s%% (%s → %s)',
           'hold_drop':'số holder giảm %s%% (%s → %s)', 'whale_out':'dòng tiền ví lớn chuyển sang ĐANG RÚT',
           'price_up':'giá tăng %s%% (%s → %s)', 'price_down':'giá giảm %s%% (%s → %s)',
           'test':'Tin thử từ Exit Radar lúc %s. Nếu bạn thấy tin này, bot đã nối đúng chat.'},
    'zh': {'score':'评分', 'liq':'流动性', 'holders':'持币人数', 'calls':'本次扫描的 CMC 调用次数',
           'price':'价格', 'order':'订单规模', 'dur':'持续时间', 'mins':'分钟',
           'dims':'已评分 %s/%s 个维度之和', 'whale_buy':'巨鲸买入 %s — 钱包 %s',
           'whale_sell':'巨鲸卖出 %s — 钱包 %s', 'score_above':'评分超过 %s（%s → %s）',
           'jump':'评分上升 %s 分（%s → %s）', 'liq_drop':'流动性下降 %s%%（%s → %s）',
           'hold_drop':'持币人数下降 %s%%（%s → %s）', 'whale_out':'巨鲸资金流转为流出',
           'price_up':'价格上涨 %s%%（%s → %s）', 'price_down':'价格下跌 %s%%（%s → %s）',
           'test':'来自 Exit Radar 的测试消息，发送时间 %s。如果你能看到它，说明机器人绑定成功。'}
}


def tg_l(chat, key, *args):
    L = TGL.get(((chat.get('conf') or {}).get('lang') or 'vi'), TGL['vi'])
    s = L.get(key) or TGL['vi'].get(key) or key
    return (s % args) if args else s


TG_HELP = {
    'en': '<b>Exit Radar — alert bot</b>\n/link CODE — link this chat to the watchlist in the web app (code shown under Bot Telegram)\n/status — what you are watching, which rules are on, last scan\n/list — token list + score + rules\n/pause — stop sending (scanning continues)\n/resume — turn alerts back on\n/quiet 23 7 — quiet hours (messages are held and sent when they end)\n/test — send a test message\n/unlink — unlink this chat\n\nNote: the bot only scans while a process runs (your machine with <code>--bot</code>, or cron). Data comes from CMC; each token costs about 8-12 credits per scan.',
    'zh': '<b>Exit Radar — 预警机器人</b>\n/link 绑定码 — 将本聊天绑定到网页里的自选列表（绑定码见网页的 Telegram 机器人板块）\n/status — 查看正在关注的内容、已开启的规则、最近一次扫描\n/list — 代币列表 + 评分 + 规则\n/pause — 暂停发送（仍会扫描）\n/resume — 恢复发送\n/quiet 23 7 — 安静时段（消息暂存，时段结束后统一发送）\n/test — 发送一条测试消息\n/unlink — 解除本聊天绑定\n\n注意：只有进程在运行时机器人才会扫描（本机运行 <code>--bot</code>，或 cron）。数据来自 CMC，每次扫描每个代币约消耗 8-12 个 credit。',
}


def _tg_help_vi():
    return ('<b>Exit Radar — bot cảnh báo</b>\n'
            '/link MÃ — nối chat này với danh sách theo dõi trong web (mã lấy ở mục Bot Telegram)\n'
            '/status — xem đang theo dõi gì, luật nào đang bật, lần quét gần nhất\n'
            '/list — danh sách token + điểm + luật\n'
            '/pause — tạm dừng gửi (vẫn quét)\n'
            '/resume — bật lại\n'
            '/quiet 23 7 — giờ yên tĩnh (tin dồn lại, gửi vào lúc kết thúc)\n'
            '/test — gửi một tin thử\n'
            '/unlink — ngắt chat này khỏi danh sách\n\n'
            'Lưu ý: bot chỉ quét khi tiến trình chạy (máy bạn chạy <code>--bot</code>, hoặc cron). '
            'Số liệu lấy từ CMC, mỗi token tốn khoảng 8-12 credit mỗi lần quét.')


def tg_help(lang='vi'):
    if lang in TG_HELP:
        return TG_HELP[lang]
    return _tg_help_vi()


def tg_code_new(st, n=6):
    ab = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    code = ''.join(ab[int(time.time() * 1000 + i * 7919) % len(ab)] for i in range(n))
    st.setdefault('codes', {})[code] = {'at': int(time.time() * 1000)}
    return code


def tg_link(st, code, chat):
    code = (code or '').strip().upper()
    codes = st.setdefault('codes', {})
    if code not in codes:
        return None
    ch = st.setdefault('chats', {}).setdefault(str(chat['id']), {})
    ch['code'] = code
    ch['title'] = chat.get('title') or chat.get('username') or chat.get('first_name') or str(chat['id'])
    ch['linkedAt'] = int(time.time() * 1000)
    ch.setdefault('pause', False)
    ch.setdefault('brief', [])
    ch.setdefault('snaps', {})
    ch.setdefault('seen', {})
    ch.setdefault('pending', [])
    ch.setdefault('conf', {'quietFrom': 23, 'quietTo': 7, 'cooldownMin': 30, 'maxPerDay': 20})
    del codes[code]
    return ch


def tg_quiet(ch, now=None):
    c = ch.get('conf') or {}
    a, b = int(c.get('quietFrom', 23)), int(c.get('quietTo', 7))
    h = time.localtime(now or time.time()).tm_hour
    return (h >= a or h < b) if a != b else False


def tg_due(ch, a, now_ms):
    """Chong lap: cung mot luat cho cung mot token chi bao lai sau cooldown."""
    c = ch.get('conf') or {}
    cd = int(c.get('cooldownMin', 30)) * 60000
    k = a.get('key') + '|' + a.get('rule')
    last = (ch.get('seen') or {}).get(k)
    if last and (now_ms - last) < cd:
        return False
    return True


def tg_cmd(st, chat, text):
    """Xu ly lenh nguoi dung gui cho bot. Tra ve (tra_loi, co_luu)."""
    t = (text or '').strip()
    low = t.lower()
    cid = str(chat['id'])
    ch = (st.get('chats') or {}).get(cid)
    if low.startswith('/start'):
        parts = t.split()
        if len(parts) > 1:
            got = tg_link(st, parts[1], chat)
            if got:
                return ('Đã nối chat này với danh sách theo dõi.\n' + tg_status(st, cid), True)
            return ('Mã liên kết không đúng hoặc đã dùng. Mở web, mục Bot Telegram, tạo mã mới.', True)
        return (tg_help((chat.get('conf') or {}).get('lang')), False)
    if low.startswith('/help'):
        return (tg_help((chat.get('conf') or {}).get('lang')), False)
    if low.startswith('/link'):
        parts = t.split()
        if len(parts) < 2:
            return ('Dùng: <code>/link MÃ</code> — mã lấy ở mục Bot Telegram trong web.', False)
        got = tg_link(st, parts[1], chat)
        return ((tg_status(st, cid) if got else 'Mã không đúng hoặc đã dùng. Tạo mã mới trong web.'), bool(got))
    if not ch:
        return ('Chat này chưa nối với danh sách nào. Mở web → mục Bot Telegram → tạo mã rồi gửi /link MÃ.', False)
    if low.startswith('/status'):
        return (tg_status(st, cid), False)
    if low.startswith('/list'):
        return (tg_list(ch), False)
    if low.startswith('/pause'):
        ch['pause'] = True
        return ('Đã tạm dừng gửi. Vẫn quét và ghi nhật ký trong web. /resume để bật lại.', True)
    if low.startswith('/resume'):
        ch['pause'] = False
        return ('Đã bật lại.', True)
    if low.startswith('/unlink'):
        st.get('chats', {}).pop(cid, None)
        return ('Đã ngắt chat này. Danh sách trong web không bị xoá.', True)
    if low.startswith('/quiet'):
        p = [x for x in t.split()[1:] if x.isdigit()]
        if len(p) < 2:
            return ('Dùng: <code>/quiet 23 7</code> (từ 23h đến 7h, tin dồn lại gửi sau).', False)
        ch.setdefault('conf', {})['quietFrom'] = int(p[0]) % 24
        ch['conf']['quietTo'] = int(p[1]) % 24
        return ('Đã đặt giờ yên tĩnh %02d:00 → %02d:00.' % (ch['conf']['quietFrom'], ch['conf']['quietTo']), True)
    if low.startswith('/lang'):
        p = t.split()
        code = (p[1].lower() if len(p) > 1 else '')
        if code not in ('en', 'vi', 'zh'):
            return ('Ngôn ngữ tin nhắn hiện tại: <b>%s</b>\nDùng: <code>/lang en</code> · <code>/lang vi</code> · <code>/lang zh</code>' %
                    ((ch.get('conf') or {}).get('lang') or 'vi'), False)
        ch.setdefault('conf', {})['lang'] = code
        return (tg_l(ch, 'test') % time.strftime('%H:%M:%S %d/%m/%Y'), True)
    if low.startswith('/test'):
        return ('Đang gửi thử…', False)
    return ('Không hiểu lệnh này. /help để xem danh sách lệnh.', False)


def tg_status(st, cid):
    ch = (st.get('chats') or {}).get(cid)
    if not ch:
        return 'Chat này chưa nối với danh sách nào.'
    b = ch.get('brief') or []
    conf = ch.get('conf') or {}
    last = ch.get('lastTick') or 0
    return ('Đang theo dõi <b>%d</b> token · %s\n'
            'Giờ yên tĩnh: %02d:00 → %02d:00 · chống lặp: %d phút · tối đa %d tin/ngày\n'
            'Lần quét gần nhất: %s\n'
            'Đã gửi hôm nay: %d\n'
            'Trạng thái: %s') % (len(b), 'ĐANG TẠM DỪNG' if ch.get('pause') else 'đang chạy',
                                 int(conf.get('quietFrom', 23)), int(conf.get('quietTo', 7)),
                                 int(conf.get('cooldownMin', 30)), int(conf.get('maxPerDay', 20)),
                                 (time.strftime('%d/%m %H:%M', time.localtime(last / 1000)) if last else 'chưa quét'),
                                 int((ch.get('sentDay') or {}).get('n') or 0),
                                 ('có tin đang chờ %d' % len(ch.get('pending') or [])) if ch.get('pending') else 'không có tin chờ')


def tg_list(ch):
    b = ch.get('brief') or []
    if not b:
        return 'Danh sách trống.'
    snaps = ch.get('snaps') or {}
    rows = []
    for w in b[:30]:
        s = snaps.get(w.get('key')) or {}
        r = w.get('tg') or {}
        on = [lab for k, lab in TG_RULES if (r.get(k) is not None and r.get(k) is not False)]
        rows.append('• <b>%s</b> (%s) — điểm %s · luật: %s' % (
            esc_tg(w.get('symbol')), esc_tg(w.get('chain')),
            (nf_txt(s.get('score'), 0) if isinstance(s.get('score'), (int, float)) else '—'),
            esc_tg(', '.join(on) if on else 'chưa đặt')))
    return '\n'.join(rows)


def tg_tick(key=None, dry=False, only=None, st=None):
    """Mot vong quet: quet tung token, so voi lan truoc, gui tin da vuot luat.

    dry=True: khong goi Telegram, tra ve nguyen van tin nhan se gui. Dung de
    kiem chung noi dung truoc khi cap token that.
    """
    st = st if st is not None else tg_load()
    now_ms = int(time.time() * 1000)
    out = {'ok': True, 'dry': dry, 'chats': 0, 'scanned': 0, 'fired': 0, 'sent': [],
           'errors': [], 'skipped': [], 'mode': store_mode(), 'botSet': bool(tg_token())}
    for cid, ch in (st.get('chats') or {}).items():
        out['chats'] += 1
        if only and str(only) != str(cid):
            continue
        brief, snaps = ch.get('brief') or [], ch.get('snaps') or {}
        if ch.get('pause'):
            out['skipped'].append('chat %s đang tạm dừng' % cid)
            continue
        limit = TG_MAX_PER_TICK
        for w in brief[:limit]:
            pl, ad = (w.get('key') or ':').split(':', 1)
            snap = tg_scan(pl, ad, key)
            if not snap.get('ok'):
                out['errors'].append({'token': w.get('symbol'), 'error': snap.get('error')})
                continue
            prev = snaps.get(w.get('key'))
            tg_r = dict(w.get('tg') or {})
            tg_r['_seenTs'] = (prev or {}).get('at') or 0
            fired, skipped = tg_eval(prev, snap, tg_r, now_ms)
            for s in skipped:
                out['skipped'].append(w.get('symbol') + ': ' + s)
            snap['level'] = ('THẤP' if (snap.get('score') or 0) < 25 else
                             'ĐỂ MẮT' if (snap.get('score') or 0) < 50 else
                             'CAO' if (snap.get('score') or 0) < 75 else 'NGHIÊM TRỌNG')
            snaps[w.get('key')] = snap
            out['scanned'] += 1
            keep = []
            for a in fired:
                a['key'] = w.get('key')
                a['symbol'] = w.get('symbol')
                if tg_due(ch, a, now_ms):
                    keep.append(a)
                    ch.setdefault('seen', {})[a['key'] + '|' + a['rule']] = now_ms
            if not keep:
                continue
            out['fired'] += len(keep)
            ch['lastTick'] = now_ms
            texts = [(w, tg_message(w, keep, snap, note=w.get('note'), lang=((ch.get('conf') or {}).get('lang') or 'vi'))) for w in [w]]
            if tg_quiet(ch) and not dry:
                ch.setdefault('pending', []).extend(
                    [{'text': tx, 'key': w.get('key'), 'at': now_ms} for w, tx in texts])
                out['skipped'].append('%s: đang giờ yên tĩnh, dồn lại' % w.get('symbol'))
                continue
            day = time.strftime('%Y-%m-%d')
            sd = ch.setdefault('sentDay', {'d': day, 'n': 0})
            if sd.get('d') != day:
                sd['d'], sd['n'] = day, 0
            if sd['n'] >= int((ch.get('conf') or {}).get('maxPerDay', 20)):
                out['skipped'].append('%s: đã chạm trần tin/ngày' % w.get('symbol'))
                continue
            for w, tx in texts:
                r = tg_send(chat_id=cid, text=tx, st=st, ch=ch, dry=dry,
                            markup=tg_markup(ch.get('appUrl'), w.get('key')))
                if r.get('ok'):
                    sd['n'] += 1
                    out['sent'].append({'to': cid, 'token': w.get('symbol'), 'chars': len(tx)})
                elif r.get('dry'):
                    out['sent'].append({'dry': True, 'to': cid, 'token': w.get('symbol'),
                                        'text': tx})
                else:
                    out['errors'].append({'token': w.get('symbol'), 'telegram': r.get('error'),
                                          'status': r.get('status'), 'retryAfter': r.get('retry_after')})
                    if r.get('retry_after'):
                        time.sleep(min(20, int(r['retry_after'])))
        # xả tin dồn khi hết giờ yên tĩnh
        if ch.get('pending') and not tg_quiet(ch) and not dry:
            p = ch['pending'][:6]
            ch['pending'] = []
            for it in p:
                tg_send(chat_id=cid, text=it['text'], st=st, ch=ch)
            out['sent'].append({'to': cid, 'flushed': len(p)})
        ch['snaps'] = snaps
    out['stored'] = tg_save(st)
    out['store'] = store_mode()
    return out


def tg_poll(key=None, interval=600):
    """Che do chay tren may: nhan lenh bang long polling + quet theo chu ky."""
    print('Bot Telegram: %s' % ('đã có token' if tg_token() else 'CHƯA có TELEGRAM_BOT_TOKEN'))
    print('Kho lưu trữ: %s' % store_mode())
    me = tg_call('getMe', {})
    print('getMe: %s' % (('@' + me['result']['username']) if me.get('ok') else me.get('error')))
    st = tg_load()
    offset, last = None, 0
    while True:
        try:
            r = tg_call('getUpdates', {'offset': offset, 'timeout': 25,
                                       'allowed_updates': ['message']}, timeout=40)
            for u in (r.get('result') or []):
                offset = u['update_id'] + 1
                m = u.get('message') or {}
                chat, txt = m.get('chat'), m.get('text')
                if not chat or not txt:
                    continue
                ans, save = tg_cmd(st, chat, txt)
                if save:
                    tg_save(st)
                if ans and not txt.lower().startswith('/test'):
                    tg_send(chat['id'], ans, st=st, ch=(st.get('chats') or {}).get(str(chat['id'])))
                elif txt.lower().startswith('/test'):
                    tg_send(chat['id'], 'Tin thử từ Exit Radar lúc ' +
                            time.strftime('%H:%M:%S %d/%m/%Y') + '.\nNếu bạn thấy tin này, bot đã nối đúng chat.',
                            st=st, ch=(st.get('chats') or {}).get(str(chat['id'])))
            if time.time() - last > interval:
                last = time.time()
                res = tg_tick(key=key, st=st)
                print('[%s] quét %d token · %d cảnh báo · gửi %d tin · lỗi %d' % (
                    time.strftime('%H:%M:%S'), res['scanned'], res['fired'],
                    len([s for s in res['sent'] if not s.get('dry')]), len(res['errors'])))
                for e in res['errors'][:3]:
                    print('   lỗi:', e)
        except KeyboardInterrupt:
            print('\ndừng bot.')
            return
        except Exception as e:
            print('vòng lặp gặp lỗi:', e)
            time.sleep(5)


def tg_http(action, body=None, q=None):
    """Diem vao HTTP cho giao dien web. Khong bao gio tra token ra ngoai."""
    body = body or {}
    q = q or {}
    st = tg_load()
    action = (action or 'status').lower()
    mode, bot = store_mode(), bool(tg_token())
    base = {'ok': True, 'botSet': bot, 'store': mode,
            'botUsername': None, 'hint': None}
    if not bot:
        base['hint'] = ('Máy chủ chưa đặt TELEGRAM_BOT_TOKEN. Tạo bot với @BotFather rồi đặt biến '
                        'môi trường TELEGRAM_BOT_TOKEN (và chạy bot bằng "python exit_radar_server.py --bot" '
                        'trên máy luôn bật, hoặc cron gọi /api/cron/tick).')
    if mode == 'khong-ghi-duoc' and not kv_on():
        base['hint'] = (base['hint'] or '') + (' Vercel không ghi được tệp: cần Upstash Redis '
                                               '(UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN) để lưu luật.')
    if mode in ('khong-ghi-duoc', 'upstash') or True:
        me = tg_call('getMe', {}) if bot and action in ('code', 'status', 'test') else {'ok': False}
        if me.get('ok'):
            base['botUsername'] = me['result'].get('username')
    if action == 'code':
        code = tg_code_new(st)
        tg_save(st)
        base['code'] = code
        base['deep'] = ('https://t.me/' + (base['botUsername'] or '<bot>') + '?start=' + code)
        base['expiresInMin'] = 60
        return base
    if action == 'status':
        code = (body.get('code') or q.get('code', ['']))[0]
        ch = None
        for cid, c in (st.get('chats') or {}).items():
            if code and c.get('code') == code:
                ch = c
        for cid, c in (st.get('chats') or {}).items():
            if code and c.get('code') != code:
                continue
            if ch is None:
                ch = c
        base['linked'] = bool(ch and code and ch.get('code') == code)
        if ch:
            base['chat'] = {'id': cid if 'cid' in dir() else None, 'title': ch.get('title'),
                            'tokens': len(ch.get('brief') or []),
                            'lastTick': ch.get('lastTick'), 'pause': ch.get('pause'),
                            'sentToday': (ch.get('sentDay') or {}).get('n'),
                            'pending': len(ch.get('pending') or [])}
        base['chats'] = len(st.get('chats') or {})
        return base
    if action == 'push':
        code = body.get('code')
        ch = None
        for cid, c in (st.get('chats') or {}).items():
            if c.get('code') == code:
                ch = c
                break
        if not ch:
            return {'ok': False, 'error': 'Chưa nối chat. Gửi /link MÃ cho bot trước.'}
        ch['brief'] = body.get('watch') or []
        if body.get('appUrl'):
            ch['appUrl'] = body['appUrl']
        if body.get('conf'):
            ch['conf'] = body['conf']
        tg_save(st)
        return {'ok': True, 'tokens': len(ch['brief']), 'chat': ch.get('title'),
                'hint': 'Đã đẩy danh sách. Bot sẽ quét theo chu kỳ và gửi khi luật bị vượt.'}
    if action == 'test':
        code = body.get('code')
        ch = None
        for cid, c in (st.get('chats') or {}).items():
            if c.get('code') == code:
                ch = c
                break
        if not ch:
            return {'ok': False, 'error': 'Chưa nối chat với mã này.'}
        cid = [k for k, c in st['chats'].items() if c is ch][0]
        r = tg_send(cid, 'Tin thử từ Exit Radar — nếu bạn thấy tin này, bot đã nối đúng chat.\n'
                    'Đang theo dõi %d token.' % len(ch.get('brief') or []), st=st, ch=ch)
        return {'ok': bool(r.get('ok')), 'telegram': r.get('error'), 'status': r.get('status'),
                'retryAfter': r.get('retry_after'), 'throttled': r.get('throttled')}
    if action == 'preview':
        return tg_tick(key=tg_key_from(body.get('key')), dry=True, only=body.get('chat'))
    if action == 'unlink':
        code = body.get('code')
        for cid, c in list((st.get('chats') or {}).items()):
            if c.get('code') == code:
                st['chats'].pop(cid)
        tg_save(st)
        return {'ok': True}
    return {'ok': False, 'error': 'action không hỗ trợ: ' + action}


def tg_key_from(k):
    return (k or os.environ.get('CMC_API_KEY') or None)


def tg_webhook(update, headers=None):
    """Webhook (neu dat): xac thuc bang header do Telegram gui."""
    sec = tg_secret()
    if sec and (headers or {}).get('X-Telegram-Bot-Api-Secret-Token') != sec:
        return {'ok': False, 'error': 'sai secret token'}
    st = tg_load()
    m = (update or {}).get('message') or {}
    chat, txt = m.get('chat'), m.get('text')
    if not chat or not txt:
        return {'ok': True, 'ignored': True}
    ans, save = tg_cmd(st, chat, txt)
    if save:
        tg_save(st)
    if ans:
        tg_send(chat['id'], ans, st=st, ch=(st.get('chats') or {}).get(str(chat['id'])))
    return {'ok': True}



# --------------------------------------------------- key CMC làm trung tâm
# Thu tu uu tien: key nguoi dung dan trong trinh duyet (header) > bien moi truong
# CMC_API_KEY > tep ER_DATA_DIR/cmc_key > khong co. Nho vay ban live dung key
# cua may chu cho MOI nguoi dung, con nguoi co key rieng van ghi de duoc.
# KHONG bao gio dat key vao ma nguon: repo nay la cong khai, commit key la phat
# tan key cho ca the gioi. Dat trong bien moi truong cua Vercel.
def _load_env_file():
    p = os.path.join(ROOT, '.env')
    try:
        with open(p, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except Exception:
        pass


_load_env_file()


def key_file_path():
    return os.path.join(TG_DIR, 'cmc_key')


def key_resolve(header=None):
    """Tra ve (key, nguon) - nguon de hien thi cho nguoi dung biet key nao dang chay."""
    h = (header or '').strip()
    if h:
        return h, 'key dán trong trình duyệt'
    e = (os.environ.get('CMC_API_KEY') or '').strip()
    if e:
        return e, 'biến môi trường CMC_API_KEY'
    try:
        with open(key_file_path(), encoding='utf-8') as f:
            v = f.read().strip()
        if v:
            return v, 'tệp ' + key_file_path()
    except Exception:
        pass
    return None, 'không có key'


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
        return key_resolve(self.headers.get('X-CMC-Key'))[0]

    def _key_src(self):
        return key_resolve(self.headers.get('X-CMC-Key'))[1]

    def do_OPTIONS(self):
        self._send(204, b'')

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        g = lambda k, d='': (q.get(k, [d])[0] or d)
        path = OPMAP.get((g('op') or '').strip().lower(), u.path)
        try:
            n = int(self.headers.get('Content-Length') or 0)
            body = json.loads(self.rfile.read(n).decode('utf-8') or '{}') if n else {}
        except Exception:
            body = {}
        try:
            if path == '/api/tg':
                return self._send(200, tg_http(g('action'), body, q))
            if path in ('/api/telegram', '/api/tg/webhook'):
                hdr = {k: v for k, v in self.headers.items()}
                return self._send(200, tg_webhook(body, hdr))
            return self._send(404, {'error': 'không có đường dẫn này'})
        except Exception as e:
            return self._send(500, {'error': str(e)})

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        g = lambda k, d='': (q.get(k, [d])[0] or d)
        path = OPMAP.get((g('op') or '').strip().lower(), u.path)
        try:
            if path in ('/', '/index.html', '/api/index'):
                p = os.path.join(ROOT, 'exit-radar-app.html')
                if os.path.exists(p):
                    return self._send(200, open(p, 'rb').read(), 'text/html; charset=utf-8')
                return self._send(404, {'error': 'không thấy exit-radar-app.html'})
            if path == '/api/health':
                k = self._key()
                probe = cmc('/v1/dex/search', {'q': 'BTC'}, k)
                ki = key_info(k) if k else None
                return self._send(200, {'ok': True, 'server': 'exit-radar',
                                        'cmcReachable': probe['ok'], 'cmcStatus': probe['status'],
                                        'keyProvided': bool(k), 'keySource': self._key_src(),
                                        'keyValid': bool(ki and ki.get('ok')),
                                        'keyError': (ki or {}).get('error'),
                                        'plan': ki if (ki and ki.get('ok')) else None,
                                        'base': CMC_BASE if k else PUBLIC,
                                        'marketsKeyless': True,
                                        'cacheTtlSec': CACHE_TTL, 'stats': dict(STATS)})
            if path == '/api/search':
                return self._send(200, search(g('q'), self._key()))
            if path == '/api/markets':
                return self._send(200, markets(self._key()))
            if path == '/api/marketctx':
                return self._send(200, market_context(self._key()))
            if path == '/api/evidence':
                return self._send(200, evidence(g('kind'), g('platform'), g('address'),
                                                g('cid') or None, self._key(), g('path') or None,
                                                (int(g('days')) if g('days').isdigit() else 30),
                                                (int(g('limit')) if g('limit').isdigit() else 16)))
            if path == '/api/scan':
                pl, ad = g('platform'), g('address')
                if not pl or not ad:
                    return self._send(400, {'error': 'thiếu platform hoặc address'})
                out = build(pl, ad, self._key())
                return self._send(200 if 'error' not in out else 502, out)
            if path == '/api/calls':
                return self._send(200, {'calls': _calls[-60:], 'stats': dict(STATS)})
            if path == '/api/tg':
                return self._send(200, tg_http(g('action'), None, q))
            if path == '/api/cron/tick':
                if not tg_secret() or (g('secret') or '') != tg_secret():
                    return self._send(403, {'error': 'thiếu hoặc sai secret'})
                return self._send(200, tg_tick(self._key()))
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
    elif '--bot' in sys.argv:
        i = sys.argv.index('--bot')
        iv = 600
        if '--every' in sys.argv:
            iv = int(sys.argv[sys.argv.index('--every') + 1])
        tg_poll(os.environ.get('CMC_API_KEY') or None, iv)
    else:
        srv = ThreadingHTTPServer(('127.0.0.1', PORT), H)
        print('Exit Radar server → http://127.0.0.1:%d' % PORT)
        print('key CMC: %s' % ('đã có trong biến môi trường' if os.environ.get('CMC_API_KEY') else 'chưa có (chế độ công khai)'))
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print('\ndừng.')
