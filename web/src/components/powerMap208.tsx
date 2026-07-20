import React from "react";
import { LocateFixed, Map as MapIcon, Minus, Plus } from "lucide-react";

import { clampMapZoom, PROVINCE_BLOCKS } from "../mapLogic";

// 208 年 8 月赤壁战前静态势力配色：按规范固定六色，不随战局变化。
// path 复用 mapLogic 的 PROVINCE_BLOCKS 共享顶点无缝轮廓。
const POWER_208_FILLS: Record<string, string> = {
  凉州: "#7b5bb0", 并州: "#234b85", 幽州: "#234b85", 冀州: "#234b85",
  青州: "#234b85", 司隶: "#234b85", 兖州: "#234b85", 徐州: "#234b85",
  豫州: "#234b85", 荆州: "#349e70", 扬州: "#c42c2c", 益州: "#c8983e",
  交州: "#32a8a8",
};

const POWER_LABELS_208: Record<string, string> = {
  凉州: "马腾、韩遂", 荆州: "刘表", 扬州: "孙权", 益州: "刘璋", 交州: "士燮",
};

const LEGEND_208 = [
  { label: "曹操", fill: "#234b85" },
  { label: "马腾、韩遂", fill: "#7b5bb0" },
  { label: "刘表", fill: "#349e70" },
  { label: "孙权", fill: "#c42c2c" },
  { label: "刘璋", fill: "#c8983e" },
  { label: "士燮", fill: "#32a8a8" },
];

export function PowerMap208() {
  const [zoom, setZoom] = React.useState(1);
  const [pan, setPan] = React.useState({ x: 0, y: 0 });
  const [tooltip, setTooltip] = React.useState<{ x: number; y: number; province: string; power: string } | null>(null);
  const drag = React.useRef<{ pointerId: number; x: number; y: number; panX: number; panY: number } | null>(null);

  const resetView = () => { setZoom(1); setPan({ x: 0, y: 0 }); };
  const changeZoom = (delta: number) => setZoom((value) => clampMapZoom(value + delta));

  return <section className="power-map-208" aria-label="公元208年8月赤壁战前十三州势力分布图">
    <div className="power-map-208-caption"><MapIcon /><span>公元208年8月 赤壁战前十三州势力分布图<small>拖动舆图 · 滚轮缩放 · 悬停州块查看割据势力</small></span></div>
    <div className="power-map-208-controls" aria-label="地图缩放控制">
      <button aria-label="缩小地图" onClick={() => changeZoom(-0.2)}><Minus /></button>
      <output>{Math.round(zoom * 100)}%</output>
      <button aria-label="放大地图" onClick={() => changeZoom(0.2)}><Plus /></button>
      <button aria-label="重置地图视角" onClick={resetView}><LocateFixed /></button>
    </div>
    <svg
      viewBox="0 0 1920 1080"
      role="img"
      aria-label="三国十三州208年势力分块地图"
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
    >
      <g transform={`translate(${pan.x} ${pan.y}) scale(${zoom})`}>
        <image href="/底图.jpg" x="0" y="0" width="1920" height="1080" preserveAspectRatio="none" opacity=".82" />
        <g className="province-blocks-208">
          {Object.entries(PROVINCE_BLOCKS).map(([province, block]) => {
            const power208 = POWER_LABELS_208[province] || "曹操";
            return <g
              key={province}
              className="province-block-208"
              tabIndex={0}
              role="img"
              aria-label={`${province} · 208年割据势力：${power208}`}
              onMouseMove={(event) => setTooltip({ x: event.clientX, y: event.clientY, province, power: power208 })}
              onMouseLeave={() => setTooltip(null)}
            >
              <path className="province-fill-208" d={block.d} fill={POWER_208_FILLS[province] || "#234b85"} />
              <text className="province-label-208" x={block.labelX} y={block.labelY}>{province}</text>
            </g>;
          })}
        </g>
      </g>
    </svg>
    {tooltip && <div className="power-map-208-tooltip" style={{ left: tooltip.x, top: tooltip.y }}>
      {tooltip.province} · 208年割据势力：{tooltip.power}
    </div>}
    <div className="power-map-208-legend">
      {LEGEND_208.map((item) => <span key={item.label}><i style={{ background: item.fill }} />{item.label}</span>)}
    </div>
  </section>;
}
