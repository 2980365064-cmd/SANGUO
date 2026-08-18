#!/usr/bin/env python3
"""Generate Liu Bei portrait with Zhao Yun style alignment."""
import json
import os
import time
import urllib.request
from pathlib import Path

API_KEY = "sk-9ec4ff47cc1e4d999a645cc65d7e319e"
# 使用 wanx-v1 模型（阿里百炼最佳图像生成模型）
MODEL = "wanx-v1"
SIZE = "1664*928"
ENDPOINT = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"

PROMPT = (
    "Create a new full-body 2D Chinese ink-and-wash historical illustration of Liu Bei (刘备) "
    "for a Three Kingdoms strategy game. "
    "STRICT STYLE ANCHOR - Must match this exact style: "
    "Clean 2D Chinese gongbi ink painting on xuan paper texture, "
    "gray-brown monochromatic palette with extremely low saturation, "
    "muted gray clouds, hand-painted brush outlines, "
    "NO bright colors, NO vivid red/orange/green, "
    "NO 3D render, NO CGI, NO anime, NO cartoon, NO plastic skin. "
    "Character source from Romance of the Three Kingdoms: "
    "性宽和，寡言语，喜怒不形于色，身长七尺五寸，面如冠玉，唇色温润， "
    "双臂修长，耳垂偏长但不怪异。 "
    "Character design: "
    "Classical Chinese gentleman face, refined features, "
    "warm and compassionate expression with subtle melancholy, "
    "NOT ugly, NOT cartoonish, NOT overly handsome, NOT angry. "
    "Wearing loose green-gray robes over light armor with Han dynasty patterns, "
    "sword at waist, wide sleeves hanging naturally. "
    "Environment: "
    "Minimalist background - only pale ink clouds and distant misty river, "
    "NO detailed buildings, NO bright sunset, NO fire, NO complex scenery. "
    "Background must be simpler and lower contrast than the character. "
    "Composition: "
    "16:9 horizontal, full body from crown to boots, centered, "
    "generous xuan-paper breathing room, "
    "NO text, NO calligraphy, NO seal stamp, NO watermark. "
    "Avoid: "
    "ugly face, distorted anatomy, cartoon, anime, 3D render, CGI, photorealism, "
    "bright colors, vivid red, vivid orange, vivid green, glossy armor, "
    "plastic skin, heavy random grain, noisy face, "
    "detailed buildings, complex background, sunset, fire."
)

NEGATIVE_PROMPT = (
    "low quality, blurry, deformed face, bad anatomy, extra fingers, modern clothes, "
    "modern haircut, cyberpunk, sci-fi, neon light, Japanese anime, western fantasy, "
    "text, Chinese characters, calligraphy, poem, caption, title, subtitle, watermark, logo, signature, "
    "childish face, ugly face, grotesque, exaggerated features, "
    "3D render, CGI, blender, octane render, photorealistic, realistic metal shine, glossy armor, plastic skin, "
    "volumetric lighting, cinematic 3d, game screenshot, fake realistic texture, "
    "bright colors, vivid red, vivid orange, vivid green, colorful, "
    "detailed buildings, complex background, sunset, fire, flames"
)

def http_json(url, api_key, payload, timeout=180):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    request = urllib.request.Request(url, data=body, method="POST", headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))

def http_get_json(url, api_key, timeout=120):
    request = urllib.request.Request(url, method="GET", headers={"Authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))

def wait_for_result(response, api_key, timeout=300):
    output = response.get("output", {})
    task_id = output.get("task_id")
    if not task_id:
        return response
    query_url = f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
    deadline = time.time() + timeout
    while time.time() < deadline:
        current = http_get_json(query_url, api_key)
        status = current.get("output", {}).get("task_status", "")
        if status in {"SUCCEEDED", "FAILED", "UNKNOWN"}:
            return current
        time.sleep(3)
    raise TimeoutError(f"Timeout: task_id={task_id}")

def generate():
    payload = {
        "model": MODEL,
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [{"text": PROMPT}],
                }
            ],
        },
        "parameters": {
            "size": SIZE,
            "n": 1,
            "negative_prompt": NEGATIVE_PROMPT,
            "prompt_extend": False,
        },
    }
    print("Sending request...")
    response = http_json(ENDPOINT, API_KEY, payload)
    print(f"Response: {response}")
    response = wait_for_result(response, API_KEY)
    if response.get("code") or response.get("message"):
        raise RuntimeError(f"Failed: {response}")
    output = response.get("output", {})
    results = output.get("results", [])
    if not results:
        raise RuntimeError(f"No results: {response}")
    url = results[0].get("url", "")
    if not url:
        raise RuntimeError(f"No URL: {response}")
    print(f"Downloading: {url}")
    with urllib.request.urlopen(url, timeout=120) as resp:
        return resp.read()

if __name__ == "__main__":
    raw = generate()
    out_path = Path("/Users/zhuanzmima0000/SANGUO/web/public/portraits/sanguo/sanguo/core_001_new.webp")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(raw)
    print(f"Saved: {out_path} ({len(raw)//1024}KB)")
