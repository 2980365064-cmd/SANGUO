import React from 'react';
import { GameStoreProvider, useCurrentPage, useGameStore } from './state/gameStore';
import { StrategicMap } from './components/map';
import { MapDesk } from './components/MapDesk';
import { SituationHub } from './pages/SituationHub';
import { CouncilHall } from './pages/CouncilHall';
import { SecretChat } from './pages/SecretChat';
import { MapDetail } from './pages/MapDetail';
import { DirectiveBook } from './pages/DirectiveBook';
import { ReviewAndDecree } from './pages/ReviewAndDecree';
import { AdjudicationFlow } from './pages/AdjudicationFlow';
import { MonthlySummary } from './pages/MonthlySummary';
import { ArmyInfo } from './pages/ArmyInfo';
import { CityGovernance } from './pages/CityGovernance';
import { CharacterDetail } from './pages/CharacterDetail';
import { DiplomacyPage } from './pages/DiplomacyPage';
import { HistoryBook } from './pages/HistoryBook';
import { EventPage } from './pages/EventPage';
import type { GameState } from './types';

/**
 * GameScreen - P0/P1 核心页面路由器
 */
function PageRouter() {
  const { currentPage } = useCurrentPage();

  switch (currentPage) {
    case 'situation':   return <SituationHub />;
    case 'council':     return <CouncilHall />;
    case 'secret':      return <SecretChat />;
    case 'map':         return <MapDesk />;
    case 'directive':   return <DirectiveBook />;
    case 'review':      return <ReviewAndDecree />;
    case 'adjudication':return <AdjudicationFlow />;
    case 'report':      return <MonthlySummary />;
    case 'army':        return <ArmyInfo />;
    case 'city':        return <CityGovernance />;
    case 'character':   return <CharacterDetail />;
    case 'diplomacy':   return <DiplomacyPage />;
    case 'history':     return <HistoryBook />;
    case 'event':       return <EventPage />;
    default:            return <SituationHub />;
  }
}

/** Keeps the real, pannable world map alive beneath every non-map scene. */
function PersistentWorldStage() {
  const { state, dispatch } = useGameStore();
  const { currentPage } = useCurrentPage();
  const [selectedId, setSelectedId] = React.useState('');

  return (
    <div className="persistent-world-stage">
      <div className="persistent-world-map" aria-label="常驻天下舆图">
        <StrategicMap
          state={state.gameState}
          selectedId={selectedId}
          selectedArmyId=""
          onSelect={setSelectedId}
          onState={(next) => dispatch({ type: 'SET_GAME_STATE', payload: next })}
        />
      </div>
      <div className="persistent-world-content"><PageRouter /></div>
    </div>
  );
}

export function GameScreen({ initial }: { initial: GameState }) {
  return (
    <GameStoreProvider initialGameState={initial}>
      <ScreenSurface />
    </GameStoreProvider>
  );
}

/** 密谈与廷议都是完整的案卷阅读面，不与天下舆图共用有限工作窗。 */
function ScreenSurface() {
  const { currentPage } = useCurrentPage();
  return currentPage === 'secret' || currentPage === 'council' || currentPage === 'army' ? <PageRouter /> : <PersistentWorldStage />;
}
