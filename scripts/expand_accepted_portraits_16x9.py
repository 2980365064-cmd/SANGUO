#!/usr/bin/env python3
"""Expand accepted SANGUO portrait images to 16:9 with Alibaba Bailian/Wan.

This script is intentionally for the approved vertical portraits, not fresh
text-to-image generation. It feeds the approved image to Bailian and asks the
model to preserve the figure while extending a 16:9 ink-wash background.
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import time
import urllib.request
from pathlib import Path
from typing import Any

from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
RUNTIME_LLM = ROOT / "data" / "runtime_llm.json"
OUT = ROOT / "web" / "public" / "portraits" / "sanguo"
ENDPOINT = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
MODEL = "wan2.7-image"
SIZE = "1664*928"

APPROVED = {
    "刘备": ("sanguo/core_001", OUT / "_style_trials" / "liu_bei_new_from_main_reference.webp"),
    "关羽": ("sanguo/core_002", OUT / "_style_trials" / "core_002_shu_core_reference_style.webp"),
    "张飞": ("sanguo/core_003", OUT / "_style_trials" / "core_003_shu_core_reference_style.webp"),
    "赵云": ("sanguo/core_004", OUT / "_style_trials" / "core_004_shu_core_reference_style.webp"),
    "诸葛亮": ("sanguo/core_005", OUT / "_style_trials" / "core_005_shu_core_reference_style.webp"),
}


def load_api_key() -> str:
    for name in ["DASHSCOPE_API_KEY", "ALIYUN_API_KEY", "BAILIAN_API_KEY", "ALIBABA_API_KEY"]:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    if RUNTIME_LLM.exists():
        value = json.loads(RUNTIME_LLM.read_text("utf-8")).get("api_key", "")
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise SystemExit("缺少百炼 API Key")


def data_url(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    raw = path.read_bytes()
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


def http_json(url: str, api_key: str, payload: dict[str, Any], timeout: int = 240) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def extract_image_url(response: dict[str, Any]) -> str:
    output = response.get("output")
    if isinstance(output, dict):
        choices = output.get("choices") or []
        for choice in choices:
            message = choice.get("message") if isinstance(choice, dict) else None
            content = message.get("content") if isinstance(message, dict) else None
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("image"):
                        return str(item["image"])
    raise RuntimeError(f"未返回图片 URL：{response}")


def download(url: str, timeout: int = 120) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read()


def save_outputs(raw: bytes, portrait_id: str, name: str) -> None:
    relative = Path(*portrait_id.split("/"))
    source = OUT / "_source_png" / relative.with_suffix(".png")
    webp = OUT / relative.with_suffix(".webp")
    trial = OUT / "_style_trials" / f"{name}_accepted_16x9.webp"
    source.parent.mkdir(parents=True, exist_ok=True)
    webp.parent.mkdir(parents=True, exist_ok=True)
    trial.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(raw)
    with Image.open(source) as im:
        rgb = im.convert("RGB")
        rgb.save(webp, "WEBP", quality=94, method=6)
        rgb.save(trial, "WEBP", quality=94, method=6)
        print(f"{name} -> {source.relative_to(ROOT)} {rgb.size} / {webp.relative_to(ROOT)} {webp.stat().st_size//1024}KB")


def prompt_for(name: str) -> str:
    return (
        f"把输入图中的{name}人物立绘改成 16:9 横幅源图。必须保留原图人物的脸、五官、气质、服饰、身形、姿态和水墨笔触，"
        "不要把人物重新设计成另一张脸，不要变丑，不要变成 3D。"
        "人物全身完整保留，居中或略偏中间，头冠到靴履完整入画，不能裁掉武器、衣摆或脚。"
        "只向左右和背景方向扩展画布，补出同风格的宣纸、水墨云雾、远山、江水、战旗或对应人物命运环境。"
        "整体风格必须与输入图一致：2D 中国水墨历史插画、粗墨线、灰褐云雾、低饱和淡彩、干笔飞白、宣纸纹理。"
        "画面四周留出后续裁剪空间。不要任何可读文字、题字、印章、水印、签名。"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default="", help="逗号分隔人物名；默认处理全部已认可五张")
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--size", default=SIZE)
    args = parser.parse_args()

    selected = APPROVED
    if args.only:
        wanted = {x.strip() for x in args.only.split(",") if x.strip()}
        selected = {k: v for k, v in APPROVED.items() if k in wanted}
    if not selected:
        raise SystemExit("没有匹配的人物")

    api_key = load_api_key()
    for index, (name, (portrait_id, src)) in enumerate(selected.items(), 1):
        if not src.exists():
            raise SystemExit(f"{name} 认可图不存在：{src}")
        payload = {
            "model": args.model,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"image": data_url(src)},
                            {"text": prompt_for(name)},
                        ],
                    }
                ]
            },
            "parameters": {
                "size": args.size,
                "n": 1,
                "watermark": False,
            },
        }
        start = time.time()
        response = http_json(ENDPOINT, api_key, payload)
        if response.get("code") or response.get("message"):
            raise RuntimeError(f"{name} 失败：{response.get('code')} {response.get('message')}")
        raw = download(extract_image_url(response))
        save_outputs(raw, portrait_id, name)
        print(f"[{index}/{len(selected)}] {name} OK {time.time()-start:.0f}s", flush=True)


if __name__ == "__main__":
    main()
