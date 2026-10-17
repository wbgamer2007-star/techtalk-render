#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render-এর জন্য র‍্যাপার। techtalk_termux_v3_1.py একদম অপরিবর্তিত থাকে।
- বট ভেতরে 127.0.0.1:8081-এ চলে (যেমন ফোনে চলত)
- এই ফাইল Render-এর পাবলিক PORT-এ শুনে:
    /webhook  -> সরাসরি বটে (Meta-র জন্য)
    /healthz  -> "ok" (UptimeRobot-এর পিং-এর জন্য)
    বাকি সব (সেটিংস পেজ) -> ইউজারনেম/পাসওয়ার্ড লাগবে (env: ADMIN_USER, ADMIN_PASS)
"""
import os, sys, time, json, base64, hmac, subprocess, threading, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.getenv('BOT_FILE') or sorted(f for f in os.listdir(HERE) if f.startswith('techtalk_termux') and f.endswith('.py'))[-1]
PUBLIC_PORT = int(os.getenv('PORT', '10000'))
INNER = 8081
ADMIN_USER = os.getenv('ADMIN_USER', 'admin')
ADMIN_PASS = os.getenv('ADMIN_PASS', '')

def log(*a): print(time.strftime('%H:%M:%S'), '[render]', *a, flush=True)

def prepare_storage():
    d = os.getenv('DATA_DIR', '/data')  # Render Disk থাকলে এখানে মাউন্ট করুন
    if os.path.isdir(d) and os.access(d, os.W_OK):
        os.makedirs(os.path.join(d, 'chats'), exist_ok=True)
        for name in ('settings.json', 'memory.db', 'chats', 'webhook_url.txt'):
            link = os.path.join(HERE, name); target = os.path.join(d, name)
            if os.path.islink(link): continue
            if os.path.isdir(link) and not os.listdir(link): os.rmdir(link)
            if not os.path.exists(link): os.symlink(target, link)
        log('স্থায়ী ডিস্ক ব্যবহার হচ্ছে:', d)
    else:
        log('⚠️ স্থায়ী ডিস্ক নেই: রিস্টার্ট হলে চ্যাট মেমোরি মুছে যাবে (সেটিংস SETTINGS_JSON env থেকে ফিরবে)')
    sp = os.path.join(HERE, 'settings.json')
    if not os.path.exists(sp) and os.getenv('SETTINGS_JSON'):
        try:
            json.loads(os.environ['SETTINGS_JSON'])
            open(sp, 'w', encoding='utf-8').write(os.environ['SETTINGS_JSON']); log('settings.json তৈরি হলো (env থেকে)')
        except Exception as e: log('SETTINGS_JSON ভুল:', e)
    url = os.getenv('RENDER_EXTERNAL_URL')
    if url:
        try: open(os.path.join(HERE, 'webhook_url.txt'), 'w', encoding='utf-8').write(url.rstrip('/') + '/webhook')
        except Exception: pass

def run_bot():
    env = dict(os.environ, PORT=str(INNER), PYTHONUNBUFFERED='1')
    while True:
        log('বট চালু হচ্ছে:', BOT)
        p = subprocess.Popen([sys.executable, os.path.join(HERE, BOT)], cwd=HERE, env=env)
        p.wait(); log('বট থেমে গেছে, ৫ সেকেন্ড পর আবার চালু'); time.sleep(5)

class P(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _out(self, code, body, ct='text/plain; charset=utf-8', extra=None):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code); self.send_header('Content-Type', ct); self.send_header('Content-Length', str(len(b)))
        for k, v in (extra or {}).items(): self.send_header(k, v)
        self.end_headers()
        if self.command != 'HEAD': self.wfile.write(b)
    def _authed(self):
        if not ADMIN_PASS: return False
        h = self.headers.get('Authorization') or ''
        try: u, _, p = base64.b64decode(h.split(' ', 1)[1]).decode().partition(':')
        except Exception: return False
        return hmac.compare_digest(u, ADMIN_USER) and hmac.compare_digest(p, ADMIN_PASS)
    def _proxy(self):
        path = self.path
        if path.split('?')[0] == '/healthz': return self._out(200, 'ok')
        if not path.startswith('/webhook'):
            if not ADMIN_PASS: return self._out(403, 'ADMIN_PASS env সেট করা নেই, তাই সেটিংস পেজ বন্ধ।')
            if not self._authed(): return self._out(401, 'লগইন দরকার', extra={'WWW-Authenticate': 'Basic realm="Tech&Talk"'})
        n = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(n) if n else None
        hd = {k: v for k, v in self.headers.items() if k.lower() in ('content-type', 'x-ttb', 'x-hub-signature-256')}
        hd['Host'] = f'127.0.0.1:{INNER}'  # বট ভাবে এটা লোকাল রিকোয়েস্ট
        try:
            with urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{INNER}{path}', data=body, headers=hd, method=self.command), timeout=60) as r:
                code, data, ct = r.status, r.read(), r.headers.get('Content-Type', 'text/plain')
        except urllib.error.HTTPError as e: code, data, ct = e.code, e.read(), e.headers.get('Content-Type', 'text/plain')
        except Exception: return self._out(503, 'বট চালু হচ্ছে, কিছুক্ষণ পর চেষ্টা করুন')
        self._out(code, data, ct)
    do_GET = do_POST = do_HEAD = _proxy

if __name__ == '__main__':
    prepare_storage()
    threading.Thread(target=run_bot, daemon=True).start()
    log('পাবলিক পোর্ট:', PUBLIC_PORT)
    ThreadingHTTPServer(('0.0.0.0', PUBLIC_PORT), P).serve_forever()
