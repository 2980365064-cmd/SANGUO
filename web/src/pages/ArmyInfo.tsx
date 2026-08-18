import { useMemo, useState, type ReactNode } from 'react';
import { ArrowLeft, BookOpen, ChevronRight, MapPinned, Search, Shield, UserRound } from 'lucide-react';
import { DraftEditor } from '../components/DraftEditor';
import { useGameStore } from '../state/gameStore';
import { ActionSealButton, AppFrame, SectionHeading, StatusMark } from '../components/ui';
import { armyRisk, filterAndSortArmies, filterArmiesByRisk, groupArmiesByPower, groupArmiesByStation, type ArmyRiskFilter, type ArmySort } from '../armyOverview';
import type { Army } from '../types';

type ArmyView = 'hub' | 'catalog' | 'dossier';
type CatalogScope = { powerId?: string; stationId?: string; risk?: ArmyRiskFilter; mode?: 'merit' | 'orders' };
const value = (n: number | undefined) => n ?? 0;
const number = (n: number | undefined) => value(n).toLocaleString();

/** 军府所藏天下军籍总册：枢纽、名录与单军行军档案三段连续阅读。 */
export function ArmyInfo() {
  const { state, navigate, openMapAt, openCharacter } = useGameStore();
  const gameState = state.gameState;
  const armies = gameState.armies || [];
  const powers = gameState.powers || [];
  const groups = useMemo(() => groupArmiesByPower(armies, powers), [armies, powers]);
  const stations = useMemo(() => groupArmiesByStation(armies), [armies]);
  const nodes = gameState.map.nodes || [];
  const [view, setView] = useState<ArmyView>('hub');
  const [scope, setScope] = useState<CatalogScope>({});
  const [armyId, setArmyId] = useState('');
  const [showDraft, setShowDraft] = useState(false);
  const selectedArmy = armies.find((army: Army) => army.id === armyId) || null;

  const enterCatalog = (next: CatalogScope = {}) => { setScope(next); setView('catalog'); };
  const enterDossier = (army: Army) => { setArmyId(army.id); setView('dossier'); };
  const stationName = (id?: string) => nodes.find((node: any) => node.id === id)?.name || id || '驻地未录';

  const header = view === 'hub' ? '军府军籍总枢' : view === 'catalog' ? '军籍分卷' : '行军档案';
  return <main className="military-hub-scene">
    <AppFrame className="military-hub-frame" title={header} eyebrow="军府所藏 · 天下军籍总册"
      back={<ActionSealButton priority="ghost" onClick={() => view === 'hub' ? navigate('map') : setView(view === 'dossier' ? 'catalog' : 'hub')}><ArrowLeft />{view === 'hub' ? '返回天下舆图' : '返前卷'}</ActionSealButton>}
      actions={view === 'dossier' && selectedArmy?.owner_power === 'liu_bei' ? <ActionSealButton priority="primary" onClick={() => setShowDraft(true)}><BookOpen />拟入方略</ActionSealButton> : <StatusMark tone="neutral">阅览天下军籍</StatusMark>}>
      {view === 'hub' && <MilitaryHub armies={armies} groups={groups} stations={stations} stationName={stationName} onCatalog={enterCatalog} />}
      {view === 'catalog' && <ArmyCatalog armies={armies} groups={groups} scope={scope} stationName={stationName} onDossier={enterDossier} />}
      {view === 'dossier' && selectedArmy && <ArmyDossier army={selectedArmy} stationName={stationName(selectedArmy.station_node)} onMap={() => openMapAt(selectedArmy.station_node)} onCommander={() => openCharacter(selectedArmy.commander, 'army')} />}
      {view === 'dossier' && !selectedArmy && <EmptyArchive onReturn={() => setView('hub')} />}
      {showDraft && selectedArmy?.owner_power === 'liu_bei' && <DraftEditor source_type="map_detail" draft={{ assignee: selectedArmy.id, target: stationName(selectedArmy.station_node), directive_type: 'military', title: '', status: 'draft' } as any} onClose={() => setShowDraft(false)} onSave={() => setShowDraft(false)} />}
    </AppFrame>
  </main>;
}

function MilitaryHub({ armies, groups, stations, stationName, onCatalog }: { armies: Army[]; groups: ReturnType<typeof groupArmiesByPower>; stations: ReturnType<typeof groupArmiesByStation>; stationName: (id?: string) => string; onCatalog: (scope?: CatalogScope) => void }) {
  const urgent = armies.filter((army) => armyRisk(army).level === 'urgent');
  const supply = armies.filter((army) => value(army.supply) < 35);
  const tired = armies.filter((army) => value(army.fatigue) >= 50);
  const ordered = armies.filter((army) => Boolean(army.current_order));
  return <div className="military-hub-sheet">
    <section className="military-verdict" aria-label="本月军情总断">
      <div><p className="archive-kicker">本月军情总断</p><h2>{urgent.length ? '粮秣、军心与疲军，宜先覆核' : '诸军军籍已汇，暂无急报'}</h2><p>军府只据当前军籍的补给、士气、疲劳与军令存录判断轻重，不另行裁断天下事实。</p></div>
      <dl><div><dt>天下军数</dt><dd>{armies.length}<small>支</small></dd></div><div><dt>合兵</dt><dd>{number(armies.reduce((sum, army) => sum + value(army.manpower), 0))}</dd></div><div><dt>可虑</dt><dd>{urgent.length}<small>支</small></dd></div></dl>
    </section>
    <section className="military-intelligence-slips" aria-label="军情入口">
      <button onClick={() => onCatalog({ risk: 'urgent' })}><em>朱印急报</em><strong>{urgent.length} 支可虑军队</strong><span>优先查看补给、士气与疲劳</span><ChevronRight /></button>
      <button onClick={() => onCatalog({ risk: 'urgent' })}><em>粮秣核簿</em><strong>{supply.length} 支补给告急</strong><span>补给低于既有警戒值</span><ChevronRight /></button>
      <button onClick={() => onCatalog({ risk: 'watch' })}><em>操练备忘</em><strong>{tired.length} 支疲军待察</strong><span>疲劳已达须留意区间</span><ChevronRight /></button>
      <button onClick={() => onCatalog({ risk: 'order', mode: 'orders' })}><em>军令待阅</em><strong>{ordered.length} 道现行军令</strong><span>入卷查阅既有军令记录</span><ChevronRight /></button>
    </section>
    <div className="military-entry-grid">
      <ArchiveEntry title="诸侯军籍" note="按势力分卷，先看兵力与风险" asset="power">
        {groups.slice(0, 5).map((group) => <button key={group.id} onClick={() => onCatalog({ powerId: group.id })}><span className="entry-seal">{group.name.slice(0, 1)}</span><strong>{group.name}</strong><small>{group.armies.length} 军 · {number(group.manpower)} 人</small>{group.riskCount > 0 && <em>{group.riskCount} 可虑</em>}</button>)}
        <button className="entry-all" onClick={() => onCatalog()}>翻阅全部诸侯军籍 <ChevronRight /></button>
      </ArchiveEntry>
      <ArchiveEntry title="战区驻军" note="按现有驻地聚合，不另设战区事实" asset="theater">
        {stations.slice(0, 5).map((station) => <button key={station.id} onClick={() => onCatalog({ stationId: station.id })}><MapPinned size={15}/><strong>{stationName(station.id)}</strong><small>{station.armies.length} 军 · {number(station.manpower)} 人</small>{station.riskCount > 0 && <em>{station.riskCount} 可虑</em>}</button>)}
        <button className="entry-all" onClick={() => onCatalog()}>查阅全部驻军分布 <ChevronRight /></button>
      </ArchiveEntry>
      <ArchiveEntry title="军令与战功" note="军令、军职与功绩均为既有存录" asset="command">
        <button onClick={() => onCatalog({ risk: 'order', mode: 'orders' })}><BookOpen size={15}/><strong>现行军令</strong><small>{ordered.length} 支军队留有军令记录</small><ChevronRight /></button>
        <button onClick={() => onCatalog({ mode: 'merit' })}><Shield size={15}/><strong>战功军籍</strong><small>按既有功绩、军职下钻查阅</small><ChevronRight /></button>
      </ArchiveEntry>
    </div>
  </div>;
}

function ArchiveEntry({ title, note, asset, children }: { title: string; note: string; asset: string; children: ReactNode }) { return <section className={`military-entry military-entry-${asset}`}><SectionHeading index="分卷" note={note}>{title}</SectionHeading><div>{children}</div></section>; }

function ArmyCatalog({ armies, groups, scope, stationName, onDossier }: { armies: Army[]; groups: ReturnType<typeof groupArmiesByPower>; scope: CatalogScope; stationName: (id?: string) => string; onDossier: (army: Army) => void }) {
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState<ArmySort>(scope.mode === 'merit' ? 'risk' : 'manpower');
  const [risk, setRisk] = useState<ArmyRiskFilter>(scope.risk || 'all');
  const title = scope.powerId ? groups.find((group) => group.id === scope.powerId)?.name || '势力' : scope.stationId ? stationName(scope.stationId) : scope.mode === 'orders' ? '军令记录' : scope.mode === 'merit' ? '战功军籍' : '天下军籍';
  const scoped = armies.filter((army) => (!scope.powerId || army.owner_power === scope.powerId) && (!scope.stationId || army.station_node === scope.stationId));
  const visible = filterAndSortArmies(filterArmiesByRisk(scoped, risk), query, sort);
  return <article className="military-catalog-sheet">
    <header className="catalog-heading"><div><p className="archive-kicker">军府存卷 · 第 {scope.powerId || scope.stationId ? '二' : '一'} 册</p><h2>{title}</h2><p>{scope.mode === 'orders' ? '军令内容为现有存录；点击军籍可查阅完整行军档案。' : '检索与筛选仅用于翻阅当前军籍，并不改写天下事实。'}</p></div><span className="catalog-red-seal">军府阅</span></header>
    <div className="catalog-tools" aria-label="军籍检索与筛选"><label className="catalog-search"><Search size={16}/><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="检索军名、统帅或驻地" /></label><LedgerChoice label="军情" value={risk} options={[['all','全录'],['urgent','急报'],['watch','可虑'],['order','有令']]} onChange={(next) => setRisk(next as ArmyRiskFilter)} /><LedgerChoice label="排卷" value={sort} options={[['manpower','兵力'],['risk','军情'],['station','驻地']]} onChange={(next) => setSort(next as ArmySort)} /></div>
    <div className="catalog-column-head"><span>军籍</span><span>统帅与驻地</span><span>兵力</span><span>军情</span></div>
    <ol className="catalog-roster">{visible.map((army, index) => { const riskState = armyRisk(army); return <li key={army.id}><button onClick={() => onDossier(army)}><span className="roster-folio">{String(index + 1).padStart(2,'0')}</span><span className="roster-title"><strong>{army.name || army.id}</strong><small>{army.military_record?.rank || '军职待录'} · {army.troop_type || '兵种待录'}</small></span><span className="roster-commander"><b>{army.commander || '统帅待考'}</b><small>{stationName(army.station_node)}</small></span><span className="roster-number">{number(army.manpower)}<small>人</small></span><span className={`roster-risk risk-${riskState.level}`}>{riskState.level === 'steady' ? '录' : riskState.level === 'urgent' ? '急' : '察'}<i>{riskState.label}</i></span><ChevronRight /></button></li>; })}</ol>
    {!visible.length && <p className="archive-empty">此分卷尚无相符军籍。</p>}
  </article>;
}

function LedgerChoice({ label, value, options, onChange }: { label: string; value: string; options: Array<[string, string]>; onChange: (value: string) => void }) { return <fieldset className="ledger-choice"><legend>{label}</legend>{options.map(([option, name]) => <button key={option} type="button" aria-pressed={value === option} onClick={() => onChange(option)}>{name}</button>)}</fieldset>; }

function ArmyDossier({ army, stationName, onMap, onCommander }: { army: Army; stationName: string; onMap: () => void; onCommander: () => void }) {
  const risk = armyRisk(army); const merits = army.military_record?.recent_merits || [];
  const readiness = [['士气', value(army.morale)], ['训练', value(army.training)], ['军械', value(army.equipment)], ['补给', value(army.supply)], ['疲劳', value(army.fatigue), true], ['经验', value(army.experience)], ['纪律', value(army.discipline)], ['机动', value(army.mobility)]] as const;
  return <article className="military-dossier-sheet">
    <header className="dossier-heading"><div className="dossier-folio">军籍正页<br/><span>{army.military_record?.rank || '军职待录'}</span></div><div className="dossier-identity"><p className="archive-kicker">行军档案 · {risk.label}</p><h2>{army.name || army.id}</h2><p>主将 <button onClick={onCommander}>{army.commander || '待考'} <UserRound size={13}/></button><i>·</i> {army.troop_type || '兵种待录'}</p></div><span className={`dossier-seal risk-${risk.level}`}>{risk.level === 'steady' ? '军籍已阅' : risk.level === 'urgent' ? '急验' : '待察'}</span></header>
    <div className="dossier-actions"><button className="dossier-station" onClick={onMap}><MapPinned size={16}/><span><b>驻地</b>{stationName}</span><small>转往舆图</small><ChevronRight /></button><span className="dossier-order-slip"><BookOpen size={15}/><b>现行军令</b>{army.current_order ? `${army.current_order.order_type || '未详'} · ${army.current_order.status || '未详'}` : '暂无'}</span></div>
    <DossierSection title="兵种编制" note={`合兵 ${number(army.manpower)} 人`}><div className="composition-list">{Object.entries(army.troop_composition || {}).map(([kind, amount]) => <p key={kind}><span>{kind}</span><b>{number(amount as number)} 人</b></p>)}{!Object.keys(army.troop_composition || {}).length && <p className="archive-empty">兵种编制尚未录入。</p>}</div></DossierSection>
    <DossierSection title="军职协同" note="主将、副将、军司马"><dl className="dossier-definition"><dt>主将</dt><dd>{army.commander || '待考'}</dd><dt>副将</dt><dd>{army.deputy_commander || '暂缺'}</dd><dt>军司马</dt><dd>{army.military_adjutant || '暂缺'}</dd><dt>军职</dt><dd>{army.military_record?.rank || '待录'}</dd></dl></DossierSection>
    <DossierSection title="战备状态" note="八项军况尺"><div className="readiness-ledger">{readiness.map(([label, amount, inverted]) => <div key={label} className={(label === '补给' && amount < 35) || (label === '疲劳' && amount >= 50) ? 'is-risk' : ''}><span>{label}</span><i><b style={{ width: `${Math.max(8, Math.min(100, inverted ? 100 - amount : amount))}%` }} /></i><strong>{amount}{label === '补给' && <small> · {value(army.supply_turns)}旬</small>}</strong></div>)}</div></DossierSection>
    <DossierSection title="当前军令" note={army.current_order ? '既有军令记录' : '暂无军令'}>{army.current_order ? <dl className="dossier-definition"><dt>军令</dt><dd>{army.current_order.order_type || '未详'}</dd><dt>状态</dt><dd>{army.current_order.status || '未详'}</dd></dl> : <p className="archive-empty">此军尚无可见现行军令。</p>}</DossierSection>
    <DossierSection title="近期战功" note={`累功 ${number(army.military_record?.merit)}`}>{merits.length ? <ol className="merit-list">{merits.map((item, index) => <li key={index}><b>{item.delta > 0 ? '+' : ''}{item.delta}</b><span>{item.source || '军籍存录'}</span></li>)}</ol> : <p className="archive-empty">军籍未录近期战功。</p>}</DossierSection>
    <p className="dossier-footnote">本页仅汇录当前世界状态；敌军档案全程只读，刘备军另可拟入方略，仍须按既有规则结算。</p>
  </article>;
}
function DossierSection({ title, note, children }: { title: string; note: string; children: ReactNode }) { return <section className="dossier-section"><SectionHeading index="卷段" note={note}>{title}</SectionHeading>{children}</section>; }
function EmptyArchive({ onReturn }: { onReturn: () => void }) { return <div className="military-dossier-sheet archive-empty"><p>此军档案未能从当前军籍中找到。</p><button onClick={onReturn}>返回军府总枢</button></div>; }
