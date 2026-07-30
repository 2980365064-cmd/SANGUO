"""regions / region_logs / classes：两京十三省与阶级，增量、明细、回合摘要、撤回恢复。

_RegionsMixin：拆自原 db.py，方法体逐字未改。"""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from ming_sim.assets import format_money, format_money_delta
from ming_sim.constants import (
    ARMY_FIELD_ALIASES, ARMY_FIELD_LABELS, ARMY_QUANTITY_FIELDS, ARMY_SCORE_FIELDS, ARMY_TEXT_FIELDS,
    BUILDING_CATEGORIES, BUILDING_FIELD_LABELS, BUILDING_OUTPUT_METRICS,
    BUILDING_QUANTITY_FIELDS, BUILDING_SCORE_FIELDS, BUILDING_TEXT_FIELDS,
    ECONOMY_ACCOUNTS, POWER_FIELD_LABELS, POWER_SCORE_FIELDS,
    POWER_FIELD_ALIASES, POWER_TEXT_FIELDS, MONEY_UNIT, REGION_FIELD_LABELS, REGION_QUANTITY_FIELDS,
    FISCAL_QUANTITY_FIELDS, FISCAL_SCORE_FIELDS, REGION_FIELD_ALIASES, REGION_SCORE_FIELDS, REGION_TEXT_FIELDS, TURN_UNIT,
)
from ming_sim.content import GameContent
from ming_sim.matching import match_army_id_from_text, match_region_id_from_text
from ming_sim.models import Event, GameState, monthly_amount, period_label
from ming_sim.token_stats import tlog
from ming_sim.db._helpers import (
    normalize_office, infer_office_type_from_office,
    _compact_lookup_text, _normalize_power_id,
    COURT_OFFICE_TYPES, MINISTRY_OFFICE_TYPES,
)


class _RegionsMixin:
    def seed_administrative_units(self) -> None:
        """按建安十三年名册播种行政城池；绝不覆盖既有动态盘面。"""
        directory = self.content.administrative_units or {}
        provinces = list(directory.get("provinces", []))
        city_directory = list(directory.get("cities", []))
        commandery_labels = dict(directory.get("commandery_labels", {}))
        for item in provinces:
            self.conn.execute(
                """INSERT OR IGNORE INTO administrative_provinces
                (id, name, capital_city_id, transport, mobilization, public_support, military_pressure, security_coordination, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (str(item["id"]), str(item["name"]), str(item.get("capital_city_id") or ""),
                 int(item.get("transport", 50)), int(item.get("mobilization", 50)),
                 int(item.get("public_support", 50)), int(item.get("military_pressure", 50)),
                 int(item.get("security_coordination", 50)), str(item.get("status") or "")),
            )
        by_commandery: Dict[str, List[Dict[str, object]]] = {}
        for item in city_directory:
            by_commandery.setdefault(str(item["commandery_id"]), []).append(dict(item))
        rows = {str(row["id"]): row for row in self.conn.execute("SELECT * FROM regions ORDER BY id").fetchall()}
        for commandery_id, label in commandery_labels.items():
            if commandery_id not in rows:
                raise ValueError(f"郡名册引用了不存在的郡：{commandery_id}")
            self.conn.execute(
                "UPDATE regions SET name=?, status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (str(label["name"]), str(label.get("status") or rows[commandery_id]["status"]), commandery_id),
            )
        rows = {str(row["id"]): row for row in self.conn.execute("SELECT * FROM regions ORDER BY id").fetchall()}
        for commandery_id, entries in by_commandery.items():
            row = rows.get(commandery_id)
            if row is None:
                raise ValueError(f"城池目录引用了不存在的郡：{commandery_id}")
            fiscal = json.loads(str(row["fiscal"] or "{}"))
            regional_stock = max(0, int(fiscal.get("grain_stock") or fiscal.get("granary") or 0))
            existing = self.conn.execute(
                "SELECT id, grain_stock FROM administrative_cities WHERE commandery_id=? ORDER BY is_commandery_capital DESC, id",
                (commandery_id,),
            ).fetchall()
            total_before = regional_stock + sum(max(0, int(city["grain_stock"] or 0)) for city in existing)
            for item in entries:
                city_id = str(item["id"])
                if self.conn.execute("SELECT 1 FROM administrative_cities WHERE id=?", (city_id,)).fetchone():
                    self.conn.execute(
                        "UPDATE administrative_cities SET name=?, commandery_id=?, province_id=?, territory_id=?, is_commandery_capital=?, strategic_role=? WHERE id=?",
                        (str(item["name"]), commandery_id, str(item["province_id"]), city_id,
                         1 if bool(item.get("capital")) else 0, str(item["role"]), city_id),
                    )
                    continue
                requested = max(0, round(total_before * float(item.get("stock_share") or 0)))
                granted = min(regional_stock, requested)
                regional_stock -= granted
                population = int(row["population"] or 0)
                self.conn.execute(
                    """INSERT INTO administrative_cities
                    (id,name,commandery_id,province_id,territory_id,is_commandery_capital,strategic_role,
                     controlled_by,order_score,grain_stock,market_capacity,fortification,garrison_capacity,status)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (city_id, str(item["name"]), commandery_id, str(item["province_id"]), city_id,
                     1 if bool(item.get("capital")) else 0, str(item["role"]), str(row["controlled_by"]),
                     max(20, min(90, int(row["public_support"]) - int(row["unrest"]) // 3)), granted,
                     max(20, min(90, int(fiscal.get("commerce_tax") or fiscal.get("commerce") or 0) * 8 + 24)),
                     max(20, min(95, int(fiscal.get("fortification") or 50))),
                     max(1, min(6, 1 + population // 110)), f"{str(item['name'])}为{str(item['role'])}"),
                )
            fiscal["grain_stock"] = regional_stock
            fiscal["granary"] = regional_stock
            self.conn.execute("UPDATE regions SET fiscal=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (json.dumps(fiscal, ensure_ascii=False), commandery_id))
        self.recompute_administrative_control()
        self.conn.commit()

    def recompute_administrative_control(self) -> None:
        """城权决定郡权，郡权多数决定州权；州权为派生事实，不单独写入。"""
        commanderies = self.conn.execute("SELECT id, kind, controlled_by FROM regions ORDER BY id").fetchall()
        for commandery in commanderies:
            cities = self.conn.execute(
                "SELECT controlled_by,is_commandery_capital FROM administrative_cities WHERE commandery_id=? ORDER BY is_commandery_capital DESC,id",
                (commandery["id"],),
            ).fetchall()
            if not cities:
                continue
            tally: Dict[str, int] = {}
            for city in cities:
                power = str(city["controlled_by"])
                tally[power] = tally.get(power, 0) + 1
            high = max(tally.values())
            leaders = sorted(power for power, count in tally.items() if count == high)
            capital = next((str(city["controlled_by"]) for city in cities if int(city["is_commandery_capital"] or 0)), "")
            controller = capital if capital in leaders else leaders[0]
            if controller != str(commandery["controlled_by"]):
                self.conn.execute("UPDATE regions SET controlled_by=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (controller, commandery["id"]))

    def settle_administrative_layers(self, state: GameState) -> List[Dict[str, object]]:
        """无随机的层级月结：城池围城/驻军 → 州域统筹；郡级仍由既有区域结算负责。"""
        turn = int(getattr(state, "turn", 0))
        changes: List[Dict[str, object]] = []
        active_targets = {str(row["target_node"]) for row in self.conn.execute("SELECT target_node FROM sieges WHERE status='active'").fetchall()}
        # 旧档围城以郡节点为目标；只在兼容读取时映射至该郡治城，不创建第二份围城事实。
        for target in list(active_targets):
            capital = self.conn.execute("SELECT id FROM administrative_cities WHERE commandery_id=? AND is_commandery_capital=1", (target,)).fetchone()
            if capital is not None:
                active_targets.add(str(capital["id"]))
        for city in self.conn.execute("SELECT * FROM administrative_cities ORDER BY id").fetchall():
            status = "围城中" if str(city["id"]) in active_targets else "未围"
            if status != str(city["siege_status"]):
                self.conn.execute("UPDATE administrative_cities SET siege_status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (status, city["id"]))
                self.conn.execute("INSERT INTO administrative_logs (turn,scope,entity_id,field,old_value,new_value,reason) VALUES (?,?,?,?,?,?,?)", (turn,"city",city["id"],"siege_status",str(city["siege_status"]),status,"围城状态随既有围城结算同步"))
                changes.append({"scope":"city","id":city["id"],"field":"siege_status","value":status})
        for province in self.conn.execute("SELECT * FROM administrative_provinces ORDER BY id").fetchall():
            rows = self.conn.execute("SELECT public_support,military_pressure FROM regions WHERE kind=?", (province["id"],)).fetchall()
            if not rows:
                continue
            support = round(sum(int(row["public_support"] or 0) for row in rows) / len(rows))
            pressure = round(sum(int(row["military_pressure"] or 0) for row in rows) / len(rows))
            for field, value in (("public_support", support), ("military_pressure", pressure)):
                old = int(province[field] or 0)
                if old == value:
                    continue
                self.conn.execute(f"UPDATE administrative_provinces SET {field}=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (value, province["id"]))
                self.conn.execute("INSERT INTO administrative_logs (turn,scope,entity_id,field,old_value,new_value,reason) VALUES (?,?,?,?,?,?,?)", (turn,"province",province["id"],field,str(old),str(value),"辖郡月度事实汇总"))
                changes.append({"scope":"province","id":province["id"],"field":field,"value":value})
        self.recompute_administrative_control()
        self.conn.commit()
        return changes

    def administrative_detail(self, scope: str, entity_id: str) -> Dict[str, object]:
        if scope == "city":
            row = self.conn.execute("SELECT * FROM administrative_cities WHERE id=?", (entity_id,)).fetchone()
            if row is None: raise ValueError("城池不存在")
            armies = self.conn.execute("SELECT * FROM armies WHERE station_node IN (?, ?) AND active=1 ORDER BY id", (row["id"], row["commandery_id"])).fetchall()
            return {"scope": "city", "id": row["id"], "name": row["name"], "commandery_id": row["commandery_id"], "province_id": row["province_id"], "controlled_by": row["controlled_by"], "strategic_role": row["strategic_role"], "order_score": row["order_score"], "grain_stock": row["grain_stock"], "market_capacity": row["market_capacity"], "fortification": row["fortification"], "garrison_capacity": row["garrison_capacity"], "siege_status": row["siege_status"], "status": row["status"], "stationed_armies": [dict(a) for a in armies]}
        if scope == "province":
            province = self.conn.execute("SELECT * FROM administrative_provinces WHERE id=?", (entity_id,)).fetchone()
            if province is None: raise ValueError("州不存在")
            commanderies = self.conn.execute("SELECT * FROM regions WHERE kind=? ORDER BY name", (entity_id,)).fetchall()
            cities = self.conn.execute("SELECT * FROM administrative_cities WHERE province_id=? ORDER BY name", (entity_id,)).fetchall()
            tally: Dict[str, int] = {}
            for commandery in commanderies: tally[str(commandery["controlled_by"])] = tally.get(str(commandery["controlled_by"]), 0) + 1
            controller = sorted(tally, key=lambda key: (-tally[key], key))[0] if tally else ""
            return {"scope":"province", "id":province["id"], "name":province["name"], "controlled_by":controller, "transport":province["transport"], "mobilization":province["mobilization"], "public_support":province["public_support"], "military_pressure":province["military_pressure"], "security_coordination":province["security_coordination"], "status":province["status"], "commandery_count":len(commanderies), "city_count":len(cities), "population":sum(int(r["population"] or 0) for r in commanderies), "tax_per_turn":sum(int(r["tax_per_turn"] or 0) for r in commanderies), "commanderies":[{"id":r["id"],"name":r["name"],"controlled_by":r["controlled_by"]} for r in commanderies]}
        row = self.conn.execute("SELECT * FROM regions WHERE id=?", (entity_id,)).fetchone()
        if row is None: raise ValueError("郡不存在")
        fiscal = json.loads(str(row["fiscal"] or "{}"))
        cities = self.conn.execute("SELECT id,name,controlled_by,fortification,grain_stock,is_commandery_capital,strategic_role,siege_status FROM administrative_cities WHERE commandery_id=? ORDER BY is_commandery_capital DESC,name", (entity_id,)).fetchall()
        capital = next((dict(city) for city in cities if int(city["is_commandery_capital"] or 0)), None)
        return {"scope":"commandery", "id":row["id"], "name":row["name"], "province_id":row["kind"], "controlled_by":row["controlled_by"], "population":row["population"], "public_support":row["public_support"], "unrest":row["unrest"], "military_pressure":row["military_pressure"], "gentry_resistance":row["gentry_resistance"], "tax_per_turn":row["tax_per_turn"], "fiscal":fiscal, "status":row["status"], "city":capital, "cities":[dict(city) for city in cities], "city_count":len(cities)}
    def region_grain_stock(self, region_id: str) -> int:
        row = self.conn.execute("SELECT fiscal FROM regions WHERE id=?", (region_id,)).fetchone()
        if row is None:
            raise ValueError(f"地区未入库：{region_id}")
        try:
            fiscal = json.loads(str(row["fiscal"] or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            fiscal = {}
        regional_stock = max(0, int(fiscal.get("grain_stock") or fiscal.get("granary") or 0))
        city_stock = sum(max(0, int(city["grain_stock"] or 0)) for city in self.conn.execute("SELECT grain_stock FROM administrative_cities WHERE commandery_id=?", (region_id,)).fetchall())
        return regional_stock + city_stock

    def adjust_region_grain_stock(
        self,
        state: object,
        region_id: str,
        delta: int,
        reason: str,
        actor: str = "补给系统",
    ) -> int:
        row = self.conn.execute("SELECT fiscal FROM regions WHERE id=?", (region_id,)).fetchone()
        if row is None:
            raise ValueError(f"地区未入库：{region_id}")
        try:
            fiscal = json.loads(str(row["fiscal"] or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            fiscal = {}
        regional_stock = max(0, int(fiscal.get("grain_stock") or fiscal.get("granary") or 0))
        cities = self.conn.execute("SELECT id, grain_stock FROM administrative_cities WHERE commandery_id=? ORDER BY is_commandery_capital DESC,id", (region_id,)).fetchall()
        city_stock = sum(max(0, int(city["grain_stock"] or 0)) for city in cities)
        old_value = regional_stock + city_stock
        requested_delta = int(delta)
        if requested_delta < 0:
            actual_delta = -min(old_value, abs(requested_delta))
            remaining = abs(actual_delta)
            city_delta = 0
            for city in cities:
                old_stock = max(0, int(city["grain_stock"] or 0))
                consumed = min(old_stock, remaining)
                if consumed:
                    self.conn.execute("UPDATE administrative_cities SET grain_stock=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (old_stock - consumed, city["id"]))
                    self.conn.execute("INSERT INTO administrative_logs (turn,scope,entity_id,field,old_value,new_value,reason) VALUES (?,?,?,?,?,?,?)", (int(getattr(state, "turn", 0)), "city", city["id"], "grain_stock", str(old_stock), str(old_stock-consumed), str(reason)))
                    city_delta -= consumed
                    remaining -= consumed
                if not remaining:
                    break
            city_stock += city_delta
            regional_stock = max(0, regional_stock - remaining)
        else:
            actual_delta = requested_delta
            city_delta = 0
            regional_stock += actual_delta
        new_value = regional_stock + city_stock
        fiscal["grain_stock"] = regional_stock
        fiscal["granary"] = regional_stock
        self.conn.execute(
            "UPDATE regions SET fiscal=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (json.dumps(fiscal, ensure_ascii=False), region_id),
        )
        self.conn.execute(
            """
            INSERT INTO region_logs
            (turn, year, period, region_id, field, old_value, new_value, delta, reason, actor)
            VALUES (?, ?, ?, ?, 'grain_stock', ?, ?, ?, ?, ?)
            """,
            (
                int(getattr(state, "turn", 0)),
                int(getattr(state, "year", 208)),
                int(getattr(state, "period", 1)),
                region_id,
                str(old_value),
                str(new_value),
                new_value - old_value,
                str(reason),
                str(actor),
            ),
        )
        self.conn.commit()
        return new_value

    def region_rows(self, limit: int | None = None, danger_order: bool = False) -> List[sqlite3.Row]:
        order = (
            "(unrest + military_pressure + gentry_resistance + (100 - public_support)) DESC, name"
            if danger_order
            else "kind DESC, name"
        )
        sql = f"""
            SELECT *
            FROM regions
            ORDER BY {order}
        """
        params: Tuple[object, ...] = ()
        if limit is not None:
            sql += " LIMIT ?"
            params = (limit,)
        return self.conn.execute(sql, params).fetchall()

    def region_payload(self, limit: int | None = None, danger_order: bool = False) -> List[Dict[str, object]]:
        payload: List[Dict[str, object]] = []
        for row in self.region_rows(limit=limit, danger_order=danger_order):
            try:
                fiscal = json.loads(str(row["fiscal"] or "{}"))
            except Exception:
                fiscal = {}
            payload.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "kind": row["kind"],
                    "population": int(row["population"]),
                    "public_support": int(row["public_support"]),
                    "unrest": int(row["unrest"]),
                    "natural_disaster": row["natural_disaster"],
                    "human_disaster": row["human_disaster"],
                    "registered_land": int(row["registered_land"]),
                    "hidden_land": int(row["hidden_land"]),
                    "tax_per_turn": int(row["tax_per_turn"]),
                    "fiscal": fiscal,
                    "grain_output": int(fiscal.get("grain_output") or 0),
                    "grain_stock": int(fiscal.get("grain_stock") or 0),
                    "gentry_resistance": int(row["gentry_resistance"]),
                    "military_pressure": int(row["military_pressure"]),
                    "status": row["status"],
                    "controlled_by": row["controlled_by"],
                }
            )
        return payload

    def region_report(self, limit: int = 5) -> str:
        rows = self.region_rows(limit=limit, danger_order=True)
        if not rows:
            return "地区尚未建档。"
        total_tax = self.conn.execute("SELECT SUM(tax_per_turn) AS total FROM regions").fetchone()
        total_tax_value = int(total_tax["total"] or 0)
        parts = []
        for row in rows:
            try:
                fiscal = json.loads(str(row["fiscal"] or "{}"))
            except Exception:
                fiscal = {}
            held = ""
            if str(row["controlled_by"]) != "liu_bei":
                held = f"【已为{self.power_display_name(row['controlled_by'])}所据】"
            parts.append(
                f"{row['name']}{held}：民心{row['public_support']}、动乱{row['unrest']}、"
                f"粮食年产{int(fiscal.get('grain_output') or 0)}万石、"
                f"可调余粮{int(fiscal.get('grain_stock') or 0)}万石、"
                f"田赋{format_money(monthly_amount(int(row['tax_per_turn'])))}/{TURN_UNIT}，{row['status']}"
            )
        return f"地区警讯：{'；'.join(parts)}。两京十三省田赋账面合计{format_money(monthly_amount(total_tax_value))}/{TURN_UNIT}（不含辽饷/盐/商）。"

    def region_detail(self, raw_name: str) -> str:
        region_id = match_region_id_from_text(raw_name, self.content.regions)
        if region_id is None:
            raise ValueError(f"未找到地区：{raw_name}")
        row = self.conn.execute("SELECT * FROM regions WHERE id = ?", (region_id,)).fetchone()
        if row is None:
            raise ValueError(f"地区未入库：{raw_name}")
        held = ""
        if str(row["controlled_by"]) != "liu_bei":
            held = f"，控制权：已为{self.power_display_name(row['controlled_by'])}所据（非己方辖治）"
        try:
            fiscal = json.loads(str(row["fiscal"] or "{}"))
        except Exception:
            fiscal = {}
        return (
            f"{row['name']}（{row['kind']}）{held}：人口{row['population']}万人，"
            f"民心{row['public_support']}，动乱{row['unrest']}，"
            f"粮食年产{int(fiscal.get('grain_output') or 0)}万石，可调余粮{int(fiscal.get('grain_stock') or 0)}万石，"
            f"田亩{row['registered_land']}万亩，隐田{row['hidden_land']}万亩，"
            f"田赋账面{format_money(monthly_amount(int(row['tax_per_turn'])))}/{TURN_UNIT}（另有辽饷/盐/商各计），"
            f"士绅阻力{row['gentry_resistance']}，军事压力{row['military_pressure']}。"
            f"天灾：{row['natural_disaster']}；人祸：{row['human_disaster']}；状态：{row['status']}"
        )

    def turn_region_summary(self, turn: int, limit: int = 10) -> str:
        rows = self.conn.execute(
            """
            SELECT rl.*, r.name AS region_name
            FROM region_logs rl
            JOIN regions r ON r.id = rl.region_id
            WHERE rl.turn = ?
            ORDER BY rl.id
            LIMIT ?
            """,
            (turn, limit),
        ).fetchall()
        if not rows:
            return f"本{TURN_UNIT}地区盘面无明确变化。"
        parts = []
        for row in rows:
            label = REGION_FIELD_LABELS.get(str(row["field"]), str(row["field"]))
            delta = row["delta"]
            if delta is None:
                parts.append(f"{row['region_name']}{label}改为{row['new_value']}（{row['reason']}）")
            else:
                sign = "+" if int(delta) > 0 else ""
                parts.append(f"{row['region_name']}{label}{sign}{int(delta)}（{row['reason']}）")
        return "；".join(parts) + "。"

    def apply_region_deltas(
        self,
        state: GameState,
        event: Event,
        edict_id: int | None,
        actor: str,
        region_deltas: Dict[str, Dict[str, object]],
    ) -> List[Dict[str, object]]:
        changes: List[Dict[str, object]] = []
        # 特殊 key「全国/__all__」：玩家不分省的商税/盐税加征减征，按各省现有占比摊到每省 fiscal。
        _NATIONWIDE_KEYS = {"全国", "__all__", "all", "nationwide"}
        _NATIONWIDE_FIELD_STEM = {"commerce_tax": "商税", "salt_tax": "盐税",
                                  "商税基数": "商税", "盐税基数": "盐税"}
        for region_id, raw_changes in region_deltas.items():
            if str(region_id).strip() in _NATIONWIDE_KEYS:
                reason = str(raw_changes.get("reason") or raw_changes.get("原因") or event.title).strip()[:80]
                for raw_field, value in raw_changes.items():
                    stem = _NATIONWIDE_FIELD_STEM.get(str(raw_field).strip())
                    if stem is None:
                        continue  # 全国 key 只摊商税/盐税绝对额；其余字段需具体省份，忽略
                    try:
                        delta = int(value)
                    except (TypeError, ValueError):
                        continue
                    touched = self.apply_dynamic_fiscal_delta(stem, delta)
                    if touched:
                        changes.append({"region_id": "全国", "field": stem,
                                        "delta": delta, "touched": touched, "reason": reason})
                continue
            row = self.conn.execute("SELECT * FROM regions WHERE id = ?", (region_id,)).fetchone()
            if row is None:
                print(f"[WARN] region_delta 引用未入库地区 '{region_id}' → 跳过")
                continue
            reason = str(raw_changes.get("reason") or raw_changes.get("原因") or event.title).strip()[:80]
            for raw_field, value in raw_changes.items():
                field = REGION_FIELD_ALIASES.get(str(raw_field).strip(), str(raw_field).strip())
                if field == "reason":
                    continue
                # 先判字段合法，再取值：非法字段直接报清楚。
                all_direct = REGION_SCORE_FIELDS + REGION_QUANTITY_FIELDS + REGION_TEXT_FIELDS
                if field not in all_direct and field not in FISCAL_SCORE_FIELDS and field not in FISCAL_QUANTITY_FIELDS:
                    raise LLMContractError(
                        f"{TURN_UNIT}末执行评估引用了非法地区字段：'{raw_field}'（地区 '{region_id}'）。"
                        f"合法字段：{all_direct + FISCAL_SCORE_FIELDS + FISCAL_QUANTITY_FIELDS}"
                    )

                # ── fiscal JSON 子字段（corruption 等）────────────────────────
                if field in FISCAL_SCORE_FIELDS or field in FISCAL_QUANTITY_FIELDS:
                    current_row = self.conn.execute(
                        "SELECT fiscal FROM regions WHERE id = ?", (region_id,)
                    ).fetchone()
                    fiscal: dict = json.loads(str((current_row or row)["fiscal"] or "{}"))
                    old_value = fiscal.get(field, 50 if field in FISCAL_SCORE_FIELDS else 0)
                    delta = int(value)
                    if field in FISCAL_SCORE_FIELDS:
                        # 帝国修正：该地区该字段若有 active 修正符，先放大/缩小 delta
                        net_pct = int(((self.legacy_modifiers(state).get("regions") or {})
                                       .get(region_id) or {}).get(field, 0) or 0)
                        if net_pct:
                            delta = self.apply_legacy_pct(delta, net_pct)
                        new_value = max(0, min(100, int(old_value) + delta))
                    else:
                        new_value = max(0, int(old_value) + delta)
                    actual_delta = new_value - int(old_value)
                    if actual_delta == 0:
                        continue
                    fiscal[field] = new_value
                    self.conn.execute(
                        "UPDATE regions SET fiscal = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (json.dumps(fiscal, ensure_ascii=False), region_id),
                    )
                    self.conn.execute(
                        """
                        INSERT INTO region_logs
                        (turn, year, period, region_id, field, old_value, new_value, delta, reason, event_id, edict_id, actor)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (state.turn, state.year, state.period, region_id,
                         field, str(old_value), str(new_value), actual_delta,
                         reason, event.id, edict_id, actor),
                    )
                    changes.append({
                        "region": row["name"], "field": field,
                        "label": REGION_FIELD_LABELS.get(field, field),
                        "old": old_value, "new": new_value,
                        "delta": actual_delta, "reason": reason,
                    })
                    continue

                # ── 直接列字段 ────────────────────────────────────────────────
                old_value = row[field]
                if field in REGION_SCORE_FIELDS:
                    delta = int(value)
                    # 遗产百分比修正：该地区该字段若有 active 遗产修正符，先放大/缩小 delta
                    net_pct = int(((self.legacy_modifiers(state).get("regions") or {})
                                   .get(region_id) or {}).get(field, 0) or 0)
                    if net_pct:
                        delta = self.apply_legacy_pct(delta, net_pct)
                    new_value = max(0, min(100, int(old_value) + delta))
                    actual_delta = new_value - int(old_value)
                    if actual_delta == 0:
                        continue
                    stored_new: object = new_value
                    log_delta: int | None = actual_delta
                elif field in REGION_QUANTITY_FIELDS:
                    delta = int(value)
                    new_value = max(0, int(old_value) + delta)
                    actual_delta = new_value - int(old_value)
                    if actual_delta == 0:
                        continue
                    stored_new = new_value
                    log_delta = actual_delta
                else:  # REGION_TEXT_FIELDS
                    text_value = str(value).strip()[:160]
                    if field == "controlled_by":
                        # 先归一化（中文名/别名/大小写 → 标准 power id），与 armies.py 同。
                        text_value = _normalize_power_id(self.conn, text_value) or text_value
                    if not text_value or text_value in ("None", "null") or text_value == str(old_value):
                        continue
                    if field == "controlled_by":
                        valid_powers = {r[0] for r in self.conn.execute("SELECT id FROM powers")}
                        if text_value not in valid_powers:
                            print(f"[WARN] controlled_by 非法值 '{text_value}'（地区 '{region_id}'）→ 跳过")
                            continue
                    stored_new = text_value
                    log_delta = None
                self.conn.execute(
                    f"UPDATE regions SET {field} = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (stored_new, region_id),
                )
                self.conn.execute(
                    """
                    INSERT INTO region_logs
                    (turn, year, period, region_id, field, old_value, new_value, delta, reason, event_id, edict_id, actor)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        state.turn, state.year, state.period, region_id,
                        field, str(old_value), str(stored_new), log_delta,
                        reason, event.id, edict_id, actor,
                    ),
                )
                changes.append(
                    {
                        "region": row["name"], "field": field,
                        "label": REGION_FIELD_LABELS.get(field, field),
                        "old": old_value, "new": stored_new,
                        "delta": log_delta, "reason": reason,
                    }
                )

                # ── 收复触发：controlled_by 由非 liu_bei → liu_bei，覆盖 on_restore 预置 ──
                if (
                    field == "controlled_by"
                    and str(stored_new) == "liu_bei"
                    and str(old_value) != "liu_bei"
                ):
                    extra = self._apply_on_restore(state, region_id, event, edict_id, actor, reason)
                    changes.extend(extra)
        self.conn.commit()
        return changes

    def _apply_on_restore(
        self,
        state: GameState,
        region_id: str,
        event: Event,
        edict_id: int | None,
        actor: str,
        reason: str,
    ) -> List[Dict[str, object]]:
        """收复瞬间用 region.on_restore 覆盖主字段，记 region_logs。"""
        region_def = self.content.regions.get(region_id)
        if region_def is None or not region_def.on_restore:
            return []
        preset = region_def.on_restore
        row = self.conn.execute("SELECT * FROM regions WHERE id = ?", (region_id,)).fetchone()
        if row is None:
            return []
        all_direct = REGION_SCORE_FIELDS + REGION_QUANTITY_FIELDS + REGION_TEXT_FIELDS
        out: List[Dict[str, object]] = []
        for raw_field, value in preset.items():
            if raw_field == "fiscal":
                if not isinstance(value, dict):
                    continue
                fiscal = json.loads(str(row["fiscal"] or "{}"))
                for sub_field, sub_val in value.items():
                    if sub_field not in FISCAL_SCORE_FIELDS:
                        continue
                    old_sub = fiscal.get(sub_field, 0)
                    new_sub = int(sub_val)
                    if int(old_sub) == new_sub:
                        continue
                    fiscal[sub_field] = new_sub
                    self.conn.execute(
                        "INSERT INTO region_logs (turn, year, period, region_id, field, old_value, new_value, delta, reason, event_id, edict_id, actor) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (state.turn, state.year, state.period, region_id,
                         sub_field, str(old_sub), str(new_sub), new_sub - int(old_sub),
                         f"收复重置：{reason}", event.id, edict_id, actor),
                    )
                    out.append({
                        "region": row["name"], "field": sub_field,
                        "label": REGION_FIELD_LABELS.get(sub_field, sub_field),
                        "old": old_sub, "new": new_sub,
                        "delta": new_sub - int(old_sub), "reason": f"收复重置：{reason}",
                    })
                self.conn.execute(
                    "UPDATE regions SET fiscal = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (json.dumps(fiscal, ensure_ascii=False), region_id),
                )
                continue
            if raw_field == "controlled_by":
                continue  # 控制权已写完，跳过
            if raw_field not in all_direct:
                continue
            old_val = row[raw_field]
            if raw_field in (REGION_SCORE_FIELDS + REGION_QUANTITY_FIELDS):
                new_val: object = int(value)
            else:
                new_val = str(value)
            if str(old_val) == str(new_val):
                continue
            self.conn.execute(
                f"UPDATE regions SET {raw_field} = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (new_val, region_id),
            )
            log_delta = (int(new_val) - int(old_val)) if raw_field in (REGION_SCORE_FIELDS + REGION_QUANTITY_FIELDS) else None
            self.conn.execute(
                "INSERT INTO region_logs (turn, year, period, region_id, field, old_value, new_value, delta, reason, event_id, edict_id, actor) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (state.turn, state.year, state.period, region_id,
                 raw_field, str(old_val), str(new_val), log_delta,
                 f"收复重置：{reason}", event.id, edict_id, actor),
            )
            out.append({
                "region": row["name"], "field": raw_field,
                "label": REGION_FIELD_LABELS.get(raw_field, raw_field),
                "old": old_val, "new": new_val,
                "delta": log_delta, "reason": f"收复重置：{reason}",
            })
        return out

    def class_rows(self, region_id: str = "") -> List[sqlite3.Row]:
        """region_id="" 取全国汇总行；其它取该省切片。"""
        return self.conn.execute(
            "SELECT name, region_id, population, satisfaction, leverage, agenda "
            "FROM classes WHERE region_id = ? ORDER BY name",
            (region_id,),
        ).fetchall()

    def class_report(self) -> str:
        """全国汇总 + 各省紧张切片（sat<=30 且 lev>=60）。"""
        national = self.class_rows("")
        if not national:
            return "阶级未建档。"
        head = "；".join(
            f"{row['name']}满意{row['satisfaction']}、势力{row['leverage']}（{row['agenda']}）"
            for row in national
        )
        hot = self.conn.execute(
            """
            SELECT c.name, c.region_id, c.satisfaction, c.leverage, r.name AS region_name
            FROM classes c
            LEFT JOIN regions r ON r.id = c.region_id
            WHERE c.region_id <> '' AND c.satisfaction <= 30 AND c.leverage >= 60
            ORDER BY c.satisfaction ASC, c.leverage DESC
            """
        ).fetchall()
        if not hot:
            return f"阶级总览：{head}。各省阶级暂无高压预警。"
        warn = "；".join(
            f"{row['region_name'] or row['region_id']} {row['name']}满意{row['satisfaction']}/势力{row['leverage']}"
            for row in hot
        )
        return f"阶级总览：{head}。高压预警：{warn}。"

    def adjust_classes(self, deltas: Dict[str, Dict[str, int]]) -> None:
        """deltas 结构：{ key: {satisfaction: +/-N, leverage: +/-N} }
        key 形式：'农民' (全国) 或 '农民@shaanxi' (省级)。
        """
        for key, fields in deltas.items():
            if not fields:
                continue
            if "@" in key:
                name, region_id = key.split("@", 1)
            else:
                name, region_id = key, ""
            row = self.conn.execute(
                "SELECT satisfaction, leverage FROM classes WHERE name = ? AND region_id = ?",
                (name.strip(), region_id.strip()),
            ).fetchone()
            if not row:
                continue
            sat = int(row["satisfaction"]) + int(fields.get("satisfaction", 0) or 0)
            lev = int(row["leverage"]) + int(fields.get("leverage", 0) or 0)
            sat = max(0, min(100, sat))
            lev = max(0, min(100, lev))
            self.conn.execute(
                "UPDATE classes SET satisfaction = ?, leverage = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE name = ? AND region_id = ?",
                (sat, lev, name.strip(), region_id.strip()),
            )
        self.conn.commit()
