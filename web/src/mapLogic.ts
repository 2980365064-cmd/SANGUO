import type { Army, StrategicCity, StrategicNode, StrategicRoute } from "./types";
import {
  ANNOTATED_CITY_BLOCKS,
  ANNOTATED_PROVINCE_BLOCKS,
} from "./annotatedMapData.ts";

export type MapLayer = "province" | "commandery" | "city" | "influence";

export const MAP_LAYERS = [
  "province",
  "commandery",
  "city",
  "influence",
] as const satisfies readonly MapLayer[];
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
  沛国: "谯县",
  "弘农/潼关": "弘农",
  "常山/中山": "常山",
  渤海: "渤海",
  上党: "上党",
  陇西: "陇西",
  汝南: "汝南",
  江夏: "江夏",
  "长沙/荆南": "长沙",
  "鱼复/白帝": "永安",
  "阆中/巴西郡": "梓潼",
  邺: "邺城",
  蓟: "蓟县",
  辽东: "襄平",
  太原: "晋阳",
  "太原郡/晋阳": "晋阳",
  "上党郡/长子": "上党",
  "五原郡/九原": "九原",
  "云中郡/云中": "云中",
  "西河郡/离石": "西河",
  "雁门郡/阴馆": "雁门",
  "汉阳郡/冀": "天水",
  "武威郡/姑臧": "姑藏",
  "酒泉郡/禄福": "酒泉",
  "敦煌郡/敦煌": "敦煌",
  张掖郡: "张掖",
  "陇西郡/狄道": "陇西",
  "广阳郡/蓟": "蓟县",
  "涿郡/涿": "涿郡",
  "渔阳郡": "渔阳",
  "渔阳郡/渔阳": "渔阳",
  "右北平郡/土垠": "右北平",
  "辽西郡/阳乐": "辽西",
  "辽东郡/襄平": "襄平",
  武威: "姑藏",
  汉中: "南郑",
  南海: "番禺",
  苍梧: "苍梧",
  郁林: "郁林",
  合浦: "合浦",
  九真: "九真",
  日南: "日南",
  建业: "秣陵",
  丹阳: "秣陵",
  九江: "合肥",
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
  合肥: "九江郡",
  永安: "巴东郡",
  梓潼: "巴西郡",
  夜郎: "牂牁郡",
  且兰: "牂牁郡",
};

const HISTORICAL_CITY_NODE_ALIASES: Record<string, string> = {
  武陵: "jingnan",
  桂阳: "jingnan",
  豫章: "yuzhang",
  合肥: "jiujiang",
  柴桑: "yuzhang",
  丹阳: "danyang",
  合浦: "hepu",
  苍梧: "cangwu",
  郁林: "yulin",
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

export type CityTerritoryBlock = {
  city: StrategicCity;
  d: string;
  boundaryD: string;
  hasHistoricalAnchor: boolean;
  cx: number;
  cy: number;
  labelX: number;
  labelY: number;
};

type MapPoint = { x: number; y: number };

// 已人工校对的益州东部门户：白帝在峡江东口，鱼复在其西侧腹地。
// 这些点位独立于后端的临时坐标，作为后续逐州校图的固定基准。
const CITY_TERRITORY_ANCHORS: Record<string, MapPoint> = {
  "city:mianzhu": { x: 690, y: 663 },
  "city:langzhong": { x: 748, y: 607 },
  "city:shangyong": { x: 963, y: 617 },
  "city:yongan": { x: 888, y: 675 },
  "city:baidi": { x: 927, y: 655 },
  // 兖州两城图：陈留、濮阳分别占两块保留主郡界；泰山并入东郡范围。
  "city:chenliu": { x: 1188, y: 500 },
  "city:dongjun": { x: 1232, y: 458 },
  // 常山原标注中心贴近上缘，城池下移至范围腹地以避开北侧墨线。
  "city:changshan": { x: 1172, y: 334 },
  "city:nanpi": { x: 1273, y: 354 },
  "city:yelang": { x: 675, y: 882 },
  "city:qielan": { x: 792, y: 812 },
  "city:wancheng": { x: 1072, y: 606 },
  "city:jiangling": { x: 1048, y: 738 },
  // 三城均避开郡界墨线，落在其实际可见辖区的腹地。
  // 襄阳固定在原手绘襄阳块的几何腹地，避开与南郡、江夏相接的墨线。
  "city:xiangyang": { x: 1126, y: 643 },
  "city:fancheng": { x: 1148, y: 630 },
  "city:yiling": { x: 955, y: 726 },
  "city:jiangxia": { x: 1136, y: 730 },
  "city:jingnan": { x: 1116, y: 846 },
  "city:wuling": { x: 1010, y: 838 },
  "city:lingling": { x: 1093, y: 873 },
  "city:guiyang": { x: 1149, y: 870 },
  // 交趾合并日南后，龙编收至其西南腹地；广信避开苍梧与猛陵的分界。
  "city:longbian": { x: 780, y: 945 },
  "city:jiaozhi": { x: 850, y: 900 },
  "city:nanhai": { x: 1183, y: 894 },
  "city:guangxin": { x: 1035, y: 890 },
  "city:wuzhou": { x: 1080, y: 920 },
  "city:bushan": { x: 930, y: 904 },
  "city:hepu": { x: 990, y: 958 },
  "city:xuwen": { x: 1015, y: 978 },
  "city:xupu": { x: 800, y: 994 },
  "city:xijuan": { x: 730, y: 954 },
  // 扬州六郡（208）：所有锚点均留在对应手绘郡界腹地。
  "city:jianye": { x: 1390, y: 668 },
  "city:wuhu": { x: 1350, y: 640 },
  "city:wu": { x: 1440, y: 710 },
  "city:qu-e": { x: 1420, y: 755 },
  "city:kuaiji": { x: 1370, y: 820 },
  "city:nanchang": { x: 1305, y: 800 },
  "city:chaisang": { x: 1218, y: 755 },
  "city:hefei": { x: 1282, y: 620 },
  "city:shouchun": { x: 1238, y: 625 },
  "city:wanling": { x: 1330, y: 700 },
  // 徐州三城图：每座城直接复用所属主郡范围，不再生成内部城界。
  "city:xiapi": { x: 1370, y: 552 },
  "city:pengcheng": { x: 1320, y: 516 },
  "city:guangling": { x: 1425, y: 592 },
  // 青州保留临淄、北海两块主郡界；三座旧郡治作为属城置入母郡腹地。
  "city:linzi": { x: 1352, y: 424 },
  "city:ju": { x: 1318, y: 466 },
  "city:dongpingling": { x: 1295, y: 420 },
  "city:linji": { x: 1462, y: 406 },
  // 豫州三城图：颍川许昌、汝南平舆、沛国相各自复用母郡曲折边界。
  "city:xuchang": { x: 1126, y: 560 },
  "city:runan": { x: 1190, y: 586 },
  "city:qiaoxian": { x: 1264, y: 550 },
  // 并州沿用三块已校的曲折郡界，三座主城均固定在原有标注腹地。
  "city:taiyuan": { x: 1080, y: 380 },
  "city:shangdang": { x: 1085, y: 430 },
  "city:jiuyuan": { x: 930, y: 275 },
  "city:yunzhong": { x: 984, y: 382 },
  // 离石由西侧边缘收回西河曲折辖区的几何腹地，避开汾河方向外界墨线。
  "city:xihe": { x: 928, y: 398 },
  "city:yanmen": { x: 1060, y: 301 },
  // 凉州六郡：河西走廊三段与陇右三郡均将郡治固定在各自曲折辖区腹地。
  "city:wuwei": { x: 645, y: 356 },
  // 张掖由走廊南缘收回张掖块腹地，避开酒泉交界和南侧墨线。
  "city:zhangye": { x: 570, y: 225 },
  "city:jiuquan": { x: 470, y: 248 },
  "city:dunhuang": { x: 330, y: 248 },
  // 汉阳（冀）由西南边缘收至汉阳曲折辖区腹地。
  "city:tianshui": { x: 840, y: 445 },
  "city:longxi": { x: 710, y: 488 },
  "city:ji": { x: 1310, y: 265 },
  "city:zhuojun": { x: 1250, y: 306 },
  "city:yuyang": { x: 1400, y: 235 },
  "city:youbeiping": { x: 1460, y: 210 },
  "city:liaoxi": { x: 1480, y: 285 },
  "city:liaodong": { x: 1530, y: 250 },
};

const MERGED_COMMANDERY_BLOCKS: Record<string, readonly string[]> = {
  南郑: ["南郑", "上庸"],
  夜郎: ["夜郎", "且兰"],
  江陵: ["江陵", "襄阳"],
  长沙: ["长沙", "零陵"],
  柴桑: ["柴桑", "豫章"],
  秣陵: ["秣陵", "丹阳"],
  濮阳: ["濮阳", "泰山"],
  南皮: ["南皮", "渤海"],
  交趾: ["交趾", "日南"],
  番禺: ["番禺", "桂阳"],
};

// 已并入可玩郡的旧手绘块不再作为城池层地理参照显示。
const HIDDEN_TOWN_REFERENCES = new Set(["日南", "桂阳"]);

const MERGED_COMMANDERY_LABELS: Record<string, string> = {
  夜郎: "牂牁",
  江陵: "南郡",
  长沙: "长沙",
  柴桑: "豫章",
  秣陵: "丹阳",
};

function polygonArea(points: MapPoint[]) {
  return (
    points.reduce((sum, point, index) => {
      const next = points[(index + 1) % points.length];
      return sum + point.x * next.y - next.x * point.y;
    }, 0) / 2
  );
}

function triangleContainsPoint(
  point: MapPoint,
  a: MapPoint,
  b: MapPoint,
  c: MapPoint,
  orientation: number,
) {
  const cross = (start: MapPoint, end: MapPoint, candidate: MapPoint) =>
    (end.x - start.x) * (candidate.y - start.y) -
    (end.y - start.y) * (candidate.x - start.x);
  const epsilon = 1e-6;
  return (
    orientation * cross(a, b, point) >= -epsilon &&
    orientation * cross(b, c, point) >= -epsilon &&
    orientation * cross(c, a, point) >= -epsilon
  );
}

/** 将任意简单郡界剖分为三角形，供后续在每一片内安全裁切。 */
function triangulatePolygon(points: MapPoint[]) {
  if (points.length < 3) return [] as MapPoint[][];
  const orientation = polygonArea(points) >= 0 ? 1 : -1;
  const remaining = points.map((_, index) => index);
  const triangles: MapPoint[][] = [];
  while (remaining.length > 3) {
    let earFound = false;
    for (let offset = 0; offset < remaining.length; offset += 1) {
      const previous =
        remaining[(offset - 1 + remaining.length) % remaining.length];
      const current = remaining[offset];
      const next = remaining[(offset + 1) % remaining.length];
      const a = points[previous];
      const b = points[current];
      const c = points[next];
      const cross = (b.x - a.x) * (c.y - b.y) - (b.y - a.y) * (c.x - b.x);
      if (orientation * cross <= 1e-6) continue;
      const hasInnerPoint = remaining.some(
        (candidate) =>
          candidate !== previous &&
          candidate !== current &&
          candidate !== next &&
          triangleContainsPoint(points[candidate], a, b, c, orientation),
      );
      if (hasInnerPoint) continue;
      triangles.push([a, b, c]);
      remaining.splice(offset, 1);
      earFound = true;
      break;
    }
    // 标注数据异常时宁可回退到整块郡界，也不生成越界辖区。
    if (!earFound) return [points];
  }
  triangles.push(remaining.map((index) => points[index]));
  return triangles;
}

/** 保留更接近 site 而非 other 的半平面；用于凸三角形内的 Voronoi 裁切。 */
function clipToNearestHalfPlane(
  polygon: MapPoint[],
  site: MapPoint,
  other: MapPoint,
) {
  const dx = other.x - site.x;
  const dy = other.y - site.y;
  const limit =
    (other.x * other.x +
      other.y * other.y -
      site.x * site.x -
      site.y * site.y) /
    2;
  const distance = (point: MapPoint) => point.x * dx + point.y * dy - limit;
  const output: MapPoint[] = [];
  polygon.forEach((current, index) => {
    const previous = polygon[(index - 1 + polygon.length) % polygon.length];
    const currentDistance = distance(current);
    const previousDistance = distance(previous);
    const currentInside = currentDistance <= 1e-6;
    const previousInside = previousDistance <= 1e-6;
    if (currentInside !== previousInside) {
      const ratio = previousDistance / (previousDistance - currentDistance);
      output.push({
        x: previous.x + (current.x - previous.x) * ratio,
        y: previous.y + (current.y - previous.y) * ratio,
      });
    }
    if (currentInside) output.push(current);
  });
  return output;
}

function polygonPath(points: MapPoint[]) {
  if (points.length < 3 || Math.abs(polygonArea(points)) < 0.01) return "";
  return `M ${points.map((point) => `${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(" L ")} Z`;
}

function roundedPointKey(point: MapPoint) {
  return `${point.x.toFixed(2)},${point.y.toFixed(2)}`;
}

function partitionBoundaryPath(
  cells: Array<{ cityId: string; pieces: MapPoint[][] }>,
) {
  const edges = new Map<
    string,
    { a: MapPoint; b: MapPoint; owners: Set<string>; count: number }
  >();
  cells.forEach(({ cityId, pieces }) =>
    pieces.forEach((polygon) =>
      polygon.forEach((point, index) => {
        const next = polygon[(index + 1) % polygon.length];
        const pointKey = roundedPointKey(point);
        const nextKey = roundedPointKey(next);
        const forward = pointKey <= nextKey;
        const key = forward
          ? `${pointKey}|${nextKey}`
          : `${nextKey}|${pointKey}`;
        const edge = edges.get(key) || {
          a: forward ? point : next,
          b: forward ? next : point,
          owners: new Set<string>(),
          count: 0,
        };
        edge.owners.add(cityId);
        edge.count += 1;
        edges.set(key, edge);
      }),
    ),
  );
  return (
    [...edges.values()]
      // 郡外边界由原始标注郡界统一绘制；这里只保留确实分隔两座城的边。
      // 这样既不会把凹多边形三角剖分线露出来，也不会用直线覆盖原有曲折郡界。
      .filter((edge) => edge.owners.size > 1)
      .map((edge) => curvedSegmentPath(edge.a, edge.b, true))
      .join(" ")
  );
}

/**
 * 城池辖区是郡级静态边界的确定性分割：先剖分凹形郡界，再在每一三角片
 * 按真实 city_id 的最近城位切分。所有辖区合并后严格覆盖所属郡界，不参与资源统计。
 */
export function getCityTerritoryBlocks(
  cities: StrategicCity[],
  commanderyBlocks: CommanderyBoundaryBlock[],
): CityTerritoryBlock[] {
  const grouped = new Map<string, StrategicCity[]>();
  cities.forEach((city) =>
    grouped.set(city.commandery_id, [
      ...(grouped.get(city.commandery_id) || []),
      city,
    ]),
  );
  // 历史城镇可借用代表节点供点击，但不能反过来覆盖该节点的真实母郡界。
  // 例如“武陵”借长沙节点时，长沙城仍必须使用“长沙＋零陵”完整边界。
  const boundaryByCommandery = new Map<string, CommanderyBoundaryBlock>();
  commanderyBlocks.filter((block) => block.node).forEach((block) => {
    const node = block.node!;
    const canonicalCity = resolveAnnotatedCityName(node.name);
    const current = boundaryByCommandery.get(node.id);
    if (!current || block.city === canonicalCity)
      boundaryByCommandery.set(node.id, block);
  });
  return [...grouped.values()].flatMap((siblings) => {
    const boundary = boundaryByCommandery.get(siblings[0].commandery_id);
    const outlines = boundary ? pathToPolygons(boundary.d) : [];
    const capital =
      siblings.find((candidate) => candidate.is_commandery_capital) ||
      siblings[0];
    const sites = new Map(
      siblings.map((city) => [
        city.id,
        CITY_TERRITORY_ANCHORS[city.id] ||
          (boundary
            ? {
                x: boundary.cx + (city.x - capital.x) * 24,
                y: boundary.cy + (city.y - capital.y) * 20,
              }
            : { x: city.x * 19.2, y: city.y * 10.8 }),
      ]),
    );
    // 郡内仅剩一座现役城池时，其辖区就是母郡完整曲线；不以三角剖分
    // 近似重画，避免长沙这类合并辖区出现伪造的内部城界。
    if (boundary && siblings.length === 1) {
      const city = siblings[0];
      const site = sites.get(city.id)!;
      return [{
        city,
        d: boundary.d,
        boundaryD: "",
        hasHistoricalAnchor: Boolean(
          CITY_TERRITORY_ANCHORS[city.id] || city.is_commandery_capital,
        ),
        cx: site.x,
        cy: site.y,
        labelX: site.x,
        labelY: site.y,
      }];
    }
    const cells = siblings.map((city) => {
      // 郡治严格回到原舆图郡位；未校勘的次级城不允许继续伪造偏移坐标。
      const hasHistoricalAnchor = Boolean(
        CITY_TERRITORY_ANCHORS[city.id] ||
        (boundary && city.is_commandery_capital),
      );
      const site = sites.get(city.id)!;
      const pieces = outlines
        .flatMap(triangulatePolygon)
        .map((triangle) =>
          siblings.reduce(
            (cell, sibling) =>
              sibling.id === city.id
                ? cell
                : clipToNearestHalfPlane(cell, site, sites.get(sibling.id)!),
            triangle,
          ),
        )
        .filter(
          (piece) => piece.length >= 3 && Math.abs(polygonArea(piece)) >= 0.01,
        );
      return { city, site, pieces };
    });
    const boundaryD = partitionBoundaryPath(
      cells.map((cell) => ({ cityId: cell.city.id, pieces: cell.pieces })),
    );
    return cells.map((cell, index) => ({
      city: cell.city,
      d: cell.pieces.map(polygonPath).filter(Boolean).join(" "),
      boundaryD: index === 0 ? boundaryD : "",
      hasHistoricalAnchor: Boolean(
        CITY_TERRITORY_ANCHORS[cell.city.id] || cell.city.is_commandery_capital,
      ),
      cx: cell.site.x,
      cy: cell.site.y,
      labelX: cell.site.x,
      labelY: cell.site.y,
    }));
  });
}

function pathToPoints(path: string) {
  return (path.match(/[ML] -?\d+ -?\d+/g) || []).map((item) => {
    const [, x, y] = item.split(" ");
    return { x: Number(x), y: Number(y) };
  });
}

function pathToPolygons(path: string) {
  return (
    path.match(
      /M -?\d+(?:\.\d+)? -?\d+(?:\.\d+)?(?: L -?\d+(?:\.\d+)? -?\d+(?:\.\d+)?)+ Z/g,
    ) || []
  )
    .map(pathToPoints)
    .filter((points) => points.length >= 3);
}

function normalizedSegment(
  a: { x: number; y: number },
  b: { x: number; y: number },
) {
  const left = a.x < b.x || (a.x === b.x && a.y <= b.y) ? a : b;
  const right = left === a ? b : a;
  return `${left.x},${left.y}|${right.x},${right.y}`;
}

function pointOnBoundary(
  point: { x: number; y: number },
  polygon: Array<{ x: number; y: number }>,
  tolerance = 1.5,
) {
  return polygon.some((a, index) => {
    const b = polygon[(index + 1) % polygon.length];
    const edgeLength = Math.hypot(b.x - a.x, b.y - a.y) || 1;
    const cross =
      ((point.x - a.x) * (b.y - a.y) - (point.y - a.y) * (b.x - a.x)) /
      edgeLength;
    const dot =
      (point.x - a.x) * (point.x - b.x) + (point.y - a.y) * (point.y - b.y);
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

function curvedSegmentPath(
  a: { x: number; y: number },
  b: { x: number; y: number },
  shouldCurve: boolean,
) {
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

export function getSharedCityBoundaryPath(
  blocks: Array<Pick<CityBoundaryBlock, "d" | "province">>,
) {
  const provinceBoundaryPoints = new Map<
    string,
    Array<{ x: number; y: number }>
  >();
  const segments = new Map<
    string,
    {
      a: { x: number; y: number };
      b: { x: number; y: number };
      curve: boolean;
      occurrences: number;
      owners: Set<number>;
    }
  >();
  for (const [blockIndex, block] of blocks.entries()) {
    const provincePoints =
      provinceBoundaryPoints.get(block.province) ||
      pathToPoints(PROVINCE_BLOCKS[block.province]?.d || "");
    if (!provinceBoundaryPoints.has(block.province))
      provinceBoundaryPoints.set(block.province, provincePoints);
    for (const points of pathToPolygons(block.d)) {
      for (let i = 0; i < points.length; i += 1) {
        const current = points[i];
        const next = points[(i + 1) % points.length];
        const key = normalizedSegment(current, next);
        const midpoint = {
          x: (current.x + next.x) / 2,
          y: (current.y + next.y) / 2,
        };
        const isProvinceEdge =
          provincePoints.length > 0 &&
          pointOnBoundary(midpoint, provincePoints, 2.5);
        const existing = segments.get(key);
        if (existing) {
          existing.curve = existing.curve || !isProvinceEdge;
          existing.occurrences += 1;
          existing.owners.add(blockIndex);
        } else {
          segments.set(key, {
            a: current,
            b: next,
            curve: !isProvinceEdge,
            occurrences: 1,
            owners: new Set([blockIndex]),
          });
        }
      }
    }
  }
  return (
    [...segments.values()]
      // 多路径合并郡（牂牁）的两块原边界相接时，公共边不再冒充郡外界；
      // 不同城池的公共边仍须保留一次，作为正常的城池分界。
      .filter(
        (segment) => !(segment.occurrences > 1 && segment.owners.size === 1),
      )
      .map((segment) => curvedSegmentPath(segment.a, segment.b, segment.curve))
      .join(" ")
  );
}

/**
 * 单个郡在悬停/选中时使用的描边。它和底层共享郡界走同一条逐段曲线，
 * 因而朱砂高亮会严格贴合黑色行政墨线，而不是退化为 polygon 的直线边。
 */
export function getCurvedCommanderyBoundaryPath(
  block: Pick<CityBoundaryBlock, "d" | "province">,
) {
  return getSharedCityBoundaryPath([block]);
}

export function clampMapZoom(value: number) {
  return Math.min(2.5, Math.max(0.75, Math.round(value * 100) / 100));
}

// 十三州疆域 path：0~1000 SVG 像素坐标。
// 边界参考东汉州界依山河走势划分（黄河/太行/秦岭/长江/淮河/燕山/南岭等），
// 形状仿古不规则。相邻两州的公共边界共用相同的顶点序列（方向相反逐点一致），
// 保证 13 块互不重叠、无缝接壤；全部 35 个郡节点（百分比 ×10）均落在
// 所属州块内部（几何合同见 tests/mapLogic.test.ts）。
export const PROVINCE_BLOCKS: Record<
  string,
  Pick<ProvinceBlock, "d" | "cx" | "cy" | "labelX" | "labelY">
> = ANNOTATED_PROVINCE_BLOCKS;

export const LEGACY_PROVINCE_BLOCKS: Record<
  string,
  Pick<ProvinceBlock, "d" | "cx" | "cy" | "labelX" | "labelY">
> = {
  凉州: {
    d: "M 67 56 L 227 32 L 413 59 L 618 41 L 726 80 L 695 162 L 733 240 L 707 305 L 637 356 L 553 423 L 503 505 L 376 510 L 242 471 L 165 369 L 104 266 L 111 160 Z",
    cx: 384,
    cy: 270,
    labelX: 384,
    labelY: 270,
  },
  并州: {
    d: "M 726 80 L 868 99 L 1014 73 L 1075 82 L 1025 153 L 1060 220 L 1048 283 L 1029 339 L 945 380 L 837 356 L 707 305 L 733 240 L 695 162 Z",
    cx: 895,
    cy: 212,
    labelX: 895,
    labelY: 212,
  },
  幽州: {
    d: "M 1356 41 L 1501 24 L 1667 37 L 1793 63 L 1855 117 L 1820 181 L 1734 224 L 1644 212 L 1540 205 L 1394 231 L 1340 168 L 1298 110 Z",
    cx: 1586,
    cy: 130,
    labelX: 1586,
    labelY: 130,
  },
  冀州: {
    d: "M 1075 82 L 1194 52 L 1290 65 L 1356 41 L 1298 110 L 1340 168 L 1394 231 L 1332 308 L 1252 395 L 1133 363 L 1029 339 L 1048 283 L 1060 220 L 1025 153 Z",
    cx: 1179,
    cy: 231,
    labelX: 1179,
    labelY: 231,
  },
  青州: {
    d: "M 1394 231 L 1540 205 L 1644 212 L 1734 224 L 1678 257 L 1705 315 L 1644 359 L 1536 406 L 1402 434 L 1252 395 L 1332 308 Z",
    cx: 1517,
    cy: 324,
    labelX: 1517,
    labelY: 324,
  },
  司隶: {
    d: "M 707 305 L 837 356 L 945 380 L 1029 339 L 983 397 L 1006 445 L 960 484 L 902 516 L 806 542 L 676 531 L 503 505 L 553 423 L 637 356 Z",
    cx: 764,
    cy: 438,
    labelX: 764,
    labelY: 438,
  },
  兖州: {
    d: "M 1029 339 L 1133 363 L 1252 395 L 1229 462 L 1206 516 L 1094 488 L 1006 445 L 983 397 Z",
    cx: 1114,
    cy: 432,
    labelX: 1114,
    labelY: 432,
  },
  徐州: {
    d: "M 1252 395 L 1402 434 L 1536 406 L 1644 359 L 1624 423 L 1651 488 L 1617 549 L 1425 592 L 1229 564 L 1194 542 L 1206 516 L 1229 462 Z",
    cx: 1425,
    cy: 499,
    labelX: 1425,
    labelY: 499,
  },
  豫州: {
    d: "M 1006 445 L 1094 488 L 1206 516 L 1194 542 L 1229 564 L 1221 600 L 1233 635 L 1106 631 L 1002 583 L 902 516 L 960 484 Z",
    cx: 1075,
    cy: 557,
    labelX: 1075,
    labelY: 557,
  },
  荆州: {
    d: "M 902 516 L 1002 583 L 1106 631 L 1233 635 L 1260 700 L 1206 773 L 1233 853 L 1213 909 L 1068 927 L 906 942 L 749 948 L 691 896 L 645 838 L 726 801 L 803 756 L 822 678 L 868 592 Z",
    cx: 983,
    cy: 756,
    labelX: 983,
    labelY: 756,
  },
  扬州: {
    d: "M 1229 564 L 1425 592 L 1617 549 L 1740 607 L 1832 698 L 1797 780 L 1715 837 L 1540 862 L 1379 888 L 1213 909 L 1233 853 L 1206 773 L 1260 700 L 1233 635 L 1221 600 Z",
    cx: 1501,
    cy: 728,
    labelX: 1501,
    labelY: 728,
  },
  益州: {
    d: "M 503 505 L 676 531 L 806 542 L 902 516 L 868 592 L 822 678 L 803 756 L 726 801 L 645 838 L 461 812 L 284 771 L 227 661 L 261 542 L 242 471 L 376 510 Z",
    cx: 515,
    cy: 661,
    labelX: 515,
    labelY: 661,
  },
  交州: {
    d: "M 1213 909 L 1379 888 L 1540 862 L 1715 837 L 1782 899 L 1732 976 L 1597 1024 L 1348 1045 L 1068 1054 L 849 1031 L 707 989 L 749 948 L 906 942 L 1068 927 Z",
    cx: 1283,
    cy: 983,
    labelX: 1283,
    labelY: 983,
  },
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
  routes: StrategicRoute[] = [],
): ReachableTarget[] {
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  // 72 城池网络：使用直连边而非州块邻接
  if (routes.length > 0) {
    const neighbors = new Set<string>();
    routes.forEach((route) => {
      if (route.source === sourceNode) neighbors.add(route.target);
      if (route.target === sourceNode) neighbors.add(route.source);
    });
    const source = nodeById.get(sourceNode);
    if (!source) return [];
    return Array.from(neighbors)
      .filter((id) => id !== sourceNode && nodeById.has(id))
      .map((id) => {
        const node = nodeById.get(id)!;
        return {
          nodeId: id,
          province: node.province,
          scope: node.province === source.province ? ("同州" as const) : ("邻州" as const),
        };
      });
  }
  // 回退：旧版州块邻接（仅兼容无路线数据的场景）
  const source = nodes.find((node) => node.id === sourceNode);
  if (!source) return [];
  const allowed = new Set([
    source.province,
    ...(PROVINCE_ADJACENCY[source.province] || []),
  ]);
  return nodes
    .filter((node) => node.id !== sourceNode && allowed.has(node.province))
    .map((node) => ({
      nodeId: node.id,
      province: node.province,
      scope: node.province === source.province ? ("同州" as const) : ("邻州" as const),
    }));
}

export function routeWarning(kind: string, note = "") {
  if (kind === "关隘")
    return `${note || "关隘"}尚未攻克时不可穿越，须先下围城军令。`;
  if (kind === "江河" || kind === "山道") {
    return `${kind}行军令粮秣立即消耗 20，并承受三回合战力与机动惩罚。`;
  }
  return "驿道通行，一条边耗时一回合。";
}

export function getNodeArmies<T extends Pick<Army, "station_node">>(
  armies: T[],
  nodeId: string,
) {
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

export function getProvinceWashes(
  nodes: Array<Pick<StrategicNode, "province" | "x" | "y">>,
): ProvinceWash[] {
  const grouped = new Map<string, Array<Pick<StrategicNode, "x" | "y">>>();
  nodes.forEach((node) => {
    const current = grouped.get(node.province) || [];
    current.push(node);
    grouped.set(node.province, current);
  });
  return Array.from(grouped.entries()).map(([province, provinceNodes]) => {
    const xs = provinceNodes.map((node) => node.x * 19.2);
    const ys = provinceNodes.map((node) => node.y * 10.8);
    const cx = Math.round(
      xs.reduce((sum, value) => sum + value, 0) / xs.length,
    );
    const cy = Math.round(
      ys.reduce((sum, value) => sum + value, 0) / ys.length,
    );
    return {
      province,
      cx,
      cy,
      rx: Math.max(
        70,
        Math.round((Math.max(...xs) - Math.min(...xs)) / 2 + 76),
      ),
      ry: Math.max(
        54,
        Math.round((Math.max(...ys) - Math.min(...ys)) / 2 + 58),
      ),
      nodeCount: provinceNodes.length,
    };
  });
}

// 州主导势力：州内控制郡数最多者上色；平票比总人口，再平按节点顺序取先出现者。
export function getProvinceController(
  nodes: Array<Pick<StrategicNode, "controller" | "population">>,
): string {
  const tally = new Map<
    string,
    { count: number; population: number; order: number }
  >();
  nodes.forEach((node, index) => {
    const key = node.controller || "";
    const current = tally.get(key) || { count: 0, population: 0, order: index };
    tally.set(key, {
      count: current.count + 1,
      population: current.population + (node.population || 0),
      order: current.order,
    });
  });
  return (
    Array.from(tally.entries()).sort(
      ([, a], [, b]) =>
        b.count - a.count || b.population - a.population || a.order - b.order,
    )[0]?.[0] || ""
  );
}

export function getProvinceBlocks(nodes: StrategicNode[]): ProvinceBlock[] {
  const grouped = new Map<string, StrategicNode[]>();
  nodes.forEach((node) =>
    grouped.set(node.province, [...(grouped.get(node.province) || []), node]),
  );
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
  // 行政名与底图旧城名同名时，显式史实别名优先：例如“丹阳”应复用秣陵
  // 郡界，“豫章”应从柴桑—豫章合并郡界取母范围。
  const directAlias = ANNOTATED_CITY_ALIASES[name];
  if (directAlias && directAlias in ANNOTATED_CITY_BLOCKS) return directAlias;
  if (name in ANNOTATED_CITY_BLOCKS) return name;
  for (const part of name
    .split(/[/:／、]/)
    .map((item) => item.trim())
    .filter(Boolean)) {
    if (part in ANNOTATED_CITY_BLOCKS) return part;
  }
  return null;
}

export function getCityInteractionBlocks(
  nodes: StrategicNode[],
): CityInteractionBlock[] {
  return nodes.flatMap((node) => {
    const city = resolveAnnotatedCityName(node.name);
    if (!city) return [];
    const block =
      ANNOTATED_CITY_BLOCKS[city as keyof typeof ANNOTATED_CITY_BLOCKS];
    return [
      {
        city,
        label: block.label,
        commanderyName: commanderyNameFor(city, block.label),
        node,
        d: block.d,
        cx: block.cx,
        cy: block.cy,
        labelX: block.labelX,
        labelY: block.labelY,
        province: block.province,
      },
    ];
  });
}

export function getCityBoundaryBlocks(
  nodes: StrategicNode[],
): CityBoundaryBlock[] {
  return getCityInteractionBlocks(nodes);
}

function getNodeByAnnotatedCity(nodes: StrategicNode[]) {
  const nodeByAnnotatedCity = new Map<string, StrategicNode>();
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  nodes.forEach((node) => {
    const city = resolveAnnotatedCityName(node.name);
    if (city && !nodeByAnnotatedCity.has(city))
      nodeByAnnotatedCity.set(city, node);
  });
  Object.entries(HISTORICAL_CITY_NODE_ALIASES).forEach(([city, nodeId]) => {
    const node = nodeById.get(nodeId);
    if (node && !nodeByAnnotatedCity.has(city))
      nodeByAnnotatedCity.set(city, node);
  });
  return nodeByAnnotatedCity;
}

export function getTownBlocks(nodes: StrategicNode[]): TownBlock[] {
  const nodeByAnnotatedCity = getNodeByAnnotatedCity(nodes);

  return Object.entries(ANNOTATED_CITY_BLOCKS).flatMap(([city, block]) => {
    if (HIDDEN_TOWN_REFERENCES.has(city)) return [];
    const node = nodeByAnnotatedCity.get(city);
    return [{
      city,
      townName: city,
      townKind: node ? ("game-city" as const) : ("historical-town" as const),
      label: block.label,
      commanderyName: commanderyNameFor(city, block.label),
      d: block.d,
      cx: block.cx,
      cy: block.cy,
      labelX: block.labelX,
      labelY: block.labelY,
      province: block.province,
      node,
    }];
  });
}

export function getCommanderyBoundaryBlocks(
  nodes: StrategicNode[],
): CommanderyBoundaryBlock[] {
  const nodeByAnnotatedCity = getNodeByAnnotatedCity(nodes);
  const mergedMembers = new Set(
    Object.values(MERGED_COMMANDERY_BLOCKS).flatMap((members) =>
      members.slice(1),
    ),
  );

  return Object.entries(ANNOTATED_CITY_BLOCKS).flatMap(([city, block]) => {
    if (mergedMembers.has(city)) return [];
    const members = MERGED_COMMANDERY_BLOCKS[city] || [city];
    const memberBlocks = members.map(
      (member) =>
        ANNOTATED_CITY_BLOCKS[member as keyof typeof ANNOTATED_CITY_BLOCKS],
    );
    const merged = members.length > 1;
    const mergedLabel = MERGED_COMMANDERY_LABELS[city];
    return [
      {
        city: city === "南郑" ? "南郑" : mergedLabel || city,
        label:
          city === "南郑"
            ? "汉中"
            : mergedLabel
              ? mergedLabel
              : nodeByAnnotatedCity.get(city)?.name.split(/[/:／、]/)[0] ||
                block.label,
        commanderyName:
          city === "南郑"
            ? "汉中郡"
            : mergedLabel
              ? /[郡国尹]$/.test(mergedLabel) ? mergedLabel : `${mergedLabel}郡`
              : commanderyNameFor(city, block.label),
        d: memberBlocks.map((member) => member.d).join(" "),
        cx: block.cx,
        cy: block.cy,
        labelX: block.labelX,
        labelY: block.labelY,
        province: block.province,
        node: nodeByAnnotatedCity.get(city),
      },
    ];
  });
}
