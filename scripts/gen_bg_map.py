#!/usr/bin/env python3
"""Generate bg-map.webp only."""
import json
import urllib.request
from pathlib import Path

API_KEY = "sk-9ec4ff47cc1e4d999a645cc65d7e319e"
MODEL = "wan2.6-t2i"
SIZE = "1920*1080"
ENDPOINT = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
OUT_DIR = Path("/Users/zhuanzmima0000/SANGUO/web/public/assets/ui")

STYLE_PREFIX = (
    "东汉末年三国时代，轻水墨设色与宣纸纤维质感，低饱和青灰、墨色、赭石与少量朱砂，"
    "电影级但克制的环境叙事，中央 60% 必须留作低对比、低细节、无人物脸部的 UI 文字安全区；"
    "叙事物件和人物只放在四周边缘；无文字、无印章文字、无水印、无现代物件、无现代 UI、"
    "无强烈光效、无密集人群特写。"
)

PROMPT = "汉末天下舆图铺在木案上，边缘有竹简、砚台、烛火，地图模糊抽象，中央留白。"

NEGATIVE_PROMPT = (
    "low quality, blurry, deformed, modern clothes, modern objects, cyberpunk, sci-fi, "
    "text, Chinese characters, calligraphy, poem, caption, title, subtitle, watermark, logo, signature, "
    "bright colors, vivid red, vivid orange, vivid green, colorful, saturated colors, "
    "3D render, CGI, photorealistic, glossy, plastic, "
    "detailed faces, crowd closeup, strong light effects, neon, "
    "ugly, distorted, creepy"
)

full_prompt = STYLE_PREFIX + PROMPT
payload = {
    "model": MODEL,
    "input": {
        "messages": [
            {"role": "user", "content": [{"text": full_prompt}]}
        ]
    },
    "parameters": {
        "size": SIZE,
        "n": 1,
        "negative_prompt": NEGATIVE_PROMPT,
        "prompt_extend": False,
    },
}

print("Sending request...")
body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {API_KEY}",
}
request = urllib.request.Request(ENDPOINT, data=body, method="POST", headers=headers)
with urllib.request.urlopen(request, timeout=180) as response:
    resp_data = json.loads(response.read().decode("utf-8"))

output = resp_data.get("output", {})
choices = output.get("choices") or []
url = ""
for choice in choices:
    message = choice.get("message") if isinstance(choice, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("image"):
                url = str(item["image"])
                break
    if url:
        break

if not url:
    raise RuntimeError(f"No URL: {resp_data}")

print(f"Downloading...")
with urllib.request.urlopen(url, timeout=120) as resp:
    raw = resp.read()

out_path = OUT_DIR / "bg-map.webp"
out_path.write_bytes(raw)
print(f"Saved: {out_path} ({len(raw)//1024}KB)")
