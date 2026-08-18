---
name: sanguo-ui-visual-critic
description: Audit completed SANGUO player-visible UI against commercial historical-strategy game standards. Use after implementation or when reviewing screenshots, pages, drawers, dialogs, maps, and components; score visual quality, identify concrete failures, and require iteration below 8/10.
---

# SANGUO UI Visual Critic

Judge visual quality, not merely code correctness or feature completion. Inspect a rendered screenshot or live surface whenever available. A correct but ordinary UI is not complete.

## Review dimensions

1. **World consistency** — Does it read as a state archive, military document, private letter, historical record, or world map rather than a website?
2. **Historical material and rhythm** — Are paper, ink, wood/bamboo, seals, layered edges, whitespace, and reading cadence structural rather than superficial color choices?
3. **Modern UI contamination** — Are there repeated cards, equal data grids, generic tables, glass panels, uniform shadows, excessive rounded rectangles, or chat bubbles?
4. **Visual hierarchy** — Is the first look identity, person, place, or decision; the second supporting facts; and the third actionable detail and immersion?
5. **Art finish** — Do materials, edges, typography, contrast, details, and whitespace feel deliberately composed at desktop and narrow views?
6. **Implementation integrity** — Did convenience-driven generic components or simple background colors undermine the chosen direction?

## Required report

Return exactly these sections in Chinese:

1. `视觉评分：x/10` — 9–10 commercial-game grade; 7–8 correct direction but needs refinement; 5–6 prototype; below 5 redesign.
2. `优点：` — evidence-based strengths.
3. `主要问题：` — the highest-impact issue(s), not vague taste claims.
4. `修改建议：` — concrete visual changes, ordered by impact.
5. `是否达到商业游戏标准：是/否` — only “是” at 9/10 or above.

When the score is below 8/10, require another design/implementation pass. Read `references/review-rubric.md` for examples of pass/fail evidence.
