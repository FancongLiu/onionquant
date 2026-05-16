import urllib.request
import socket
import ssl

print("\n===== 网络连通性测试 =====\n")

def test_url(url, timeout=8):
    try:
        with urllib.request.urlopen(url, timeout=timeout, context=ssl.create_default_context()) as resp:
            print(f"✅ {url} 连接成功，状态码: {resp.status}")
    except Exception as e:
        print(f"❌ {url} 连接失败: {type(e).__name__}: {e}")

# 测试 DuckDuckGo
print("[1] 测试 DuckDuckGo ...")
test_url("https://duckduckgo.com")

# 测试 Google
print("[2] 测试 Google ...")
test_url("https://www.google.com")

# 测试 Bing
print("[3] 测试 Bing ...")
test_url("https://www.bing.com")

# 测试 Yahoo
print("[4] 测试 Yahoo ...")
test_url("https://news.yahoo.com")

print("\n===== 测试结束 =====\n")
