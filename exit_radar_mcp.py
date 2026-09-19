#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Exit Radar MCP server (stdio, JSON-RPC 2.0).

Bo tro cho CMC MCP / CMC Agent Hub: CMC MCP tra du lieu thi truong tho, con MCP nay
tra KET LUAN da cham diem cua Exit Radar (diem 0-100 + so chieu chấm duoc + dan chung).

Chay:
    python3 exit_radar_server.py           # may chu du lieu (mac dinh 127.0.0.1:8787)
    python3 exit_radar_mcp.py              # MCP server noi vao may chu tren qua stdio

Bien moi truong:
    EXIT_RADAR_URL      dia chi may chu Exit Radar (mac dinh http://127.0.0.1:8787)
    EXIT_RADAR_TIMEOUT  giay cho toi da moi loi goi (mac dinh 90)
    CMC_API_KEY         key CMC gui kem qua header X-CMC-Key (tuy chon)
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

SERVER_NAME = 'exit-radar'
SERVER_VERSION = '1.1.0'
PROTOCOL = '2025-06-18'
BASE = os.environ.get('EXIT_RADAR_URL', 'http://127.0.0.1:8787').rstrip('/')
TIMEOUT = float(os.environ.get('EXIT_RADAR_TIMEOUT', '90') or 90)


def _get(path, params=None):
    url = BASE + path
    clean = {k: v for k, v in (params or {}).items() if v not in (None, '')}
    if clean:
        url += ('&' if '?' in url else '?') + urllib.parse.urlencode(clean)
    req = urllib.request.Request(url, headers={'Accept': 'application/json'})
    key = os.environ.get('CMC_API_KEY')
    if key:
        req.add_header('X-CMC-Key', key)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
    except Exception as e:
        raise RuntimeError('khong goi duoc ' + url + ': ' + str(e))
    try:
        return json.loads(raw)
    except Exception:
        return {'ok': False, 'raw': raw[:4000]}


TOOLS = [
    {
        'name': 'er_health',
        'description': ('Trang thai may chu Exit Radar: da ket noi chua, che do du lieu, co key CMC chua, '
                        'nguon key (header/env/tep), so chiều chấm được. Goi dau tien khi co loi.'),
        'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False},
    },
    {
        'name': 'er_search',
        'description': ('Tim token DEX theo ten, symbol hoac dia chi contract. Tra danh sach ung vien '
                        'kem chuoi, dia chi, cap DEX. Dung truoc er_scan khi chua chac dia chi.'),
        'inputSchema': {'type': 'object', 'properties': {
            'q': {'type': 'string', 'description': 'tu khoa: symbol, ten, hoac dia chi contract'}},
            'required': ['q'], 'additionalProperties': False},
    },
    {
        'name': 'er_scan',
        'description': ('Cham diem rui ro cau truc cho MOT token DEX: diem 0-100, muc rui ro, so chiều chấm '
                        'được (dimsScored/dimsTotal), diem tung chiều, danh sach dan chung (pool, vi lon, giao dich). '
                        'Chiều nao thieu du lieu thi bi loai, khong tinh la 0.'),
        'inputSchema': {'type': 'object', 'properties': {
            'q': {'type': 'string', 'description': 'symbol hoac dia chi contract'},
            'chain': {'type': 'string', 'description': 'tuy chon: loc theo chuoi, vi du solana, bsc, base'}},
            'required': ['q'], 'additionalProperties': False},
    },
    {
        'name': 'er_evidence',
        'description': ('Bang dan chung cua mot token: tung so lieu tho dung de cham diem, nguon endpoint CMC, '
                        'thoi diem lay. Dung khi can trich nguon cho bao cao.'),
        'inputSchema': {'type': 'object', 'properties': {
            'q': {'type': 'string', 'description': 'symbol hoac dia chi contract'}},
            'required': ['q'], 'additionalProperties': False},
    },
    {
        'name': 'er_marketctx',
        'description': ('Boi canh thi truong tong: von hoa, BTC/ETH chi phoi, stablecoin, khoi luong phai sinh, '
                        'chi so so hai & tham lam, mua altcoin. Dung de dat ket qua vao boi canh.'),
        'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False},
    },
    {
        'name': 'er_calls',
        'description': ('So loi goi CMC va so credit da dung cho lan quet gan nhat. Dung de uoc luong ngan sach truoc khi quet hang loat.'),
        'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False},
    },
    {
        'name': 'er_mcp_vs_cmc',
        'description': ('Huong dan chon duong: khi nao goi MCP nay (ket luan da cham diem), khi nao goi CMC MCP / '
                        'x402 / REST (du lieu tho), va cac bay endpoint CMC da kiem chung.'),
        'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False},
    },
]

_GUIDE = {
    'dung_mcp_nay_khi': [
        'can mot KET LUAN: token nay rui ro khong, vi sao, va dan chung o dau',
        'can diem 0-100 kem so chiều chấm được de so sanh nhieu token',
        'can boi canh thi truong va ngan sach credit truoc khi quet hang loat',
    ],
    'dung_cmc_mcp_hoac_rest_khi': [
        'can du lieu tho chua qua xu ly: gia, nen, so du vi, danh sach cap DEX',
        'can endpoint khong co trong Exit Radar: listings, converters, derivatives, exchange',
        'chay khong co key: x402 tra tung request bang USDC tren Base (0.01 USD/request)',
    ],
    'duong_ket_noi_cmc': {
        'mcp_x402': 'https://mcp.coinmarketcap.com/x402/mcp (streamable HTTP, thanh toan x402)',
        'mcp_chuan': 'https://pro.coinmarketcap.com/api/documentation/ai-agent-hub/mcp',
        'skills_mo': 'https://github.com/coinmarketcap-official/skills-for-ai-agents-by-coinmarketcap',
        'cli': 'CMC CLI (Agent Hub)',
        'rest': 'https://pro-api.coinmarketcap.com (can key Pro; KHONG goi /public-api kem key)',
    },
    'bay_da_kiem_chung': [
        '/public-api + key -> 401 error_code 1001; co key thi doi sang pro-api',
        'v2/.../ohlcv/historical -> 403 error_code 1006; dung v1/cryptocurrency/quotes/historical',
        'v1/dex/holders/trend/list -> 403; holders/list -> 500 "The system is busy"',
        'dex/search khop CHUOI CON: phai doi chieu dia chi contract',
        'pcid = nen tang (Solana 5426), cid = token (BONK 23095); txId la so noi bo, khong phai ma giao dich',
    ],
}


def tool_call(name, args):
    args = args or {}
    if name == 'er_health':
        return _get('/api/health')
    if name == 'er_search':
        return _get('/api/search', {'q': args.get('q')})
    if name == 'er_scan':
        return _get('/api/scan', {'q': args.get('q'), 'chain': args.get('chain')})
    if name == 'er_evidence':
        return _get('/api/evidence', {'q': args.get('q')})
    if name == 'er_marketctx':
        return _get('/api/marketctx')
    if name == 'er_calls':
        return _get('/api/calls')
    if name == 'er_mcp_vs_cmc':
        return _GUIDE
    raise ValueError('khong biet tool: ' + str(name))


def handle(req):
    mid = req.get('id')
    method = req.get('method')
    if method == 'initialize':
        return {'jsonrpc': '2.0', 'id': mid, 'result': {
            'protocolVersion': PROTOCOL,
            'capabilities': {'tools': {'listChanged': False}},
            'serverInfo': {'name': SERVER_NAME, 'version': SERVER_VERSION}}}
    if method in ('notifications/initialized', 'notifications/cancelled'):
        return None
    if method == 'ping':
        return {'jsonrpc': '2.0', 'id': mid, 'result': {}}
    if method == 'tools/list':
        return {'jsonrpc': '2.0', 'id': mid, 'result': {'tools': TOOLS}}
    if method == 'tools/call':
        p = req.get('params') or {}
        name = p.get('name')
        try:
            out = tool_call(name, p.get('arguments'))
            text = json.dumps(out, ensure_ascii=False, indent=2)
            if len(text) > 120000:
                text = text[:120000] + '\n... (da cat bot)'
            return {'jsonrpc': '2.0', 'id': mid, 'result': {
                'content': [{'type': 'text', 'text': text}], 'isError': False}}
        except Exception as e:
            return {'jsonrpc': '2.0', 'id': mid, 'result': {
                'content': [{'type': 'text', 'text': 'Loi: ' + str(e)}], 'isError': True}}
    return {'jsonrpc': '2.0', 'id': mid, 'error': {'code': -32601, 'message': 'Method not found: ' + str(method)}}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue
        try:
            resp = handle(req)
        except Exception as e:
            resp = {'jsonrpc': '2.0', 'id': req.get('id'), 'error': {'code': -32603, 'message': str(e)}}
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + '\n')
            sys.stdout.flush()


if __name__ == '__main__':
    main()
