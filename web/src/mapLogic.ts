import type { Army, StrategicNode } from "./types";
import { ANNOTATED_CITY_BLOCKS, ANNOTATED_PROVINCE_BLOCKS } from "./annotatedMapData.ts";

export type MapLayer = "province" | "commandery" | "city";

export const MAP_LAYERS = ["province", "commandery", "city"] as const satisfies readonly MapLayer[];
export const DEFAULT_MAP_LAYER: MapLayer = "province";
export type StaticMapLabelPolicy = {
  provinceLabels: "base-map-only" | "overlay";
  commanderyLabels: "base-map-only" | "overlay";
  cityLabels: "base-map-only" | "overlay";
};

export const STATIC_MAP_LABEL_POLICY: StaticMapLabelPolicy = {
  provinceLabels: "overlay",
  commanderyLabels: "overlay",
  cityLabels: "overlay",
};

const ANNOTATED_CITY_ALIASES: Record<string, string> = {
  "成都/蜀郡": "成都",
  "江陵/南郡": "江陵",
  "合肥/庐江": "合肥",
  "江州/巴郡": "江州",
  "东郡/濮阳": "濮阳",
  "许昌/颍川": "许昌",
  "弘农/潼关": "弘农",
  "常山/中山": "常山",
  渤海: "渤海",
  上党: "上党",
  陇西: "陇西",
  汝南: "汝南",
  江夏: "江夏",
  "长沙/荆南": "长沙",
  "永安/白帝": "永安",
  邺: "邺城",
  蓟: "蓟县",
  辽东: "襄平",
  太原: "晋阳",
  武威: "姑藏",
  汉中: "南郑",
  南海: "番禺",
  建业: "秣陵",
  豫章: "柴桑",
};

const COMMANDERY_NAME_OVERRIDES: Record<string, string> = {
  蓟县: "广阳郡",
  九原: "五原郡",
  南皮: "渤海郡",
  邺城: "魏郡",
  临淄: "齐国",
  长安: "京兆尹",
  洛阳: "河南尹",
  濮阳: "东郡",
  下邳: "下邳国",
  彭城: "彭城国",
  宛城: "南阳郡",
  襄阳: "襄阳郡",
  秣陵: "丹阳郡",
  柴桑: "豫章郡",
  永安: "巴东郡",
  夜郎: "牂牁郡",
  且兰: "牂牁郡",
};

const HISTORICAL_CITY_NODE_ALIASES: Record<string, string> = {
  武陵: "jingnan",
  零陵: "jingnan",
  桂阳: "jingnan",
  豫章: "chaisang",
  丹阳: "jianye",
  合浦: "nanhai",
  苍梧: "nanhai",
  郁林: "nanhai",
};

function commanderyNameFor(city: string, label: string) {
  const override = COMMANDERY_NAME_OVERRIDES[city];
  if (override) return override;
  if (/[郡国尹]$/.test(label)) return label;
  return `${label}郡`;
}

export type ReachableTarget = {
  nodeId: string;
  province: string;
  scope: "同州" | "邻州";
};

export type ProvinceBlock = {
  province: string;
  d: string;
  cx: number;
  cy: number;
  labelX: number;
  labelY: number;
  controller: string;
  nodes: StrategicNode[];
};

export type CityInteractionBlock = {
  city: string;
  label: string;
  commanderyName: string;
  d: string;
  cx: number;
  cy: number;
  labelX: number;
  labelY: number;
  province: string;
  node: StrategicNode;
};

export type CityBoundaryBlock = {
  city: string;
  label: string;
  commanderyName: string;
  d: string;
  cx: number;
  cy: number;
  labelX: number;
  labelY: number;
  province: string;
  node?: StrategicNode;
};

export type CommanderyBoundaryBlock = CityBoundaryBlock;

export type TownBlock = CityBoundaryBlock & {
  townName: string;
  townKind: "game-city" | "historical-town";
};

function pathToPoints(path: string) {
  return (path.match(/[ML] -?\d+ -?\d+/g) || []).map((item) => {
    const [, x, y] = item.split(" ");
    return { x: Number(x), y: Number(y) };
  });
}

function normalizedSegment(a: { x: number; y: number }, b: { x: number; y: number }) {
  const left = a.x < b.x || (a.x === b.x && a.y <= b.y) ? a : b;
  const right = left === a ? b : a;
  return `${left.x},${left.y}|${right.x},${right.y}`;
}

function pointOnBoundary(point: { x: number; y: number }, polygon: Array<{ x: number; y: number }>, tolerance = 1.5) {
  return polygon.some((a, index) => {
    const b = polygon[(index + 1) % polygon.length];
    const edgeLength = Math.hypot(b.x - a.x, b.y - a.y) || 1;
    const cross = ((point.x - a.x) * (b.y - a.y) - (point.y - a.y) * (b.x - a.x)) / edgeLength;
    const dot = (point.x - a.x) * (point.x - b.x) + (point.y - a.y) * (point.y - b.y);
    return Math.abs(cross) <= tolerance && dot <= tolerance;
  });
}

function segmentHash(a: { x: number; y: number }, b: { x: number; y: number }) {
  const text = normalizedSegment(a, b);
  let hash = 2166136261;
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function curvedSegmentPath(a: { x: number; y: number }, b: { x: number; y: number }, shouldCurve: boolean) {
  const length = Math.hypot(b.x - a.x, b.y - a.y);
  if (!shouldCurve || length < 8) return `M ${a.x} ${a.y} L ${b.x} ${b.y}`;
  const direction = segmentHash(a, b) % 2 === 0 ? 1 : -1;
  const amplitude = Math.min(25, Math.max(9, length / 5.5)) * direction;
  const nx = -(b.y - a.y) / length;
  const ny = (b.x - a.x) / length;
  const cx = Math.round((a.x + b.x) / 2 + nx * amplitude);
  const cy = Math.round((a.y + b.y) / 2 + ny * amplitude);
  return `M ${a.x} ${a.y} Q ${cx} ${cy} ${b.x} ${b.y}`;
}

export function getSharedCityBoundaryPath(blocks: Array<Pick<CityBoundaryBlock, "d" | "province">>) {
  const provinceBoundaryPoints = new Map<string, Array<{ x: number; y: number }>>();
  const segments = new Map<string, { a: { x: number; y: number }; b: { x: number; y: number }; curve: boolean }>();
  for (const block of blocks) {
    const points = pathToPoints(block.d);
    const provincePoints = provinceBoundaryPoints.get(block.province) || pathToPoints(PROVINCE_BLOCKS[block.province]?.d || "");
    if (!provinceBoundaryPoints.has(block.province)) provinceBoundaryPoints.set(block.province, provincePoints);
    for (let i = 0; i < points.length; i += 1) {
      const current = points[i];
      const next = points[(i + 1) % points.length];
      const key = normalizedSegment(current, next);
      const midpoint = { x: (current.x + next.x) / 2, y: (current.y + next.y) / 2 };
      const isProvinceEdge = provincePoints.length > 0 && pointOnBoundary(midpoint, provincePoints, 2.5);
      const existing = segments.get(key);
      if (existing) {
        existing.curve = existing.curve || !isProvinceEdge;
      } else {
        segments.set(key, { a: current, b: next, curve: !isProvinceEdge });
      }
    }
  }
  return [...segments.values()].map((segment) => curvedSegmentPath(segment.a, segment.b, segment.curve)).join(" ");
}

export function clampMapZoom(value: number) {
  return Math.min(2.5, Math.max(0.75, Math.round(value * 100) / 100));
}

// 十三州疆域 path：0~1000 SVG 像素坐标。
// 边界参考东汉州界依山河走势划分（黄河/太行/秦岭/长江/淮河/燕山/南岭等），
// 形状仿古不规则。相邻两州的公共边界共用相同的顶点序列（方向相反逐点一致），
// 保证 13 块互不重叠、无缝接壤；全部 35 个郡节点（百分比 ×10）均落在
// 所属州块内部（几何合同见 tests/mapLogic.test.ts）。
export const PROVINCE_BLOCKS: Record<string, Pick<ProvinceBlock, "d" | "cx" | "cy" | "labelX" | "labelY">> = ANNOTATED_PROVINCE_BLOCKS;

export const LEGACY_PROVINCE_BLOCKS: Record<string, Pick<ProvinceBlock, "d" | "cx" | "cy" | "labelX" | "labelY">> = {
  凉州: { d: "M 67 56 L 227 32 L 413 59 L 618 41 L 726 80 L 695 162 L 733 240 L 707 305 L 637 356 L 553 423 L 503 505 L 376 510 L 242 471 L 165 369 L 104 266 L 111 160 Z", cx: 384, cy: 270, labelX: 384, labelY: 270 },
  并州: { d: "M 726 80 L 868 99 L 1014 73 L 1075 82 L 1025 153 L 1060 220 L 1048 283 L 1029 339 L 945 380 L 837 356 L 707 305 L 733 240 L 695 162 Z", cx: 895, cy: 212, labelX: 895, labelY: 212 },
  幽州: { d: "M 1356 41 L 1501 24 L 1667 37 L 1793 63 L 1855 117 L 1820 181 L 1734 224 L 1644 212 L 1540 205 L 1394 231 L 1340 168 L 1298 110 Z", cx: 1586, cy: 130, labelX: 1586, labelY: 130 },
  冀州: { d: "M 1075 82 L 1194 52 L 1290 65 L 1356 41 L 1298 110 L 1340 168 L 1394 231 L 1332 308 L 1252 395 L 1133 363 L 1029 339 L 1048 283 L 1060 220 L 1025 153 Z", cx: 1179, cy: 231, labelX: 1179, labelY: 231 },
  青州: { d: "M 1394 231 L 1540 205 L 1644 212 L 1734 224 L 1678 257 L 1705 315 L 1644 359 L 1536 406 L 1402 434 L 1252 395 L 1332 308 Z", cx: 1517, cy: 324, labelX: 1517, labelY: 324 },
  司隶: { d: "M 707 305 L 837 356 L 945 380 L 1029 339 L 983 397 L 1006 445 L 960 484 L 902 516 L 806 542 L 676 531 L 503 505 L 553 423 L 637 356 Z", cx: 764, cy: 438, labelX: 764, labelY: 438 },
  兖州: { d: "M 1029 339 L 1133 363 L 1252 395 L 1229 462 L 1206 516 L 1094 488 L 1006 445 L 983 397 Z", cx: 1114, cy: 432, labelX: 1114, labelY: 432 },
  徐州: { d: "M 1252 395 L 1402 434 L 1536 406 L 1644 359 L 1624 423 L 1651 488 L 1617 549 L 1425 592 L 1229 564 L 1194 542 L 1206 516 L 1229 462 Z", cx: 1425, cy: 499, labelX: 1425, labelY: 499 },
  豫州: { d: "M 1006 445 L 1094 488 L 1206 516 L 1194 542 L 1229 564 L 1221 600 L 1233 635 L 1106 631 L 1002 583 L 902 516 L 960 484 Z", cx: 1075, cy: 557, labelX: 1075, labelY: 557 },
  荆州: { d: "M 902 516 L 1002 583 L 1106 631 L 1233 635 L 1260 700 L 1206 773 L 1233 853 L 1213 909 L 1068 927 L 906 942 L 749 948 L 691 896 L 645 838 L 726 801 L 803 756 L 822 678 L 868 592 Z", cx: 983, cy: 756, labelX: 983, labelY: 756 },
  扬州: { d: "M 1229 564 L 1425 592 L 1617 549 L 1740 607 L 1832 698 L 1797 780 L 1715 837 L 1540 862 L 1379 888 L 1213 909 L 1233 853 L 1206 773 L 1260 700 L 1233 635 L 1221 600 Z", cx: 1501, cy: 728, labelX: 1501, labelY: 728 },
  益州: { d: "M 503 505 L 676 531 L 806 542 L 902 516 L 868 592 L 822 678 L 803 756 L 726 801 L 645 838 L 461 812 L 284 771 L 227 661 L 261 542 L 242 471 L 376 510 Z", cx: 515, cy: 661, labelX: 515, labelY: 661 },
  交州: { d: "M 1213 909 L 1379 888 L 1540 862 L 1715 837 L 1782 899 L 1732 976 L 1597 1024 L 1348 1045 L 1068 1054 L 849 1031 L 707 989 L 749 948 L 906 942 L 1068 927 Z", cx: 1283, cy: 983, labelX: 1283, labelY: 983 },
};

const PROVINCE_ADJACENCY: Record<string, string[]> = {
  凉州: ["司隶", "益州"],
  并州: ["司隶", "冀州"],
  幽州: ["冀州", "青州"],
  冀州: ["并州", "幽州", "青州", "兖州"],
  青州: ["幽州", "冀州", "徐州"],
  司隶: ["凉州", "并州", "兖州", "豫州", "益州"],
  兖州: ["冀州", "司隶", "豫州", "徐州"],
  徐州: ["青州", "兖州", "扬州", "豫州"],
  豫州: ["司隶", "兖州", "徐州", "荆州", "扬州"],
  荆州: ["豫州", "扬州", "益州", "交州"],
  扬州: ["徐州", "豫州", "荆州", "交州"],
  益州: ["凉州", "司隶", "荆州"],
  交州: ["荆州", "扬州"],
};

export function getReachableTargets(
  nodes: Array<Pick<StrategicNode, "id" | "province">>,
  sourceNode: string,
): ReachableTarget[] {
  const source = nodes.find((node) => node.id === sourceNode);
  if (!source) return [];
  const allowed = new Set([source.province, ...(PROVINCE_ADJACENCY[source.province] || [])]);
  return nodes
    .filter((node) => node.id !== sourceNode && allowed.has(node.province))
    .map((node) => ({
      nodeId: node.id,
      province: node.province,
      scope: node.province === source.province ? "同州" : "邻州",
    }));
}

export function routeWarning(kind: string, note = "") {
  if (kind === "关隘") return `${note || "关隘"}尚未攻克时不可穿越，须先下围城军令。`;
  if (kind === "江河" || kind === "山道") {
    return `${kind}行军令粮秣立即消耗 20，并承受三回合战力与机动惩罚。`;
  }
  return "驿道通行，一条边耗时一回合。";
}

export function getNodeArmies<T extends Pick<Army, "station_node">>(armies: T[], nodeId: string) {
  return armies.filter((army) => army.station_node === nodeId);
}

export type ProvinceWash = {
  province: string;
  cx: number;
  cy: number;
  rx: number;
  ry: number;
  nodeCount: number;
};

export function getProvinceWashes(nodes: Array<Pick<StrategicNode, "province" | "x" | "y">>): ProvinceWash[] {
  const grouped = new Map<string, Array<Pick<StrategicNode, "x" | "y">>>();
  nodes.forEach((node) => {
    const current = grouped.get(node.province) || [];
    current.push(node);
    grouped.set(node.province, current);
  });
  return Array.from(grouped.entries()).map(([province, provinceNodes]) => {
    const xs = provinceNodes.map((node) => node.x * 19.2);
    const ys = provinceNodes.map((node) => node.y * 10.8);
    const cx = Math.round(xs.reduce((sum, value) => sum + value, 0) / xs.length);
    const cy = Math.round(ys.reduce((sum, value) => sum + value, 0) / ys.length);
    return {
      province,
      cx,
      cy,
      rx: Math.max(70, Math.round((Math.max(...xs) - Math.min(...xs)) / 2 + 76)),
      ry: Math.max(54, Math.round((Math.max(...ys) - Math.min(...ys)) / 2 + 58)),
      nodeCount: provinceNodes.length,
    };
  });
}

// 州主导势力：州内控制郡数最多者上色；平票比总人口，再平按节点顺序取先出现者。
export function getProvinceController(nodes: Array<Pick<StrategicNode, "controller" | "population">>): string {
  const tally = new Map<string, { count: number; population: number; order: number }>();
  nodes.forEach((node, index) => {
    const key = node.controller || "";
    const current = tally.get(key) || { count: 0, population: 0, order: index };
    tally.set(key, { count: current.count + 1, population: current.population + (node.population || 0), order: current.order });
  });
  return Array.from(tally.entries()).sort(([, a], [, b]) =>
    b.count - a.count || b.population - a.population || a.order - b.order,
  )[0]?.[0] || "";
}

export function getProvinceBlocks(nodes: StrategicNode[]): ProvinceBlock[] {
  const grouped = new Map<string, StrategicNode[]>();
  nodes.forEach((node) => grouped.set(node.province, [...(grouped.get(node.province) || []), node]));
  return Array.from(grouped.entries()).map(([province, provinceNodes]) => {
    const controller = getProvinceController(provinceNodes);
    const block = PROVINCE_BLOCKS[province];
    if (block) return { province, nodes: provinceNodes, controller, ...block };
    const wash = getProvinceWashes(provinceNodes)[0];
    return {
      province,
      nodes: provinceNodes,
      controller,
      d: `M${wash.cx - wash.rx} ${wash.cy} Q${wash.cx} ${wash.cy - wash.ry} ${wash.cx + wash.rx} ${wash.cy} Q${wash.cx} ${wash.cy + wash.ry} ${wash.cx - wash.rx} ${wash.cy} Z`,
      cx: wash.cx,
      cy: wash.cy,
      labelX: wash.cx,
      labelY: wash.cy,
    };
  });
}

export function resolveAnnotatedCityName(name: string): string | null {
  if (name in ANNOTATED_CITY_BLOCKS) return name;
  for (const part of name.split(/[/:／、]/).map((item) => item.trim()).filter(Boolean)) {
    if (part in ANNOTATED_CITY_BLOCKS) return part;
  }
  const alias = ANNOTATED_CITY_ALIASES[name];
  return alias && alias in ANNOTATED_CITY_BLOCKS ? alias : null;
}

export function getCityInteractionBlocks(nodes: StrategicNode[]): CityInteractionBlock[] {
  return nodes.flatMap((node) => {
    const city = resolveAnnotatedCityName(node.name);
    if (!city) return [];
    const block = ANNOTATED_CITY_BLOCKS[city as keyof typeof ANNOTATED_CITY_BLOCKS];
    return [{ city, label: block.label, commanderyName: commanderyNameFor(city, block.label), node, d: block.d, cx: block.cx, cy: block.cy, labelX: block.labelX, labelY: block.labelY, province: block.province }];
  });
}

export function getCityBoundaryBlocks(nodes: StrategicNode[]): CityBoundaryBlock[] {
  return getCityInteractionBlocks(nodes);
}

function getNodeByAnnotatedCity(nodes: StrategicNode[]) {
  const nodeByAnnotatedCity = new Map<string, StrategicNode>();
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  nodes.forEach((node) => {
    const city = resolveAnnotatedCityName(node.name);
    if (city && !nodeByAnnotatedCity.has(city)) nodeByAnnotatedCity.set(city, node);
  });
  Object.entries(HISTORICAL_CITY_NODE_ALIASES).forEach(([city, nodeId]) => {
    const node = nodeById.get(nodeId);
    if (node && !nodeByAnnotatedCity.has(city)) nodeByAnnotatedCity.set(city, node);
  });
  return nodeByAnnotatedCity;
}

export function getTownBlocks(nodes: StrategicNode[]): TownBlock[] {
  const nodeByAnnotatedCity = getNodeByAnnotatedCity(nodes);

  return Object.entries(ANNOTATED_CITY_BLOCKS).map(([city, block]) => {
    const node = nodeByAnnotatedCity.get(city);
    return {
      city,
      townName: city,
      townKind: node ? "game-city" as const : "historical-town" as const,
      label: block.label,
      commanderyName: commanderyNameFor(city, block.label),
      d: block.d,
      cx: block.cx,
      cy: block.cy,
      labelX: block.labelX,
      labelY: block.labelY,
      province: block.province,
      node,
    };
  });
}

export function getCommanderyBoundaryBlocks(nodes: StrategicNode[]): CommanderyBoundaryBlock[] {
  const nodeByAnnotatedCity = getNodeByAnnotatedCity(nodes);

  return Object.entries(ANNOTATED_CITY_BLOCKS).map(([city, block]) => ({
    city,
    label: block.label,
    commanderyName: commanderyNameFor(city, block.label),
    d: block.d,
    cx: block.cx,
    cy: block.cy,
    labelX: block.labelX,
    labelY: block.labelY,
    province: block.province,
    node: nodeByAnnotatedCity.get(city),
  }));
}
