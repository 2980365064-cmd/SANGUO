#!/usr/bin/env python3
"""Generate UI asset images (frames, backgrounds, textures) via DashScope.

Reads prompt templates from scripts/prompts/ui/*.md and generates .webp images
to web/public/assets/ui/.

Key lookup order for API key:
  1. --api-key-env, default DASHSCOPE_API_KEY
  2. ALIYUN_API_KEY / BAILIAN_API_KEY / ALIBABA_API_KEY
  3. data/runtime_llm.json api_key

Examples:
  python3 scripts/gen_ui_assets.py                    # generate all
  python3 scripts/gen_ui_assets.py --only bg-hall     # generate specific asset
  python3 scripts/gen_ui_assets.py --dry-run          # show prompts only
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Any

from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = ROOT / "scripts" / "prompts" / "ui"
OUT_DIR = ROOT / "web" / "public" / "assets" / "ui"
RUNTIME_LLM = ROOT / "data" / "runtime_llm.json"

DEFAULT_MODEL = "wan2.6-t2i"
DEFAULT_NEGATIVE = (
    "text, Chinese characters, calligraphy, poem, caption, title, subtitle, watermark, logo, signature, "
    "low quality, blurry, 3D render, CGI, photorealistic, neon, cyberpunk, Japanese anime style, "
    "modern elements, people, human figures, faces, hands"
)
DEFAULT_SYNC_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
DEFAULT_ASYNC_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/image-generation/generation"

# Asset definitions: name -> (prompt_file, generate_size, crop_size, output_filename)
# generate_size: DashScope 生成尺寸（必须用支持的尺寸）
# crop_size: 后处理裁剪到目标尺寸（None=不裁剪，resize）
ASSETS = {
    "panel-frame": {
        "prompt_file": "panel-frame.md",
        "size": "1024*1024",
        "output": "frame-panel-ink.webp",
        "negative": DEFAULT_NEGATIVE + ", people, figures",
    },
    "card-frame": {
        "prompt_file": "card-frame.md",
        "size": "1024*1024",   # DashScope 不支持 512x640，用 1024x1024 生成后裁
        "output": "frame-card-ink.webp",
        "crop": (400, 500),    # 裁切到 400x500 近似 4:5
        "negative": DEFAULT_NEGATIVE + ", people, figures",
    },
    "button-frame": {
        "prompt_file": "button-frame.md",
        "size": "1024*1024",   # DashScope 不支持 512x128
        "output": "frame-button-ink.webp",
        "crop": (800, 200),    # 裁切到 800x200 近似 4:1
        "negative": DEFAULT_NEGATIVE + ", people, figures",
    },
    "bg-hall": {
        "prompt_file": "bg-hall.md",
        "size": "1664*928",
        "output": "bg-hall.webp",
        "negative": (
            "heavy black ink, dark blotches, muddy black, thick ink pooling, "
            "text, Chinese characters, watermark, logo, signature, low quality, blurry, "
            "3D render, photorealistic, modern elements, UI elements, buttons"
        ),
    },
    "bg-secret-chamber": {
        "prompt_file": "bg-secret.md",
        "size": "1664*928",
        "output": "bg-secret-chamber.webp",
        "negative": (
            "heavy black ink, dark blotches, muddy black, thick ink pooling, "
            "text, Chinese characters, watermark, logo, signature, low quality, blurry, "
            "3D render, photorealistic, modern elements, UI elements, buttons, people"
        ),
    },
    "bg-dock-right": {
        "prompt_file": "bg-dock.md",
        "size": "1024*1024",
        "output": "bg-dock-right.webp",
        "crop": (480, 960),    # 裁切为竖向
        "negative": DEFAULT_NEGATIVE + ", people, figures",
    },
    "bg-city": {
        "prompt_file": "bg-city.md",
        "size": "1664*928",
        "output": "bg-city.webp",
        "negative": (
            "heavy black ink, dark blotches, muddy black, thick ink pooling, "
            "text, Chinese characters, watermark, logo, signature, low quality, blurry, "
            "3D render, photorealistic, modern elements, UI elements, buttons, people"
        ),
    },
    "bg-province": {
        "prompt_file": "bg-province.md",
        "size": "1664*928",
        "output": "bg-province.webp",
        "negative": (
            "heavy black ink, dark blotches, muddy black, thick ink pooling, "
            "text, Chinese characters, watermark, logo, signature, low quality, blurry, "
            "3D render, photorealistic, modern elements, UI elements, buttons, people"
        ),
    },
    "bg-army": {
        "prompt_file": "bg-army.md",
        "size": "1664*928",
        "output": "bg-army.webp",
        "negative": (
            "heavy black ink, dark blotches, muddy black, thick ink pooling, "
            "text, Chinese characters, watermark, logo, signature, low quality, blurry, "
            "3D render, photorealistic, modern elements, UI elements, buttons, people"
        ),
    },
    "bg-character": {
        "prompt_file": "bg-character.md",
        "size": "1664*928",
        "output": "bg-character.webp",
        "negative": (
            "heavy black ink, dark blotches, muddy black, thick ink pooling, "
            "text, Chinese characters, watermark, logo, signature, low quality, blurry, "
            "3D render, photorealistic, modern elements, UI elements, buttons, people"
        ),
    },
    "bg-diplomacy": {
        "prompt_file": "bg-diplomacy.md",
        "size": "1664*928",
        "output": "bg-diplomacy.webp",
        "negative": (
            "heavy black ink, dark blotches, muddy black, thick ink pooling, "
            "text, Chinese characters, watermark, logo, signature, low quality, blurry, "
            "3D render, photorealistic, modern elements, UI elements, buttons, people"
        ),
    },
    "bg-strategy": {
        "prompt_file": "bg-strategy.md",
        "size": "1664*928",
        "output": "bg-strategy.webp",
        "negative": (
            "heavy black ink, dark blotches, muddy black, thick ink pooling, "
            "text, Chinese characters, watermark, logo, signature, low quality, blurry, "
            "3D render, photorealistic, modern elements, UI elements, buttons, people"
        ),
    },
    "bg-history": {
        "prompt_file": "bg-history.md",
        "size": "1664*928",
        "output": "bg-history.webp",
        "negative": (
            "heavy black ink, dark blotches, muddy black, thick ink pooling, "
            "text, Chinese characters, watermark, logo, signature, low quality, blurry, "
            "3D render, photorealistic, modern elements, UI elements, buttons, people"
        ),
    },
    "bg-family": {
        "prompt_file": "bg-family.md",
        "size": "1664*928",
        "output": "bg-family.webp",
        "negative": (
            "heavy black ink, dark blotches, muddy black, thick ink pooling, "
            "text, Chinese characters, watermark, logo, signature, low quality, blurry, "
            "3D render, photorealistic, modern elements, UI elements, buttons, people"
        ),
    },
    "bg-menu-side": {
        "prompt_file": "bg-dock.md",
        "size": "1024*1024",
        "output": "bg-menu-side.webp",
        "crop": (480, 960),
        "negative": DEFAULT_NEGATIVE + ", people, figures",
    },
    "texture-paper": {
        "prompt_file": "texture-paper.md",
        "size": "1024*1024",   # 用 1024x1024 生成，tile 用
        "output": "texture-paper.webp",
        "negative": (
            "text, characters, patterns, borders, frames, people, figures, "
            "low quality, blurry, 3D render, modern elements"
        ),
    },
    "texture-ink-wash": {
        "prompt_file": "texture-wash.md",
        "size": "1024*1024",
        "output": "texture-ink-wash.webp",
        "negative": (
            "text, characters, patterns, borders, frames, people, figures, "
            "low quality, blurry, 3D render, solid colors, uniform"
        ),
    },
    "divider-ink": {
        "prompt_file": "divider.md",
        "size": "1024*1024",   # 生成后裁切
        "output": "divider-ink.webp",
        "crop": (1024, 128),
        "negative": DEFAULT_NEGATIVE + ", people, figures",
    },
}


def load_api_key(primary_env: str) -> str:
    for name in [primary_env, "DASHSCOPE_API_KEY", "ALIYUN_API_KEY", "BAILIAN_API_KEY", "ALIBABA_API_KEY"]:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    if RUNTIME_LLM.exists():
        try:
            value = json.loads(RUNTIME_LLM.read_text("utf-8")).get("api_key", "")
            if isinstance(value, str) and value.strip():
                return value.strip()
        except (OSError, json.JSONDecodeError):
            pass
    raise SystemExit(
        "缺少百炼/DashScope API Key：请设置 DASHSCOPE_API_KEY，"
        "或确认 data/runtime_llm.json 有 api_key。"
    )


def load_prompt(prompt_file: str) -> str:
    path = PROMPTS_DIR / prompt_file
    if not path.exists():
        raise FileNotFoundError(f"Prompt 文件不存在: {path}")
    return path.read_text("utf-8").strip()


def http_json(url: str, api_key: str, payload: dict[str, Any], async_mode: bool = False, timeout: int = 180) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    if async_mode:
        headers["X-DashScope-Async"] = "enable"
    request = urllib.request.Request(url, data=body, method="POST", headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def http_get_json(url: str, api_key: str, timeout: int = 120) -> dict[str, Any]:
    request = urllib.request.Request(url, method="GET", headers={"Authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_result(response: dict[str, Any], api_key: str, endpoint_url: str, timeout: int) -> dict[str, Any]:
    output = response.get("output")
    task_id = output.get("task_id") if isinstance(output, dict) else None
    if not task_id:
        return response
    query_url = endpoint_url.split("/api/v1/services/", 1)[0] + f"/api/v1/tasks/{task_id}"
    deadline = time.time() + timeout
    current = response
    while time.time() < deadline:
        current = http_get_json(query_url, api_key)
        output = current.get("output")
        status = output.get("task_status") if isinstance(output, dict) else ""
        if status in {"SUCCEEDED", "FAILED", "UNKNOWN"}:
            return current
        time.sleep(3)
    raise TimeoutError(f"等待 DashScope 生图超时：task_id={task_id}")


def extract_image_url(response: dict[str, Any]) -> str:
    output = response.get("output")
    if isinstance(output, dict):
        choices = output.get("choices") or []
        for choice in choices:
            message = choice.get("message") if isinstance(choice, dict) else None
            content = message.get("content") if isinstance(message, dict) else None
            if not isinstance(content, list):
                continue
            for item in content:
                if isinstance(item, dict) and item.get("image"):
                    return str(item["image"])
        results = output.get("results") or output.get("images") or []
        if results:
            first = results[0]
            if isinstance(first, dict):
                return str(first.get("url") or first.get("image_url") or "")
        task_id = output.get("task_id")
        if task_id:
            raise RuntimeError(f"任务仍在队列中，task_id={task_id}，未返回图片 URL")
    raise RuntimeError(f"未能从返回结果提取图片 URL：{response}")


def generate(
    api_key: str, model: str, endpoint_url: str, async_mode: bool,
    prompt: str, negative_prompt: str, size: str, timeout: int,
) -> bytes:
    payload = {
        "model": model,
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [{"text": prompt}],
                }
            ],
        },
        "parameters": {
            "prompt_extend": False,
            "watermark": False,
            "n": 1,
            "negative_prompt": negative_prompt,
            "size": size,
        },
    }
    response = http_json(endpoint_url, api_key, payload, async_mode=async_mode, timeout=timeout)
    response = wait_for_result(response, api_key, endpoint_url, timeout)
    if response.get("code") or response.get("message"):
        raise RuntimeError(f"DashScope 请求失败：{response.get('code')} {response.get('message')}")
    url = extract_image_url(response)
    if not url:
        raise RuntimeError(f"DashScope 未返回图片 URL：{response}")
    with urllib.request.urlopen(url, timeout=120) as resp:
        return resp.read()


def save_webp(raw: bytes, output_path: Path, webp_size: int = 0, crop: tuple[int, int] | None = None) -> None:
    """Save raw image bytes as webp, optionally resizing and cropping."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Save source PNG first
    png_path = output_path.with_suffix(".png")
    png_path.write_bytes(raw)

    with Image.open(png_path) as src:
        im = src.convert("RGBA" if src.mode in ("RGBA", "LA", "PA") else "RGB")

        # Optional center crop
        if crop:
            cw, ch = crop
            if im.width >= cw and im.height >= ch:
                left = (im.width - cw) // 2
                top = (im.height - ch) // 2
                im = im.crop((left, top, left + cw, top + ch))
                print(f"  [crop] {im.size}")

        # Optional resize
        if webp_size > 0:
            scale = webp_size / max(im.size)
            if scale < 1:
                im = im.resize(
                    (round(im.width * scale), round(im.height * scale)),
                    Image.LANCZOS
                )
        im.save(output_path, format="WEBP", quality=90, method=6)
    print(f"  -> {output_path.relative_to(ROOT)} ({output_path.stat().st_size // 1024}KB)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate UI assets via DashScope")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--endpoint-url", default=DEFAULT_SYNC_URL)
    parser.add_argument("--async-mode", action="store_true")
    parser.add_argument("--webp-size", type=int, default=0, help="Max dimension for output webp (0=no resize)")
    parser.add_argument("--only", default="", help="Comma-separated asset names to generate")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--api-key-env", default="DASHSCOPE_API_KEY")
    args = parser.parse_args()

    if args.async_mode and args.endpoint_url == DEFAULT_SYNC_URL:
        args.endpoint_url = DEFAULT_ASYNC_URL

    # Determine which assets to generate
    if args.only:
        names = [n.strip() for n in args.only.split(",") if n.strip()]
        assets = {k: v for k, v in ASSETS.items() if k in names}
        unknown = set(names) - set(ASSETS.keys())
        if unknown:
            print(f"警告: 未知素材名 {unknown}，可选: {list(ASSETS.keys())}")
    else:
        assets = ASSETS

    api_key = "" if args.dry_run else load_api_key(args.api_key_env)

    todo = []
    for name, config in assets.items():
        output_path = OUT_DIR / config["output"]
        if args.force or not output_path.exists():
            todo.append((name, config, output_path))

    print(f"待生成素材: {len(todo)} / {len(assets)} 个")
    if args.dry_run:
        for name, config, output_path in todo:
            prompt = load_prompt(config["prompt_file"])
            print(f"\n[{name}] -> {output_path.relative_to(ROOT)}")
            print(f"  尺寸: {config['size']}")
            print(f"  Prompt: {prompt[:200]}...")
        return

    for index, (name, config, output_path) in enumerate(todo, 1):
        print(f"\n[{index}/{len(todo)}] 生成 {name} ({config['size']})...")
        prompt = load_prompt(config["prompt_file"])
        negative = config.get("negative", DEFAULT_NEGATIVE)

        for attempt in range(1, args.retries + 2):
            start = time.time()
            try:
                raw = generate(
                    api_key, args.model, args.endpoint_url, args.async_mode,
                    prompt, negative, config["size"], args.timeout,
                )
                save_webp(raw, output_path, args.webp_size, config.get("crop"))
                elapsed = time.time() - start
                print(f"  OK ({elapsed:.0f}s)")
                break
            except Exception as error:
                if attempt > args.retries:
                    print(f"  FAIL final: {error}")
                    break
                print(f"  FAIL({attempt}): {error}，重试...")
                time.sleep(5)

    print(f"\n完成！生成文件在: {OUT_DIR.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
