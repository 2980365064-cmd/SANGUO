"""chat_messages：召对对话存档（持久化，进程重启恢复内存缓存）。

_ChatMixin。撤回最后一轮召对发言：删 chat_messages 末尾 user+minister 两行 + 裁掉
agno_sessions 里对应 session 的最后一条 run（让大臣后续对话不再带这轮上下文）。
流式中途退出整轮不落库（无副作用），故撤回只需处理已落库的完整轮。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple


class _ChatMixin:
    def append_chat_message(self, minister_name: str, turn: int, role: str, content: str) -> int:
        """召对聊天单条消息落库（chat_messages）。"""
        cur = self.conn.execute(
            "INSERT INTO chat_messages (minister_name, turn, role, content) VALUES (?, ?, ?, ?)",
            (minister_name, turn, role, content),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def load_all_chat_history(self) -> Dict[str, List[Dict[str, str]]]:
        """读出全部召对记录，按大臣分组，供进程启动时恢复内存缓存。"""
        rows = self.conn.execute(
            "SELECT minister_name, role, content FROM chat_messages ORDER BY id"
        ).fetchall()
        history: Dict[str, List[Dict[str, str]]] = {}
        for row in rows:
            history.setdefault(row["minister_name"], []).append(
                {"role": row["role"], "content": row["content"]}
            )
        return history

    def count_chat_rounds_in_turn(self, minister_name: str, turn: int) -> int:
        """本回合该大臣已聊几轮（一轮=一条 minister 回复）。供跨月补足算 need。"""
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM chat_messages "
            "WHERE minister_name = ? AND turn = ? AND role = 'minister'",
            (minister_name, int(turn)),
        ).fetchone()
        return int(row["n"]) if row else 0

    def ministers_chatted_in_turn(self, turn: int) -> List[str]:
        """本回合被召见聊过的大臣名单（按首次出现序）。供月末懒生成私人对话纪要——
        一个月通常只召见两三人，只给他们跑 recap，不全员浪费。"""
        rows = self.conn.execute(
            "SELECT minister_name FROM chat_messages "
            "WHERE turn = ? GROUP BY minister_name ORDER BY MIN(id)",
            (int(turn),),
        ).fetchall()
        return [r["minister_name"] for r in rows]

    def load_turn_chat_messages(self, minister_name: str, turn: int) -> List[Dict[str, str]]:
        """取某大臣本回合与皇帝的全部奏对（时间正序，纯文本 user/minister）。供月末喂 recap agent。"""
        rows = self.conn.execute(
            "SELECT role, content FROM chat_messages "
            "WHERE minister_name = ? AND turn = ? ORDER BY id",
            (minister_name, int(turn)),
        ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in rows]

    def load_recent_chat_rounds(
        self, minister_name: str, max_rounds: int
    ) -> List[Dict[str, str]]:
        """取该大臣最近 max_rounds 轮纯文本对话（跨月连续，不分本月/往月，按 id）。
        一轮=user+minister 两行；按 id DESC 取尾 2*max_rounds 行再反转为时间正序。
        历史全在 chat_messages（每轮答完即落库），此查询是喂 LLM 历史的唯一来源——
        不靠 agno session 存历史（agno runs 是整块 blob，读必全量进内存，无法分段）。
        走 idx_chat_messages_minister(minister_name, id)，真 LIMIT 分段，不全表扫、不全量进内存。"""
        if max_rounds <= 0:
            return []
        rows = self.conn.execute(
            "SELECT turn, role, content FROM chat_messages "
            "WHERE minister_name = ? ORDER BY id DESC LIMIT ?",
            (minister_name, max_rounds * 2),
        ).fetchall()
        return [
            {"turn": row["turn"], "role": row["role"], "content": row["content"]}
            for row in reversed(rows)
        ]

    def load_prev_chat_rounds(
        self, minister_name: str, before_turn: int, max_rounds: int
    ) -> List[Dict[str, str]]:
        """取该大臣 turn < before_turn 的尾 max_rounds 轮纯文本对话（跨月连续，按 id）。
        一轮=user+minister 两行；按 id DESC 取尾 2*max_rounds 行再反转为时间正序。
        走 idx_chat_messages_minister(minister_name, id)，不全表扫。"""
        if max_rounds <= 0:
            return []
        rows = self.conn.execute(
            "SELECT turn, role, content FROM chat_messages "
            "WHERE minister_name = ? AND turn < ? ORDER BY id DESC LIMIT ?",
            (minister_name, int(before_turn), max_rounds * 2),
        ).fetchall()
        return [
            {"turn": row["turn"], "role": row["role"], "content": row["content"]}
            for row in reversed(rows)
        ]

    def append_court_chat_message(self, turn: int, role: str, speaker: str, content: str) -> int:
        """朝会聊天室单条消息落库（court_chat_messages）。"""
        cur = self.conn.execute(
            "INSERT INTO court_chat_messages (turn, role, speaker, content) VALUES (?, ?, ?, ?)",
            (int(turn), role, speaker, content),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def last_chat_round_ids(self, minister_name: str, turn: int) -> Tuple[int, int]:
        """取该大臣本回合最后一轮 (user_id, minister_id)。无完整轮返回 (0, 0)。
        一轮＝紧邻的 user 行 + minister 行；按 id 取末尾 minister 行，再取其前最近的 user 行。"""
        m_row = self.conn.execute(
            "SELECT id FROM chat_messages "
            "WHERE minister_name = ? AND turn = ? AND role = 'minister' "
            "ORDER BY id DESC LIMIT 1",
            (minister_name, int(turn)),
        ).fetchone()
        if m_row is None:
            return (0, 0)
        minister_id = int(m_row["id"])
        u_row = self.conn.execute(
            "SELECT id FROM chat_messages "
            "WHERE minister_name = ? AND turn = ? AND role = 'user' AND id < ? "
            "ORDER BY id DESC LIMIT 1",
            (minister_name, int(turn), minister_id),
        ).fetchone()
        user_id = int(u_row["id"]) if u_row else 0
        return (user_id, minister_id)

    def revoke_last_chat_round(self, minister_name: str, turn: int, agno_session_id: str = "") -> bool:
        """撤回该大臣本回合最后一轮召对：删 user+minister 两行 + 裁掉 agno 末轮 run。
        无可撤回轮返回 False。agno_session_id 给空则跳过 agno 裁剪（只删存档行）。"""
        user_id, minister_id = self.last_chat_round_ids(minister_name, turn)
        if not minister_id:
            return False
        ids = [minister_id] + ([user_id] if user_id else [])
        placeholders = ",".join("?" for _ in ids)
        self.conn.execute(
            f"DELETE FROM chat_messages WHERE id IN ({placeholders})", ids
        )
        if agno_session_id:
            length = self.agno_runs_length(agno_session_id)
            if length > 0:
                self._truncate_agno_runs(agno_session_id, length - 1)
        self.conn.commit()
        return True

    # --- agno_sessions runs 裁剪（minister agent 跨轮对话历史存这里）---

    def agno_runs_length(self, session_id: str) -> int:
        if not session_id or not self._table_exists("agno_sessions"):
            return 0
        row = self.conn.execute(
            "SELECT runs FROM agno_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            return 0
        runs, _encoded_as_string = self._decode_agno_runs(row["runs"])
        return len(runs)

    def _decode_agno_runs(self, raw: Any) -> Tuple[List[Any], bool]:
        if raw in (None, ""):
            return [], False
        try:
            decoded = json.loads(raw)
            encoded_as_string = isinstance(decoded, str)
            if encoded_as_string:
                decoded = json.loads(decoded or "[]")
            return (decoded if isinstance(decoded, list) else []), encoded_as_string
        except (TypeError, ValueError):
            return [], False

    def _encode_agno_runs(self, runs: List[Any], encoded_as_string: bool) -> str:
        if encoded_as_string:
            return json.dumps(json.dumps(runs, ensure_ascii=False), ensure_ascii=False)
        return json.dumps(runs, ensure_ascii=False)

    def _truncate_agno_runs(self, session_id: str, keep_count: int) -> None:
        if not session_id or not self._table_exists("agno_sessions"):
            return
        row = self.conn.execute(
            "SELECT runs FROM agno_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            return
        runs, encoded_as_string = self._decode_agno_runs(row["runs"])
        kept = runs[: max(0, int(keep_count))]
        self.conn.execute(
            "UPDATE agno_sessions SET runs = ?, updated_at = strftime('%s','now') WHERE session_id = ?",
            (self._encode_agno_runs(kept, encoded_as_string), session_id),
        )

    def load_court_chat_history(self, turn: int) -> List[Dict[str, str]]:
        """读取某一回合（月）的朝会聊天室记录。"""
        rows = self.conn.execute(
            "SELECT role, speaker, content FROM court_chat_messages WHERE turn = ? ORDER BY id",
            (int(turn),),
        ).fetchall()
        return [
            {"role": row["role"], "speaker": row["speaker"], "content": row["content"]}
            for row in rows
        ]
