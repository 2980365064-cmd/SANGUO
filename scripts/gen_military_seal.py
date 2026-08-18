#!/usr/bin/env python3
"""Generate military command seal (军令) icon via DashScope wanx-v1."""
import json, os, time, urllib.request
from pathlib import Path

API_KEY = "sk-9ec4ff47cc1e4d999a645cc65d7e319e"
MODEL = "wan2.6-t2i"
SIZE = "1024*1024"
ENDPOINT = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"

PROMPT = (
    "中国水墨风格军令印章图标，古代官方文书朱砂红印章，"
    "方形印章刻有'军令'二字，三国汉代风格，"
    "干净白色背景，游戏UI图标，"
    "鲜明朱砂红印章印迹，略带古旧印章质感，"
    "高对比度，边缘锐利，图标化可辨识。"
)

NEGATIVE_PROMPT = (
    "低质量, 模糊, 变形, 现代设计, 3D渲染, "
    "写实, 渐变, 彩虹, 多种颜色, "
    "除印章文字外的其他文字, 英文, 水印, "
    "复杂背景, 风景, 人物, 动物"
)

OUTPUT = Path(__file__).resolve().parent.parent / "web/public/assets/ui/seal/slices/military-order.webp"

def http_json(url, payload, timeout=180):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

def http_get_json(url, timeout=120):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {API_KEY}"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

def wait_for_result(response, timeout=300):
    task_id = response.get("output", {}).get("task_id")
    if not task_id:
        return response
    url = f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
    deadline = time.time() + timeout
    while time.time() < deadline:
        cur = http_get_json(url)
        status = cur.get("output", {}).get("task_status", "")
        print(f"  status: {status}")
        if status in {"SUCCEEDED", "FAILED", "UNKNOWN"}:
            return cur
        time.sleep(3)
    raise TimeoutError(f"Timeout: task_id={task_id}")

def main():
    payload = {
        "model": MODEL,
        "input": {"messages": [{"role": "user", "content": [{"text": PROMPT}]}]},
        "parameters": {"size": SIZE, "n": 1, "negative_prompt": NEGATIVE_PROMPT, "prompt_extend": False},
    }
    print("Sending generation request...")
    resp = http_json(ENDPOINT, payload)
    print(f"Task submitted: {resp.get('output', {}).get('task_id', 'unknown')}")
    resp = wait_for_result(resp)
    if resp.get("code") or resp.get("message"):
        raise RuntimeError(f"Failed: {resp}")
    results = resp.get("output", {}).get("results", [])
    if not results:
        raise RuntimeError(f"No results: {resp}")
    img_url = results[0].get("url", "")
    if not img_url:
        raise RuntimeError(f"No URL in results: {results}")
    print(f"Downloading from: {img_url}")
    urllib.request.urlretrieve(img_url, str(OUTPUT))
    print(f"Saved to: {OUTPUT}")

if __name__ == "__main__":
    main()
