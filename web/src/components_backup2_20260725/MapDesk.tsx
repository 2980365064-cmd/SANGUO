import { BookOpen, MessageCircle, ScrollText, Users } from 'lucide-react';
import { MetricBar } from './hud';
import { ActionSealButton, PaperPanel, SectionHeading, StatusMark } from './ui';
import { useGameStore } from '../state/gameStore';

/** 地图主舞台上的轻量案头；地图始终可见、可操作。 */
export function MapDesk() {
  const { state, navigate } = useGameStore();
  const game = state.gameState;
  const ended = Boolean(game.ending);
  return <div className="map-desk">
    <MetricBar state={game} />
    <PaperPanel className="map-desk-agenda" tone="floating">
      <SectionHeading index="当月" note={`${game.turn.year}年${game.turn.period}月`}>本月要议</SectionHeading>
      <p>{ended ? '此局已封卷，可继续查阅地图与史册。' : '先在地图点选州郡城镇，确认事实后再召集人物、拟定方略。'}</p>
      <StatusMark tone={ended ? 'complete' : 'action'}>{ended ? '已封卷' : '地图待察'}</StatusMark>
      <div className="map-desk-actions">
        <ActionSealButton priority="primary" disabled={ended} onClick={() => navigate('directive')}><ScrollText /> 拟定方略</ActionSealButton>
        <ActionSealButton priority="secondary" disabled={ended} onClick={() => navigate('council')}><Users /> 府堂廷议</ActionSealButton>
        <ActionSealButton priority="secondary" disabled={ended} onClick={() => navigate('secret')}><MessageCircle /> 单独密谈</ActionSealButton>
        <ActionSealButton priority="ghost" onClick={() => navigate('situation')}><BookOpen /> 展开本月案卷</ActionSealButton>
      </div>
    </PaperPanel>
  </div>;
}
