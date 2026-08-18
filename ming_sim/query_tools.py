"""AI 裁决查询工具集。

提供一组只读查询函数,AI 裁决 Agent 可以按需调用,获取真实盘面数据。
替代原有的固定裁决包(adjudication pack)方案。

核心原则:
1. 所有工具只读,不修改任何数据
2. 返回结构化字典(可 JSON 序列化)
3. AI Agent 按需查询,而不是被喂固定数据包
4. 查询结果必须来自数据库真实数据
"""

from __future__ import annotations

import json
import threading
from typing import Any, Callable, Dict, List, Optional

from ming_sim.db import GameDB
from ming_sim.models import GameState


__all__ = [
    "build_query_tools",
    "QueryToolKit",
    "BatchQueryCache",
]


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _row_to_dict(row) -> Optional[Dict[str, Any]]:
    """将 sqlite3 Row 转为字典,处理 JSON 字段。"""
    if row is None:
        return None
    result = dict(row)
    # 尝试解析常见的 JSON 字段
    for key in list(result.keys()):
        value = result[key]
        if isinstance(value, str) and value.strip().startswith(("{", "[")):
            try:
                result[key] = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                pass
    return result


def _rows_to_list(rows, limit: int = 50) -> List[Dict[str, Any]]:
    """将多行结果转为字典列表,带默认限制。"""
    return [_row_to_dict(row) for row in rows[:limit]]


# ---------------------------------------------------------------------------
# 批次查询缓存
# ---------------------------------------------------------------------------

class BatchQueryCache:
    """线程安全的查询结果缓存，用于同一裁决批次内共享查询结果。

    用法：
        cache = BatchQueryCache()
        toolkit = QueryToolKit(db, state, cache=cache)
        # 批次结束后清空
        cache.clear()
    """

    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get_or_compute(self, key: str, compute_fn: Callable[[], Any]) -> Any:
        """从缓存获取或计算并存储。计算在锁外执行以避免阻塞。"""
        with self._lock:
            if key in self._cache:
                self.hits += 1
                return self._cache[key]
            self.misses += 1

        # 计算在锁外（可能涉及慢速 DB 查询）
        value = compute_fn()

        with self._lock:
            # 双重检查：其他线程可能已填入
            if key not in self._cache:
                self._cache[key] = value
            return self._cache[key]

    def set(self, key: str, value: Any) -> None:
        """直接写入缓存。"""
        with self._lock:
            self._cache[key] = value

    def get(self, key: str) -> Optional[Any]:
        """直接读取缓存（不触发计算）。"""
        with self._lock:
            return self._cache.get(key)

    def clear(self) -> None:
        """清空缓存和统计。"""
        with self._lock:
            self._cache.clear()
            self.hits = 0
            self.misses = 0

    def stats(self) -> Dict[str, int]:
        """返回缓存统计。"""
        with self._lock:
            return {"hits": self.hits, "misses": self.misses, "size": len(self._cache)}


# ---------------------------------------------------------------------------
# 工具集构建器
# ---------------------------------------------------------------------------

class QueryToolKit:
    """查询工具集工厂。

    用法:
        toolkit = QueryToolKit(db, state)
        tools = toolkit.get_tools()
        # 传给 agno Agent
        agent = Agent(tools=tools, ...)

    缓存:
        可传入 BatchQueryCache 实现同批次内查询结果共享。
    """

    def __init__(self, db: GameDB, state: GameState, *, cache: Optional[BatchQueryCache] = None):
        self.db = db
        self.state = state
        self._cache = cache

    def _cache_key(self, method: str, *args: Any) -> str:
        """生成缓存 key。"""
        return f"{method}:{':'.join(str(a) for a in args)}"

    def _cached(self, key: str, compute_fn: Callable[[], Any]) -> Any:
        """如果有缓存则走缓存，否则直接计算。"""
        if self._cache is None:
            return compute_fn()
        return self._cache.get_or_compute(key, compute_fn)
    
    def get_tools(self) -> List[Callable]:
        """返回所有查询工具函数列表。"""
        return [
            self.query_character,
            self.query_army,
            self.query_region,
            self.query_power,
            self.query_diplomacy,
            self.query_building,
            self.query_city,
            self.query_faction_internal,
            self.query_world_context,
            self.query_regional_state,
            self.query_regional_incidents,
            self.query_power_internal_dynamics,
            self.query_economy,
            self.query_metrics,
            self.query_intelligence_reports,
            self.query_events,
            self.query_memorials,
            self.query_secret_orders,
            self.query_battle_history,
            self.query_siege,
            self.query_turn_report,
            self.search_memories,
            self.query_tactic_reference,
            self.query_rules,
        ]
    
    # -----------------------------------------------------------------------
    # 核心实体查询
    # -----------------------------------------------------------------------
    
    def query_character(self, name: str) -> Dict[str, Any]:
        """查询人物详情。

        Args:
            name: 人物姓名(如 "诸葛亮")

        Returns:
            包含人物属性、特性、派系、忠诚度、官职、状态等信息的字典。
        """
        def _compute():
            # 合并 character + faction 为 1 次 LEFT JOIN（P2 优化）
            row = self.db.conn.execute(
                """
                SELECT c.*,
                       f.satisfaction AS _f_satisfaction,
                       f.leverage AS _f_leverage,
                       f.agenda AS _f_agenda
                FROM characters c
                LEFT JOIN factions f ON c.faction = f.name
                WHERE c.name = ?
                """,
                (name,),
            ).fetchone()

            if row is None:
                return {"found": False, "error": f"未找到人物: {name}"}

            result = _row_to_dict(row)
            result["found"] = True

            # 提取 faction 信息（以 _f_ 前缀标记）
            faction_info = {}
            for prefix_key in ("_f_satisfaction", "_f_leverage", "_f_agenda"):
                if prefix_key in result:
                    clean_key = prefix_key[3:]  # 去掉 _f_
                    faction_info[clean_key] = result.pop(prefix_key)
            if faction_info:
                result["faction_info"] = faction_info

            return result

        return self._cached(self._cache_key("character", name), _compute)
    
    def query_army(self, army_id: str) -> Dict[str, Any]:
        """查询军队详情。

        Args:
            army_id: 军队 ID(如 "guanyu_fleet")

        Returns:
            包含军队兵力、训练、装备、士气、补给、疲劳、位置、统帅等信息的字典。
        """
        def _compute():
            # 合并 army + commander + station 为 1 次 JOIN（P2 优化）
            # id 或 name 均可匹配，避免两次 fallback 查询
            row = self.db.conn.execute(
                """
                SELECT a.*,
                       c.name AS _cmd_name, c.intelligence AS _cmd_intelligence,
                       c.courage AS _cmd_courage, c.leadership AS _cmd_leadership,
                       c.martial AS _cmd_martial, c.personal_skills AS _cmd_personal_skills,
                       r.name AS _st_name, r.kind AS _st_kind
                FROM armies a
                LEFT JOIN characters c ON a.commander = c.name
                LEFT JOIN regions r ON a.station = r.id OR a.station = r.name
                WHERE a.id = ? OR a.name = ?
                LIMIT 1
                """,
                (army_id, army_id),
            ).fetchone()

            if row is None:
                return {"found": False, "error": f"未找到军队: {army_id}"}

            result = _row_to_dict(row)
            result["found"] = True

            # 提取统帅信息（以 _cmd_ 前缀标记）
            commander_info = {}
            for prefix_key in list(result.keys()):
                if prefix_key.startswith("_cmd_"):
                    clean_key = prefix_key[5:]  # 去掉 _cmd_
                    commander_info[clean_key] = result.pop(prefix_key)
            if commander_info.get("name"):
                result["commander_info"] = commander_info

            # 提取驻军地信息（以 _st_ 前缀标记）
            station_info = {}
            for prefix_key in list(result.keys()):
                if prefix_key.startswith("_st_"):
                    clean_key = prefix_key[4:]  # 去掉 _st_
                    station_info[clean_key] = result.pop(prefix_key)
            if station_info:
                result["station_info"] = station_info

            return result

        return self._cached(self._cache_key("army", army_id), _compute)
    
    def query_region(self, region_id: str) -> Dict[str, Any]:
        """查询郡县详情。

        Args:
            region_id: 郡县 ID(如 "xiangyang")或名称

        Returns:
            包含郡县人口、民心、动乱、田赋、城防、建筑等信息的字典。
        """
        def _compute():
            row = self.db.conn.execute(
                "SELECT * FROM regions WHERE id = ? OR name = ?",
                (region_id, region_id),
            ).fetchone()

            if row is None:
                return {"found": False, "error": f"未找到郡县: {region_id}"}

            result = _row_to_dict(row)
            result["found"] = True

            # 查询该郡县的建筑
            buildings = self.db.conn.execute(
                "SELECT id, name, category, level, condition, output_metric, output_amount, status FROM buildings WHERE region_id = ? ORDER BY category, level DESC",
                (result.get("id"),),
            ).fetchall()
            result["buildings"] = _rows_to_list(buildings)

            return result

        return self._cached(self._cache_key("region", region_id), _compute)
    
    def query_power(self, power_id: str) -> Dict[str, Any]:
        """查询势力详情。

        Args:
            power_id: 势力 ID(如 "cao_cao")或名称

        Returns:
            包含势力军力、补给、凝聚、态势、议程等信息的字典。
        """
        def _compute():
            # 合并 power + armies 为 1 次 LEFT JOIN（P2 优化）
            rows = self.db.conn.execute(
                """
                SELECT p.*,
                       a.id AS _a_id, a.name AS _a_name, a.station AS _a_station,
                       a.troop_type AS _a_troop_type, a.manpower AS _a_manpower,
                       a.morale AS _a_morale, a.training AS _a_training,
                       a.equipment AS _a_equipment, a.supply AS _a_supply,
                       a.supply_turns AS _a_supply_turns, a.fatigue AS _a_fatigue,
                       a.status AS _a_status
                FROM powers p
                LEFT JOIN armies a ON a.owner_power = p.id
                WHERE p.id = ? OR p.name = ?
                ORDER BY a.id
                """,
                (power_id, power_id),
            ).fetchall()

            if not rows:
                return {"found": False, "error": f"未找到势力: {power_id}"}

            # 提取 power 数据（每行重复，取第一行即可）
            result = _row_to_dict(rows[0])
            # 清除 army 前缀列
            for k in list(result.keys()):
                if k.startswith("_a_"):
                    del result[k]
            result["found"] = True

            # 提取 armies 列表
            armies = []
            for row in rows:
                d = _row_to_dict(row)
                army = {}
                for k in list(d.keys()):
                    if k.startswith("_a_"):
                        army[k[3:]] = d[k]  # 去掉 _a_ 前缀
                if army.get("id") is not None:
                    armies.append(army)

            result["armies"] = armies[:20]
            result["armies_count"] = len(armies)

            return result

        return self._cached(self._cache_key("power", power_id), _compute)
    
    def query_diplomacy(self, power_a: str, power_b: str) -> Dict[str, Any]:
        """查询两个势力之间的外交关系。

        Args:
            power_a: 势力 A 的 ID 或名称
            power_b: 势力 B 的 ID 或名称

        Returns:
            包含关系值、信任度、条约、军事协同等信息的字典。
        """
        # 合并两个 power 解析为 1 次查询（P2 优化）
        powers = self.db.conn.execute(
            """
            SELECT a.id AS id_a, b.id AS id_b
            FROM powers a, powers b
            WHERE (a.id = ? OR a.name = ?)
              AND (b.id = ? OR b.name = ?)
            """,
            (power_a, power_a, power_b, power_b),
        ).fetchone()

        if not powers:
            return {"found": False, "error": f"势力不存在: {power_a} 或 {power_b}"}

        id_a, id_b = powers["id_a"], powers["id_b"]

        # 查询关系（两个方向都查）
        row = self.db.conn.execute(
            """
            SELECT * FROM diplomatic_relations
            WHERE (power_a = ? AND power_b = ?) OR (power_a = ? AND power_b = ?)
            """,
            (id_a, id_b, id_b, id_a),
        ).fetchone()

        if row is None:
            return {"found": False, "error": f"无外交关系: {power_a} - {power_b}"}

        result = _row_to_dict(row)
        result["found"] = True

        # 查询活跃条约
        treaties = self.db.conn.execute(
            """
            SELECT * FROM diplomacy_treaties
            WHERE ((proposer = ? AND target = ?) OR (proposer = ? AND target = ?))
              AND status IN ('proposed', 'active')
            ORDER BY id DESC
            """,
            (id_a, id_b, id_b, id_a),
        ).fetchall()
        result["treaties"] = _rows_to_list(treaties)

        return result
    
    def query_building(self, building_id: str) -> Dict[str, Any]:
        """查询建筑详情。
        
        Args:
            building_id: 建筑 ID 或名称
        
        Returns:
            包含建筑类别、等级、产出、状态等信息的字典。
        """
        row = self.db.conn.execute(
            """
            SELECT * FROM buildings WHERE id = ? OR name = ?
            """,
            (building_id, building_id),
        ).fetchone()
        
        if row is None:
            return {"found": False, "error": f"未找到建筑: {building_id}"}
        
        result = _row_to_dict(row)
        result["found"] = True
        return result
    
    def query_city(self, city_id: str) -> Dict[str, Any]:
        """查询城池详情。
        
        Args:
            city_id: 城池 ID 或名称
        
        Returns:
            包含城池归属、城防、仓储、市易、围城状态等信息的字典。
        """
        row = self.db.conn.execute(
            """
            SELECT * FROM administrative_cities WHERE id = ? OR name = ?
            """,
            (city_id, city_id),
        ).fetchone()
        
        if row is None:
            return {"found": False, "error": f"未找到城池: {city_id}"}
        
        result = _row_to_dict(row)
        result["found"] = True
        return result
    
    # -----------------------------------------------------------------------
    # 战略态势查询
    # -----------------------------------------------------------------------
    
    def query_faction_internal(self, power_id: str) -> Dict[str, Any]:
        """查询势力内部派系状态。
        
        Args:
            power_id: 势力 ID(目前主要指刘备势力的派系)
        
        Returns:
            包含派系满意度、杠杆、议程等信息的字典。
        """
        # 查询所有派系
        factions = self.db.conn.execute(
            """
            SELECT name, satisfaction, leverage, agenda FROM factions
            ORDER BY satisfaction DESC
            """
        ).fetchall()
        
        return {
            "found": True,
            "power_id": power_id,
            "factions": _rows_to_list(factions),
            "factions_count": len(factions),
        }
    
    def query_world_context(self, turn: Optional[int] = None) -> Dict[str, Any]:
        """查询世界上下文(季节、天气、民情等)。
        
        Args:
            turn: 回合数,默认为当前回合
        
        Returns:
            包含季节、天气、民情、势力预算等信息的字典。
        """
        target_turn = turn if turn is not None else self.state.turn
        
        row = self.db.conn.execute(
            """
            SELECT * FROM world_simulation_contexts WHERE turn = ?
            """,
            (target_turn,),
        ).fetchone()
        
        if row is None:
            # 查最近的
            row = self.db.conn.execute(
                """
                SELECT * FROM world_simulation_contexts
                WHERE turn <= ?
                ORDER BY turn DESC
                LIMIT 1
                """,
                (target_turn,),
            ).fetchone()
        
        if row is None:
            return {"found": False, "error": f"无世界上下文数据(回合 {target_turn})"}
        
        result = _row_to_dict(row)
        result["found"] = True
        return result
    
    def query_regional_state(self, region_id: str, turn: Optional[int] = None) -> Dict[str, Any]:
        """查询区域状态(天气、道路、粮运、收成、疫病、灾害等)。
        
        Args:
            region_id: 郡县 ID
            turn: 回合数,默认为当前回合
        
        Returns:
            包含区域状态信息的字典。
        """
        target_turn = turn if turn is not None else self.state.turn
        
        row = self.db.conn.execute(
            """
            SELECT * FROM regional_world_states
            WHERE region_id = ? AND turn = ?
            """,
            (region_id, target_turn),
        ).fetchone()
        
        if row is None:
            # 查最近的
            row = self.db.conn.execute(
                """
                SELECT * FROM regional_world_states
                WHERE region_id = ? AND turn <= ?
                ORDER BY turn DESC
                LIMIT 1
                """,
                (region_id, target_turn),
            ).fetchone()
        
        if row is None:
            return {"found": False, "error": f"无区域状态数据: {region_id}"}
        
        result = _row_to_dict(row)
        result["found"] = True
        return result
    
    def query_regional_incidents(self, region_id: str, turn: Optional[int] = None) -> Dict[str, Any]:
        """查询区域事件。
        
        Args:
            region_id: 郡县 ID
            turn: 回合数,默认为当前回合
        
        Returns:
            包含本月事件列表(普通事件+重大事件)的字典。
        """
        target_turn = turn if turn is not None else self.state.turn
        
        incidents = self.db.conn.execute(
            """
            SELECT * FROM regional_incidents
            WHERE region_id = ? AND turn = ?
            ORDER BY severity DESC, id
            """,
            (region_id, target_turn),
        ).fetchall()
        
        return {
            "found": True,
            "region_id": region_id,
            "turn": target_turn,
            "incidents": _rows_to_list(incidents),
            "incidents_count": len(incidents),
        }
    
    def query_power_internal_dynamics(self, power_id: str, turn: Optional[int] = None) -> Dict[str, Any]:
        """查询势力内部动态(内斗、补给争端、指挥争端等)。
        
        Args:
            power_id: 势力 ID
            turn: 回合数,默认为当前回合
        
        Returns:
            包含势力内部动态列表的字典。
        """
        target_turn = turn if turn is not None else self.state.turn
        
        dynamics = self.db.conn.execute(
            """
            SELECT * FROM power_internal_dynamics
            WHERE power_id = ? AND turn = ?
            ORDER BY id
            """,
            (power_id, target_turn),
        ).fetchall()
        
        return {
            "found": True,
            "power_id": power_id,
            "turn": target_turn,
            "dynamics": _rows_to_list(dynamics),
            "dynamics_count": len(dynamics),
        }
    
    def query_economy(self, account: Optional[str] = None) -> Dict[str, Any]:
        """查询经济账目。
        
        Args:
            account: 账目名称(如 "国库"),不填则返回所有账目
        
        Returns:
            包含账目余额、收支明细的字典。
        """
        if account:
            row = self.db.conn.execute(
                "SELECT * FROM economy_accounts WHERE account = ? OR note = ?",
                (account, account),
            ).fetchone()
            
            if row is None:
                return {"found": False, "error": f"未找到账目: {account}"}
            
            result = _row_to_dict(row)
            result["found"] = True
            return result
        else:
            # 返回所有账目
            accounts = self.db.conn.execute(
                "SELECT * FROM economy_accounts ORDER BY account"
            ).fetchall()
            
            return {
                "found": True,
                "accounts": _rows_to_list(accounts),
                "accounts_count": len(accounts),
            }
    
    def query_metrics(self) -> Dict[str, Any]:
        """查询全局指标(军资、粮秣、民望、名分、军心等)。
        
        Returns:
            包含所有全局指标的字典。
        """
        metrics = self.db.conn.execute(
            "SELECT key, value FROM metrics ORDER BY key"
        ).fetchall()
        
        return {
            "found": True,
            "metrics": {row["key"]: row["value"] for row in metrics},
        }
    
    # -----------------------------------------------------------------------
    # 情报与记忆查询
    # -----------------------------------------------------------------------
    
    def query_intelligence_reports(
        self,
        power_id: Optional[str] = None,
        visibility: Optional[str] = None,
        turn: Optional[int] = None,
    ) -> Dict[str, Any]:
        """查询情报报告。
        
        Args:
            power_id: 势力 ID(可选)
            visibility: 可见性(rumor/assessment/confirmed,可选)
            turn: 回合数,默认为当前回合
        
        Returns:
            包含情报报告列表的字典。
        """
        target_turn = turn if turn is not None else self.state.turn
        
        query = """
            SELECT * FROM external_intelligence_reports
            WHERE turn <= ?
        """
        params = [target_turn]
        
        if power_id:
            query += " AND power_id = ?"
            params.append(power_id)
        
        if visibility:
            query += " AND visibility = ?"
            params.append(visibility)
        
        query += " ORDER BY turn DESC, id DESC LIMIT 20"
        
        reports = self.db.conn.execute(query, params).fetchall()
        
        return {
            "found": True,
            "reports": _rows_to_list(reports),
            "reports_count": len(reports),
        }
    
    def query_events(
        self,
        event_id: Optional[str] = None,
        kind: Optional[str] = None,
        turn: Optional[int] = None,
    ) -> Dict[str, Any]:
        """查询事件。
        
        Args:
            event_id: 事件 ID(可选)
            kind: 事件类型(situation/node/ending,可选)
            turn: 回合数,默认为当前回合
        
        Returns:
            包含事件列表或单个事件详情的字典。
        """
        if event_id:
            row = self.db.conn.execute(
                "SELECT * FROM events WHERE id = ?",
                (event_id,),
            ).fetchone()
            
            if row is None:
                return {"found": False, "error": f"未找到事件: {event_id}"}
            
            result = _row_to_dict(row)
            result["found"] = True
            
            # 查询事件状态
            state_row = self.db.conn.execute(
                "SELECT * FROM historical_event_states WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            if state_row:
                result["state"] = _row_to_dict(state_row)
            
            return result
        else:
            # 查询近期事件
            target_turn = turn if turn is not None else self.state.turn
            
            query = "SELECT * FROM events WHERE 1=1"
            params = []
            
            if kind:
                query += " AND kind = ?"
                params.append(kind)
            
            query += " ORDER BY urgency DESC, severity DESC LIMIT 20"
            
            events = self.db.conn.execute(query, params).fetchall()
            
            return {
                "found": True,
                "events": _rows_to_list(events),
                "events_count": len(events),
            }
    
    def query_memorials(self, status: Optional[str] = None, turn: Optional[int] = None) -> Dict[str, Any]:
        """查询奏议(议题)。
        
        Args:
            status: 状态(open/resolved等,可选)
            turn: 回合数,默认为当前回合
        
        Returns:
            包含奏议列表的字典。
        """
        target_turn = turn if turn is not None else self.state.turn
        
        query = """
            SELECT * FROM minister_memorials
            WHERE turn <= ?
        """
        params = [target_turn]
        
        if status:
            query += " AND status = ?"
            params.append(status)
        
        query += " ORDER BY turn DESC, id DESC LIMIT 20"
        
        memorials = self.db.conn.execute(query, params).fetchall()
        
        return {
            "found": True,
            "memorials": _rows_to_list(memorials),
            "memorials_count": len(memorials),
        }
    
    def query_secret_orders(
        self,
        minister_name: Optional[str] = None,
        status: Optional[str] = None,
        turn: Optional[int] = None,
    ) -> Dict[str, Any]:
        """查询密令。
        
        Args:
            minister_name: 承办大臣姓名(可选)
            status: 状态(active/pending_review/completed等,可选)
            turn: 回合数,默认为当前回合
        
        Returns:
            包含密令列表的字典。
        """
        target_turn = turn if turn is not None else self.state.turn
        
        query = """
            SELECT * FROM secret_orders
            WHERE turn_issued <= ?
        """
        params = [target_turn]
        
        if minister_name:
            query += " AND minister_name = ?"
            params.append(minister_name)
        
        if status:
            query += " AND status = ?"
            params.append(status)
        
        query += " ORDER BY turn_issued DESC, id DESC LIMIT 20"
        
        orders = self.db.conn.execute(query, params).fetchall()
        
        return {
            "found": True,
            "orders": _rows_to_list(orders),
            "orders_count": len(orders),
        }
    
    def query_battle_history(
        self,
        turn: Optional[int] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """查询战役历史。
        
        Args:
            turn: 回合数,默认为当前回合
            limit: 返回数量限制,默认 20
        
        Returns:
            包含战役列表的字典。
        """
        target_turn = turn if turn is not None else self.state.turn
        
        battles = self.db.conn.execute(
            """
            SELECT * FROM battles
            WHERE turn <= ?
            ORDER BY turn DESC, id DESC
            LIMIT ?
            """,
            (target_turn, limit),
        ).fetchall()
        
        return {
            "found": True,
            "battles": _rows_to_list(battles, limit=limit),
            "battles_count": len(battles),
        }
    
    def query_siege(self, siege_id: Optional[int] = None, turn: Optional[int] = None) -> Dict[str, Any]:
        """查询围城状态。
        
        Args:
            siege_id: 围城 ID(可选)
            turn: 回合数,默认为当前回合
        
        Returns:
            包含围城详情或列表的字典。
        """
        if siege_id is not None:
            row = self.db.conn.execute(
                "SELECT * FROM sieges WHERE id = ?",
                (siege_id,),
            ).fetchone()
            
            if row is None:
                return {"found": False, "error": f"未找到围城: {siege_id}"}
            
            result = _row_to_dict(row)
            result["found"] = True
            return result
        else:
            target_turn = turn if turn is not None else self.state.turn
            
            sieges = self.db.conn.execute(
                """
                SELECT * FROM sieges
                WHERE turn_started <= ?
                ORDER BY turn_started DESC, id DESC
                LIMIT 20
                """,
                (target_turn,),
            ).fetchall()
            
            return {
                "found": True,
                "sieges": _rows_to_list(sieges),
                "sieges_count": len(sieges),
            }
    
    def query_turn_report(self, turn: Optional[int] = None) -> Dict[str, Any]:
        """查询月报(邸报)。
        
        Args:
            turn: 回合数,默认为当前回合
        
        Returns:
            包含月报全文的字典。
        """
        target_turn = turn if turn is not None else self.state.turn
        
        row = self.db.conn.execute(
            "SELECT * FROM turn_reports WHERE turn = ?",
            (target_turn,),
        ).fetchone()
        
        if row is None:
            # 查最近的
            row = self.db.conn.execute(
                """
                SELECT * FROM turn_reports
                WHERE turn <= ?
                ORDER BY turn DESC
                LIMIT 1
                """,
                (target_turn,),
            ).fetchone()
        
        if row is None:
            return {"found": False, "error": f"无月报数据(回合 {target_turn})"}
        
        result = _row_to_dict(row)
        result["found"] = True
        return result
    
    def search_memories(
        self,
        keywords: Optional[str] = None,
        year: Optional[int] = None,
        period: Optional[int] = None,
        turn: Optional[int] = None,
    ) -> Dict[str, Any]:
        """检索记忆(起居注、旧事)。
        
        Args:
            keywords: 关键词(逗号分隔)
            year: 年份(如 208)
            period: 月份(1-12)
            turn: 回合数,默认为当前回合
        
        Returns:
            包含匹配记忆列表的字典。
        """
        target_turn = turn if turn is not None else self.state.turn
        
        # 使用既有记忆检索接口
        all_memories = self.db.list_chapter_memories(upto_turn=target_turn)
        
        hits = []
        
        # 按年月筛选
        if year:
            ref_turn = (int(year) - 207) * 12 + (int(period or 1) - 1) + 1
            hits = [c for c in all_memories if abs(int(c.get("turn", 0)) - ref_turn) <= 2]
        
        # 按关键词筛选
        if keywords:
            kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
            kw_hits = [
                c for c in all_memories
                if any(
                    kw in (c.get("body") or "")
                    or kw in (c.get("title") or "")
                    for kw in kw_list
                )
            ]
            seen = {c.get("turn") for c in hits}
            hits += [c for c in kw_hits if c.get("turn") not in seen]
        
        if not hits:
            return {
                "found": True,
                "memories": [],
                "memories_count": 0,
                "query": {"keywords": keywords, "year": year, "period": period},
            }
        
        return {
            "found": True,
            "memories": _rows_to_list(hits[-20:]),
            "memories_count": len(hits),
            "query": {"keywords": keywords, "year": year, "period": period},
        }

    # -----------------------------------------------------------------------
    # 上下文预加载（用于校验上下文复用）
    # -----------------------------------------------------------------------

    def preload_context(self, context: Dict[str, Any]) -> None:
        """将预构建的校验上下文注入缓存，避免 AI 查询时重复访问 DB。

        接受 build_*_adjudication_pack() 返回的 facts 字典，
        提取其中的实体数据填入缓存。
        """
        if self._cache is None:
            return

        # 人物数据
        candidate = context.get("candidate")
        if isinstance(candidate, dict) and candidate.get("name"):
            self._cache.set(
                self._cache_key("character", candidate["name"]),
                {"found": True, **candidate},
            )

        # 军队数据
        army_breakdown = context.get("army_breakdown", {})
        for side in ("attackers", "defenders"):
            for army in army_breakdown.get(side, []):
                if isinstance(army, dict) and army.get("id"):
                    self._cache.set(
                        self._cache_key("army", army["id"]),
                        {"found": True, **army},
                    )

        # 势力数据
        power = context.get("power")
        if isinstance(power, dict) and power.get("id"):
            self._cache.set(
                self._cache_key("power", power["id"]),
                {"found": True, **power},
            )

        # 区域数据
        region = context.get("region") or context.get("selected_region")
        if isinstance(region, dict) and region.get("id"):
            self._cache.set(
                self._cache_key("region", region["id"]),
                {"found": True, **region},
            )

    # -----------------------------------------------------------------------
    # 规则与边界查询
    # -----------------------------------------------------------------------
    
    def query_tactic_reference(self) -> Dict[str, Any]:
        """查询战术参考(基准战术列表、边界常量)。
        
        Returns:
            包含战术参考信息的字典。
        """
        from ming_sim.battle import TACTIC_RULES, FREE_TACTIC_BOUNDS
        
        tactics = []
        for name, rule in TACTIC_RULES.items():
            tactics.append({
                "name": name,
                "delta": rule.get("delta", 0),
                "trait": rule.get("trait"),
                "terrain": rule.get("terrain"),
                "min_intelligence": rule.get("min_intelligence"),
                "min_courage": rule.get("min_courage"),
            })
        
        return {
            "found": True,
            "baseline_tactics": tactics,
            "free_tactic_bounds": FREE_TACTIC_BOUNDS,
        }
    
    def query_rules(self) -> Dict[str, Any]:
        """查询当前适用的规则边界。
        
        Returns:
            包含规则边界摘要的字典。
        """
        from ming_sim.battle import FREE_TACTIC_BOUNDS
        
        return {
            "found": True,
            "free_tactic_bounds": FREE_TACTIC_BOUNDS,
            "common_forbidden_outcomes": [
                "unlisted_death",
                "spawn_army",
                "free_reinforcements",
                "unvalidated_territory_change",
                "unvalidated_treaty_effect",
                "ignore_supply",
                "revive_character",
            ],
            "protocol_version": 1,
        }


# ---------------------------------------------------------------------------
# 便捷工厂函数
# ---------------------------------------------------------------------------

def build_query_tools(
    db: GameDB,
    state: GameState,
    *,
    cache: Optional[BatchQueryCache] = None,
) -> List[Callable]:
    """构建查询工具列表（便捷入口）。

    Args:
        db: 数据库连接
        state: 游戏状态
        cache: 可选的批次缓存

    Returns:
        查询工具函数列表，可直接传给 agno Agent
    """
    toolkit = QueryToolKit(db, state, cache=cache)
    return toolkit.get_tools()
