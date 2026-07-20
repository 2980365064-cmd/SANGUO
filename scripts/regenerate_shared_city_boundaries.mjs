import fs from "node:fs";
import vm from "node:vm";
import polygonClipping from "../web/node_modules/polygon-clipping/dist/polygon-clipping.esm.js";

const root = new URL("../", import.meta.url);
const dataPath = new URL("web/public/annotation_data.json", root);
const publicSvgPath = new URL("web/public/标注数据_SVG.js", root);
const typedDataPath = new URL("web/src/annotatedMapData.ts", root);
const utilsPath = new URL("web/public/annotation_path_utils.js", root);

const data = JSON.parse(fs.readFileSync(dataPath, "utf8"));
const sandbox = { window: {} };
vm.runInNewContext(fs.readFileSync(utilsPath, "utf8"), sandbox);
const { pointsToSvgPath, provincePointsToSvgPath } = sandbox.window.annotationPathUtils;

const PROVINCES = ["凉州", "并州", "幽州", "冀州", "青州", "司隶", "兖州", "徐州", "豫州", "荆州", "扬州", "益州", "交州"];

const CITY_PROVINCE = {
  "姑藏": "凉州", "张掖": "凉州", "天水": "凉州", "陇西": "凉州",
  "晋阳": "并州", "九原": "并州", "上党": "并州",
  "襄平": "幽州", "蓟县": "幽州", "涿郡": "幽州", "右北平": "幽州",
  "南皮": "冀州", "邺城": "冀州", "常山": "冀州", "渤海": "冀州",
  "临淄": "青州", "北海": "青州",
  "长安": "司隶", "洛阳": "司隶", "弘农": "司隶",
  "陈留": "兖州", "濮阳": "兖州", "泰山": "兖州",
  "下邳": "徐州", "彭城": "徐州", "广陵": "徐州",
  "谯县": "豫州", "许昌": "豫州", "汝南": "豫州",
  "宛城": "荆州", "襄阳": "荆州", "江陵": "荆州", "江夏": "荆州", "长沙": "荆州", "武陵": "荆州", "零陵": "荆州", "桂阳": "荆州",
  "合肥": "扬州", "秣陵": "扬州", "吴郡": "扬州", "会稽": "扬州", "柴桑": "扬州", "豫章": "扬州", "丹阳": "扬州",
  "成都": "益州", "梓潼": "益州", "江州": "益州", "南郑": "益州", "上庸": "益州", "永安": "益州", "夜郎": "益州", "且兰": "益州",
  "番禺": "交州", "交趾": "交州", "合浦": "交州", "苍梧": "交州", "郁林": "交州",
};

const HISTORICAL_SEEDS = {
  "成都": { x: 636, y: 736 }, "梓潼": { x: 748, y: 607 }, "南郑": { x: 868, y: 579 }, "上庸": { x: 963, y: 617 }, "永安": { x: 930, y: 680 },
  "江州": { x: 855, y: 722 }, "夜郎": { x: 702, y: 876 }, "且兰": { x: 798, y: 806 },
  "张掖": { x: 496, y: 248 }, "姑藏": { x: 645, y: 356 }, "天水": { x: 812, y: 502 }, "陇西": { x: 710, y: 488 },
  "晋阳": { x: 1076, y: 365 }, "九原": { x: 933, y: 338 }, "上党": { x: 1085, y: 430 },
  "蓟县": { x: 1310, y: 265 }, "涿郡": { x: 1250, y: 306 }, "右北平": { x: 1440, y: 235 }, "襄平": { x: 1510, y: 260 },
  "南皮": { x: 1273, y: 354 }, "邺城": { x: 1171, y: 387 }, "常山": { x: 1190, y: 330 }, "渤海": { x: 1305, y: 333 },
  "临淄": { x: 1352, y: 424 }, "北海": { x: 1448, y: 410 },
  "长安": { x: 925, y: 518 }, "洛阳": { x: 1074, y: 489 }, "弘农": { x: 1006, y: 522 },
  "陈留": { x: 1190, y: 497 }, "濮阳": { x: 1234, y: 462 }, "泰山": { x: 1250, y: 492 },
  "彭城": { x: 1320, y: 516 }, "下邳": { x: 1370, y: 552 }, "广陵": { x: 1425, y: 592 },
  "谯县": { x: 1258, y: 530 }, "许昌": { x: 1134, y: 564 }, "汝南": { x: 1190, y: 590 },
  "宛城": { x: 1072, y: 606 }, "襄阳": { x: 1126, y: 643 }, "江陵": { x: 1048, y: 738 }, "江夏": { x: 1178, y: 724 }, "长沙": { x: 1116, y: 846 },
  "武陵": { x: 1010, y: 838 }, "零陵": { x: 1100, y: 902 }, "桂阳": { x: 1166, y: 884 },
  "合肥": { x: 1277, y: 627 }, "秣陵": { x: 1390, y: 668 }, "吴郡": { x: 1440, y: 725 }, "会稽": { x: 1370, y: 820 },
  "柴桑": { x: 1228, y: 754 }, "豫章": { x: 1305, y: 800 }, "丹阳": { x: 1338, y: 696 },
  "番禺": { x: 1138, y: 930 }, "交趾": { x: 820, y: 930 }, "合浦": { x: 990, y: 958 }, "苍梧": { x: 1058, y: 900 }, "郁林": { x: 930, y: 904 },
};

const DISPLAY_LABELS = {
  "姑藏": "武威",
  "晋阳": "太原",
  "蓟县": "蓟",
  "襄平": "辽东",
  "谯县": "谯郡",
  "许昌": "颍川",
  "宛城": "南阳",
  "江陵": "南郡",
  "合肥": "庐江",
  "秣陵": "建业",
  "成都": "蜀郡",
  "南郑": "汉中",
  "江州": "巴郡",
  "番禺": "南海",
};

const REPARTITION_PROVINCES = PROVINCES;

function pathToPoints(path) {
  return (path.match(/[ML] -?\d+ -?\d+/g) || []).map((item) => {
    const [, x, y] = item.split(" ");
    return { x: Number(x), y: Number(y) };
  });
}

const provincePolygons = Object.fromEntries(PROVINCES.map((province) => [
  province,
  pathToPoints(provincePointsToSvgPath(data.provincePoints[province])),
]));

function orderedPointsToSvgPath(points) {
  const clean = dedupeConsecutive(points).map((point) => ({ x: Math.round(point.x), y: Math.round(point.y) }));
  if (clean.length < 3) return "";
  return `${clean.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`).join(" ")} Z`;
}

function clipByCloserToSeed(polygon, seed, other) {
  const a = 2 * (other.x - seed.x);
  const b = 2 * (other.y - seed.y);
  const c = other.x * other.x + other.y * other.y - seed.x * seed.x - seed.y * seed.y;
  return polygonClipping.intersection(polygon, halfPlaneMultiPolygon(a, b, c));
}

function halfPlaneMultiPolygon(a, b, c) {
  const rect = [
    { x: -1000, y: -1000 },
    { x: 3000, y: -1000 },
    { x: 3000, y: 3000 },
    { x: -1000, y: 3000 },
  ];
  const inside = (point) => a * point.x + b * point.y <= c + 1e-7;
  const intersect = (from, to) => {
    const fromValue = a * from.x + b * from.y - c;
    const toValue = a * to.x + b * to.y - c;
    const t = fromValue / (fromValue - toValue);
    return { x: from.x + (to.x - from.x) * t, y: from.y + (to.y - from.y) * t };
  };
  const output = [];
  for (let i = 0; i < rect.length; i += 1) {
    const current = rect[i];
    const next = rect[(i + 1) % rect.length];
    const currentInside = inside(current);
    const nextInside = inside(next);
    if (currentInside && nextInside) {
      output.push(next);
    } else if (currentInside && !nextInside) {
      output.push(intersect(current, next));
    } else if (!currentInside && nextInside) {
      output.push(intersect(current, next), next);
    }
  }
  return output.length >= 3 ? [[closeRing(output.map((point) => [point.x, point.y]))]] : [];
}

function pointsToMultiPolygon(points) {
  return [[closeRing(points.map((point) => [point.x, point.y]))]];
}

function closeRing(ring) {
  if (!ring.length) return ring;
  const first = ring[0];
  const last = ring[ring.length - 1];
  if (first[0] === last[0] && first[1] === last[1]) return ring;
  return [...ring, first];
}

function ringArea(ring) {
  let area = 0;
  for (let i = 0; i < ring.length - 1; i += 1) area += ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1];
  return Math.abs(area) / 2;
}

function pointInRing(seed, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 2; i < ring.length - 1; j = i++) {
    const a = { x: ring[i][0], y: ring[i][1] };
    const b = { x: ring[j][0], y: ring[j][1] };
    if ((a.y > seed.y) !== (b.y > seed.y) && seed.x < ((b.x - a.x) * (seed.y - a.y)) / (b.y - a.y) + a.x) inside = !inside;
  }
  return inside;
}

function chooseCellRing(multiPolygon, seed) {
  const rings = multiPolygon.flatMap((polygon) => polygon.slice(0, 1));
  const containing = rings.find((ring) => pointInRing(seed, ring));
  const best = containing || rings.sort((a, b) => ringArea(b) - ringArea(a))[0];
  return (best || []).slice(0, -1).map(([x, y]) => ({ x, y }));
}

function pointInPolygon(point, polygon, tolerance = 0) {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const a = polygon[i];
    const b = polygon[j];
    const edgeLength = Math.hypot(b.x - a.x, b.y - a.y) || 1;
    const cross = ((point.x - a.x) * (b.y - a.y) - (point.y - a.y) * (b.x - a.x)) / edgeLength;
    const dot = (point.x - a.x) * (point.x - b.x) + (point.y - a.y) * (point.y - b.y);
    if (Math.abs(cross) <= tolerance && dot <= tolerance) return true;
    if ((a.y > point.y) !== (b.y > point.y) && point.x < ((b.x - a.x) * (point.y - a.y)) / (b.y - a.y) + a.x) inside = !inside;
  }
  return inside;
}

function pointOnPolygonBoundary(point, polygon, tolerance = 1.2) {
  return polygon.some((a, index) => {
    const b = polygon[(index + 1) % polygon.length];
    const edgeLength = Math.hypot(b.x - a.x, b.y - a.y) || 1;
    const cross = ((point.x - a.x) * (b.y - a.y) - (point.y - a.y) * (b.x - a.x)) / edgeLength;
    const dot = (point.x - a.x) * (point.x - b.x) + (point.y - a.y) * (point.y - b.y);
    return Math.abs(cross) <= tolerance && dot <= tolerance;
  });
}

function boundaryEdgeIndex(point, polygon, tolerance = 1.8) {
  return polygon.findIndex((a, index) => {
    const b = polygon[(index + 1) % polygon.length];
    const edgeLength = Math.hypot(b.x - a.x, b.y - a.y) || 1;
    const cross = ((point.x - a.x) * (b.y - a.y) - (point.y - a.y) * (b.x - a.x)) / edgeLength;
    const dot = (point.x - a.x) * (point.x - b.x) + (point.y - a.y) * (point.y - b.y);
    return Math.abs(cross) <= tolerance && dot <= tolerance;
  });
}

function polylineLength(points) {
  let total = 0;
  for (let i = 0; i < points.length - 1; i += 1) total += Math.hypot(points[i + 1].x - points[i].x, points[i + 1].y - points[i].y);
  return total;
}

function boundaryChain(from, to, provincePolygon, forward) {
  const fromEdge = boundaryEdgeIndex(from, provincePolygon);
  const toEdge = boundaryEdgeIndex(to, provincePolygon);
  if (fromEdge < 0 || toEdge < 0) return null;
  const chain = [{ x: Math.round(from.x), y: Math.round(from.y) }];
  let index = forward ? (fromEdge + 1) % provincePolygon.length : fromEdge;
  let guard = 0;
  while (guard < provincePolygon.length + 2) {
    if (forward && index === (toEdge + 1) % provincePolygon.length) break;
    if (!forward && index === toEdge) break;
    chain.push(provincePolygon[index]);
    index = forward ? (index + 1) % provincePolygon.length : (index - 1 + provincePolygon.length) % provincePolygon.length;
    guard += 1;
  }
  chain.push({ x: Math.round(to.x), y: Math.round(to.y) });
  return dedupeConsecutive(chain);
}

function repairSegmentsInsideProvince(points, provincePolygon) {
  const repaired = [];
  for (let i = 0; i < points.length; i += 1) {
    const current = points[i];
    const following = points[(i + 1) % points.length];
    if (i === 0) repaired.push(current);
    const samplesInside = [0.25, 0.5, 0.75].every((t) => pointInPolygon({
      x: current.x + (following.x - current.x) * t,
      y: current.y + (following.y - current.y) * t,
    }, provincePolygon, 1.5));
    if (samplesInside) {
      repaired.push(following);
      continue;
    }
    const forward = boundaryChain(current, following, provincePolygon, true);
    const backward = boundaryChain(current, following, provincePolygon, false);
    const replacement = [forward, backward].filter(Boolean).sort((a, b) => polylineLength(a) - polylineLength(b))[0];
    if (replacement) {
      repaired.push(...replacement.slice(1));
    } else {
      repaired.push(following);
    }
  }
  return dedupeConsecutive(repaired);
}

function normalizedEndpoints(from, to) {
  const forward = from.x < to.x || (from.x === to.x && from.y <= to.y);
  return forward ? [from, to, false] : [to, from, true];
}

function hashSegment(from, to) {
  const [a, b] = normalizedEndpoints(from, to);
  const text = `${Math.round(a.x)},${Math.round(a.y)}|${Math.round(b.x)},${Math.round(b.y)}`;
  let hash = 2166136261;
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function curvedSegment(from, to, provincePolygon) {
  const len = Math.hypot(to.x - from.x, to.y - from.y);
  const steps = Math.max(1, Math.ceil(len / 30));
  if (steps === 1) return [{ x: Math.round(to.x), y: Math.round(to.y) }];
  const midpoint = { x: (from.x + to.x) / 2, y: (from.y + to.y) / 2 };
  const shouldCurve = false && !pointOnPolygonBoundary(midpoint, provincePolygon);
  const hash = hashSegment(from, to);
  const direction = hash % 2 === 0 ? 1 : -1;
  const amplitude = shouldCurve ? Math.min(12, Math.max(3, len / 18)) * direction : 0;
  const nx = -(to.y - from.y) / len;
  const ny = (to.x - from.x) / len;
  const points = [];
  for (let i = 1; i <= steps; i += 1) {
    const t = i / steps;
    const wave = Math.sin(Math.PI * t) * amplitude;
    points.push({ x: Math.round(from.x + (to.x - from.x) * t + nx * wave), y: Math.round(from.y + (to.y - from.y) * t + ny * wave) });
  }
  return points.every((point) => pointInPolygon(point, provincePolygon, 1.5))
    ? points
    : Array.from({ length: steps }, (_, index) => {
      const t = (index + 1) / steps;
      return { x: Math.round(from.x + (to.x - from.x) * t), y: Math.round(from.y + (to.y - from.y) * t) };
    });
}

function dedupeConsecutive(points) {
  const output = [];
  for (const point of points) {
    const rounded = { x: Math.round(point.x), y: Math.round(point.y) };
    const last = output[output.length - 1];
    if (last && last.x === rounded.x && last.y === rounded.y) continue;
    output.push(rounded);
  }
  if (output.length > 1) {
    const first = output[0];
    const last = output[output.length - 1];
    if (first.x === last.x && first.y === last.y) output.pop();
  }
  return output;
}

function splitLongEdges(points) {
  let output = points;
  for (let pass = 0; pass < 4; pass += 1) {
    const next = [];
    let changed = false;
    for (let i = 0; i < output.length; i += 1) {
      const current = output[i];
      const following = output[(i + 1) % output.length];
      next.push(current);
      if (Math.hypot(following.x - current.x, following.y - current.y) <= 78) continue;
      next.push({ x: Math.round((current.x + following.x) / 2), y: Math.round((current.y + following.y) / 2) });
      changed = true;
    }
    output = dedupeConsecutive(next);
    if (!changed) break;
  }
  return output;
}

function naturalizePolygon(points, provincePolygon) {
  const output = [];
  for (let i = 0; i < points.length; i += 1) {
    if (i === 0) output.push({ x: Math.round(points[i].x), y: Math.round(points[i].y) });
    output.push(...curvedSegment(points[i], points[(i + 1) % points.length], provincePolygon));
  }
  return splitLongEdges(repairSegmentsInsideProvince(dedupeConsecutive(output), provincePolygon));
}

data.cityPoints = {};

for (const province of REPARTITION_PROVINCES) {
  const cities = Object.entries(CITY_PROVINCE)
    .filter(([, cityProvince]) => cityProvince === province)
    .map(([city]) => city)
    .filter((city) => HISTORICAL_SEEDS[city]);
  const provincePolygon = provincePolygons[province];
  if (!provincePolygon || cities.length < 2) continue;

  for (const city of cities) {
    let cell = pointsToMultiPolygon(provincePolygon);
    const seed = HISTORICAL_SEEDS[city];
    for (const otherCity of cities) {
      if (otherCity === city) continue;
      cell = clipByCloserToSeed(cell, seed, HISTORICAL_SEEDS[otherCity]);
    }
    data.cityPoints[city] = naturalizePolygon(chooseCellRing(cell, seed), provincePolygon);
  }
}

fs.writeFileSync(dataPath, `${JSON.stringify(data, null, 2)}\n`);

function centerFor(city, points) {
  const seed = HISTORICAL_SEEDS[city];
  if (seed && pointInPolygon(seed, points, 1.5)) return { cx: seed.x, cy: seed.y };
  const centroid = {
    cx: Math.round(points.reduce((sum, point) => sum + point.x, 0) / points.length),
    cy: Math.round(points.reduce((sum, point) => sum + point.y, 0) / points.length),
  };
  if (pointInPolygon({ x: centroid.cx, y: centroid.cy }, points, 1.5)) return centroid;
  const fallback = points.find((point) => pointInPolygon(point, points, 1.5)) || points[0];
  return { cx: fallback.x, cy: fallback.y };
}

function provinceCenter(points) {
  return {
    cx: Math.round(points.reduce((sum, point) => sum + point.x, 0) / points.length),
    cy: Math.round(points.reduce((sum, point) => sum + point.y, 0) / points.length),
  };
}

const cityNames = Object.keys(CITY_PROVINCE).filter((city) => data.cityPoints[city]?.length >= 3);

let js = `// 双层标注数据 - 由 scripts/regenerate_shared_city_boundaries.mjs 生成\n\n`;
js += `export const PROVINCE_BLOCKS = ${JSON.stringify(Object.fromEntries(PROVINCES.map((province) => {
  const points = provincePolygons[province];
  const { cx, cy } = provinceCenter(points);
  return [province, { d: provincePointsToSvgPath(points), cx, cy, labelX: cx, labelY: cy }];
})), null, 2)};\n\n`;
js += `export const CITY_BLOCKS = ${JSON.stringify(Object.fromEntries(cityNames.map((city) => {
  const points = data.cityPoints[city];
  const { cx, cy } = centerFor(city, points);
  return [city, { d: orderedPointsToSvgPath(points), cx, cy, labelX: cx, labelY: cy, province: CITY_PROVINCE[city] || "", label: DISPLAY_LABELS[city] || city }];
})), null, 2)};\n`;
fs.writeFileSync(publicSvgPath, js);

let ts = `export type AnnotatedProvinceBlock = { d: string; cx: number; cy: number; labelX: number; labelY: number };\n`;
ts += `export type AnnotatedCityBlock = { d: string; cx: number; cy: number; labelX: number; labelY: number; province: string; label: string };\n\n`;
ts += `export const ANNOTATED_PROVINCE_BLOCKS = ${JSON.stringify(Object.fromEntries(PROVINCES.map((province) => {
  const points = provincePolygons[province];
  const { cx, cy } = provinceCenter(points);
  return [province, { d: provincePointsToSvgPath(points), cx, cy, labelX: cx, labelY: cy }];
})), null, 2)} as const satisfies Record<string, AnnotatedProvinceBlock>;\n\n`;
ts += `export const ANNOTATED_CITY_BLOCKS = ${JSON.stringify(Object.fromEntries(cityNames.map((city) => {
  const points = data.cityPoints[city];
  const { cx, cy } = centerFor(city, points);
  return [city, { d: orderedPointsToSvgPath(points), cx, cy, labelX: cx, labelY: cy, province: CITY_PROVINCE[city] || "", label: DISPLAY_LABELS[city] || city }];
})), null, 2)} as const satisfies Record<string, AnnotatedCityBlock>;\n`;
fs.writeFileSync(typedDataPath, ts);
