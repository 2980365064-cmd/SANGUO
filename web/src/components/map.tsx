import React from "react";
import {
  Building,
  Expand,
  Flag,
  Map as MapIcon,
  Scroll,
  Shrink,
} from "lucide-react";

import {
  DEFAULT_MAP_LAYER,
  STATIC_MAP_LABEL_POLICY,
  clampMapZoom,
  getCityTerritoryBlocks,
  getCommanderyBoundaryBlocks,
  getTownBlocks,
  getProvinceBlocks,
  getSharedCityBoundaryPath,
} from "../mapLogic";
import type { MapLayer } from "../mapLogic";
import type { AdministrativeScope, Army, GameState } from "../types";
import { POWER_COLORS } from "../constants/powerColors";
import { MapInfoDrawer } from "./mapInfo/MapInfoDrawer";

export function StrategicMap({
  state,
  selectedArmyId,
  onSelect,
}: {
  state: GameState;
  selectedId: string;
  selectedArmyId: string;
  onSelect: (id: string) => void;
  onState?: (state: GameState) => void;
}) {
  const [zoom, setZoom] = React.useState(1);
  const [pan, setPan] = React.useState({ x: 0, y: 0 });
  const [expanded, setExpanded] = React.useState(false);
  const [tooltip, setTooltip] = React.useState<{
    x: number;
    y: number;
    text: string;
  } | null>(null);
  const [mapLayer, setMapLayer] = React.useState<MapLayer>(DEFAULT_MAP_LAYER);
  const [selectedProvince, setSelectedProvince] = React.useState<string | null>(
    null,
  );
  const [selectedCommandery, setSelectedCommandery] = React.useState<
    string | null
  >(null);
  const [selectedCity, setSelectedCity] = React.useState<string | null>(null);
  const [infoTarget, setInfoTarget] = React.useState<{
    scope: AdministrativeScope;
    entityId: string;
  } | null>(null);
  const drag = React.useRef<{
    pointerId: number;
    x: number;
    y: number;
    panX: number;
    panY: number;
  } | null>(null);

  const provinceBlocks = getProvinceBlocks(state.map.nodes);
  const commanderyBlocks = React.useMemo(
    () => getCommanderyBoundaryBlocks(state.map.nodes),
    [state.map.nodes],
  );
  // 旧版已校准的城镇坐标是新增城池落位的地理基准，永不由运行时坐标推导覆盖。
  const historicalTownBlocks = React.useMemo(
    () => getTownBlocks(state.map.nodes),
    [state.map.nodes],
  );
  const cityBlocks = React.useMemo(
    () => getCityTerritoryBlocks(state.map.cities || [], commanderyBlocks),
    [state.map.cities, commanderyBlocks],
  );
  const sharedCommanderyBoundaryPath = React.useMemo(
    () => getSharedCityBoundaryPath(commanderyBlocks),
    [commanderyBlocks],
  );
  // 高亮裁切同一张边界网络；不能另算一条近似曲线。
  const cityInternalBoundaryPath = React.useMemo(
    () =>
      cityBlocks
        .map((block) => block.boundaryD)
        .filter(Boolean)
        .join(" "),
    [cityBlocks],
  );
  const cityBoundaryNetworkPath = `${sharedCommanderyBoundaryPath} ${cityInternalBoundaryPath}`;
  const cityClipId = (cityId: string) =>
    `city-highlight-${cityId.replace(/[^a-zA-Z0-9_-]/g, "_")}`;
  const showProvinceLabels =
    STATIC_MAP_LABEL_POLICY.provinceLabels === "overlay";
  const showCommanderyLabels =
    STATIC_MAP_LABEL_POLICY.commanderyLabels === "overlay";
  const showCityLabels = STATIC_MAP_LABEL_POLICY.cityLabels === "overlay";
  const powerLabel = (powerId: string) =>
    state.powers.find((power) => power.id === powerId)?.name || "无主";
  const openNodeInfo = (
    nodeId: string,
    scope: AdministrativeScope,
    entityId: string,
  ) => {
    onSelect(nodeId);
    setInfoTarget({ scope, entityId });
  };
  const cityArmies = (cityId: string, commanderyId: string): Army[] =>
    state.armies.filter(
      (army) =>
        army.station_node === cityId || army.station_node === commanderyId,
    );
  const switchLayer = (layer: MapLayer) => {
    setMapLayer(layer);
    setTooltip(null);
    if (layer === "province") {
      setSelectedCommandery(null);
      setSelectedCity(null);
    }
    if (layer === "commandery") {
      setSelectedProvince(null);
      setSelectedCity(null);
    }
    if (layer === "city" || layer === "influence") {
      setSelectedProvince(null);
      setSelectedCommandery(null);
    }
  };

  return (
    <section
      className={`strategic-map ${expanded ? "map-expanded" : ""}`}
      aria-label="天下舆图"
    >
      <div className="map-caption">
        <MapIcon />
        <span>
          天下舆图<small>拖动舆图 · 滚轮缩放 · 调阅州、郡与城防军府簿</small>
        </span>
      </div>
      <div className="map-controls" aria-label="地图控制">
        <button
          aria-label={expanded ? "收起大地图" : "展开大地图"}
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? <Shrink /> : <Expand />}
        </button>
      </div>
      <svg
        viewBox="0 0 1920 1080"
        preserveAspectRatio="xMidYMid slice"
        role="img"
        aria-label="建安十三年天下舆图"
        onWheel={(event) => {
          event.preventDefault();
          setZoom((value) =>
            clampMapZoom(value + (event.deltaY < 0 ? 0.12 : -0.12)),
          );
        }}
        onPointerDown={(event) => {
          if (event.button !== 0) return;
          event.currentTarget.setPointerCapture(event.pointerId);
          drag.current = {
            pointerId: event.pointerId,
            x: event.clientX,
            y: event.clientY,
            panX: pan.x,
            panY: pan.y,
          };
        }}
        onPointerMove={(event) => {
          if (!drag.current || drag.current.pointerId !== event.pointerId)
            return;
          const rect = event.currentTarget.getBoundingClientRect();
          setPan({
            x:
              drag.current.panX +
              ((event.clientX - drag.current.x) * 1920) / rect.width,
            y:
              drag.current.panY +
              ((event.clientY - drag.current.y) * 1080) / rect.height,
          });
        }}
        onPointerUp={() => {
          drag.current = null;
        }}
        onPointerCancel={() => {
          drag.current = null;
        }}
        onContextMenu={(event) => event.preventDefault()}
      >
        <defs>
          <filter
            id="border-roughen"
            x="-14%"
            y="-14%"
            width="128%"
            height="128%"
          >
            <feTurbulence
              type="fractalNoise"
              baseFrequency="0.052 0.068"
              numOctaves="3"
              seed="38"
              result="noise"
            />
            <feDisplacementMap
              in="SourceGraphic"
              in2="noise"
              scale="15"
              xChannelSelector="R"
              yChannelSelector="G"
              result="roughLine"
            />
            <feDropShadow
              in="roughLine"
              dx="0"
              dy="1"
              stdDeviation="1"
              floodColor="#ecd6a8"
              floodOpacity=".48"
            />
          </filter>
          <pattern
            id="siege-hatch"
            width="11"
            height="11"
            patternUnits="userSpaceOnUse"
            patternTransform="rotate(34)"
          >
            <line
              x1="0"
              y1="0"
              x2="0"
              y2="11"
              stroke="#9A4037"
              strokeWidth="2.5"
              opacity=".7"
            />
          </pattern>
          {commanderyBlocks.map((block) => (
            <clipPath
              id={`commandery-highlight-${block.city}`}
              key={block.city}
            >
              <path d={block.d} />
            </clipPath>
          ))}
          {cityBlocks.map((block) => (
            <clipPath id={cityClipId(block.city.id)} key={block.city.id}>
              <path d={block.d} />
            </clipPath>
          ))}
        </defs>
        <g
          className="map-zoom-frame"
          transform={`translate(${960 + pan.x} ${540 + pan.y}) scale(${zoom}) translate(-960 -540)`}
        >
          <image
            href="/底图_expanded-v2.png?v=20260727-seamless-map"
            x="-320"
            y="-180"
            width="2560"
            height="1440"
            preserveAspectRatio="none"
          />
          {mapLayer === "province" && (
            <g className="province-blocks annotated-province-layer">
              {provinceBlocks.map((block) => (
                <g
                  key={block.province}
                  className={`province-block annotated-province-block ${block.province === selectedProvince ? "selected" : ""}`}
                  onPointerDown={(event) => event.stopPropagation()}
                  onClick={(event) => {
                    event.stopPropagation();
                    setSelectedProvince(block.province);
                    setSelectedCommandery(null);
                    setSelectedCity(null);
                    const node = block.nodes[0];
                    if (node) openNodeInfo(node.id, "province", block.province);
                  }}
                  onMouseMove={(event) =>
                    setTooltip({
                      x: event.clientX,
                      y: event.clientY,
                      text: `${block.province} · ${powerLabel(block.controller)}`,
                    })
                  }
                  onMouseLeave={() => setTooltip(null)}
                  role="button"
                  tabIndex={0}
                  aria-label={`${block.province}，${powerLabel(block.controller)}据有`}
                >
                  <path className="province-hit-area" d={block.d} />
                  <path className="province-outline" d={block.d} />
                  {showProvinceLabels && (
                    <text
                      className="province-label"
                      x={block.labelX}
                      y={block.labelY}
                    >
                      {block.province}
                    </text>
                  )}
                </g>
              ))}
            </g>
          )}
          {mapLayer === "commandery" && (
            <g className="commandery-blocks annotated-commandery-layer">
              <path
                className="commandery-shared-boundaries"
                d={sharedCommanderyBoundaryPath}
                aria-hidden="true"
              />
              {commanderyBlocks.map((block) => {
                const node = block.node;
                return (
                  <g
                    key={block.city}
                    className={`commandery-block annotated-commandery-block ${block.city === selectedCommandery ? "selected" : ""}`}
                    onPointerDown={(event) => event.stopPropagation()}
                    onClick={(event) => {
                      event.stopPropagation();
                      setSelectedCommandery(block.city);
                      setSelectedProvince(null);
                      setSelectedCity(null);
                      if (node)
                        openNodeInfo(
                          node.id,
                          "commandery",
                          node.commandery_id || node.id,
                        );
                    }}
                    onMouseMove={(event) =>
                      setTooltip({
                        x: event.clientX,
                        y: event.clientY,
                        text: `${block.commanderyName} · ${block.province}`,
                      })
                    }
                    onMouseLeave={() => setTooltip(null)}
                    role="button"
                    tabIndex={0}
                    aria-label={`${block.commanderyName}，${block.province}`}
                  >
                    <path className="commandery-hit-area" d={block.d} />
                    <path
                      className="commandery-boundary"
                      d={sharedCommanderyBoundaryPath}
                      clipPath={`url(#commandery-highlight-${block.city})`}
                    />
                    {showCommanderyLabels && (
                      <text
                        className="commandery-label"
                        x={block.labelX}
                        y={block.labelY}
                      >
                        {block.commanderyName}
                      </text>
                    )}
                  </g>
                );
              })}
            </g>
          )}
          {(mapLayer === "city" || mapLayer === "influence") && (
            <g
              className={`city-territories ${mapLayer === "influence" ? "city-influence-layer" : "city-node-layer"}`}
            >
              <path
                className="city-commandery-boundaries"
                d={sharedCommanderyBoundaryPath}
                aria-hidden="true"
              />
              <g
                className="historical-town-reference"
                aria-label="历史城镇地理参照"
              >
                {historicalTownBlocks.map((town) => (
                  <g
                    key={town.city}
                    transform={`translate(${town.cx} ${town.cy})`}
                    aria-hidden="true"
                  >
                    <circle className="historical-town-reference-dot" r="2.8" />
                    <text
                      className="historical-town-reference-label"
                      x="5"
                      y="-4"
                    >
                      {town.townName}
                    </text>
                  </g>
                ))}
              </g>
              {cityBlocks.map((block) => {
                const city = block.city;
                const armies = cityArmies(city.id, city.commandery_id);
                return (
                  <g
                    key={city.id}
                    className={`city-node territory-city-node ${city.is_commandery_capital ? "capital-town" : ""} ${block.hasHistoricalAnchor ? "" : "unanchored-city"} ${city.id === selectedCity ? "selected" : ""}`}
                    onPointerDown={(event) => event.stopPropagation()}
                    onClick={(event) => {
                      event.stopPropagation();
                      setSelectedCity(city.id);
                      setSelectedProvince(null);
                      setSelectedCommandery(null);
                      openNodeInfo(city.commandery_id, "city", city.id);
                    }}
                    onMouseMove={(event) =>
                      setTooltip({
                        x: event.clientX,
                        y: event.clientY,
                        text: `${city.name} · ${city.strategic_role} · ${armies.length}支军队`,
                      })
                    }
                    onMouseLeave={() => setTooltip(null)}
                    role="button"
                    tabIndex={0}
                    aria-label={`${city.name}，${city.strategic_role}`}
                  >
                    <path
                      className={`city-territory ${city.siege_status === "围城中" ? "under-siege" : ""}`}
                      d={block.d}
                      fill={
                        city.siege_status === "围城中"
                          ? "url(#siege-hatch)"
                          : POWER_COLORS[city.controller] || "#655c4b"
                      }
                    />
                    <path
                      className="city-territory-boundary"
                      d={block.boundaryD}
                    />
                    <path
                      className="city-highlight-boundary"
                      d={cityBoundaryNetworkPath}
                      clipPath={`url(#${cityClipId(city.id)})`}
                    />
                    <circle
                      className="city-node-hit-area"
                      cx={block.cx}
                      cy={block.cy}
                      r="18"
                    />
                    <g
                      className="city-model"
                      transform={`translate(${block.cx} ${block.cy})`}
                    >
                      <image
                        className="city-sprite"
                        href={`/assets/ui/cities/${city.strategic_role.includes("关隘") ? "fort" : city.strategic_role.includes("港") ? "port" : city.is_commandery_capital ? "capital" : "town"}.png`}
                        x="-18"
                        y="-25"
                        width="36"
                        height="29"
                        preserveAspectRatio="xMidYMax meet"
                      />
                      {city.is_commandery_capital && (
                        <rect
                          className="city-sprite-plaque-cover"
                          x="-5.3"
                          y="-6.8"
                          width="10.6"
                          height="2.9"
                          rx=".5"
                        />
                      )}
                      <path
                        className="city-banner"
                        d="M 10 -12 L 10 -24 L 20 -20 L 10 -17 Z"
                        fill={POWER_COLORS[city.controller] || "#655c4b"}
                      />
                    </g>
                    {city.is_commandery_capital && (
                      <text
                        className="capital-star"
                        x={block.cx}
                        y={block.cy - 20}
                      >
                        ★
                      </text>
                    )}
                    {armies.length > 0 && (
                      <g
                        className="army-marker city-army-marker"
                        transform={`translate(${block.cx + 13} ${block.cy - 21})`}
                      >
                        <rect width="16" height="12" rx="1" />
                        <text x="8" y="9" fontSize="8">
                          {armies.length}
                        </text>
                      </g>
                    )}
                    {showCityLabels &&
                      (mapLayer === "city" || city.is_commandery_capital) && (
                        <text
                          className="city-label"
                          x={block.labelX}
                          y={block.labelY + 16}
                        >
                          {city.name}
                        </text>
                      )}
                  </g>
                );
              })}
            </g>
          )}
        </g>
      </svg>
      {tooltip && (
        <div
          className="map-province-tooltip"
          style={{ left: tooltip.x, top: tooltip.y }}
        >
          {tooltip.text}
        </div>
      )}
      <div className="map-layer-toggle" aria-label="地图图层切换">
        <button
          type="button"
          className={mapLayer === "province" ? "active" : ""}
          onClick={() => switchLayer("province")}
        >
          <MapIcon />州
        </button>
        <button
          type="button"
          className={mapLayer === "commandery" ? "active" : ""}
          onClick={() => switchLayer("commandery")}
        >
          <Scroll />郡
        </button>
        <button
          type="button"
          className={mapLayer === "city" ? "active" : ""}
          onClick={() => switchLayer("city")}
        >
          <Building />
          城池
        </button>
        <button
          type="button"
          className={mapLayer === "influence" ? "active" : ""}
          onClick={() => switchLayer("influence")}
        >
          <Flag />
          势力
        </button>
      </div>
      <div className="map-legend">
        <span>
          <i className="ordinary" />
          {mapLayer === "province"
            ? "州界"
            : mapLayer === "commandery"
              ? "郡界"
              : mapLayer === "influence"
                ? "城池势力范围"
                : "城池辖区"}
        </span>
        <span>
          <i className="city-range" />
          围城朱砂斜纹
        </span>
      </div>
      {infoTarget && (
        <MapInfoDrawer
          state={state}
          scope={infoTarget.scope}
          entityId={infoTarget.entityId}
          onClose={() => setInfoTarget(null)}
        />
      )}
    </section>
  );
}
