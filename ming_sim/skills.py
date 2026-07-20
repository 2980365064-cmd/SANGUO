"""Runtime skill-tool templates.

Visible skill cards were removed; Agno runtime skills/tools are surfaced from
registry/tools and DB office grants. This module only keeps text templates used
by tool implementations.
"""

from __future__ import annotations

from typing import Optional

from ming_sim.content import GameContent

_content: Optional[GameContent] = None


def bind_content(content: GameContent) -> None:
    global _content
    _content = content


def _ctx() -> GameContent:
    if _content is None:
        raise RuntimeError("skills.bind_content() 未调用：GameContent 未注入。")
    return _content


def skill_template(template_id: str, **values: object) -> str:
    template = _ctx().skill_tool_templates.get(template_id)
    if template is None:
        raise SystemExit(f"skill_tools.json 缺少模板：{template_id}")
    return template.format(**values)
