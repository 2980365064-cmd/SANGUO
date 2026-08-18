/**
 * 全局面板状态管理。
 *
 * 替代 GameScreen 中散落的 useState(panel / panelOpen / infoOpen / dialogue / ...)，
 * 用 React Context + useReducer 集中管理面板开关、z-index、backdrop。
 *
 * 面板分类：
 *   居中模态（互斥 + backdrop）: API配置 / 人物详情 / 密谈 / 建议库
 *   右侧浮动（单开，无 backdrop）: Dock 面板
 *   地图信息（右抽屉）: province / commandery / site
 *   左上 HUD（不参与互斥）: WorldActionPanel / MonthlyReportPanel
 */
import React, { createContext, useCallback, useContext, useReducer } from "react";

// ── Types ──────────────────────────────────────────────────────────────────

export type DockPanel =
  | "朝议" | "军令" | "任事" | "外交" | "国策" | "家族" | "史册"
  | "府堂议事" | "人物";

export type CenteredModal =
  | "API 配置"
  | "人物详情"
  | "密谈"
  | "建议库"
  | null;

export type MapInfoKind = "province" | "commandery" | "site";

export interface PanelState {
  dock: DockPanel | null;
  centered: CenteredModal;
  mapInfo: { kind: MapInfoKind; id: string } | null;
  dialogueCharacter: string | null;
  council: { ministers: string[]; active: boolean } | null;
  secretChat: { character: string; active: boolean } | null;
  monthlyReportOpen: boolean;
}

type DockAction =
  | { type: "OPEN_DOCK"; kind: DockPanel }
  | { type: "TOGGLE_DOCK"; kind: DockPanel }
  | { type: "CLOSE_DOCK" };

type CenteredAction =
  | { type: "OPEN_CENTERED"; kind: NonNullable<CenteredModal> }
  | { type: "CLOSE_CENTERED" };

type MapInfoAction =
  | { type: "SET_MAP_INFO"; info: PanelState["mapInfo"] };

type DialogueAction =
  | { type: "OPEN_DIALOGUE"; name: string }
  | { type: "CLOSE_DIALOGUE" };

type CouncilAction =
  | { type: "START_COUNCIL"; ministers: string[] }
  | { type: "END_COUNCIL" };

type SecretChatAction =
  | { type: "START_SECRET_CHAT"; character: string }
  | { type: "END_SECRET_CHAT" };

type MonthlyReportAction =
  | { type: "TOGGLE_MONTHLY_REPORT" }
  | { type: "SET_MONTHLY_REPORT"; open: boolean };

export type PanelAction =
  | DockAction
  | CenteredAction
  | MapInfoAction
  | DialogueAction
  | CouncilAction
  | SecretChatAction
  | MonthlyReportAction;

// ── Initial State ──────────────────────────────────────────────────────────

const initialState: PanelState = {
  dock: null,
  centered: null,
  mapInfo: null,
  dialogueCharacter: null,
  council: null,
  secretChat: null,
  monthlyReportOpen: false,
};

// ── Reducer ────────────────────────────────────────────────────────────────

function panelReducer(state: PanelState, action: PanelAction): PanelState {
  switch (action.type) {
    // Dock: 互斥打开右侧浮动面板
    case "OPEN_DOCK":
      return { ...state, dock: action.kind };

    case "TOGGLE_DOCK":
      return { ...state, dock: state.dock === action.kind ? null : action.kind };

    case "CLOSE_DOCK":
      return { ...state, dock: null };

    // Centered: 互斥打开居中模态 + backdrop
    case "OPEN_CENTERED":
      return { ...state, centered: action.kind };

    case "CLOSE_CENTERED":
      return { ...state, centered: null };

    // Map info drawer
    case "SET_MAP_INFO":
      return { ...state, mapInfo: action.info };

    // Dialogue (private chat)
    case "OPEN_DIALOGUE":
      return { ...state, dialogueCharacter: action.name, centered: "密谈" };

    case "CLOSE_DIALOGUE":
      return { ...state, dialogueCharacter: null, centered: state.centered === "密谈" ? null : state.centered };

    // Council (廷议)
    case "START_COUNCIL":
      return {
        ...state,
        council: { ministers: action.ministers, active: true },
        dock: "府堂议事",
      };

    case "END_COUNCIL":
      return {
        ...state,
        council: null,
        dock: state.dock === "府堂议事" ? null : state.dock,
      };

    // Secret chat (密谈)
    case "START_SECRET_CHAT":
      return {
        ...state,
        secretChat: { character: action.character, active: true },
        centered: "密谈",
      };

    case "END_SECRET_CHAT":
      return {
        ...state,
        secretChat: null,
        centered: state.centered === "密谈" ? null : state.centered,
      };

    // Monthly report
    case "TOGGLE_MONTHLY_REPORT":
      return { ...state, monthlyReportOpen: !state.monthlyReportOpen };

    case "SET_MONTHLY_REPORT":
      return { ...state, monthlyReportOpen: action.open };

    default:
      return state;
  }
}

// ── Context ───────────────────────────────────────────────────────────────

interface PanelContextValue {
  state: PanelState;
  dispatch: React.Dispatch<PanelAction>;
}

const PanelContext = createContext<PanelContextValue | null>(null);

export function PanelProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(panelReducer, initialState);
  return <PanelContext.Provider value={{ state, dispatch }}>{children}</PanelContext.Provider>;
}

export function usePanel(): PanelContextValue {
  const ctx = useContext(PanelContext);
  if (!ctx) throw new Error("usePanel must be used within PanelProvider");
  return ctx;
}

// ── Helpers ────────────────────────────────────────────────────────────────

/** 是否显示 backdrop（居中模态打开时） */
export function useShowBackdrop(): boolean {
  const { state } = usePanel();
  return state.centered !== null;
}

/** 是否显示右侧浮动面板 */
export function useDockOpen(): boolean {
  const { state } = usePanel();
  return state.dock !== null;
}

/** 获取当前浮动面板类型 */
export function useCurrentDock(): DockPanel | null {
  const { state } = usePanel();
  return state.dock;
}
