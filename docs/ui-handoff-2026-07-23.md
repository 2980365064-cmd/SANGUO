# SANGUO UI 重构交接（2026-07-23）

## 已确认的目标与约束

- 对标《历史模拟器：崇祯》的信息秩序和完成度，不复制其资产或界面。
- 本作保持刘备视角的浅宣纸、淡墨、灰青、朱砂风格；禁止回到厚重深棕、金边方框和通用后台 UI。
- **地图永远作为游戏底层**：所有非地图页都是有限宽度、半透明的内容卷/档案，不得重新做成全屏换场。
- 核心闭环：局势枢纽、地图、廷议、密谈、军府方略、审阅颁令、每月总计；AI 叙事和硬规则边界不得被 UI 改动破坏。
- 当前项目路径：`/Users/zhuanzmima0000/SANGUO`，不是 Git 仓库；工作区原本就有大量用户改动，禁止清理无关文件或初始化 Git。

## 阶段状态

| 阶段 | 状态 | 已交付/缺口 |
| --- | --- | --- |
| 1. 视觉基线 | 已完成（当前存档可达范围） | `docs/ui-baseline/` 中有 1440×900 的 11 张截图；无草案存档，故未覆盖审阅颁令、廷议进行中、长文本、加载/错误等状态 |
| 2. 原创资产包 | 已完成 | 已生成原创纸纹、场景衬景、印记、图标；详细用途见 `docs/ui-asset-manifest.md` |
| 3. 设计系统与技术骨架 | 进行中 | 浅水墨令牌、密度、`GameDialog`、`MetricLedger`、`MetricChip`、`StatusMark`、`ActionSealButton`、`AppFrame` 已建立；旧 `styles.css` 仍在兼容导入，不能称为完成 |
| 4. 核心场景 | 部分完成 | 常驻地图底层、廷议选人/舞台、密谈密令框、审阅确认框、局势和地图页部分改造已完成；五个核心页尚未达到计划终态 |
| 5. 通用浮层与其余页面 | 未开始 | 仅密令和颁令确认已迁入 `GameDialog` |
| 6. 验证与验收 | 未开始 | `npm run build` 和 `node --test tests/*.test.ts` 均通过（31/31）；尚无完整 Playwright、键盘、窄桌面、极端状态验收 |

## 已完成实现

1. 常驻地图：`web/src/GameScreen.tsx` 的 `PersistentWorldStage` 在所有非地图页下持续渲染真实 `StrategicMap`。
2. 单一 CSS 入口：`web/src/main.tsx` 只引入 `styles/index.css`；但该入口仍通过 `@import '../styles.css'` 作为过渡兼容层。
3. 视觉资产已通过 `web/src/styles/tokens/colors.css` 的 `--revival-*` 令牌注册，具体用途在 `web/src/styles/revival.css`。
4. 廷议：`MinisterSelection.tsx` 已是名录 + 已选席位的双栏；`CouncilHallStage.tsx` 有出席列和录入式主舞台。
5. 密谈和颁令：`SecretChatStage.tsx`、`ReviewAndDecree.tsx` 使用 Radix 驱动的 `GameDialog`。
6. 局势：`hud.tsx` 已用紧凑指标横卷替代旧进度条；`SituationHub.tsx` 已开始使用印记和主行动按钮。
7. 地图：`MapDetail.tsx` 已迁入 `AppFrame`，视觉基线为 `10-map-app-frame.png`。

## 原创素材位置

全部为 WebP，原始 PNG 仅作生成留档，前端令牌只引用 WebP：

- 纸纹：`web/public/assets/ui/texture-paper-revival.webp`
- 场景衬景：`web/public/assets/ui/scene/{council-hall,secret-chamber,directive-desk,monthly-desk,map-dossier}-revival.webp`
- 图框图谱：`web/public/assets/ui/frame/frame-atlas-revival.webp`
- 印记图谱与切片：`web/public/assets/ui/seal/seal-atlas-revival.webp`、`web/public/assets/ui/seal/slices/{action,confirmed,danger,month-end}.webp`
- 状态图谱与切片：`web/public/assets/ui/icon/status-atlas-revival.webp`、`web/public/assets/ui/icon/slices/{people,legitimacy,morale,grain,wealth,intel,relation,risk,pending}.webp`
- 木牍/封缄图谱：`web/public/assets/ui/prop/command-prop-atlas-revival.webp`

不要修改这些生成文件本身；若视觉不合格，重生成并替换注册，而不是用 CSS 掩盖 AI 伪文字或脏边。

## 下一会话的推荐执行顺序

1. 继续阶段三：迁移 `DirectiveBook.tsx`、`MonthlySummary.tsx` 至 `AppFrame`，并使用 `PaperPanel`、`SectionHeading`、`StatusMark`、`ActionSealButton`；每次迁移后构建、测试、截图。
2. 建立并逐步填充真实的 `styles/scenes/*.css` 与 `styles/components/*.css`，从核心场景开始搬离 `styles.css`。不得先删除 `@import '../styles.css'`；只有通过截图证明替代完整后才能删相应旧规则。
3. 完成阶段三后再集中做阶段四：
   - 局势页收为“本月要议 + 编年列 + 印章行动栏”；
   - 地图档案改为概况—人物—军政—行动的轻抽屉；
   - 密谈去 IM 气泡；
   - 方略改为拟定—审阅—下达三步卷；
   - 月报改为本月结论—已发生之事—天下余波史册。
4. 在阶段六制作带草案、待议事件和长文本的专用测试存档，补齐不可达状态的截图与无障碍测试。

## 验证命令与限制

```bash
cd /Users/zhuanzmima0000/SANGUO/web
npm run build
node --test tests/*.test.ts
```

最近一次验证：构建成功，31/31 前端契约测试通过。它们不证明视觉几何；视觉结论必须基于活存档截图。当前开发服务器曾使用 `http://127.0.0.1:5174/`，进入下一会话前应先检查端口是否仍被占用。
