"""Structured fixed directive templates.

These directives are independent from decree drafts. They give the simulator a
typed, fielded source for commands that should be easier to核销 than prose.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from ming_sim.constants import ROOT_DIR
from ming_sim.matching import match_army_id_from_text, match_region_id_from_text
from ming_sim.models import Army, Region

TEMPLATE_PATH = Path(ROOT_DIR) / "content" / "directive_templates.json"


class StructuredDirectiveError(ValueError):
    pass


def load_directive_templates() -> List[Dict[str, Any]]:
    with TEMPLATE_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise StructuredDirectiveError("directive_templates.json 顶层必须是数组。")
    return data


def get_directive_template(template_id: str) -> Dict[str, Any]:
    template_id = (template_id or "").strip()
    for item in load_directive_templates():
        if str(item.get("id") or "") == template_id:
            return item
    raise StructuredDirectiveError(f"未知固定指令模板：{template_id}")


def _clean_fields(template: Dict[str, Any], fields: Dict[str, Any]) -> Dict[str, str]:
    if not isinstance(fields, dict):
        raise StructuredDirectiveError("固定指令字段必须是 object。")
    cleaned: Dict[str, str] = {}
    for spec in template.get("fields") or []:
        key = str(spec.get("key") or "").strip()
        if not key:
            continue
        value = str(fields.get(key) or "").strip()
        required = bool(spec.get("required"))
        required_when = spec.get("required_when")
        if isinstance(required_when, dict):
            other_key = str(required_when.get("field") or "")
            values = required_when.get("values") or []
            required = required or str(fields.get(other_key) or "").strip() in {str(v) for v in values}
        if required and not value:
            raise StructuredDirectiveError(f"字段「{spec.get('label') or key}」不能为空。")
        cleaned[key] = value
    return cleaned


def _compile_tax_reform(cleaned: Dict[str, str]) -> str:
    tax_type = cleaned.get("tax_type") or "财政科目"
    regional_items = {"田赋", "辽饷", "盐税", "商税", "人头税"}
    scope = cleaned.get("scope") if tax_type in regional_items else "全国财政科目"
    action = cleaned.get("action") or "调整"
    rate = cleaned.get("rate") or "未定"
    audit = cleaned.get("audit") or "照例查核"
    note = cleaned.get("note") or ""
    return " ".join(
        f"财政科目改革：对{scope}的{tax_type}施行{action}，幅度为{rate}。查核要求：{audit}。{note}".split()
    )


def _validate_ming_selectables(template: Dict[str, Any], cleaned: Dict[str, str], db: Any = None) -> None:
    if db is None:
        return
    for spec in template.get("fields") or []:
        key = str(spec.get("key") or "").strip()
        source = str(spec.get("option_source") or "").strip()
        value = cleaned.get(key, "").strip()
        if not value:
            continue
        if source == "armies":
            row = db.conn.execute("SELECT * FROM armies WHERE name = ? OR id = ?", (value, value)).fetchone()
            if row is None:
                armies: Dict[str, Army] = {}
                for item in db.army_payload():
                    try:
                        armies[str(item["id"])] = Army(**item)
                    except TypeError:
                        continue
                matched_id = match_army_id_from_text(value, armies)
                if matched_id:
                    row = db.conn.execute("SELECT * FROM armies WHERE id = ?", (matched_id,)).fetchone()
            if row is None or str(row["owner_power"] or "ming") != "ming":
                raise StructuredDirectiveError(f"字段「{spec.get('label') or key}」只能选择大明军队。")
        elif source in ("regions", "regions_or_all") and value != "全国":
            row = db.conn.execute("SELECT * FROM regions WHERE name = ? OR id = ?", (value, value)).fetchone()
            if row is None:
                regions: Dict[str, Region] = {}
                for item in db.region_payload():
                    try:
                        fiscal = item.get("fiscal") if isinstance(item.get("fiscal"), dict) else {}
                        regions[str(item["id"])] = Region(
                            id=str(item["id"]),
                            name=str(item["name"]),
                            kind=str(item["kind"]),
                            population=int(item["population"]),
                            public_support=int(item["public_support"]),
                            unrest=int(item["unrest"]),
                            natural_disaster=str(item["natural_disaster"]),
                            human_disaster=str(item["human_disaster"]),
                            registered_land=int(item["registered_land"]),
                            hidden_land=int(item["hidden_land"]),
                            tax_per_turn=int(item["tax_per_turn"]),
                            gentry_resistance=int(item["gentry_resistance"]),
                            military_pressure=int(item["military_pressure"]),
                            status=str(item["status"]),
                            controlled_by=str(item.get("controlled_by") or "ming"),
                            fiscal=fiscal,
                        )
                    except (TypeError, ValueError, KeyError):
                        continue
                matched_id = match_region_id_from_text(value, regions)
                if matched_id:
                    row = db.conn.execute("SELECT * FROM regions WHERE id = ?", (matched_id,)).fetchone()
            if row is None or str(row["controlled_by"] or "ming") != "ming":
                raise StructuredDirectiveError(f"字段「{spec.get('label') or key}」只能选择大明辖治地区。")
        elif source == "people":
            row = db.conn.execute(
                "SELECT power_id FROM characters WHERE name = ?",
                (value,),
            ).fetchone()
            if row is None or str(row["power_id"] or "ming") != "ming":
                raise StructuredDirectiveError(f"字段「{spec.get('label') or key}」只能选择大明人物。")
        elif source == "buildings":
            row = db.conn.execute(
                """
                SELECT r.controlled_by
                FROM buildings b JOIN regions r ON r.id = b.region_id
                WHERE b.name = ? OR b.id = ?
                """,
                (value, value),
            ).fetchone()
            if row is None or str(row["controlled_by"] or "ming") != "ming":
                raise StructuredDirectiveError(f"字段「{spec.get('label') or key}」只能选择大明辖内建筑。")


def compile_structured_directive(template_id: str, fields: Dict[str, Any], db: Any = None) -> Dict[str, Any]:
    template = get_directive_template(template_id)
    cleaned = _clean_fields(template, fields)
    _validate_ming_selectables(template, cleaned, db)
    if str(template.get("id") or template_id) == "tax_reform":
        compiled = _compile_tax_reform(cleaned)
    else:
        text_template = str(template.get("compiled_text") or "{title}")
        compiled = text_template.format_map({k: v for k, v in cleaned.items()})
        compiled = " ".join(compiled.split())
    title = str(template.get("label") or template.get("id") or "固定指令")
    return {
        "template_id": str(template.get("id") or template_id),
        "category": str(template.get("category") or ""),
        "title": title,
        "fields": cleaned,
        "compiled_text": compiled,
        "settlement_hint": str(template.get("settlement_hint") or ""),
    }
