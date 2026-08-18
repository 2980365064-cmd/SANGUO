#!/usr/bin/env python3
"""Generate 13 background images for SANGUO UI scenes."""
import json
import os
import time
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

BACKGROUNDS = [
    {
        "filename": "bg-map.webp",
        "scene": "行动枢纽/战略地图",
        "prompt": "大幅汉末天下舆图铺在深色木案上，边缘有卷起的竹简、砚台、兵符、烛火和少量战报，地图本身模糊抽象，不要可读地名，中央留白适合覆盖交互地图。"
    },
    {
        "filename": "bg-review.webp",
        "scene": "审阅与颁令",
        "prompt": "刘备军府的颁令案台，边缘有展开的空白帛书、毛笔、朱砂印泥、镇纸与半卷军令，中央是干净的浅色宣纸安全区，庄重而不过暗。"
    },
    {
        "filename": "bg-adjudication.webp",
        "scene": "推演总览",
        "prompt": "夜间军府推演案，边缘有沙盘、军旗影、筹策、烛台、卷宗和远处模糊营火，中央留白用于流式推演日志。"
    },
    {
        "filename": "bg-adjudication-march.webp",
        "scene": "行军推演",
        "prompt": "汉末军队沿山道或江汉平原行军，队伍与旌旗位于画面左右边缘，中央为雾气、道路与留白，不要正面将领特写。"
    },
    {
        "filename": "bg-adjudication-naval.webp",
        "scene": "水战推演",
        "prompt": "长江或汉水上的汉末战船，远处水墨江面、薄雾与岸边烽烟，战船集中在两侧，中央保持开阔水面和低对比留白。"
    },
    {
        "filename": "bg-adjudication-siege.webp",
        "scene": "攻城推演",
        "prompt": "汉末城池攻防远景，城墙、云梯、投石机和旗帜安排于边缘，中央为烟雾与空阔天空，不出现血腥近景。"
    },
    {
        "filename": "bg-adjudication-camp.webp",
        "scene": "军营推演",
        "prompt": "夜间军营，边缘是帐篷、拒马、巡逻火把、粮车与军旗，中央为被营火轻照的空地，适合叠加推演文本。"
    },
    {
        "filename": "bg-adjudication-envoy.webp",
        "scene": "使臣道路",
        "prompt": "汉末使团沿驿道经过江边、关隘或山林，马车、随从与驿亭安排在边缘，中央留出道路与雾景。"
    },
    {
        "filename": "bg-adjudication-disaster.webp",
        "scene": "灾荒推演",
        "prompt": "灾后乡里远景，枯田、破损水渠、少量流民和赈济车队只在边缘，中央是灰白宣纸感天空与田野留白；克制、不猎奇。"
    },
    {
        "filename": "bg-event-urgent.webp",
        "scene": "雨夜急报事件",
        "prompt": "雨夜军府/驿亭，边缘有披蓑急使、湿透的战报、灯笼与水洼反光，中央为暗而可读的雾化留白。"
    },
    {
        "filename": "bg-event-disaster.webp",
        "scene": "灾荒事件",
        "prompt": "白日灾荒地方场景，边缘有受损民居、干裂土地、粮木车与地方小吏，中央保持浅色低对比，可叠加事件选项。"
    },
    {
        "filename": "bg-event-harvest.webp",
        "scene": "丰收事件",
        "prompt": "秋收后的汉末乡野，边缘有粮仓、晒谷场、农人背影、金黄稻束和远山，中央柔和留白；氛围安定但不明艳。"
    },
    {
        "filename": "bg-report.webp",
        "scene": "每月总计/回奏",
        "prompt": "军府月度回奏案卷，边缘有分类卷宗、封缄书信、朱砂批注、砚台和微弱晨光，中央为最干净的宣纸内容区，适合长篇月报阅读。"
    },
]

NEGATIVE_PROMPT = (
    "low quality, blurry, deformed, modern clothes, modern objects, cyberpunk, sci-fi, "
    "text, Chinese characters, calligraphy, poem, caption, title, subtitle, watermark, logo, signature, "
    "bright colors, vivid red, vivid orange, vivid green, colorful, saturated colors, "
    "3D render, CGI, photorealistic, glossy, plastic, "
    "detailed faces, crowd closeup, strong light effects, neon, "
    "ugly, distorted, creepy"
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
        print(f"  Waiting... ({int(time.time() - deadline + timeout)}s remaining)")
        time.sleep(3)
    raise TimeoutError(f"Timeout: task_id={task_id}")


def extract_image_url(response: dict) -> str:
    """Extract image URL from response - handles both sync and async formats."""
    output = response.get("output")
    if isinstance(output, dict):
        # Check choices (sync format)
        choices = output.get("choices") or []
        for choice in choices:
            message = choice.get("message") if isinstance(choice, dict) else None
            content = message.get("content") if isinstance(message, dict) else None
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("image"):
                        return str(item["image"])
        # Check results (async format)
        results = output.get("results") or output.get("images") or []
        if results:
            first = results[0]
            if isinstance(first, dict):
                return str(first.get("url") or first.get("image_url") or "")
    raise RuntimeError(f"Could not extract image URL from response")


def generate_one(bg: dict, index: int, total: int) -> Path:
    filename = bg["filename"]
    scene = bg["scene"]
    prompt = bg["prompt"]
    out_path = OUT_DIR / filename

    print(f"\n[{index}/{total}] {filename} - {scene}")

    full_prompt = f"{STYLE_PREFIX}{prompt}"

    payload = {
        "model": MODEL,
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [{"text": full_prompt}],
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

    print("  Sending request...")
    response = http_json(ENDPOINT, API_KEY, payload)

    # Extract URL directly (sync response)
    try:
        url = extract_image_url(response)
    except RuntimeError:
        # Try waiting for async result
        response = wait_for_result(response, API_KEY)
        url = extract_image_url(response)

    if not url:
        raise RuntimeError(f"No URL: {response}")

    print(f"  Downloading...")
    with urllib.request.urlopen(url, timeout=120) as resp:
        raw = resp.read()

    out_path.write_bytes(raw)
    print(f"  Saved: {out_path} ({len(raw)//1024}KB)")
    return out_path


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Check existing files
    existing = [bg for bg in BACKGROUNDS if (OUT_DIR / bg["filename"]).exists()]
    if existing:
        print("Existing files (will be overwritten):")
        for bg in existing:
            print(f"  - {bg['filename']}")
        input("Press Enter to continue or Ctrl+C to abort...")

    todo = BACKGROUNDS
    print(f"Generating {len(todo)} background images...")

    success = 0
    failed = []
    for i, bg in enumerate(todo, 1):
        try:
            generate_one(bg, i, len(todo))
            success += 1
        except Exception as e:
            print(f"  FAILED: {e}")
            failed.append(bg["filename"])

    print(f"\n{'='*60}")
    print(f"Completed: {success}/{len(todo)}")
    if failed:
        print(f"Failed: {', '.join(failed)}")
    else:
        print("All backgrounds generated successfully!")


if __name__ == "__main__":
    main()
