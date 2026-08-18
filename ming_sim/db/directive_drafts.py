"""Directive drafts and batches - P0 core loop.

This module manages the unified directive submission system:
- directive_drafts: player/council ideas that don't change the world yet
- directive_batches: immutable snapshots of issued directives
- directive_batch_items: execution tracking for each draft in a batch
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


class _DirectiveDraftsMixin:
    """Mixin for directive_drafts table operations."""

    def create_directive_draft(
        self,
        turn: int,
        year: int,
        period: int,
        source_type: str,
        directive_type: str,
        title: str,
        assignee: str = "",
        target: str = "",
        duration_months: int = 1,
        priority: int = 50,
        resources_json: str = "{}",
        constraints_json: str = "[]",
        risks_json: str = "[]",
        narrative_text: str = "",
        compiled_text: str = "",
        status: str = "draft",
        source_id: Optional[int] = None,
    ) -> int:
        """Create a new directive draft. Returns the draft ID."""
        cursor = self.conn.execute(
            """
            INSERT INTO directive_drafts (
                turn, year, period, source_type, source_id,
                directive_type, title, assignee, target,
                duration_months, priority,
                resources_json, constraints_json, risks_json,
                narrative_text, compiled_text, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                turn, year, period, source_type, source_id,
                directive_type, title, assignee, target,
                duration_months, priority,
                resources_json, constraints_json, risks_json,
                narrative_text, compiled_text, status,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_directive_draft(self, draft_id: int) -> Optional[Dict[str, Any]]:
        """Get a single directive draft by ID."""
        row = self.conn.execute(
            "SELECT * FROM directive_drafts WHERE id = ?", (draft_id,)
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def list_directive_drafts(
        self,
        turn: Optional[int] = None,
        status: Optional[str] = None,
        directive_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List directive drafts with optional filters."""
        query = "SELECT * FROM directive_drafts WHERE 1=1"
        params: List[Any] = []

        if turn is not None:
            query += " AND turn = ?"
            params.append(turn)
        if status is not None:
            query += " AND status = ?"
            params.append(status)
        if directive_type is not None:
            query += " AND directive_type = ?"
            params.append(directive_type)

        query += " ORDER BY priority DESC, created_at DESC"
        rows = self.conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def update_directive_draft(
        self,
        draft_id: int,
        **updates: Any,
    ) -> bool:
        """Update a directive draft. Returns True if updated."""
        allowed_fields = {
            "title", "assignee", "target", "duration_months", "priority",
            "resources_json", "constraints_json", "risks_json",
            "narrative_text", "compiled_text", "status",
            "validation_result_json",
        }
        filtered = {k: v for k, v in updates.items() if k in allowed_fields}
        if not filtered:
            return False

        set_clause = ", ".join(f"{k} = ?" for k in filtered.keys())
        values = list(filtered.values()) + [draft_id]

        cursor = self.conn.execute(
            f"UPDATE directive_drafts SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            values,
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def delete_directive_draft(self, draft_id: int) -> bool:
        """Delete a directive draft. Returns True if deleted."""
        cursor = self.conn.execute(
            "DELETE FROM directive_drafts WHERE id = ?", (draft_id,)
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def validate_directive_draft(self, draft_id: int) -> Dict[str, Any]:
        """Validate a directive draft against game state. Returns validation result."""
        draft = self.get_directive_draft(draft_id)
        if draft is None:
            return {"valid": False, "errors": ["草案不存在"]}

        errors: List[str] = []

        # Validate assignee
        if draft["assignee"]:
            row = self.conn.execute(
                "SELECT power_id, status FROM characters WHERE name = ?",
                (draft["assignee"],),
            ).fetchone()
            if row is None:
                errors.append(f"执行者 {draft['assignee']} 不存在")
            elif row["power_id"] != "liu_bei":
                errors.append(f"{draft['assignee']} 不属于刘备势力")
            elif row["status"] != "active":
                errors.append(f"{draft['assignee']} 当前不可用")

        # Validate target (if region)
        if draft["target"] and draft["directive_type"] in ("military", "internal"):
            row = self.conn.execute(
                "SELECT controlled_by FROM regions WHERE id = ?",
                (draft["target"],),
            ).fetchone()
            if row is None:
                errors.append(f"目标区域 {draft['target']} 不存在")
            elif draft["directive_type"] == "internal" and row["controlled_by"] != "liu_bei":
                errors.append(f"内政策略只能针对己方区域")

        # Validate duration
        if draft["duration_months"] < 1 or draft["duration_months"] > 12:
            errors.append("时限必须在 1-12 个月之间")

        # Validate priority
        if draft["priority"] < 0 or draft["priority"] > 100:
            errors.append("优先级必须在 0-100 之间")

        result = {
            "valid": len(errors) == 0,
            "errors": errors,
        }

        # Update validation result
        self.update_directive_draft(
            draft_id,
            validation_result_json=json.dumps(result, ensure_ascii=False),
            status="validated" if result["valid"] else "invalid",
        )

        return result


class _DirectiveBatchesMixin:
    """Mixin for directive_batches table operations."""

    def create_directive_batch(
        self,
        turn: int,
        year: int,
        period: int,
        batch_title: str,
        draft_ids: List[int],
        decree_text: str = "",
    ) -> int:
        """Create a new directive batch from draft IDs. Returns the batch ID."""
        # Create the batch
        cursor = self.conn.execute(
            """
            INSERT INTO directive_batches (
                turn, year, period, batch_title, decree_text, total_drafts
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (turn, year, period, batch_title, decree_text, len(draft_ids)),
        )
        batch_id = cursor.lastrowid

        # Create batch items
        for order, draft_id in enumerate(draft_ids, start=1):
            self.conn.execute(
                """
                INSERT INTO directive_batch_items (
                    batch_id, draft_id, execution_order
                ) VALUES (?, ?, ?)
                """,
                (batch_id, draft_id, order),
            )

        # Update draft statuses to 'issued'
        if draft_ids:
            placeholders = ",".join("?" * len(draft_ids))
            self.conn.execute(
                f"UPDATE directive_drafts SET status = 'issued' WHERE id IN ({placeholders})",
                draft_ids,
            )

        self.conn.commit()
        return batch_id

    def get_directive_batch(self, batch_id: int) -> Optional[Dict[str, Any]]:
        """Get a single directive batch by ID."""
        row = self.conn.execute(
            "SELECT * FROM directive_batches WHERE id = ?", (batch_id,)
        ).fetchone()
        if row is None:
            return None

        batch = dict(row)

        # Fetch batch items with draft details
        items = self.conn.execute(
            """
            SELECT
                dbi.*,
                dd.title as draft_title,
                dd.directive_type,
                dd.assignee,
                dd.target
            FROM directive_batch_items dbi
            JOIN directive_drafts dd ON dbi.draft_id = dd.id
            WHERE dbi.batch_id = ?
            ORDER BY dbi.execution_order
            """,
            (batch_id,),
        ).fetchall()

        batch["items"] = [dict(item) for item in items]
        return batch

    def list_directive_batches(
        self,
        turn: Optional[int] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List directive batches with optional filters."""
        query = "SELECT * FROM directive_batches WHERE 1=1"
        params: List[Any] = []

        if turn is not None:
            query += " AND turn = ?"
            params.append(turn)
        if status is not None:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY created_at DESC"
        rows = self.conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def update_directive_batch(
        self,
        batch_id: int,
        **updates: Any,
    ) -> bool:
        """Update a directive batch. Returns True if updated."""
        allowed_fields = {
            "decree_text", "status", "issued_at", "completed_at",
        }
        filtered = {k: v for k, v in updates.items() if k in allowed_fields}
        if not filtered:
            return False

        set_clause = ", ".join(f"{k} = ?" for k in filtered.keys())
        values = list(filtered.values()) + [batch_id]

        cursor = self.conn.execute(
            f"UPDATE directive_batches SET {set_clause} WHERE id = ?",
            values,
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def update_batch_item_execution(
        self,
        batch_id: int,
        draft_id: int,
        execution_status: str,
        execution_result_json: str = "{}",
    ) -> bool:
        """Update execution status for a batch item."""
        cursor = self.conn.execute(
            """
            UPDATE directive_batch_items
            SET execution_status = ?, execution_result_json = ?
            WHERE batch_id = ? AND draft_id = ?
            """,
            (execution_status, execution_result_json, batch_id, draft_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def get_directive_batch_checkpoint(self, batch_id: int) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            "SELECT * FROM directive_batch_checkpoints WHERE batch_id=?", (int(batch_id),)
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        try:
            result["options"] = json.loads(str(result.pop("options_json") or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            result["options"] = []
        return result

    def save_directive_batch_checkpoint(
        self, batch_id: int, *, phase: str, draft_id: int, options: List[Dict[str, Any]], status: str = "pending",
    ) -> Dict[str, Any]:
        self.conn.execute(
            """INSERT INTO directive_batch_checkpoints (batch_id, phase, draft_id, options_json, status)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(batch_id) DO UPDATE SET phase=excluded.phase, draft_id=excluded.draft_id,
                options_json=excluded.options_json, choice='', status=excluded.status, updated_at=CURRENT_TIMESTAMP""",
            (int(batch_id), str(phase), int(draft_id), json.dumps(options, ensure_ascii=False), str(status)),
        )
        self.conn.commit()
        return self.get_directive_batch_checkpoint(batch_id) or {}

    def resolve_directive_batch_checkpoint(self, batch_id: int, choice: str) -> Dict[str, Any]:
        row = self.get_directive_batch_checkpoint(batch_id)
        if row is None or str(row.get("status")) != "pending":
            raise ValueError("当前批次没有待恢复的决策检查点")
        self.conn.execute(
            "UPDATE directive_batch_checkpoints SET choice=?, status='ready', updated_at=CURRENT_TIMESTAMP WHERE batch_id=?",
            (str(choice), int(batch_id)),
        )
        self.conn.commit()
        return self.get_directive_batch_checkpoint(batch_id) or {}

    def complete_directive_batch_checkpoint(self, batch_id: int) -> None:
        self.conn.execute(
            "UPDATE directive_batch_checkpoints SET status='completed', updated_at=CURRENT_TIMESTAMP WHERE batch_id=?",
            (int(batch_id),),
        )
        self.conn.commit()
