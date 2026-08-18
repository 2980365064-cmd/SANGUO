import { useState } from 'react';
import { BookOpen, ChevronDown, ChevronUp, MessageCircle, Shield, Users } from 'lucide-react';
import { MetricBar } from './hud';
import { useGameStore } from '../state/gameStore';

/** 地图主舞台上的轻量案头；地图始终可见、可操作。 */
export function MapDesk() {
  const { state, navigate } = useGameStore();
  const game = state.gameState;
  const ended = Boolean(game.ending);
  const [scrollOpen, setScrollOpen] = useState(true);
  return <div className="map-desk">
    <MetricBar state={game} />
    <aside className={`map-desk-scroll ${scrollOpen ? 'is-open' : 'is-folded'}`} aria-label="军府案头">
      <button className="map-desk-scroll-handle" type="button" onClick={() => setScrollOpen((open) => !open)} aria-expanded={scrollOpen}>
        <span className="map-desk-scroll-cap" aria-hidden="true" />
        <span className="map-desk-scroll-handle-label">军府案头</span>
        {scrollOpen ? <ChevronUp aria-hidden="true" /> : <ChevronDown aria-hidden="true" />}
      </button>
      <div className="map-desk-scroll-sheet" aria-hidden={!scrollOpen}>
        <div className="map-desk-scroll-heading"><span>本月待议</span><strong>{game.turn.year} 年 {game.turn.period} 月</strong></div>
        <p>{ended ? '此局已封卷，可继续查阅天下舆图与编年史册。' : '先点选州、郡、城核实地方事实，再将处置整理入军府方略。'}</p>
        <nav className="map-desk-scroll-actions" aria-label="案头入口">
          <button type="button" disabled={ended} onClick={() => navigate('council')}><Users aria-hidden="true" /><span>府堂廷议</span><small>召集群臣议定大势</small></button>
          <button type="button" disabled={ended} onClick={() => navigate('secret')}><MessageCircle aria-hidden="true" /><span>单独密谈</span><small>与人物往来私札</small></button>
          <button type="button" onClick={() => navigate('army')}><Shield aria-hidden="true" /><span>军府总览</span><small>查阅天下军籍与战备</small></button>
          <button type="button" onClick={() => navigate('situation')}><BookOpen aria-hidden="true" /><span>展开本月案卷</span><small>查看局势与待办事项</small></button>
        </nav>
        <div className="map-desk-scroll-foot"><i aria-hidden="true">汉</i><span>{ended ? '封卷可阅' : '待拟方略'}</span></div>
      </div>
      <span className="map-desk-scroll-bottom" aria-hidden="true" />
    </aside>
    <button className="map-desk-fab" disabled={ended} onClick={() => navigate('directive')} title="拟定方略">
      <span className="fab-seal" />
      <strong>拟定方略</strong>
    </button>
  </div>;
}
