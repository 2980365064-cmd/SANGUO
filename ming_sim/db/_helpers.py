"""db 包内共享：office 规范化 / 势力 id 归一等模块级纯函数与常量。L3 叶子。"""

from __future__ import annotations

import re
import sqlite3
from typing import List


def normalize_office(office: str) -> str:
    """官职多职统一为半角逗号分隔：旧「兼/兼掌/兼署」与全角「，」「、」一律归一逗号，
    去空分项、去重、保序。是 office 字段落库的唯一规范化入口——所有写 characters.office
    的路径都过它，保证去重/顶缺时能按逗号分项匹配。"""
    s = (office or "").strip()
    if not s:
        return ""
    s = s.replace("兼掌", ",").replace("兼署", ",").replace("兼", ",")
    s = s.replace("，", ",").replace("、", ",")
    seen: set = set()
    parts: List[str] = []
    for p in (x.strip() for x in s.split(",")):
        if p and p not in seen:
            seen.add(p)
            parts.append(p)
    return ",".join(parts)


COURT_OFFICE_TYPES = {"内阁", "吏部", "户部", "礼部", "兵部", "刑部", "工部"}
MINISTRY_OFFICE_TYPES = {"吏部", "户部", "礼部", "兵部", "刑部", "工部"}


def infer_office_type_from_office(office: str, current_type: str = "") -> str:
    """用 office 文本校正 office_type，避免旧标签把无实职人物塞进内阁/六部。"""
    kind = (current_type or "").strip()
    if kind == "后宫":
        return kind
    text = normalize_office(office)
    if not text:
        return "待铨" if kind in COURT_OFFICE_TYPES or not kind else kind

    if re.search(r"内阁|大学士|首辅|次辅", text):
        return "内阁"
    for ministry in MINISTRY_OFFICE_TYPES:
        if ministry in text and re.search(r"尚书|侍郎|郎中|员外郎|主事|给事中", text):
            return ministry

    if re.search(r"司礼监|秉笔太监|掌印太监|随堂太监", text):
        return "司礼监"
    if re.search(r"东厂|提督东厂", text):
        return "东厂"
    if re.search(r"锦衣卫|北镇抚司|镇抚司|指挥使|千户", text):
        return "锦衣卫"
    if re.search(r"都察院|都御史|御史|巡按", text):
        return "都察院"
    if re.search(r"翰林院|翰林|编修|检讨|庶吉士|詹事", text):
        return "翰林院"
    if re.search(r"总督|巡抚|布政使|按察使|参政|知府|知县|兵备道|督粮", text):
        return "地方"
    if re.search(r"督师|经略|总兵|副总兵|游击|参将|守备|山海关|辽东|蓟辽|东江|大同|宣大", text):
        return "边镇"

    return "待铨" if kind in COURT_OFFICE_TYPES or not kind else kind


def _compact_lookup_text(value: str) -> str:
    return re.sub(r"[\s　`'\"“”‘’、/／|，,。；;：:（）()【】\[\]{}<>《》-]+", "", str(value or "")).lower()


def _normalize_power_id(conn: sqlite3.Connection, value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    rows = conn.execute("SELECT id, name, aliases FROM powers").fetchall()
    ids = {str(r["id"]) for r in rows}
    if raw in ids:
        return raw
    wanted = _compact_lookup_text(raw)
    for row in rows:
        candidates = [str(row["id"]), str(row["name"] or "")]
        aliases = str(row["aliases"] or "")
        candidates.extend(x.strip() for x in re.split(r"[,，、/／|]", aliases) if x.strip())
        for candidate in candidates:
            if _compact_lookup_text(candidate) == wanted:
                return str(row["id"])
    return raw
