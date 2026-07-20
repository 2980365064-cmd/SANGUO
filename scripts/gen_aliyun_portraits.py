#!/usr/bin/env python3
"""Generate SANGUO character portraits through Alibaba DashScope/Bailian.

The script reads content/characters.json and writes images where the current
frontend expects them: web/public/portraits/sanguo/<portrait_id>.webp.

Key lookup order:
  1. --api-key-env, default DASHSCOPE_API_KEY
  2. ALIYUN_API_KEY / BAILIAN_API_KEY / ALIBABA_API_KEY
  3. data/runtime_llm.json api_key

Examples:
  python3 scripts/gen_aliyun_portraits.py --limit 5
  python3 scripts/gen_aliyun_portraits.py --only 刘备 --force
  python3 scripts/gen_aliyun_portraits.py --tiers S,1 --limit 5
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.request
from pathlib import Path
from typing import Any

from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
CHARACTERS = ROOT / "content" / "characters.json"
RUNTIME_LLM = ROOT / "data" / "runtime_llm.json"
OUT = ROOT / "web" / "public" / "portraits" / "sanguo"

DEFAULT_MODEL = "wan2.6-t2i"
DEFAULT_SIZE = "1664*928"
DEFAULT_PROMPT_EXTEND = False
DEFAULT_SYNC_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
DEFAULT_ASYNC_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/image-generation/generation"
DEFAULT_NEGATIVE = (
    "low quality, blurry, deformed face, bad anatomy, extra fingers, modern clothes, "
    "modern haircut, cyberpunk, sci-fi armor, neon light, Japanese anime, western fantasy, "
    "text, Chinese characters, calligraphy, poem, caption, title, subtitle, watermark, logo, signature, frame, cropped head, "
    "childish face, generic handsome man, angry tyrant, exaggerated monster ears, grotesque long arms, "
    "3D render, CGI, blender, octane render, photorealistic, realistic metal shine, glossy armor, plastic skin, "
    "volumetric lighting, cinematic 3d, game screenshot, fake realistic texture"
)

POWER_STYLE = {
    "liu_bei": "蜀汉阵营气质，温润青绿与朱砂细节，衣甲朴厚而有汉室正统感",
    "cao_cao": "曹魏阵营气质，玄黑重甲与冷金细节，威严、秩序、北方军府感",
    "sun_quan": "江东阵营气质，青铜绿与赤金细节，水军、江南士族、年轻锐气",
    "liu_zhang": "益州阵营气质，蜀地士族服饰，沉稳、守成、锦纹细节",
    "liu_qi": "荆州阵营气质，士人衣冠与水泽纹样，清雅、流亡政权感",
    "zhang_lu": "汉中阵营气质，道教符箓与山地军府元素，素色衣甲",
    "ma_han": "西凉阵营气质，边地骑兵、皮革札甲、风沙质感",
    "shi_xie": "交州阵营气质，南方郡守、湿热边地、青铜与深绿纹样",
    "gongsun_kang": "辽东阵营气质，寒地边镇、皮裘、铁甲与灰白风雪感",
}

OFFICE_STYLE = {
    "君主": "君主全身立绘，冠服端正，目光坚定，有统摄群臣的气度",
    "宗室": "宗室贵族全身立绘，汉代冠服，神情自持",
    "军政": "武将全身立绘，汉末札甲，肩甲清晰，英武但不夸张",
    "军师": "谋士全身立绘，纶巾或文冠，羽扇或简牍，眼神深沉",
    "政务": "文臣全身立绘，深衣与冠带，手持笏板或竹简，沉稳可信",
    "外交": "使者全身立绘，士人冠服，表情机敏，衣袖与佩绶整洁",
}

NAME_STYLE = {
    "刘备": (
        "刘备专属风格锚点，严格参考《三国演义》人物描述：性宽和，寡言语，喜怒不形于色；"
        "身长七尺五寸，耳垂明显偏长并要能看见但不要怪异，双臂修长、宽袖自然下垂接近膝部，面如冠玉，唇色温润。"
        "人物气质突出仁义、宽厚、能纳众人的温和威仪，不画成霸气帝王、冷酷武夫或普通英俊青年。"
        "服饰不要重甲压身，外罩青绿宽袍，内有轻甲和汉室纹样，腰间佩剑，整体像仁德之主而不是冲阵猛将。"
        "面容要有长期流亡、屡败屡起的沧桑，眉眼宽和、悲悯而坚定，像在乱世中仍愿意托住百姓与旧臣。"
        "悲情氛围来自环境：夷陵败后的江雾、孤舟、残阳、湿冷山城、远处白帝城般的高阁，"
        "近处有将熄未熄的汉室火光和散落的战旗边角，暗示托孤前的迟暮与自责。"
        "不要直接画死亡、哭泣、棺椁、印章或任何文字。整体情绪是仁义之君的温暖与迟暮英雄的哀而不伤。"
        "风格必须贴近游戏主界面：平面 2D 水墨插画、粗墨线轮廓、宣纸底纹、灰褐色云雾、飞白笔触、低饱和淡彩，"
        "人物像画在纸上，不要 3D、不要厚涂写实、不要照片级皮肤和金属高光。"
        "参考主界面三人立绘的表现方式：粗黑外轮廓，衣袍用大块墨色和少量青绿色淡彩铺开，"
        "脸部只用简练线条和少量阴影，不做真实皮肤渲染；背景云层像水墨铺染，不要真实体积雾。"
    ),
    "关羽": (
        "关羽专属锚点，参考《三国演义》常见外貌描写：身长九尺，髯长二尺，面如重枣，唇若涂脂，"
        "丹凤眼，卧蚕眉，相貌堂堂，威严肃穆。气质重在忠义、骄矜、威慑与晚期孤忠悲剧，"
        "不要画丑、不要妖化红脸、不要把长髯画成怪物。青绿长袍、轻甲、青龙偃月刀，"
        "环境可用月夜江风、孤城、冷雾、远舟暗示麦城之悲。"
    ),
    "张飞": (
        "张飞专属锚点，参考《三国演义》常见外貌描写：身长八尺，豹头环眼，燕颔虎须，声若巨雷，势如奔马。"
        "气质勇猛、直接、忠烈、爆发力强，但必须有英雄审美，不要丑化成怪物或莽夫笑料。"
        "黑色/深褐战袍，轻甲，丈八蛇矛，环境可用长坂桥、风暴、断桥、残旗，表现一夫当关的压迫感。"
    ),
    "赵云": (
        "赵云专属锚点：姿颜雄伟、清俊英武、忠诚护主、临危不乱。"
        "脸要好看但不幼态，眉眼坚毅，白银与青灰衣甲，红色细节，长枪。"
        "环境可用长坂坡烟尘、破旗、远处追兵墨影，表现护主救孤的明亮忠勇。"
    ),
    "诸葛亮": (
        "诸葛亮专属锚点，参考《三国演义》常见外貌描写：身长八尺，面如冠玉，头戴纶巾，身披鹤氅，飘飘然有神仙之概。"
        "气质清雅、深谋、安静、远见、肩负蜀汉命运，不要画老丑、不要魔法师化。"
        "羽扇、纶巾、鹤氅或浅色大氅，环境可用山雾、草庐余韵、远处北伐道路与军阵淡影。"
    ),
}


def safe_name(text: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", text).strip("_")


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
    raise SystemExit("缺少百炼/DashScope API Key：请设置 DASHSCOPE_API_KEY，或确认 data/runtime_llm.json 有 api_key。")


def load_characters() -> list[dict[str, Any]]:
    payload = json.loads(CHARACTERS.read_text("utf-8"))
    characters = payload.get("characters")
    if not isinstance(characters, list):
        raise SystemExit("content/characters.json 缺 characters 数组")
    return [c for c in characters if isinstance(c, dict)]


def output_paths(character: dict[str, Any]) -> tuple[Path, Path]:
    portrait_id = str(character.get("portrait_id") or safe_name(str(character.get("name", "unknown"))))
    # The frontend URL is /portraits/sanguo/${encodeURIComponent(portrait_id)}.webp.
    # If the server decodes %2F, portrait_id "sanguo/core_001" maps to this nested path.
    relative = Path(*portrait_id.split("/"))
    webp = OUT / relative.with_suffix(".webp")
    png = OUT / "_source_png" / relative.with_suffix(".png")
    return png, webp


def build_prompt(character: dict[str, Any]) -> str:
    name = str(character.get("name", "")).strip()
    office = str(character.get("office", "")).strip()
    office_type = str(character.get("office_type", "")).strip()
    faction = str(character.get("faction", "")).strip()
    power_id = str(character.get("power_id", "")).strip()
    tier = str(character.get("core_tier", "")).strip()
    skills = "、".join(str(x) for x in character.get("personal_skills", []) if x)
    summary = str(character.get("summary", "")).strip()

    power_style = POWER_STYLE.get(power_id, "汉末三国历史人物气质，服饰可信，材质厚重")
    office_style = OFFICE_STYLE.get(office_type, "汉末人物半身像，服饰符合身份")
    name_style = NAME_STYLE.get(name, "")
    prominence = "高辨识度核心名将，脸部特征鲜明" if tier in {"S", "1"} else "可用于策略游戏人物册的专属头像"

    return (
        f"为一款三国策略游戏生成一张人物全身立绘：{name}。"
        f"身份：{office}；类型：{office_type}；派系：{faction}；特性：{skills}。"
        f"{summary}。{power_style}。{office_style}。{name_style}。{prominence}。"
        "构图要求：16:9 横幅全身场景图，单人全身完整位于画面中央，从头冠到靴履完整入画，"
        "四周留出充足宣纸空间，方便后续裁成竖版、头像或卡面；不能裁掉头、手、衣摆、武器或脚。"
        "人物站姿端正，正面或三分之二侧身，脸部清晰，双手自然下垂、持武器或持身份道具，"
        "背景为淡宣纸与墨色山河纹理，画面任何位置都必须留白无字，不出现印章、可读文字、题字、诗句、标题或签名。"
        "美术风格：与游戏主界面一致的 2D 水墨历史插画，汉末服饰考据感，黑金、宣纸、朱砂暗线、青铜器纹样，"
        "墨色层次丰富，淡彩晕染，衣料、腰带、佩剑与面部细节用线描和墨块表达，边缘有毛笔飞白与纸纹，"
        "沉稳厚重，平面插画光影，类似手绘游戏主菜单 key art，非 3D，非厚涂，非照片写实，非日漫。"
    )


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
    if "/api/v1/services/" not in endpoint_url:
        raise RuntimeError(f"无法从 endpoint 推导 task 查询地址：{endpoint_url}")
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


def generate(api_key: str, model: str, endpoint_url: str, async_mode: bool, prompt: str, negative_prompt: str, size: str, timeout: int, prompt_extend: bool) -> bytes:
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
            "prompt_extend": prompt_extend,
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


def save_images(raw: bytes, png: Path, webp: Path, webp_size: int) -> None:
    png.parent.mkdir(parents=True, exist_ok=True)
    webp.parent.mkdir(parents=True, exist_ok=True)
    png.write_bytes(raw)
    with Image.open(png) as src:
        im = src.convert("RGB")
        scale = webp_size / max(im.size)
        if scale < 1:
            im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
        im.save(webp, format="WEBP", quality=88, method=6)


def select_characters(characters: list[dict[str, Any]], only: str, tiers: str) -> list[dict[str, Any]]:
    selected = characters
    if only:
        needles = [x.strip() for x in only.split(",") if x.strip()]
        selected = [
            c for c in selected
            if any(n in str(c.get("name", "")) or n in str(c.get("portrait_id", "")) for n in needles)
        ]
    if tiers:
        wanted = {x.strip() for x in tiers.split(",") if x.strip()}
        selected = [c for c in selected if str(c.get("core_tier", "")).strip() in wanted]
    return selected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--size", default=DEFAULT_SIZE)
    parser.add_argument("--endpoint-url", default=DEFAULT_SYNC_URL)
    parser.add_argument("--async-mode", action="store_true", help=f"使用异步接口，通常配合 --endpoint-url {DEFAULT_ASYNC_URL}")
    parser.add_argument("--prompt-extend", action="store_true", default=DEFAULT_PROMPT_EXTEND)
    parser.add_argument("--webp-size", type=int, default=768)
    parser.add_argument("--only", default="", help="逗号分隔，匹配人物名或 portrait_id")
    parser.add_argument("--tiers", default="", help="逗号分隔，如 S,1,2")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--api-key-env", default="DASHSCOPE_API_KEY")
    args = parser.parse_args()
    if args.async_mode and args.endpoint_url == DEFAULT_SYNC_URL:
        args.endpoint_url = DEFAULT_ASYNC_URL

    api_key = "" if args.dry_run else load_api_key(args.api_key_env)
    characters = select_characters(load_characters(), args.only, args.tiers)
    if args.limit:
        characters = characters[: args.limit]

    todo: list[dict[str, Any]] = []
    seen_outputs: set[Path] = set()
    for character in characters:
        _, webp = output_paths(character)
        if webp in seen_outputs:
            continue
        seen_outputs.add(webp)
        if args.force or not webp.exists():
            todo.append(character)

    print(f"角色 {len(characters)} 个，唯一待处理 {len(todo)} 张（已存在跳过，重复 portrait_id 跳过）")
    for index, character in enumerate(todo, 1):
        name = str(character.get("name", ""))
        png, webp = output_paths(character)
        prompt = build_prompt(character)
        if args.dry_run:
            print(f"[{index}/{len(todo)}] {name} -> {webp.relative_to(ROOT)}")
            print(prompt[:260] + ("..." if len(prompt) > 260 else ""))
            continue
        for attempt in range(1, args.retries + 2):
            start = time.time()
            try:
                raw = generate(api_key, args.model, args.endpoint_url, args.async_mode, prompt, DEFAULT_NEGATIVE, args.size, args.timeout, args.prompt_extend)
                save_images(raw, png, webp, args.webp_size)
                print(f"[{index}/{len(todo)}] {name} -> {webp.relative_to(ROOT)} {len(raw)//1024}KB {time.time()-start:.0f}s OK", flush=True)
                break
            except Exception as error:
                if attempt > args.retries:
                    print(f"[{index}/{len(todo)}] {name} FAIL final: {error}", flush=True)
                    break
                print(f"[{index}/{len(todo)}] {name} FAIL({attempt}): {error}，重试", flush=True)
                time.sleep(5)


if __name__ == "__main__":
    main()
