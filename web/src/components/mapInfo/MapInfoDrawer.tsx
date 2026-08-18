/** 州、郡、城三层地方簿册：仅调阅已确认行政事实。 */
import React from "react";
import { Flame, HeartPulse, ShieldAlert, Warehouse } from "lucide-react";
import { getAdministrativeDetail } from "../../api";
import type { AdministrativeDetail, AdministrativeScope, GameState } from "../../types";
import { POWER_COLORS } from "../../constants/powerColors";
import { GameDialog } from "../GameDialog";
import { SectionHeading } from "../ui";

const scopeCopy: Record<AdministrativeScope, { kicker: string; overview: string; bg: string }> = {
  province: { kicker: "州域统筹簿", overview: "全州一览", bg: "var(--archive-administrative-province-ledger-v3)" },
  commandery: { kicker: "郡治民政簿", overview: "治民与守土", bg: "var(--archive-administrative-commandery-ledger-v3)" },
  city: { kicker: "城防军府簿", overview: "城防与仓廪", bg: "var(--archive-administrative-city-ledger-v3)" },
};

function Meter({ label, value, tone, Icon }: { label: string; value: number; tone: string; Icon: React.ElementType }) {
  return <div className={`map-info-state map-info-state-${tone}`}><Icon aria-hidden="true" /><dt>{label}</dt><dd>{value}<small>/100</small></dd><i className="map-info-meter" style={{ "--meter": `${Math.max(0, Math.min(100, value))}%` } as React.CSSProperties} /></div>;
}

function ArchiveNotes({ detail }: { detail: AdministrativeDetail }) {
  const notes = detail.risk_notes || [], history = detail.recent_history || [];
  return <>
    <section className="map-info-record map-info-marginalia map-info-annotation-slip"><SectionHeading index="待议批注">地方待议</SectionHeading>{notes.length ? <ol>{notes.map((note) => <li key={note}>{note}</li>)}</ol> : <p>当前未见须立即整理入方略的地方警讯。</p>}<small>仅据已确认事实提示；处置仍须入方略簿颁行。</small></section>
    <section className="map-info-record map-info-chronicle map-info-chronicle-slip"><SectionHeading index="近月纪事">近三月纪事</SectionHeading>{history.length ? <ol>{history.map((item, index) => <li key={`${item.turn}-${index}`}><time>第{item.turn}回合</time><span>{item.text}</span></li>)}</ol> : <p>近月无可载纪事。</p>}</section>
  </>;
}

export function MapInfoDrawer({ state, scope, entityId, onClose }: { state: GameState; scope: AdministrativeScope; entityId: string; onClose: () => void; }) {
  const [detail, setDetail] = React.useState<AdministrativeDetail | null>(null);
  const [loading, setLoading] = React.useState(true); const [loadError, setLoadError] = React.useState<string | null>(null);
  const copy = scopeCopy[scope];
  React.useEffect(() => { let alive = true; setLoading(true); setLoadError(null); getAdministrativeDetail(scope, entityId).then((item) => { if (alive) setDetail(item); }).catch((cause: unknown) => { if (alive) { setDetail(null); setLoadError(cause instanceof Error ? cause.message : "行政档案暂不可读取。"); } }).finally(() => { if (alive) setLoading(false); }); return () => { alive = false; }; }, [scope, entityId, state.turn.turn]);
  const powerName = detail ? (state.powers.find((p) => p.id === detail.controlled_by)?.name || "无主") : "";
  const title = detail?.name || "调阅档案", armies = detail?.stationed_armies || [], fiscal = detail?.fiscal || {};
  const number = (key: string) => Number(fiscal[key] || 0);
  return <GameDialog open onOpenChange={(open) => { if (!open) onClose(); }} title={`${title}${copy.kicker}`} tone="default" presentation="map-drawer" bgAsset={copy.bg} className={`map-info-material-${scope}`}>
    <div className={`map-info-drawer-inner map-info-scope-${scope}`}><div className="map-info-hero"><div className="map-info-hero-text"><span className="map-info-kicker">{copy.kicker}</span><div className="map-info-title-deck"><i className="map-info-city-seal">{title.slice(0, 1)}</i><h2 className="map-info-hero-title">{title}</h2></div>{detail && <><p className="map-info-hero-sub"><i className="map-info-power-dot" style={{ background: POWER_COLORS[detail.controlled_by] || "#666" }} />{powerName}据有</p><p className="map-info-hero-judgement">{detail.summary || detail.status}</p></>}</div></div>
      <div className="map-info-scroll">{detail && <>
        {scope === "province" && <><section className="map-info-record map-info-primary-ledger"><SectionHeading index="州府总览">{copy.overview}</SectionHeading><dl className="map-info-grand-totals"><div><dt>辖郡</dt><dd>{detail.commandery_count}</dd></div><div><dt>辖城</dt><dd>{detail.city_count}</dd></div><div><dt>编户</dt><dd>{detail.population}</dd></div><div><dt>岁赋</dt><dd>{detail.tax_per_turn}</dd></div></dl><dl className="map-info-state-list"><Meter label="转运" value={detail.transport || 0} tone="support" Icon={Warehouse}/><Meter label="征发" value={detail.mobilization || 0} tone="pressure" Icon={ShieldAlert}/><Meter label="治安协同" value={detail.security_coordination || 0} tone="unrest" Icon={Flame}/></dl></section><section className="map-info-record map-info-directory-slip"><SectionHeading index="辖郡舆情">辖郡目录</SectionHeading><div className="map-info-armies map-info-subrolls">{detail.commanderies?.map((item) => <article key={item.id}><i style={{ background: POWER_COLORS[item.controlled_by] || "#666" }} /><div><strong>{item.name}</strong><small>{state.powers.find((p) => p.id === item.controlled_by)?.name || "无主"}据有 · 民情与军压待核</small></div></article>)}</div></section><ArchiveNotes detail={detail}/></>}
        {scope === "commandery" && <><section className="map-info-record map-info-primary-ledger"><SectionHeading index="郡治概况">{copy.overview}</SectionHeading><dl className="map-info-grand-totals"><div><dt>编户</dt><dd>{detail.population}</dd></div><div><dt>田赋</dt><dd>{detail.tax_per_turn}</dd></div><div><dt>粮产</dt><dd>{number("grain_output")}</dd></div><div><dt>可调粮</dt><dd>{detail.available_grain}</dd></div></dl><dl className="map-info-state-list"><Meter label="民心" value={detail.public_support || 0} tone="support" Icon={HeartPulse}/><Meter label="动乱" value={detail.unrest || 0} tone="unrest" Icon={Flame}/><Meter label="士族阻力" value={detail.gentry_resistance || 0} tone="pressure" Icon={ShieldAlert}/></dl></section><section className="map-info-record map-info-directory-slip"><SectionHeading index="属城分卷">属城目录</SectionHeading><div className="map-info-armies map-info-city-directory">{detail.cities?.map((city) => <article key={city.id}><i style={{ background: POWER_COLORS[city.controlled_by] || "#666" }} /><div><strong>{city.name}{city.is_commandery_capital ? " · 郡治" : ""}</strong><small>{city.strategic_role} · 城防{city.fortification} · 仓粮{city.grain_stock} · {city.siege_status}</small></div></article>)}</div></section><ArchiveNotes detail={detail}/></>}
        {scope === "city" && <><section className="map-info-record map-info-primary-ledger"><SectionHeading index="城防纪要">{copy.overview}</SectionHeading><dl className="map-info-grand-totals"><div><dt>城防</dt><dd>{detail.fortification}</dd></div><div><dt>秩序</dt><dd>{detail.order_score}</dd></div><div><dt>仓粮</dt><dd>{detail.grain_stock}</dd></div><div><dt>市易</dt><dd>{detail.market_capacity}</dd></div></dl><p className="map-info-ledger-note">{detail.strategic_role} · 容纳{detail.garrison_capacity}军 · {detail.siege_status}</p></section><section className="map-info-record map-info-directory-slip"><SectionHeading index="守备形势" note={`${armies.length} 支 · ${detail.stationed_manpower?.toLocaleString() || 0}人`}>城内驻军</SectionHeading>{armies.length ? <div className="map-info-armies">{armies.map((army) => <article key={army.id}><i style={{ background: POWER_COLORS[army.owner_power] || "#666" }} /><div><strong>{army.name}</strong><small>{army.commander} · {army.troop_type} · {army.manpower.toLocaleString()}人 · 粮{army.supply}/气{army.morale}</small></div></article>)}</div> : <p>城内未见建档驻军。</p>}</section><section className="map-info-record map-info-annotation-slip"><SectionHeading index="仓廪市易">城中账目</SectionHeading><p className="map-info-ledger-note">城池仓廪与市易独立记载，不与郡级赋税重复计算。</p></section><ArchiveNotes detail={detail}/></>}
      </>}{loading && <p className="empty-note">正在调阅簿册……</p>}{!loading && !detail && <p className="empty-note">{loadError || "此份行政档案尚未入库。"}</p>}</div>
    </div></GameDialog>;
}
