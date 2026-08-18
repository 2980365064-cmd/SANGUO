"""suggestions：建议库——从廷议文本中选词加入，可转将令（ActionIntent）。

_SuggestionsMixin：轻量 CRUD，不涉及 LLM 或推演。"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


class _SuggestionsMixin:
    # ----- suggestions（建议库）-----

    def create_suggestion(
        self,
        turn: int,
        year: int,
        period: int,
        text: str,
        source: str = "",
    ) -> int:
        text = (text or "").strip()
        if not text:
            raise ValueError("建议文本不能为空")
        cur = self.conn.execute(
            """
            INSERT INTO suggestions (turn, year, period, text, source, status)
            VALUES (?, ?, ?, ?, ?, 'pending')
            """,
            (int(turn), int(year), int(period), text, (source or "").strip()),
        )
        self.conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def list_suggestions(
        self,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        clauses, params = [], []
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self.conn.execute(
            f"SELECT * FROM suggestions {where} ORDER BY id DESC LIMIT ?",
            params + [max(1, int(limit))],
        ).fetchall()
        return [self._suggestion_row_to_dict(r) for r in rows]

    def get_suggestion(self, suggestion_id: int) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            "SELECT * FROM suggestions WHERE id = ?", (int(suggestion_id),)
        ).fetchone()
        if row is None:
            return None
        return self._suggestion_row_to_dict(row)

    def delete_suggestion(self, suggestion_id: int) -> bool:
        row = self.conn.execute(
            "SELECT id FROM suggestions WHERE id = ?", (int(suggestion_id),)
        ).fetchone()
        if row is None:
            return False
        self.conn.execute("DELETE FROM suggestions WHERE id = ?", (int(suggestion_id),))
        self.conn.commit()
        return True

    def convert_suggestion_to_order(
        self,
        state: object,
        suggestion_id: int,
    ) -> Dict[str, Any]:
        """将建议转为 ActionIntent，并标记建议 status='converted'。"""
        suggestion = self.get_suggestion(suggestion_id)
        if suggestion is None:
            raise ValueError(f"建议不存在：{suggestion_id}")
        if suggestion["status"] == "converted":
            raise ValueError("该建议已转为将令")
        # 创建 ActionIntent
        intent_id = self.create_action_intent(
            state,
            source="建议库",
            text=suggestion["text"],
        )
        self.conn.execute(
            """
            UPDATE suggestions
            SET status = 'converted', converted_to_intent_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (int(intent_id), int(suggestion_id)),
        )
        self.conn.commit()
        intent = self.conn.execute(
            "SELECT * FROM action_intents WHERE id = ?", (int(intent_id),)
        ).fetchone()
        return {
            "suggestion": {**suggestion, "status": "converted", "converted_to_intent_id": int(intent_id)},
            "intent": dict(intent) if intent else {"id": int(intent_id)},
        }

    @staticmethod
    def _suggestion_row_to_dict(row: object) -> Dict[str, Any]:
        r = row  # type: ignore[assignment]
        return {
            "id": int(r["id"]),
            "turn": int(r["turn"]),
            "year": int(r["year"]),
            "period": int(r["period"]),
            "text": r["text"],
            "source": r["source"] or "",
            "status": r["status"],
            "converted_to_intent_id": r["converted_to_intent_id"] if "converted_to_intent_id" in r.keys() else None,
            "created_at": r["created_at"],
        }
