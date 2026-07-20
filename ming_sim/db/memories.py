"""event_memories / event_memory_sources：事件记忆 upsert/检索 + 每回合章节记忆。

_MemoriesMixin：拆自原 db.py，方法体逐字未改。"""

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
    FISCAL_SCORE_FIELDS, REGION_FIELD_ALIASES, REGION_SCORE_FIELDS, REGION_TEXT_FIELDS, TURN_UNIT,
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


class _MemoriesMixin:
    # ----- event memories（渐进式记忆：摘要卡 + 来源摘录） -----

    def upsert_event_memory(
        self,
        state: GameState,
        subject_type: str,
        subject_id: str,
        event_type: str,
        title: str,
        cause: str = "",
        process: str = "",
        outcome: str = "",
        sentiment: str = "neutral",
        importance: int = 3,
        tags: Optional[List[str]] = None,
        source_kind: str = "system",
        source_id: str = "",
        expires_turn: Optional[int] = None,
    ) -> int:
        """写入/更新一张事件记忆摘要卡，按主体+类型+来源去重。"""
        subject_type = (subject_type or "").strip()
        subject_id = (subject_id or "").strip()
        event_type = (event_type or "").strip()
        source_kind = (source_kind or "system").strip()
        source_id = str(source_id or "").strip()
        if not subject_type or not subject_id or not event_type or not source_id:
            return 0
        importance = max(1, min(5, int(importance or 3)))
        if expires_turn is None:
            # 按重要度自动衰减；importance=5 永久保留（None）
            _ttl = {1: 6, 2: 12, 3: 24, 4: 48}
            ttl = _ttl.get(importance)
            if ttl is not None:
                expires_turn = int(state.turn) + ttl
        clean_tags = []
        for tag in tags or []:
            t = str(tag).strip()
            if t and t not in clean_tags:
                clean_tags.append(t[:40])
        existed = self.conn.execute(
            """
            SELECT id FROM event_memories
            WHERE subject_type=? AND subject_id=? AND event_type=? AND source_kind=? AND source_id=?
            """,
            (subject_type, subject_id, event_type, source_kind, source_id),
        ).fetchone()
        self.conn.execute(
            """
            INSERT INTO event_memories
                (subject_type, subject_id, turn, year, period, event_type, title,
                 cause, process, outcome, sentiment, importance, tags,
                 source_kind, source_id, expires_turn)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(subject_type, subject_id, event_type, source_kind, source_id)
            DO UPDATE SET
                turn = excluded.turn,
                year = excluded.year,
                period = excluded.period,
                title = excluded.title,
                cause = excluded.cause,
                process = excluded.process,
                outcome = excluded.outcome,
                sentiment = excluded.sentiment,
                importance = excluded.importance,
                tags = excluded.tags,
                expires_turn = excluded.expires_turn,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                subject_type, subject_id, state.turn, state.year, state.period,
                event_type, str(title or "")[:40], str(cause or "")[:80],
                str(process or "")[:80], str(outcome or "")[:80],
                sentiment if sentiment in {"positive", "neutral", "negative", "mixed"} else "neutral",
                importance, json.dumps(clean_tags, ensure_ascii=False),
                source_kind, source_id, expires_turn,
            ),
        )
        row = self.conn.execute(
            """
            SELECT id FROM event_memories
            WHERE subject_type=? AND subject_id=? AND event_type=? AND source_kind=? AND source_id=?
            """,
            (subject_type, subject_id, event_type, source_kind, source_id),
        ).fetchone()
        self.conn.commit()
        action = "更新" if existed else "保存"
        tlog(
            f"[memory/{action}] #{int(row['id']) if row else '?'} "
            f"{subject_type}:{subject_id} {event_type}《{str(title or '')[:24]}》"
            f" imp={importance} src={source_kind}:{source_id}"
        )
        tlog(
            f"[MEM-IO/db.upsert/BODY] #{int(row['id']) if row else '?'} "
            f"title={str(title or '')!r} cause={str(cause or '')!r} "
            f"process={str(process or '')!r} outcome={str(outcome or '')!r} "
            f"sentiment={sentiment} tags={clean_tags} expires_turn={expires_turn}"
        )
        return int(row["id"]) if row else 0

    def add_event_memory_source(
        self,
        memory_id: int,
        source_kind: str,
        source_id: str,
        excerpt: str = "",
        locator: Optional[Dict[str, object]] = None,
    ) -> None:
        if not memory_id:
            return
        locator_json = json.dumps(locator or {}, ensure_ascii=False, sort_keys=True)
        self.conn.execute(
            """
            INSERT INTO event_memory_sources
                (memory_id, source_kind, source_id, excerpt, locator)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(memory_id, source_kind, source_id, locator)
            DO UPDATE SET
                excerpt = excluded.excerpt,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                int(memory_id), str(source_kind or "system"), str(source_id or ""),
                str(excerpt or "")[:200], locator_json,
            ),
        )
        self.conn.commit()
        tlog(
            f"[memory/source] memory=#{int(memory_id)} {source_kind}:{source_id} "
            f"excerpt={str(excerpt or '')[:48]}"
        )

    def prune_event_memories_for_turn(self, turn: int, per_subject: int = 3) -> None:
        """同一主体同回合只保留若干高价值摘要卡，避免记忆膨胀。"""
        rows = self.conn.execute(
            """
            SELECT id, subject_type, subject_id, importance, updated_at
            FROM event_memories
            WHERE turn = ?
            ORDER BY subject_type, subject_id, importance DESC, id DESC
            """,
            (int(turn),),
        ).fetchall()
        seen: Dict[Tuple[str, str], int] = {}
        delete_ids: List[int] = []
        for row in rows:
            key = (row["subject_type"], row["subject_id"])
            seen[key] = seen.get(key, 0) + 1
            if seen[key] > per_subject:
                delete_ids.append(int(row["id"]))
        if delete_ids:
            placeholders = ",".join("?" for _ in delete_ids)
            self.conn.execute(f"DELETE FROM event_memory_sources WHERE memory_id IN ({placeholders})", delete_ids)
            self.conn.execute(f"DELETE FROM event_memories WHERE id IN ({placeholders})", delete_ids)
            self.conn.commit()
            tlog(f"[memory/prune] turn={turn} deleted={delete_ids}")

    def get_relevant_event_memories(
        self,
        character_name: str,
        faction: str,
        office_type: str,
        turn: int,
        limit: int = 5,
        ignore_expiry: bool = False,
    ) -> List[Dict[str, object]]:
        """召见前取少量相关旧事摘要；纯结构化检索，不走向量库。
        ignore_expiry=True 时按历史时点查，不受 expires_turn 过滤。
        """
        active_issues = self.list_active_issues()
        active_issue_tags: List[str] = []
        for issue in active_issues[:12]:
            active_issue_tags.append(f"#{int(issue['id'])}")
            if issue["title"]:
                active_issue_tags.append(str(issue["title"])[:20])
        tag_needles = [character_name, faction, office_type] + active_issue_tags
        expiry_clause = "" if ignore_expiry else "AND (expires_turn IS NULL OR expires_turn >= ?)"
        params: list = [int(turn)]
        if not ignore_expiry:
            params.append(int(turn))
        params += [character_name, faction, f"%{character_name}%", f"%{faction}%", f"%{office_type}%"]
        rows = self.conn.execute(
            f"""
            SELECT *
            FROM event_memories
            WHERE turn <= ?
              {expiry_clause}
              AND (
                (subject_type='character' AND subject_id=?)
                OR (subject_type='faction' AND subject_id=?)
                OR (subject_type='court' AND importance>=4)
                OR tags LIKE ?
                OR tags LIKE ?
                OR tags LIKE ?
              )
            """,
            params,
        ).fetchall()
        scored: List[Tuple[int, sqlite3.Row, List[str]]] = []
        for row in rows:
            age = max(0, int(turn) - int(row["turn"]))
            if int(row["importance"]) <= 1 and not (
                row["subject_type"] == "character" and row["subject_id"] == character_name and age <= 3
            ):
                continue
            try:
                tags = json.loads(row["tags"] or "[]")
            except Exception:
                tags = []
            tag_matches = [t for t in tag_needles if t and any(str(t) in str(tag) or str(tag) in str(t) for tag in tags)]
            exact = row["subject_type"] == "character" and row["subject_id"] == character_name
            active_hit = any(str(t).startswith("#") or t in active_issue_tags for t in tag_matches)
            score = (
                int(row["importance"]) * 10
                + (20 if exact else 0)
                + len(tag_matches) * 4
                + max(0, 10 - age)
                + (12 if active_hit else 0)
            )
            scored.append((score, row, tag_matches))
        scored.sort(key=lambda item: (item[0], int(item[1]["turn"]), int(item[1]["id"])), reverse=True)
        result: List[Dict[str, object]] = []
        for _score, row, _matches in scored[:limit]:
            result.append({
                "id": int(row["id"]),
                "subject_type": row["subject_type"],
                "subject_id": row["subject_id"],
                "turn": int(row["turn"]),
                "year": int(row["year"]),
                "period": int(row["period"]),
                "event_type": row["event_type"],
                "title": row["title"],
                "cause": row["cause"],
                "process": row["process"],
                "outcome": row["outcome"],
                "sentiment": row["sentiment"],
                "importance": int(row["importance"]),
                "tags": json.loads(row["tags"] or "[]"),
            })
        if result:
            ids = ",".join(str(item["id"]) for item in result)
            tlog(f"[memory/recall] {character_name} hit={len(result)} ids={ids}")
            tlog(f"[MEM-IO/db.recall/OUTPUT] {character_name} full={json.dumps(result, ensure_ascii=False)}")
        else:
            tlog(f"[memory/recall] {character_name} hit=0")
        return result

    def get_recent_event_memories(
        self,
        turn: int,
        window: int = 5,
        limit: int = 100,
    ) -> List[Dict[str, object]]:
        """取近 window 回合内所有 event_memories，按 turn/id 升序，上限 limit 条。"""
        since = max(1, turn - window + 1)
        rows = self.conn.execute(
            """
            SELECT id, subject_type, subject_id, turn, year, period,
                   event_type, title, cause, process, outcome, sentiment, importance, tags
            FROM event_memories
            WHERE turn >= ? AND turn <= ?
            ORDER BY turn ASC, id ASC
            LIMIT ?
            """,
            (since, turn, limit),
        ).fetchall()
        result = []
        for row in rows:
            result.append({
                "id": int(row["id"]),
                "subject_type": row["subject_type"],
                "subject_id": row["subject_id"],
                "turn": int(row["turn"]),
                "year": int(row["year"]),
                "period": int(row["period"]),
                "event_type": row["event_type"],
                "title": row["title"],
                "cause": row["cause"],
                "process": row["process"],
                "outcome": row["outcome"],
                "sentiment": row["sentiment"],
                "importance": int(row["importance"]),
                "tags": json.loads(row["tags"] or "[]"),
            })
        tlog(f"[memory/recent] turn={turn} window={window} hit={len(result)}")
        if result:
            tlog(f"[MEM-IO/db.recent/OUTPUT] turn={turn} window={window} full={json.dumps(result, ensure_ascii=False)}")
        return result

    def get_memories_by_keywords(
        self,
        keywords: List[str],
        turn: int,
        limit: int = 10,
        ignore_expiry: bool = False,
    ) -> List[Dict[str, object]]:
        """推演前按关键词集合检索相关记忆，供 simulator/extractor 注入。

        keywords 来自 memory_retrieval agent 抽取的人名/地区/军队/势力/操作词。
        每个词对 tags JSON 做 LIKE 匹配，命中任一词即入候选，按 importance+时效评分。
        ignore_expiry=True 时按历史时点查，不受 expires_turn 过滤。
        """
        if not keywords:
            return []
        active_issue_tags = [
            f"#{int(r['id'])}"
            for r in self.conn.execute(
                "SELECT id FROM issues WHERE status='active'"
            ).fetchall()
        ]
        needles = list(dict.fromkeys([k for k in keywords if k] + active_issue_tags))
        like_clauses = " OR ".join(["tags LIKE ?" for _ in needles])
        like_params = [f"%{n}%" for n in needles]
        expiry_clause = "" if ignore_expiry else "AND (expires_turn IS NULL OR expires_turn >= ?)"
        base_params: list = [int(turn)]
        if not ignore_expiry:
            base_params.append(int(turn))

        rows = self.conn.execute(
            f"""
            SELECT * FROM event_memories
            WHERE turn <= ?
              {expiry_clause}
              AND ({like_clauses})
            ORDER BY importance DESC, turn DESC
            LIMIT ?
            """,
            base_params + like_params + [limit * 3],
        ).fetchall()

        scored: List[tuple] = []
        for row in rows:
            age = max(0, int(turn) - int(row["turn"]))
            try:
                tags = json.loads(row["tags"] or "[]")
            except Exception:
                tags = []
            hit_count = sum(
                1 for n in needles
                if any(n in str(t) or str(t) in n for t in tags)
            )
            score = int(row["importance"]) * 10 + hit_count * 5 + max(0, 8 - age)
            scored.append((score, row))

        scored.sort(key=lambda x: x[0], reverse=True)
        result = []
        for _score, row in scored[:limit]:
            result.append({
                "id": int(row["id"]),
                "subject_type": row["subject_type"],
                "subject_id": row["subject_id"],
                "turn": int(row["turn"]),
                "year": int(row["year"]),
                "period": int(row["period"]),
                "title": row["title"],
                "cause": row["cause"],
                "outcome": row["outcome"],
                "importance": int(row["importance"]),
                "tags": json.loads(row["tags"] or "[]"),
                "source_kind": row["source_kind"],  # 演算记忆 vs 大臣记忆
            })
        tlog(f"[memory/keywords] needles={len(needles)} hit={len(result)}")
        tlog(f"[MEM-IO/db.keywords/INPUT] keywords={keywords} turn={turn} ignore_expiry={ignore_expiry} needles={needles}")
        if result:
            tlog(f"[MEM-IO/db.keywords/OUTPUT] full={json.dumps(result, ensure_ascii=False)}")
        return result

    def event_memory_detail(self, memory_id: int) -> str:
        tlog(f"[memory/detail] request=#{int(memory_id)}")
        memory = self.conn.execute(
            "SELECT * FROM event_memories WHERE id = ?",
            (int(memory_id),),
        ).fetchone()
        if memory is None:
            return f"未找到旧事记忆 #{memory_id}。"
        sources = self.conn.execute(
            """
            SELECT source_kind, source_id, excerpt, locator
            FROM event_memory_sources
            WHERE memory_id = ?
            ORDER BY id
            """,
            (int(memory_id),),
        ).fetchall()
        header = (
            f"旧事 #{memory['id']}：{memory['year']}年{memory['period']}月，{memory['title']}。"
            f"起因：{memory['cause']}。经过：{memory['process']}。结果：{memory['outcome']}。"
        )
        if not sources:
            return header + "\n未存原始摘录。"
        lines = [header, "来源摘录："]
        for idx, row in enumerate(sources, 1):
            locator = row["locator"] or "{}"
            lines.append(
                f"{idx}. [{row['source_kind']}:{row['source_id']}] {row['excerpt']}"
                + (f"（定位 {locator}）" if locator and locator != "{}" else "")
            )
        out = "\n".join(lines)
        tlog(f"[MEM-IO/db.detail/OUTPUT] #{memory_id} ({len(out)}字):\n{out}")
        return out

    # ── 章节记忆（event_memories 的 chapter_summary 类，每回合一条，importance=5 永久）──

    def save_chapter_memory(
        self, state: GameState, title: str, body: str, tags: Optional[List[str]] = None
    ) -> int:
        """落本回合章节记忆。subject 固定 court/chapter，event_type=chapter_summary，
        source_id=turn 保证每回合唯一。body 存整段叙事章节（不受 outcome 80 字限）。

        tags：除固定的 `章节`/`turnN` 外，并入 LLM 抽出的人物/地点/派系/事件召回标签，
        供 recall_memories 按人名/派系命中本章。"""
        base_tags = ["章节", f"turn{state.turn}"]
        for t in tags or []:
            t = str(t).strip()
            if t and t not in base_tags:
                base_tags.append(t)
        memory_id = self.upsert_event_memory(
            state,
            subject_type="court",
            subject_id="chapter",
            event_type="chapter_summary",
            title=str(title or f"崇祯{state.year}年{state.period}月")[:40],
            outcome=str(title or "")[:80],
            sentiment="neutral",
            importance=5,
            tags=base_tags,
            source_kind="turn_report",
            source_id=str(state.turn),
            expires_turn=None,
        )
        if memory_id:
            self.conn.execute(
                "UPDATE event_memories SET body = ? WHERE id = ?",
                (str(body or ""), memory_id),
            )
            self.conn.commit()
        return memory_id

    def list_chapter_memories(
        self, upto_turn: Optional[int] = None, recent: Optional[int] = None
    ) -> List[Dict[str, object]]:
        """取章节记忆，按 turn 升序。upto_turn 限上界；recent 只取最近 N 回合（喂大臣/推演用）。"""
        clauses = ["event_type = 'chapter_summary'"]
        params: list = []
        if upto_turn is not None:
            clauses.append("turn <= ?")
            params.append(int(upto_turn))
        if recent is not None and upto_turn is not None:
            clauses.append("turn >= ?")
            params.append(max(1, int(upto_turn) - int(recent) + 1))
        where = " AND ".join(clauses)
        rows = self.conn.execute(
            f"SELECT turn, year, period, title, body FROM event_memories "
            f"WHERE {where} ORDER BY turn ASC",
            params,
        ).fetchall()
        return [
            {
                "turn": int(r["turn"]),
                "year": int(r["year"]),
                "period": int(r["period"]),
                "title": r["title"] or "",
                "body": r["body"] or "",
            }
            for r in rows
        ]

    # ── 大臣私人对话纪要（event_memories 的 minister_recap 类，每大臣每回合一条，永久）──
    # 月内对话历史交 agno 每月一个 session 自管（含 tool 痕迹）；跨月靠这条 LLM 压缩纪要补失忆，
    # 月初注入该大臣 system（registry.build_minister_recap_brief）。subject_id=大臣名 → 私有于本人。

    def save_minister_recap(self, state: GameState, minister_name: str, recap: str) -> int:
        """落某大臣本回合私人对话纪要。subject_type=character、subject_id=大臣名、
        event_type=minister_recap、source_id=turn 保证每大臣每回合唯一。纪要正文存 body。"""
        name = (minister_name or "").strip()
        text = (recap or "").strip()
        if not name or not text:
            return 0
        title = f"崇祯{state.year}年{state.period}{TURN_UNIT}·{name}奏对"
        memory_id = self.upsert_event_memory(
            state,
            subject_type="character",
            subject_id=name,
            event_type="minister_recap",
            title=title,
            outcome=title[:80],
            sentiment="neutral",
            importance=5,
            tags=["奏对纪要", f"turn{state.turn}", name],
            source_kind="chat",
            source_id=str(state.turn),
            expires_turn=None,
        )
        if memory_id:
            self.conn.execute(
                "UPDATE event_memories SET body = ? WHERE id = ?",
                (text, memory_id),
            )
            self.conn.commit()
        return memory_id

    def get_recent_minister_recaps(
        self, minister_name: str, upto_turn: int, recent: int = 3
    ) -> List[Dict[str, object]]:
        """取某大臣 turn < upto_turn 的最近 recent 条私人对话纪要，按 turn 升序（喂其 system 用）。
        只取更早回合（< upto_turn）：本回合纪要要月末结算才生成，召见时尚不存在。"""
        name = (minister_name or "").strip()
        if not name:
            return []
        rows = self.conn.execute(
            "SELECT turn, year, period, body FROM event_memories "
            "WHERE event_type = 'minister_recap' AND subject_id = ? AND turn < ? "
            "ORDER BY turn DESC LIMIT ?",
            (name, int(upto_turn), max(1, int(recent))),
        ).fetchall()
        return [
            {
                "turn": int(r["turn"]),
                "year": int(r["year"]),
                "period": int(r["period"]),
                "body": r["body"] or "",
            }
            for r in reversed(rows)
        ]
