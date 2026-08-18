/**
 * 地图信息抽屉：根据当前图层（省/郡/城）显示完整信息。
 * 替代原有的 ArmyCommandPanel 在 map-info-dock 中的使用。
 */
import React from "react";
import { X, Sword, Users, Building, Scroll } from "lucide-react";
import { getRegionDetail } from "../../api";
import type { GameState, Army, RegionDetail } from "../../types";
import { fiscalNumber, REGION_INVESTMENTS, REGION_LEDGER_ITEMS } from "../regionManagementModel";
import { POWER_COLORS } from "../../constants/powerColors";
import { GameDialog } from "../GameDialog";
import { PaperPanel, SectionHeading } from "../ui";

export function MapInfoDrawer({
  state,
  nodeId,
  onClose,
  onState,
}: {
  state: GameState;
  nodeId: string;
  onClose: () => void;
  onState?: (state: GameState) => void;
}) {
  const [detail, setDetail] = React.useState<RegionDetail | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [investmentBusy, setInvestmentBusy] = React.useState("");

  const node = state.map.nodes.find((n) => n.id === nodeId) || null;
  const province = node ? state.map.nodes.filter((n) => n.province === node.province) : [];
  const provinceArmies = state.armies.filter((army) =>
    province.some((n) => n.id === army.station_node)
  );
  const cityArmies = node ? state.armies.filter((army) => army.station_node === node.id) : [];
  const powerName = node ? (state.powers.find((p) => p.id === node.controller)?.name || "无主") : "";

  React.useEffect(() => {
    if (!nodeId) return;
    setLoading(true);
    getRegionDetail(nodeId)
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setLoading(false));
  }, [nodeId, state.turn.turn]);

  const investRegion = async (category: string) => {
    if (!nodeId) return;
    setInvestmentBusy(category);
    try {
      const { startInvestment } = await import("../../api");
      const result = await startInvestment(nodeId, category);
      onState?.(result.state);
      const newDetail = await getRegionDetail(nodeId);
      setDetail(newDetail);
    } finally {
      setInvestmentBusy("");
    }
  };

  if (!node) return null;

  return (
    <GameDialog open onOpenChange={(open) => { if (!open) onClose(); }} title={node.name} description={`${node.province} · ${powerName}据有`} tone="default" presentation="map-drawer">
      <div className="map-info-drawer-inner">
        <p className="map-info-controller"><i style={{ background: POWER_COLORS[node.controller] || "#666" }} />{powerName}据有</p>

        {/* 基础信息 */}
        <PaperPanel className="map-info-section">
          <SectionHeading index="概况">基础信息</SectionHeading>
          <div className="map-info-stats">
            <span>人口<strong>{node.population}</strong><small>万户</small></span>
            <span>民心<strong>{node.public_support}</strong><small>/100</small></span>
            <span>动乱<strong>{node.unrest}</strong><small>/100</small></span>
            <span>军事压力<strong>{node.military_pressure}</strong><small>/100</small></span>
          </div>
          {node.status && <p className="map-info-status">{node.status}</p>}
        </PaperPanel>

        {/* 财政/经营信息 */}
        {detail && (
          <PaperPanel className="map-info-section">
            <SectionHeading index="军政">郡县经营</SectionHeading>
            <div className="map-info-ledger">
              {REGION_LEDGER_ITEMS.map((item) => {
                const value = item.key === "gentry_resistance"
                  ? detail.gentry_resistance ?? node.military_pressure
                  : fiscalNumber(detail, item.key);
                return (
                  <span key={item.key} title={item.description}>
                    <b>{item.label}</b><strong>{value}</strong><small>{item.short}</small>
                  </span>
                );
              })}
            </div>
          </PaperPanel>
        )}

        {/* 郡县投资 */}
        {detail?.can_invest && (
          <PaperPanel className="map-info-section">
            <SectionHeading index="处置">投资方向</SectionHeading>
            {detail.investment && (
              <p className="investment-current">
                正在推进：{String(detail.investment.category ?? "")} · {Number(detail.investment.progress ?? 0)}%
              </p>
            )}
            <div className="investment-actions">
              {REGION_INVESTMENTS.map((item) => (
                <button
                  key={item.category}
                  onClick={() => void investRegion(item.category)}
                  disabled={!!investmentBusy || !!detail.investment}
                  title={detail.investment
                    ? `已有投资正在推进：${String(detail.investment.category ?? "")}`
                    : item.description}
                >
                  {investmentBusy === item.category ? "…" : null}
                  <span>{item.category}</span><small>{item.hint}</small>
                </button>
              ))}
            </div>
          </PaperPanel>
        )}

        {/* 州内军队 */}
        {provinceArmies.length > 0 && (
          <PaperPanel className="map-info-section">
            <SectionHeading index="军府" note={`${provinceArmies.length} 支`}>州内军队</SectionHeading>
            <div className="map-info-armies">
              {provinceArmies.map((army) => (
                <article key={army.id}>
                  <i style={{ background: POWER_COLORS[army.owner_power] }} />
                  <div>
                    <strong>{army.name}</strong>
                    <small>{army.commander} · {army.manpower.toLocaleString()}人</small>
                  </div>
                </article>
              ))}
            </div>
          </PaperPanel>
        )}

        {/* 城内驻军 */}
        {cityArmies.length > 0 && cityArmies.length !== provinceArmies.length && (
          <PaperPanel className="map-info-section">
            <SectionHeading index="军府" note={`${cityArmies.length} 支`}>城内驻军</SectionHeading>
            <div className="map-info-armies">
              {cityArmies.map((army) => (
                <article key={army.id}>
                  <i style={{ background: POWER_COLORS[army.owner_power] }} />
                  <div>
                    <strong>{army.name}</strong>
                    <small>{army.commander} · {army.manpower.toLocaleString()}人 · {army.status}</small>
                  </div>
                </article>
              ))}
            </div>
          </PaperPanel>
        )}

        {loading && <p className="empty-note">正在调阅簿册……</p>}
        {detail && !detail.can_invest && (
          <p className="empty-note">此地非刘备实际控制，只可观察与问策。</p>
        )}
      </div>
    </GameDialog>
  );
}
