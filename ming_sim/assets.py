"""资源加载与 JSON 校验辅助。L0 叶子模块。

只读 content/ 下设定文件；不持有任何全局态。
"""

from __future__ import annotations

import json
import os
import re
import textwrap
from typing import Dict, List

from ming_sim.constants import CONTENT_DIR, MONEY_UNIT, TURN_UNIT, WRAP


def wrap(text: str) -> str:
    return "\n".join(textwrap.wrap(text, width=WRAP, replace_whitespace=False))


def _resolve_asset_path(relative_path: str) -> str:
    """解析设定文件实际路径：激活剧本里有该文件就用它，否则回退默认 content/。

    延迟导入 scenario_active 保持本叶子模块干净、避免导入环。覆盖只做路径解析，
    loader 对「存在但损坏」的文件照样 SystemExit（不破坏「无 fallback」）。
    """
    from ming_sim.scenario_active import active_scenario_dir

    base = active_scenario_dir()
    if base:
        candidate = os.path.join(base, relative_path)
        if os.path.isfile(candidate):
            return candidate
    return os.path.join(CONTENT_DIR, relative_path)


def load_text_asset(relative_path: str) -> str:
    path = _resolve_asset_path(relative_path)
    try:
        with open(path, "r", encoding="utf-8") as file:
            text = file.read().strip()
    except OSError as error:
        raise SystemExit(f"设定文件缺失或不可读：{path} ({error})") from error
    return text.replace("{{TURN_UNIT}}", TURN_UNIT)


def load_json_asset(relative_path: str) -> object:
    path = _resolve_asset_path(relative_path)
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except OSError as error:
        raise SystemExit(f"设定文件缺失或不可读：{path} ({error})") from error
    except json.JSONDecodeError as error:
        raise SystemExit(f"设定文件 JSON 格式错误：{path} ({error})") from error


def strip_json_fence(text: str) -> str:
    match = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if match:
        return match.group(1).strip()
    return text.strip()


def money_value(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def format_money(value: object) -> str:
    amount = money_value(value)
    if abs(amount) < 1 and amount:
        liang = amount * 10000
        text = f"{liang:.2f}".rstrip("0").rstrip(".")
        return f"{text}两"
    text = f"{amount:.4f}".rstrip("0").rstrip(".")
    return f"{text}{MONEY_UNIT}"


def format_money_delta(value: object) -> str:
    sign = "+" if money_value(value) > 0 else ""
    return f"{sign}{format_money(value)}"


def require_dict(data: object, path: str) -> Dict[str, object]:
    if not isinstance(data, dict):
        raise SystemExit(f"设定文件应为 JSON object：content/{path}")
    return data


def require_list(data: object, path: str) -> List[object]:
    if not isinstance(data, list):
        raise SystemExit(f"设定文件应为 JSON array：content/{path}")
    return data


def string_list(value: object, path: str) -> List[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SystemExit(f"设定字段应为字符串数组：{path}")
    return [str(item) for item in value]


def int_field(data: Dict[str, object], key: str, path: str) -> int:
    try:
        return int(data[key])
    except (KeyError, TypeError, ValueError) as error:
        raise SystemExit(f"设定字段应为整数：{path}.{key}") from error


def str_field(data: Dict[str, object], key: str, path: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SystemExit(f"设定字段应为非空字符串：{path}.{key}")
    return value.strip()


# ---- 触发条件表达式（gate）的结构校验 ----
# 纯结构校验，不碰 DB（求值器在 gating.py，L4）。放 L0 供 content(L2) 调用。
# 表达式语法见 gating.py 模块 docstring：and/or 布尔树 + 叶子 + 扁平 dict（隐式 AND）。

_GATE_LEAF_OPS = (">=", "<=", ">", "<", "==", "!=", "contains")
# 扁平 dict / 叶子 cond 串允许的格式：数值比较 或 文本 ==/!=
_GATE_COND_RE = re.compile(r"^(>=|<=|>|<|==|!=)\s*\S+$")


def _validate_gate_leaf(node: Dict[str, object], path: str) -> None:
    if "key" not in node or not isinstance(node["key"], str) or not node["key"].strip():
        raise SystemExit(f"{path} 叶子缺 key（非空字符串）。")
    has_cond = "cond" in node
    has_op = "op" in node
    if has_cond == has_op:
        raise SystemExit(f"{path} 叶子须二选一：'cond' 串 或 'op'+'val'。")
    if has_cond:
        cond = str(node["cond"]).strip()
        if not _GATE_COND_RE.match(cond):
            raise SystemExit(f"{path}.cond 非法：{cond!r}（应形如 '<=240' / '==ming'）。")
        return
    op = str(node.get("op", "")).strip()
    if op not in _GATE_LEAF_OPS:
        raise SystemExit(f"{path}.op 非法：{op!r}（须属 {_GATE_LEAF_OPS}）。")
    if "val" not in node:
        raise SystemExit(f"{path} 叶子用 op 时必须带 val。")


def validate_gate_expr(expr: object, path: str) -> Dict[str, object]:
    """递归校验触发条件表达式，加载即报错（无 fallback）。返回原 expr。
    空 dict 合法（=无条件，恒真）；是否允许空由调用方决定。
    char/event 叶子的 id/field 存在性不在此校验，由 runtime 求值器处理（与 trigger_gate 一致）。"""
    if not isinstance(expr, dict):
        raise SystemExit(f"{path} 必须是对象（布尔树 / 扁平 gate）。")
    if not expr:
        return {}
    if "and" in expr or "or" in expr:
        boolkey = "and" if "and" in expr else "or"
        children = expr.get(boolkey)
        if len(expr) != 1 or not isinstance(children, list) or not children:
            raise SystemExit(f"{path}.{boolkey} 须是非空数组，且该节点只含 {boolkey} 一个键。")
        for i, child in enumerate(children):
            validate_gate_expr(child, f"{path}.{boolkey}[{i}]")
        return expr
    if "key" in expr:
        _validate_gate_leaf(expr, path)
        return expr
    # 扁平 dict：每个 value 必须是合法 cond 串
    for k, v in expr.items():
        cond = str(v).strip()
        if not _GATE_COND_RE.match(cond):
            raise SystemExit(f"{path}['{k}'] 非法条件式：{cond!r}（应形如 '<=240' / '==ming'）。")
    return expr
