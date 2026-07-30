# Design QA: 操作地图与浮窗布局

final result: passed

## Source Reference

- Reference: `/Users/zhuanzmima0000/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/wxid_o9mj0npb9ceu22_2a37/temp/RWTemp/2026-07/3058af737fe86598b758722ceb880ea8.jpg`
- Target intent: 大地图为主体，左上资源状态，右侧功能按钮坞，信息与面板默认收起，未来十二月时间线为轻量点线。

## Verification

- Local production page: `http://127.0.0.1:8010/`
- Main map detected: yes
- Right dock buttons: 8
- Timeline dots: 12
- Province washes: 13
- Expanded right panel: 430px wide, no console errors
- Expanded map info panel: 360px wide, no console errors

## Notes

- This pass implements the operation layout and procedural province wash layer only.
- The formal generated map background can still be replaced later through DashScope after art direction is approved.

## Visual Polish Pass

final result: passed

Reference direction: public screenshots and coverage of `汉祚再兴·刘备传` on Steam/community media and game press coverage.

Changes:

- Upgraded the map surface toward a darker desk-and-paper presentation.
- Reworked the HUD, timeline, command dock, right panel, and province dossier with black-gold lacquer, inner linework, seal red highlights, and thicker paper shadows.
- Kept the approved layout unchanged: full-screen map, left-top resources, right-side command dock, 12-dot timeline, collapsed info windows.

Verification:

- `node --test --experimental-strip-types web/tests/*.test.ts` -> `11 passed`
- `npm run build` -> passed
- Browser QA on `http://127.0.0.1:8010/`: closed and expanded states render, no console errors.

## Province Block Map Pass

final result: passed

Reference direction: user-provided `汉祚再兴·刘备传` style screenshot, with the route-line map replaced by a province-block interaction model.

Changes:

- Replaced route drawing with 13 province block outlines; hover/focus/selected states emphasize the province contour.
- Kept all 35 commandery names visible inside their province block.
- Replaced army order target UI with same-province / neighboring-province targets.
- Stopped exposing route data through the frontend map payload; backend action validation now uses province blocks.

Verification:

- `node --test web/tests/*.test.ts` -> `11 passed`
- `npm run build` -> passed
- `python3 -m pytest tests/test_sanguo_strategic_rules.py tests/test_sanguo_schema.py tests/test_siege.py tests/test_battle_resolution.py -q` -> `28 passed`
- Browser QA at `http://127.0.0.1:4173/` with backend `8010`: `provinceBlocks=13`, `commanderyLabels=35`, visible `routeLines=0`; army panel shows province targets and no visible route target/note UI.
- Screenshots: `design-qa-map.png`, `design-qa-army-targets.png`.
