import React, { createContext, useContext, useReducer, ReactNode } from 'react';
import type { GameState, DirectiveDraft, DirectiveBatch } from '../types';

/**
 * 游戏状态管理 - P0 核心
 * 统一管理游戏状态、草案、批次和页面导航
 */

// 页面类型
export type PageType =
  | 'situation'      // 本月局势与行动枢纽
  | 'council'        // 府堂廷议
  | 'secret'         // 单独密谈
  | 'map'            // 地图与详情
  | 'directive'      // 本月军府方略簿
  | 'review'         // 审阅与颁令
  | 'adjudication'   // 分阶段推演
  | 'report'         // 每月总计
  | 'army'           // 军队信息
  | 'city'           // 城池治理
  | 'character'      // 人物详情
  | 'diplomacy'      // 外交
  | 'history'        // 史册
  | 'event';         // 事件详情

// 游戏 Store 状态
interface GameStoreState {
  // 游戏状态
  gameState: GameState;

  // 当前页面
  currentPage: PageType;

  // 草案列表
  drafts: DirectiveDraft[];

  // 当前批次
  currentBatch: DirectiveBatch | null;

  // UI 状态
  loading: boolean;
  error: string | null;
  mapFocusNodeId: string | null;
  characterFocusName: string | null;
  characterReturnPage: PageType;
}

// Action 类型
type GameStoreAction =
  | { type: 'SET_GAME_STATE'; payload: GameState }
  | { type: 'SET_PAGE'; payload: PageType }
  | { type: 'SET_DRAFTS'; payload: DirectiveDraft[] }
  | { type: 'ADD_DRAFT'; payload: DirectiveDraft }
  | { type: 'UPDATE_DRAFT'; payload: { id: number; updates: Partial<DirectiveDraft> } }
  | { type: 'REMOVE_DRAFT'; payload: number }
  | { type: 'SET_CURRENT_BATCH'; payload: DirectiveBatch | null }
  | { type: 'SET_LOADING'; payload: boolean }
  | { type: 'SET_ERROR'; payload: string | null }
  | { type: 'SET_MAP_FOCUS_NODE'; payload: string | null }
  | { type: 'SET_CHARACTER_FOCUS'; payload: { name: string | null; returnPage: PageType } };

// 初始状态
const initialState: GameStoreState = {
  gameState: null as any, // 将在 Provider 中初始化
  // 地图是主舞台；其他场景作为叠在地图上的工作模块打开。
  currentPage: 'map',
  drafts: [],
  currentBatch: null,
  loading: false,
  error: null,
  mapFocusNodeId: null,
  characterFocusName: null,
  characterReturnPage: 'situation',
};

// Reducer
function gameStoreReducer(
  state: GameStoreState,
  action: GameStoreAction
): GameStoreState {
  switch (action.type) {
    case 'SET_GAME_STATE':
      return { ...state, gameState: action.payload };

    case 'SET_PAGE':
      return { ...state, currentPage: action.payload };

    case 'SET_DRAFTS':
      return { ...state, drafts: action.payload };

    case 'ADD_DRAFT':
      return { ...state, drafts: [action.payload, ...state.drafts] };

    case 'UPDATE_DRAFT':
      return {
        ...state,
        drafts: state.drafts.map(d =>
          d.id === action.payload.id ? { ...d, ...action.payload.updates } : d
        ),
      };

    case 'REMOVE_DRAFT':
      return {
        ...state,
        drafts: state.drafts.filter(d => d.id !== action.payload),
      };

    case 'SET_CURRENT_BATCH':
      return { ...state, currentBatch: action.payload };

    case 'SET_LOADING':
      return { ...state, loading: action.payload };

    case 'SET_ERROR':
      return { ...state, error: action.payload };

    case 'SET_MAP_FOCUS_NODE':
      return { ...state, mapFocusNodeId: action.payload };

    case 'SET_CHARACTER_FOCUS':
      return { ...state, characterFocusName: action.payload.name, characterReturnPage: action.payload.returnPage };

    default:
      return state;
  }
}

// Context 类型
interface GameStoreContextType {
  state: GameStoreState;
  dispatch: React.Dispatch<GameStoreAction>;
  navigate: (page: PageType) => void;
  openMapAt: (nodeId: string) => void;
  openCharacter: (name: string | undefined, returnPage?: PageType) => void;
}

// Context
const GameStoreContext = createContext<GameStoreContextType | null>(null);

// Provider Props
interface GameStoreProviderProps {
  children: ReactNode;
  initialGameState: GameState;
}

// Provider
export function GameStoreProvider({ children, initialGameState }: GameStoreProviderProps) {
  const [state, dispatch] = useReducer(gameStoreReducer, {
    ...initialState,
    gameState: initialGameState,
  });

  const navigate = (page: PageType) => {
    dispatch({ type: 'SET_PAGE', payload: page });
  };
  const openMapAt = (nodeId: string) => {
    dispatch({ type: 'SET_MAP_FOCUS_NODE', payload: nodeId });
    dispatch({ type: 'SET_PAGE', payload: 'map' });
  };
  const openCharacter = (name: string | undefined, returnPage: PageType = 'army') => {
    if (!name) return;
    dispatch({ type: 'SET_CHARACTER_FOCUS', payload: { name, returnPage } });
    dispatch({ type: 'SET_PAGE', payload: 'character' });
  };

  return (
    <GameStoreContext.Provider value={{ state, dispatch, navigate, openMapAt, openCharacter }}>
      {children}
    </GameStoreContext.Provider>
  );
}

// Hook
export function useGameStore() {
  const context = useContext(GameStoreContext);
  if (!context) {
    throw new Error('useGameStore must be used within GameStoreProvider');
  }
  return context;
}

// 便捷 hooks
export function useGameState() {
  const { state } = useGameStore();
  return state.gameState;
}

export function useCurrentPage() {
  const { state, navigate } = useGameStore();
  return { currentPage: state.currentPage, navigate };
}

export function useDrafts() {
  const { state, dispatch } = useGameStore();
  return {
    drafts: state.drafts,
    setDrafts: (drafts: DirectiveDraft[]) => dispatch({ type: 'SET_DRAFTS', payload: drafts }),
    addDraft: (draft: DirectiveDraft) => dispatch({ type: 'ADD_DRAFT', payload: draft }),
    updateDraft: (id: number, updates: Partial<DirectiveDraft>) =>
      dispatch({ type: 'UPDATE_DRAFT', payload: { id, updates } }),
    removeDraft: (id: number) => dispatch({ type: 'REMOVE_DRAFT', payload: id }),
  };
}

export function useCurrentBatch() {
  const { state, dispatch } = useGameStore();
  return {
    currentBatch: state.currentBatch,
    setCurrentBatch: (batch: DirectiveBatch | null) =>
      dispatch({ type: 'SET_CURRENT_BATCH', payload: batch }),
  };
}
