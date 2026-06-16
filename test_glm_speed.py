import time, json, urllib.request

url = 'http://122.51.254.107:55888/anthropic/v1/messages'
headers = {
    'x-api-key': 'sk-sp-UCTrtaXyvLd1NFrXrBS7LgRJqZDknWn3',
    'anthropic-version': '2023-06-01',
    'Content-Type': 'application/json'
}

tests = [
    ('简单一问', {"model":"glm-5.1","max_tokens":50,"messages":[{"role":"user","content":"1+1=? answer in one word"}]}),
    ('中等解释', {"model":"glm-5.1","max_tokens":200,"messages":[{"role":"user","content":"explain what is Python decorator in 2 short sentences"}]}),
    ('写代码', {"model":"glm-5.1","max_tokens":300,"messages":[{"role":"user","content":"write a simple quicksort function in Python"}]}),
]

print("=" * 60)
print("GLM-5.1 中转站速度测试 (Anthropic协议)")
print("=" * 60)

for name, body in tests:
    data = json.dumps(body).encode()
    start = time.time()
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=90)
        elapsed = time.time() - start
        raw = resp.read().decode()
        result = json.loads(raw)
        
        # parse content safely
        content_list = result.get('content', [])
        text_parts = []
        for block in content_list:
            if block.get('type') == 'text':
                text_parts.append(block.get('text', ''))
        text = ' '.join(text_parts)[:120].replace('\n', ' ')
        
        usage = result.get('usage', {})
        in_tok = usage.get('input_tokens', 0)
        out_tok = usage.get('output_tokens', 0)
        tps = out_tok / elapsed if elapsed > 0 else 0
        model = result.get('model', '?')
        
        print(f'[{name}] {elapsed:.1f}s | in:{in_tok} out:{out_tok} tok | {tps:.0f} tok/s | model:{model}')
        print(f'  -> {text}')
        print()
    except Exception as e:
        elapsed = time.time() - start
        print(f'[{name}] FAIL after {elapsed:.1f}s: {e}')
        print()

print("=" * 60)
print("测试完成 - 如果上述全部 200 OK，中转站完全正常")
