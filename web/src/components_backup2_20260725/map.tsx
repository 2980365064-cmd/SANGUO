import React from "react";
import { Expand, Map as MapIcon, Shrink, Scroll, Building } from "lucide-react";

import { DEFAULT_MAP_LAYER, STATIC_MAP_LABEL_POLICY, clampMapZoom, getCommanderyBoundaryBlocks, getProvinceBlocks, getSharedCityBoundaryPath, getTownBlocks } from "../mapLogic";
import type { MapLayer } from "../mapLogic";
import type { Army, GameState } from "../types";
import { POWER_COLORS } from "../constants/powerColors";
import { MapInfoDrawer } from "./mapInfo/MapInfoDrawer";

export function StrategicMap({ state, selectedId, selectedArmyId, onSelect, onState }: {
  state: GameState;
  selectedId: string;
  selectedArmyId: string;
  onSelect: (id: string) => void;
  onState?: (state: GameState) => void;
}) {
  const [zoom, setZoom] = React.useState(1);
  const [pan, setPan] = React.useState({ x: 0, y: 0 });
  const [expanded, setExpanded] = React.useState(false);
  const [tooltip, setTooltip] = React.useState<{ x: number; y: number; text: string } | null>(null);
  const [mapLayer, setMapLayer] = React.useState<MapLayer>(DEFAULT_MAP_LAYER);
  const [selectedProvince, setSelectedProvince] = React.useState<string | null>(null);
  const [selectedCommandery, setSelectedCommandery] = React.useState<string | null>(null);
  const [selectedCity, setSelectedCity] = React.useState<string | null>(null);
  const [infoNodeId, setInfoNodeId] = React.useState("");
  const drag = React.useRef<{ pointerId: number; x: number; y: number; panX: number; panY: number } | null>(null);

  const provinceBlocks = getProvinceBlocks(state.map.nodes);
  const commanderyBlocks = getCommanderyBoundaryBlocks(state.map.nodes);
  const cityBlocks = getTownBlocks(state.map.nodes);
  const sharedCommanderyBoundaryPath = React.useMemo(() => getSharedCityBoundaryPath(commanderyBlocks), [commanderyBlocks]);
  const selectedArmy = state.armies.find((army) => army.id === selectedArmyId);

  const showProvinceLabels = STATIC_MAP_LABEL_POLICY.provinceLabels === "overlay";
  const showCommanderyLabels = STATIC_MAP_LABEL_POLICY.commanderyLabels === "overlay";
  const showCityLabels = STATIC_MAP_LABEL_POLICY.cityLabels === "overlay";

  const powerLabel = (powerId: string) => state.powers.find((power) => power.id === powerId)?.name || "无主";
  const openNodeInfo = (nodeId: string) => { onSelect(nodeId); setInfoNodeId(nodeId); };

  const changeZoom = (delta: number) => setZoom((value) => clampMapZoom(value + delta));
  const switchLayer = (layer: MapLayer) => {
    setMapLayer(layer);
    setTooltip(null);
    if (layer === "province") { setSelectedCommandery(null); setSelectedCity(null); }
    if (layer === "commandery") { setSelectedProvince(null); setSelectedCity(null); }
    if (layer === "city") { setSelectedProvince(null); setSelectedCommandery(null); }
  };

  // 获取城池的军队
  const getCityArmies = (cityName: string): Army[] => {
    const cityBlock = cityBlocks.find((b) => b.city === cityName || b.node?.name === cityName);
    const node = cityBlock?.node || state.map.nodes.find((n) => n.name === cityName);
    if (!node) return [];
    return state.armies.filter((army) => army.station_node === node.id);
  };

  // 左键点击州块
  const handleProvinceClick = (province: string, event: React.MouseEvent) => {
    event.stopPropagation();
    setSelectedProvince(province);
    setSelectedCommandery(null);
    setSelectedCity(null);
    const node = provinceBlocks.find((block) => block.province === province)?.nodes[0];
    if (node) openNodeInfo(node.id);
  };

  // 左键点击郡域
  const handleCommanderyClick = (block: typeof commanderyBlocks[number], event: React.MouseEvent) => {
    event.stopPropagation();
    setSelectedCommandery(block.city);
    setSelectedProvince(null);
    setSelectedCity(null);
    if (block.node) openNodeInfo(block.node.id);
  };

  // 左键点击城池
  const handleCityClick = (block: typeof cityBlocks[number], event: React.MouseEvent) => {
    event.stopPropagation();
    setSelectedCity(block.city);
    setSelectedProvince(null);
    setSelectedCommandery(null);
    if (block.node) openNodeInfo(block.node.id);
  };

  return <section className={`strategic-map ${expanded ? "map-expanded" : ""}`} aria-label="天下战略沙盘">
    <div className="map-caption"><MapIcon /><span>天下州郡<small>拖动舆图 · 滚轮缩放 · 悬停查看州/郡/城镇信息</small></span></div>
    <div className="map-controls" aria-label="地图控制">
      <button aria-label={expanded ? "收起大地图" : "展开大地图"} onClick={() => setExpanded((value) => !value)}>{expanded ? <Shrink /> : <Expand />}</button>
    </div>
    <svg
      viewBox="0 0 1920 1080"
      preserveAspectRatio="xMidYMid slice"
      role="img"
      aria-label="三国十三州分块战略地图"
      onWheel={(event) => { event.preventDefault(); changeZoom(event.deltaY < 0 ? 0.12 : -0.12); }}
      onPointerDown={(event) => {
        if (event.button !== 0) return;
        event.currentTarget.setPointerCapture(event.pointerId);
        drag.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, panX: pan.x, panY: pan.y };
      }}
      onPointerMove={(event) => {
        if (!drag.current || drag.current.pointerId !== event.pointerId) return;
        const rect = event.currentTarget.getBoundingClientRect();
        setPan({
          x: drag.current.panX + (event.clientX - drag.current.x) * 1920 / rect.width,
          y: drag.current.panY + (event.clientY - drag.current.y) * 1080 / rect.height,
        });
      }}
      onPointerUp={() => { drag.current = null; }}
      onPointerCancel={() => { drag.current = null; }}
      onContextMenu={(event) => event.preventDefault()}
    >
      <defs>
        <filter id="map-shadow"><feDropShadow dx="0" dy="4" stdDeviation="5" floodOpacity=".42" /></filter>
        <filter id="border-roughen" x="-14%" y="-14%" width="128%" height="128%">
          <feTurbulence type="fractalNoise" baseFrequency="0.052 0.068" numOctaves="3" seed="38" result="noise" />
          <feDisplacementMap in="SourceGraphic" in2="noise" scale="15" xChannelSelector="R" yChannelSelector="G" result="roughLine" />
          <feDropShadow in="roughLine" dx="0" dy="1" stdDeviation="1" floodColor="#ecd6a8" floodOpacity=".48" />
        </filter>
      </defs>
      <g className="map-zoom-frame" transform={`translate(${960 + pan.x} ${540 + pan.y}) scale(${zoom}) translate(-960 -540)`}>
        <image href="/底图_expanded.jpg?v=20260720-rect-crop-outpaint" x="-320" y="-180" width="2560" height="1440" preserveAspectRatio="none" />

        {/* 第一层：州地块 */}
        {mapLayer === "province" && <g className="province-blocks annotated-province-layer">
          {provinceBlocks.map((block) => {
            const active = block.province === selectedProvince;
            const power = powerLabel(block.controller);
            return <g
              key={block.province}
              className={`province-block annotated-province-block ${active ? "selected" : ""}`}
              onPointerDown={(event) => event.stopPropagation()}
              onClick={(event) => handleProvinceClick(block.province, event)}
              onMouseMove={(event) => setTooltip({ x: event.clientX, y: event.clientY, text: `${block.province} · ${power}` })}
              onMouseLeave={() => setTooltip(null)}
              role="button"
              tabIndex={0}
              aria-label={`${block.province}，${power}据有`}
              onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") handleProvinceClick(block.province, event as unknown as React.MouseEvent); }}
            >
              <path className="province-hit-area" d={block.d} />
              <path className="province-outline" d={block.d} />
              {showProvinceLabels && <text className="province-label" x={block.labelX} y={block.labelY}>{block.province}</text>}
            </g>;
          })}
        </g>}

        {/* 第二层：郡域线稿 */}
        {mapLayer === "commandery" && <g className="commandery-blocks annotated-commandery-layer">
          <path className="commandery-shared-boundaries" d={sharedCommanderyBoundaryPath} aria-hidden="true" />
          {commanderyBlocks.map((block) => {
            const node = block.node;
            const isActive = block.city === selectedCommandery || node?.name === selectedCommandery;
            return <g
              key={block.city}
              className={`commandery-block annotated-commandery-block ${node ? "game-commandery" : "annotated-only-commandery"} ${isActive ? "selected" : ""}`}
              onPointerDown={(event) => event.stopPropagation()}
              onClick={(event) => handleCommanderyClick(block, event)}
              onMouseMove={(event) => setTooltip({ x: event.clientX, y: event.clientY, text: node ? `${block.commanderyName} · ${node.province} · 已接入节点` : `${block.commanderyName} · ${block.province} · 待校郡域` })}
              onMouseLeave={() => setTooltip(null)}
              role="button"
              tabIndex={0}
              aria-label={node ? `${block.commanderyName}，${node.province}` : `${block.commanderyName}，${block.province}`}
              onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") handleCommanderyClick(block, event as unknown as React.MouseEvent); }}
            >
              <path className="commandery-hit-area" d={block.d} />
              <path className="commandery-boundary" d={block.d} />
              {showCommanderyLabels && <text className="commandery-label" x={block.labelX} y={block.labelY}>{block.commanderyName}</text>}
            </g>;
          })}
        </g>}

        {/* 第三层：城镇/治所点位 */}
        {mapLayer === "city" && <g className="city-nodes city-node-layer">
          {cityBlocks.map((block) => {
            const node = block.node;
            const isActive = block.city === selectedCity || node?.name === selectedCity;
            const armies = getCityArmies(block.city);
            const townStatus = block.townKind === "historical-town" ? "历史城镇" : `${armies.length}支军队`;
            return <g
              key={node?.id || block.city}
              className={`city-node annotated-city-node ${block.townKind} ${isActive ? "selected" : ""}`}
              onPointerDown={(event) => event.stopPropagation()}
              onClick={(event) => handleCityClick(block, event)}
              onMouseMove={(event) => setTooltip({ x: event.clientX, y: event.clientY, text: `${block.townName} · ${block.commanderyName} · ${townStatus}` })}
              onMouseLeave={() => setTooltip(null)}
              role="button"
              tabIndex={0}
              aria-label={`${block.townName}，${block.commanderyName}`}
              onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") handleCityClick(block, event as unknown as React.MouseEvent); }}
            >
              <circle className="city-node-hit-area" cx={block.cx} cy={block.cy} r="22" />
              <g className={`city-model ${block.townKind} ${node?.is_capital || node?.name === "长安" ? "capital-town" : ""}`} transform={`translate(${block.cx} ${block.cy})`}>
                <image className="city-sprite" href="/assets/city-watercolor-grounded.png" x="-17.5" y="-25.5" width="35" height="27.5" preserveAspectRatio="xMidYMax meet" />
                {node && <path className="city-banner" d="M 10 -12.5 L 10 -25 L 21 -21 L 10 -17.5 Z" fill={POWER_COLORS[node.controller] || "#655c4b"} />}
              </g>
              {node?.is_capital || node?.name === "长安" ? <text className="capital-star" x={block.cx} y={block.cy - 20}>★</text> : null}
              {armies.length > 0 && <g className="army-marker city-army-marker" transform={`translate(${block.cx + 13} ${block.cy - 21})`}>
                <rect width="16" height="12" rx="1" /><text x="8" y="9" fontSize="8">{armies.length}</text>
              </g>}
              {showCityLabels && <text
                className="city-label"
                x={block.labelX}
                y={block.labelY + 16}
                onPointerDown={(event) => event.stopPropagation()}
                onClick={(event) => handleCityClick(block, event)}
              >{block.townName}</text>}
            </g>;
          })}
        </g>}
      </g>
    </svg>

    {/* 悬停提示 */}
    {tooltip && <div className="map-province-tooltip" style={{ left: tooltip.x, top: tooltip.y }}>
      {tooltip.text}
    </div>}

    <div className="map-layer-toggle" aria-label="地图图层切换">
      <button type="button" className={mapLayer === "province" ? "active" : ""} onClick={() => switchLayer("province")} aria-pressed={mapLayer === "province"}><MapIcon />州</button>
      <button type="button" className={mapLayer === "commandery" ? "active" : ""} onClick={() => switchLayer("commandery")} aria-pressed={mapLayer === "commandery"}><Scroll />郡</button>
      <button type="button" className={mapLayer === "city" ? "active" : ""} onClick={() => switchLayer("city")} aria-pressed={mapLayer === "city"}><Building />城镇</button>
    </div>

    <div className="map-legend">
      <span><i className="ordinary" />{mapLayer === "province" ? "州界" : mapLayer === "commandery" ? "郡界" : "城镇点位"}</span>
      <span><i className="city-range" />悬停高亮</span>
      <span>{mapLayer === "province" ? "州图层" : mapLayer === "commandery" ? "郡图层" : "城镇图层"}</span>
    </div>
    {infoNodeId && <MapInfoDrawer state={state} nodeId={infoNodeId} onClose={() => setInfoNodeId("")} onState={onState} />}

  </section>;
}
