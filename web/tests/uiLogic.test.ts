import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  RESOURCE_METRICS,
  buildFutureMonthLine,
  getStageScene,
  timelineStatusLabel,
} from "../src/uiLogic.ts";
import { armyRisk, filterAndSortArmies, filterArmiesByRisk, groupArmiesByPower, groupArmiesByStation } from "../src/armyOverview.ts";

const source = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");

test("游戏以常驻地图串联可回返的核心模块", () => {
  const game = source("../src/GameScreen.tsx");
  for (const page of [
    "SituationHub", "CouncilHall", "SecretChat", "MapDesk", "DirectiveBook",
    "ReviewAndDecree", "AdjudicationFlow", "MonthlySummary", "ArmyInfo",
    "CityGovernance", "CharacterDetail", "DiplomacyPage", "HistoryBook", "EventPage",
  ]) {
    assert.match(game, new RegExp(`<${page}`));
  }
  assert.match(game, /<StrategicMap/);
  assert.match(game, /persistent-world-map/);
  assert.match(game, /onState=\{\(next\) => dispatch/);
  assert.match(game, /default:\s+return <SituationHub/);
});

test("信息页只把行动拟入方略，不保留即时改写世界的前端入口", () => {
  const army = source("../src/pages/ArmyInfo.tsx");
  const city = source("../src/pages/CityGovernance.tsx");
  const event = source("../src/pages/EventPage.tsx");

  assert.match(army, /拟入方略/);
  assert.match(city, /拟入方略/);
  assert.match(event, /createDirectiveDraft/);
  assert.match(event, /random_event_resolution/);
  assert.doesNotMatch(event, /random-events\/\$\{eventId\}\/resolve/);
});

test("军府总览按势力汇总、可检索排序，并只保留己方方略入口", () => {
  const armies: any[] = [
    { id: "liu-1", name: "左军", owner_power: "liu_bei", commander: "关羽", station_node: "jiangxia", troop_type: "步军", manpower: 12000, supply: 62, morale: 70, fatigue: 20 },
    { id: "cao-1", name: "北军", owner_power: "cao_cao", commander: "曹操", station_node: "xuchang", troop_type: "骑军", manpower: 18000, supply: 30, morale: 66, fatigue: 20 },
  ];
  const groups = groupArmiesByPower(armies, [{ id: "liu_bei", name: "刘备", military_strength: 0 }, { id: "cao_cao", name: "曹操", military_strength: 0 }] as any);
  assert.deepEqual(groups.map((group) => [group.name, group.manpower, group.riskCount]), [["曹操", 18000, 1], ["刘备", 12000, 0]]);
  assert.equal(armyRisk(armies[1]).label, "军情紧急");
  assert.deepEqual(filterAndSortArmies(armies, "关羽", "manpower").map((army) => army.id), ["liu-1"]);
  assert.deepEqual(filterAndSortArmies(armies, "", "risk").map((army) => army.id), ["cao-1", "liu-1"]);
  assert.deepEqual(filterArmiesByRisk(armies, "urgent").map((army) => army.id), ["cao-1"]);
  assert.equal(groupArmiesByStation(armies)[0].id, "xuchang");
  const page = source("../src/pages/ArmyInfo.tsx");
  assert.match(page, /owner_power === 'liu_bei'/);
  assert.match(page, /openMapAt\(selectedArmy\.station_node\)/);
  assert.match(page, /天下军籍/);
  assert.match(page, /LedgerChoice/);
  assert.match(page, /readiness-ledger/);
  assert.doesNotMatch(page, /<select/);
  const armyStyles = source("../src/styles/scenes/army-overview.css");
  assert.match(armyStyles, /registry-catalog-desktop-v2/);
  assert.match(armyStyles, /marching-dossier-desktop-v3/);
  assert.match(armyStyles, /marching-dossier-mobile-v2/);
  assert.match(source("../src/styles/scenes/army-fullscreen-overrides.css"), /marching-dossier-mobile-v3/);
  assert.doesNotMatch(armyStyles, /command-still-life-v1|hub-scroll-v1|roster-scroll-v1/);
  assert.match(source("../src/components/MapDesk.tsx"), /navigate\('army'\)/);
});

test("审阅颁令与每月总计使用批次和月报链路", () => {
  const review = source("../src/pages/ReviewAndDecree.tsx");
  const report = source("../src/pages/MonthlySummary.tsx");

  assert.match(review, /issueDirectiveBatch/);
  assert.match(review, /校验/);
  assert.match(report, /getMonthlyReport/);
  assert.match(report, /每月总计/);
});

test("百炼背景统一从注册表和 CSS token 接入，窄屏保留方略抽屉", () => {
  const assets = source("../src/components/sceneAssets.ts");
  const tokens = source("../src/styles/tokens/colors.css");
  const shell = source("../src/styles/components/scene-shell.css");
  const hubStyles = source("../src/styles/scenes/situation-hub.css");
  assert.doesNotMatch(assets, /status: 'missing'/);
  for (const token of ["--ink-bg-map", "--ink-bg-review", "--ink-bg-adjudication", "--ink-bg-report"]) {
    assert.match(tokens, new RegExp(token));
  }
  assert.match(shell, /scene-adjudication-march[\s\S]*--ink-bg-adjudication-march/);
  assert.match(hubStyles, /@media \(max-width: 1100px\)[\s\S]*position: fixed/);
  assert.match(hubStyles, /bottom: 54px/);
});

test("设计系统入口不再加载旧巨型样式或末尾覆盖层", () => {
  const entry = source("../src/styles/index.css");
  const coreLoop = source("../src/styles/components/core-loop.css");
  const adjudication = source("../src/pages/AdjudicationFlow.tsx");
  assert.doesNotMatch(entry, /\.\.\/styles\.css|revival\.css/);
  assert.match(entry, /legacy\/foundation\.css/);
  assert.match(entry, /components\/core-loop\.css/);
  assert.match(coreLoop, /禁止作为全局覆盖层/);
  assert.doesNotMatch(adjudication, /<style>/);
});

test("阶段五信息页与通用设置浮层复用统一组件", () => {
  for (const page of ["ArmyInfo", "CityGovernance", "CharacterDetail", "DiplomacyPage", "HistoryBook", "EventPage"]) {
    assert.match(source(`../src/pages/${page}.tsx`), /<AppFrame/);
  }
  assert.match(source("../src/pages/ArmyInfo.tsx"), /military-hub-sheet/);
  assert.match(source("../src/pages/CityGovernance.tsx"), /PaperPanel/);
  assert.match(source("../src/components/apiConfigModal.tsx"), /<GameDialog/);
  assert.match(source("../src/components/DisplaySettings.tsx"), /<GameDialog/);
  assert.match(source("../src/components/PanelRoot.tsx"), /<GameDialog/);
  assert.match(source("../src/components/charactersPanel/CharactersPanel.tsx"), /<GameDialog/);
  assert.match(source("../src/components/mapInfo/MapInfoDrawer.tsx"), /<GameDialog/);
  assert.match(source("../src/components/mapInfo/MapInfoDrawer.tsx"), /presentation="map-drawer"/);
  assert.match(source("../src/components/characterBook.tsx"), /<GameDialog/);
  assert.match(source("../src/components/GameDialog.tsx"), /modal=\{presentation !== 'map-drawer'\}/);
});

test("阶段六保留核心场景主行动、焦点对话框与减少动效契约", () => {
  const dialog = source("../src/components/GameDialog.tsx");
  const coreCss = source("../src/styles/components/core-loop.css");
  assert.match(dialog, /<Dialog\.Root open=\{open\}/);
  assert.match(dialog, /<Dialog\.Overlay/);
  assert.match(dialog, /<Dialog\.Content/);
  assert.match(dialog, /<Dialog\.Close aria-label="关闭"/);
  assert.match(coreCss, /@media \(prefers-reduced-motion: reduce\)/);
  assert.match(coreCss, /button:focus-visible/);
  for (const page of ["SituationHub", "MapDetail", "CouncilHall", "SecretChat", "DirectiveBook", "ReviewAndDecree", "MonthlySummary"]) {
    const content = source(`../src/pages/${page}.tsx`);
    assert.match(content, /ActionSealButton|AppFrame/);
    assert.doesNotMatch(content, /window\.confirm\(/);
  }
});

test("结局封卷有前端提示，并由服务端拒绝新的世界写入", () => {
  const hub = source("../src/pages/SituationHub.tsx");
  const directive = source("../src/pages/DirectiveBook.tsx");
  const app = source("../../web_app.py");
  assert.match(hub, /此局已封卷/);
  assert.match(hub, /disabled=\{ended\}/);
  assert.match(directive, /不会直接下达或改变天下事实/);
  assert.match(directive, /status !== 'issued'/);
  assert.match(app, /不能新建方略/);
  assert.match(app, /不能创建颁令批次/);
  assert.match(app, /不能颁令/);
  assert.match(app, /不能修改方略/);
});

test("方略簿与月度史册迁入统一框架和确认交互", () => {
  const directive = source("../src/pages/DirectiveBook.tsx");
  const monthly = source("../src/pages/MonthlySummary.tsx");
  const directiveCss = source("../src/styles/scenes/directive.css");
  const monthlyCss = source("../src/styles/scenes/monthly-report.css");
  const reset = source("../src/styles/base/reset.css");

  for (const component of ["AppFrame", "PaperPanel", "SectionHeading", "StatusMark", "ActionSealButton"]) {
    assert.match(directive, new RegExp(component));
  }
  assert.doesNotMatch(directive, /confirm\s*\(/);
  assert.match(monthly, /封存本月纪事，进入下月/);
  assert.match(monthly, /disabled=\{pendingReactions\.length > 0\}/);
  assert.doesNotMatch(monthly, /<style>/);
  assert.match(directiveCss, /directive-desk-layout/);
  assert.match(monthlyCss, /monthly-ledger-columns/);
  assert.match(reset, /min-width:\s*0/);
});

test("军府方略簿为建议库、四类整合槽位与一键下达闭环", () => {
  const directive = source("../src/pages/DirectiveBook.tsx");
  const styles = source("../src/styles/scenes/directive.css");
  assert.match(directive, /建议库/);
  assert.match(directive, /内政.*军事.*外交.*其他/s);
  assert.match(directive, /归入方略/);
  assert.match(directive, /整理文书/);
  assert.match(directive, /下达军令/);
  assert.match(directive, /executeDirectiveBatch/);
  assert.match(directive, /<GameDialog/);
  assert.match(directive, /getSuggestions/);
  assert.match(styles, /directive-desk-layout/);
  assert.match(styles, /directive-slot-grid/);
});

test("方略草案与颁令批次客户端统一经由 API 前缀访问", () => {
  const draftsApi = source("../src/api/directiveDrafts.ts");
  const batchesApi = source("../src/api/directiveBatches.ts");
  assert.doesNotMatch(draftsApi, /api\(['"]\/directive-drafts/);
  assert.doesNotMatch(batchesApi, /api\(['"]\/directive-batches/);
  assert.match(draftsApi, /\/api\/directive-drafts/);
  assert.match(batchesApi, /\/api\/directive-batches/);
});

test("资源条只保留军资到士族支持六项", () => {
  assert.deepEqual(RESOURCE_METRICS, ["军资", "粮秣", "民望", "名分", "军心", "士族支持"]);
});

test("未来十二月时间线固定生成十二个点并把同月大事挂到对应点", () => {
  const slots = buildFutureMonthLine(
    { year: 208, period: 11, turn: 8, phase: "decree" },
    [
      { id: "red_cliff", title: "赤壁火攻", window: "208年12月", status: "scheduled" },
      { id: "jingnan", title: "荆南归附", window: "209年2月", status: "adapted" },
    ],
  );
  assert.equal(slots.length, 12);
  assert.deepEqual(slots.slice(0, 4).map((slot) => slot.label), ["208.11", "208.12", "209.1", "209.2"]);
  assert.deepEqual(slots[1].events.map((event) => event.title), ["赤壁火攻"]);
  assert.deepEqual(slots[3].events.map((event) => event.title), ["荆南归附"]);
});

test("五个政权阶段具有明确且可切换的场景视觉", () => {
  const stages = ["流亡军", "荆州立足", "益州治蜀", "汉中王", "称帝后"];
  const scenes = stages.map(getStageScene);
  assert.deepEqual(scenes.map((item) => item.label), ["夏口军营", "荆州治所", "成都军府", "汉中王府", "蜀汉宫城"]);
  assert.equal(new Set(scenes.map((item) => `${item.asset}:${item.position}`)).size, 5);
});

test("史势条目保留历史改写状态而不泄漏结果", () => {
  assert.equal(timelineStatusLabel("scheduled"), "史势将至");
  assert.equal(timelineStatusLabel("adapted"), "已改写");
  assert.equal(timelineStatusLabel("superseded"), "变体发生");
  assert.equal(timelineStatusLabel("expired"), "已失效");
});

test("主地图不再使用可见遮盖块处理底图文字", () => {
  const map = source("../src/components/map.tsx");
  const styles = source("../src/styles.css");
  assert.doesNotMatch(map, /map-label-erasers|LabelMasks/);
  assert.doesNotMatch(styles, /map-label-erasers/);
});

test("郡图层保留手绘边界与水墨城镇点位", () => {
  const map = source("../src/components/map.tsx");
  const styles = source("../src/styles.css");
  assert.match(map, /id="border-roughen"/);
  assert.match(map, /scale="15"/);
  assert.match(map, /city-sprite/);
  assert.match(map, /\/assets\/ui\/cities\//);
  assert.match(styles, /\.commandery-shared-boundaries\{[^}]*url\(#border-roughen\)/);
  assert.match(styles, /\.city-sprite/);
});

// === 第二阶段：区域局势合同 ===

test("局势页将区域事件、奏议与天下反应收束为本月要议", () => {
  const hub = source("../src/pages/SituationHub.tsx");
  assert.doesNotMatch(hub, /局势卡片将在后续版本中显示/);
  assert.match(hub, /军府本月待议/);
  assert.match(hub, /policy_pending/);
  assert.match(hub, /world\.memorials/);
  assert.match(hub, /天下反应待裁断/);
  assert.match(hub, /situation-side-chronicle/);
});

test("地图页保持地图主体并将节点事实收束为地方档案", () => {
  const page = source("../src/pages/MapDetail.tsx");
  const map = source("../src/components/map.tsx");
  const styles = source("../src/styles/scenes/map.css");
  assert.match(page, /map-dossier/);
  assert.match(page, /地方档案/);
  assert.match(page, /以此为目标拟定方略/);
  assert.match(styles, /\.app-frame\.map-hub \{ display:grid/);
  assert.match(styles, /@media \(max-width: 900px\)/);
  assert.doesNotMatch(map, /province-detail-panel|commandery-detail-panel|city-detail-panel|context-menu/);
});

test("密谈、方略与月报作为地图工作窗关闭回天下舆图", () => {
  const coreCss = source("../src/styles/components/core-loop.css");
  assert.match(coreCss, /非地图模块不是换场/);
  assert.match(coreCss, /persistent-world-content \.scene-shell \{ position: absolute/);
  for (const page of ["SecretChat", "DirectiveBook", "MonthlySummary"]) {
    const content = source(`../src/pages/${page}.tsx`);
    assert.match(content, /navigate\('map'\)/);
    assert.match(content, /返回天下舆图/);
  }
});

test("廷议与密谈使用书记录入和封缄确认，而非聊天气泡入口", () => {
  const councilPage = source("../src/pages/CouncilHall.tsx");
  const secretPage = source("../src/pages/SecretChat.tsx");
  const secret = source("../src/components/charactersPanel/SecretChatStage.tsx");
  const council = source("../src/components/councilHall/CouncilHallStage.tsx");
  const secretCss = source("../src/styles/scenes/secret-chat.css");
  const councilCss = source("../src/styles/scenes/council.css");
  assert.match(councilPage, /<AppFrame/);
  assert.match(secretPage, /<AppFrame/);
  assert.match(secret, /secret-record/);
  assert.match(secret, /封缄密令/);
  assert.match(secret, /GameDialog/);
  assert.match(council, /议席发言/);
  assert.match(council, /PaperPanel/);
  assert.match(secretCss, /书案式私录/);
  assert.match(councilCss, /书吏录入/);
});

test("月报组件支持 regional section 与中文标签", () => {
  const report = source("../src/components/monthlyReportPanel.tsx");
  assert.match(report, /regional/);
  assert.match(report, /区域局势/);
  assert.match(report, /MountainSnow/);
});

test("前端类型定义包含 WorldState 与区域事件类型", () => {
  const types = source("../src/types.ts");
  assert.match(types, /export type WorldState/);
  assert.match(types, /export type RegionalState/);
  assert.match(types, /export type RegionalIncident/);
  assert.match(types, /tier: "ordinary" \| "dramatic"/);
  assert.match(types, /visibility: RegionalVisibility/);
});

test("前端不使用裸 JSON.stringify 输出审计数据", () => {
  const hub = source("../src/pages/SituationHub.tsx");
  const report = source("../src/components/monthlyReportPanel.tsx");
  // 允许 BattleAudit 内的 <pre>{JSON.stringify(...)} 用于可展开细目
  // 但不允许直接输出 item.audit 的裸 JSON
  assert.doesNotMatch(hub, /JSON\.stringify\(item\.audit\)/);
  assert.doesNotMatch(hub, /JSON\.stringify\(inc\.local_effects\)/);
});
