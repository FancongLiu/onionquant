import time, json, urllib.request, ssl

API_KEY = 'sk-sp-UCTrtaXyvLd1NFrXrBS7LgRJqZDknWn3'
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

tests = [
    ('Node1-Anthropic', 'http://122.51.254.107:55888/anthropic/v1/messages', 'anthropic'),
    ('Node1-OpenAI',   'http://122.51.254.107:55888/openai/v1/chat/completions', 'openai'),
    ('Node2-Anthropic', 'https://api1.halphen.cn:55888/anthropic/v1/messages', 'anthropic'),
    ('Node2-OpenAI',   'https://api1.halphen.cn:55888/openai/v1/chat/completions', 'openai'),
]

print("=" * 60)
print("GLM-5.2 Node Test")
print("=" * 60)

for name, url, proto in tests:
    if proto == 'anthropic':
        body = {"model":"glm-5.2","max_tokens":200,"messages":[{"role":"user","content":"explain Python decorator in 2 short sentences"}]}
        headers = {'x-api-key': API_KEY, 'anthropic-version': '2023-06-01', 'Content-Type': 'application/json'}
    else:
        body = {"model":"glm-5.2","max_tokens":200,"messages":[{"role":"user","content":"explain Python decorator in 2 short sentences"}]}
        headers = {'Authorization': 'Bearer ' + API_KEY, 'Content-Type': 'application/json'}
    
    payload = json.dumps(body).encode()
    start = time.time()
    try:
        if 'https' in url:
            req = urllib.request.Request(url, data=payload, headers=headers)
            resp = urllib.request.urlopen(req, timeout=120, context=ctx)
        else:
            req = urllib.request.Request(url, data=payload, headers=headers)
            resp = urllib.request.urlopen(req, timeout=120)
        elapsed = time.time() - start
        raw = resp.read().decode()
        data = json.loads(raw)
        
        if proto == 'anthropic':
            text = ' '.join([b.get('text','') for b in data.get('content',[]) if b.get('type')=='text'])
            out_tok = data.get('usage',{}).get('output_tokens',0)
        else:
            text = data['choices'][0]['message']['content']
            out_tok = data.get('usage',{}).get('completion_tokens',0)
        
        tps = out_tok / elapsed if elapsed > 0 else 0
        print('[%s] OK  %.1fs | %d tok | %d tok/s' % (name, elapsed, out_tok, tps))
        print('  %s' % text[:120].replace('\n',' '))
    except Exception as e:
        elapsed = time.time() - start
        print('[%s] FAIL (%.1fs): %s' % (name, elapsed, str(e)[:120]))
    print()

print("=" * 60)
print("Done")
