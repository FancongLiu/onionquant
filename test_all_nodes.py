import time, json, urllib.request, ssl

API_KEY = 'sk-sp-UCTrtaXyvLd1NFrXrBS7LgRJqZDknWn3'

# 所有待测端点
endpoints = [
    # 节点1 - Anthropic (已知可用, 做基准)
    ('节点1 Anthropic', 'http://122.51.254.107:55888/anthropic/v1/messages', 'anthropic'),
    # 节点1 - OpenAI ✨新
    ('节点1 OpenAI', 'http://122.51.254.107:55888/openai/v1/chat/completions', 'openai'),
    # 节点2 - Anthropic (HTTPS)
    ('节点2 Anthropic', 'https://api1.halphen.cn:55888/anthropic/v1/messages', 'anthropic'),
    # 节点2 - OpenAI (HTTPS) ✨新
    ('节点2 OpenAI', 'https://api1.halphen.cn:55888/openai/v1/chat/completions', 'openai'),
]

def build_request(url, protocol):
    if protocol == 'anthropic':
        body = {
            "model": "glm-5.2",
            "max_tokens": 100,
            "messages": [{"role": "user", "content": "say hello in 3 words"}]
        }
        headers = {
            'x-api-key': API_KEY,
            'anthropic-version': '2023-06-01',
            'Content-Type': 'application/json'
        }
    else:  # openai
        body = {
            "model": "glm-5.2",
            "max_tokens": 100,
            "messages": [{"role": "user", "content": "say hello in 3 words"}]
        }
        headers = {
            'Authorization': f'Bearer {API_KEY}',
            'Content-Type': 'application/json'
        }
    return json.dumps(body).encode(), headers

def parse_response(raw, protocol):
    data = json.loads(raw)
    if protocol == 'anthropic':
        text = ' '.join([b.get('text','') for b in data.get('content',[]) if b.get('type')=='text'])
        return text, data.get('usage',{}).get('output_tokens',0), data.get('model','?')
    else:  # openai
        choices = data.get('choices', [{}])
        text = choices[0].get('message', {}).get('content', '')
        return text, data.get('usage',{}).get('completion_tokens',0), data.get('model','?')

print("=" * 70)
print("GLM-5.2 备用节点全量测试")
print("=" * 70)

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

for name, url, protocol in endpoints:
    body, headers = build_request(url, protocol)
    start = time.time()
    try:
        if url.startswith('https'):
            req = urllib.request.Request(url, data=body, headers=headers)
            resp = urllib.request.urlopen(req, timeout=30, context=ctx)
        else:
            req = urllib.request.Request(url, data=body, headers=headers)
            resp = urllib.request.urlopen(req, timeout=30)
        elapsed = time.time() - start
        raw = resp.read().decode()
        text, tokens, model = parse_response(raw, protocol)
        tps = tokens / elapsed if elapsed > 0 else 0
        status = '✅ 可用'
        print(f'[{name}] {status}')
        print(f'  耗时: {elapsed:.1f}s | 输出: {tokens} tok | 速度: {tps:.0f} tok/s | 模型: {model}')
        print(f'  响应: {text[:100]}')
    except urllib.error.HTTPError as e:
        elapsed = time.time() - start
        print(f'[{name}] ❌ HTTP {e.code} after {elapsed:.1f}s')
    except Exception as e:
        elapsed = time.time() - start
        err = str(e)[:100]
        print(f'[{name}] ❌ 失败 ({elapsed:.1f}s): {err}')
    print()

# ===== 速度对比测试 (仅可用节点) =====
print("=" * 70)
print("速度对比测试 (中等难度问题)")
print("=" * 70)

speed_test = {"model":"glm-5.2","max_tokens":200,"messages":[{"role":"user","content":"explain what is a Python list comprehension in 2 sentences"}]}

for name, base_url, protocol in endpoints:
    # 重建URL确保正确
    if protocol == 'anthropic':
        url = base_url
        headers = {'x-api-key': API_KEY, 'anthropic-version': '2023-06-01', 'Content-Type': 'application/json'}
        body = speed_test.copy()
    else:
        url = base_url
        headers = {'Authorization': f'Bearer {API_KEY}', 'Content-Type': 'application/json'}
        body = speed_test.copy()
    
    payload = json.dumps(body).encode()
    start = time.time()
    try:
        if url.startswith('https'):
            req = urllib.request.Request(url, data=payload, headers=headers)
            resp = urllib.request.urlopen(req, timeout=60, context=ctx)
        else:
            req = urllib.request.Request(url, data=payload, headers=headers)
            resp = urllib.request.urlopen(req, timeout=60)
        elapsed = time.time() - start
        raw = resp.read().decode()
        text, tokens, model = parse_response(raw, protocol)
        tps = tokens / elapsed if elapsed > 0 else 0
        print(f'[{name}] {elapsed:.1f}s | {tokens} tok | {tps:.0f} tok/s | 可用 ✅')
    except Exception as e:
        elapsed = time.time() - start
        print(f'[{name}] 跳过 (基础测试未通过)')

print()
print("=" * 70)
print("测试完成")
