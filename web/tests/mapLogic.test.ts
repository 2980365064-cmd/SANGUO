import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_MAP_LAYER,
  MAP_LAYERS,
  STATIC_MAP_LABEL_POLICY,
  clampMapZoom,
  getCityBoundaryBlocks,
  getCityTerritoryBlocks,
  getInfluenceRegions,
  getCityInteractionBlocks,
  getCommanderyBoundaryBlocks,
  getCurvedCommanderyBoundaryPath,
  getSharedCityBoundaryPath,
  getProvinceBlocks,
  getProvinceWashes,
  getNodeArmies,
  getReachableTargets,
  getTownBlocks,
  isPointInCityTerritory,
  resolveAnnotatedCityName,
} from "../src/mapLogic.ts";
import { ANNOTATED_CITY_BLOCKS } from "../src/annotatedMapData.ts";

const annotated = await import("../public/标注数据_SVG.js");

test("势力题签按真实城池共边分区，飞地不与角点或异势力误合并", () => {
  const block = (id: string, controller: string, d: string, x: number, y: number) => ({
    city: { id, controller }, d, boundaryD: "", hasHistoricalAnchor: true,
    cx: x, cy: y, labelX: x, labelY: y,
  });
  const territories = [
    block("city:a", "liu_bei", "M 0 0 L 10 0 L 10 10 L 0 10 Z", 5, 5),
    block("city:b", "liu_bei", "M 10 0 L 20 0 L 20 10 L 10 10 Z", 15, 5),
    block("city:c", "cao_cao", "M 20 0 L 30 0 L 30 10 L 20 10 Z", 25, 5),
    block("city:fly", "liu_bei", "M 40 0 L 50 0 L 50 10 L 40 10 Z", 45, 5),
  ] as any;
  const regions = getInfluenceRegions(territories);
  assert.deepEqual(regions.map((region) => [region.controller, region.cityIds]), [
    ["cao_cao", ["city:c"]],
    ["liu_bei", ["city:a", "city:b"]],
    ["liu_bei", ["city:fly"]],
  ]);
  for (const region of regions) {
    const labelTerritory = territories.find((item: any) => item.city.id === region.labelCityId)!;
    assert.ok(isPointInCityTerritory({ x: region.labelX, y: region.labelY }, labelTerritory.d));
  }
});

test("地图缩放被限制在适合桌面沙盘操作的范围内", () => {
  assert.equal(clampMapZoom(0.2), 0.75);
  assert.equal(clampMapZoom(1.6), 1.6);
  assert.equal(clampMapZoom(4), 2.5);
});

test("军队目标按城池直连路线返回可达节点", () => {
  const nodes = [
    { id: "city:jiangxia", province: "荆州" },
    { id: "city:xiangyang", province: "荆州" },
    { id: "city:chaisang", province: "扬州" },
    { id: "city:ji", province: "幽州" },
  ];
  const routes = [
    { source: "city:jiangxia", target: "city:xiangyang", kind: "普通路", note: "" },
    { source: "city:jiangxia", target: "city:chaisang", kind: "普通路", note: "" },
  ];
  assert.deepEqual(getReachableTargets(nodes, "city:jiangxia", routes), [
    { nodeId: "city:xiangyang", province: "荆州", scope: "同州" },
    { nodeId: "city:chaisang", province: "扬州", scope: "邻州" },
  ]);
});

test("州郡详情只展示该节点实际驻扎的军队", () => {
  const armies = [
    { id: "a", station_node: "jiangxia" },
    { id: "b", station_node: "xiangyang" },
    { id: "c", station_node: "jiangxia" },
  ];
  assert.deepEqual(
    getNodeArmies(armies, "jiangxia").map((army) => army.id),
    ["a", "c"],
  );
});

test("地图州郡色块从游戏节点的 province 聚合生成", () => {
  const washes = getProvinceWashes([
    { id: "jiangxia", name: "江夏", province: "荆州", x: 62, y: 56 },
    { id: "xiangyang", name: "襄阳", province: "荆州", x: 58, y: 45 },
    { id: "jianye", name: "建业", province: "扬州", x: 75, y: 62 },
  ]);
  assert.deepEqual(
    washes.map((wash) => wash.province),
    ["荆州", "扬州"],
  );
  assert.equal(washes[0].nodeCount, 2);
  assert.equal(washes[0].cx, 1152);
  assert.equal(washes[0].cy, 545);
  assert.ok(washes[0].rx > washes[1].rx);
});

test("十三州州块带有可渲染轮廓和州内郡列表", () => {
  const blocks = getProvinceBlocks([
    {
      id: "jiangxia",
      name: "江夏",
      province: "荆州",
      x: 59,
      y: 65,
      controller: "liu_bei",
      public_support: 50,
      unrest: 0,
      military_pressure: 0,
      population: 10,
      status: "",
      stationed_army_ids: [],
    },
    {
      id: "xiangyang",
      name: "襄阳",
      province: "荆州",
      x: 48,
      y: 61,
      controller: "cao_cao",
      public_support: 50,
      unrest: 0,
      military_pressure: 0,
      population: 10,
      status: "",
      stationed_army_ids: [],
    },
  ]);
  assert.equal(blocks[0].province, "荆州");
  assert.match(blocks[0].d, /^M/);
  assert.deepEqual(
    blocks[0].nodes.map((node) => node.name),
    ["江夏", "襄阳"],
  );
});

test("主游戏州块使用标注项目导出的真实州界路径", () => {
  const blocks = getProvinceBlocks([
    {
      id: "chengdu",
      name: "成都",
      province: "益州",
      x: 40,
      y: 68,
      controller: "liu_zhang",
      public_support: 50,
      unrest: 0,
      military_pressure: 0,
      population: 10,
      status: "",
      stationed_army_ids: [],
    },
  ]);

  assert.equal(blocks[0].d, annotated.PROVINCE_BLOCKS["益州"].d);
  assert.equal(Object.keys(annotated.PROVINCE_BLOCKS).length, 13);
});

test("地图交互图层固定为州、郡、城池与势力范围，默认进入州图层", () => {
  assert.deepEqual(MAP_LAYERS, ["province", "commandery", "city", "influence"]);
  assert.equal(DEFAULT_MAP_LAYER, "province");
});

function svgPathArea(path: string) {
  const polygons = Array.from(
    path.matchAll(/M ([\d.-]+) ([\d.-]+)((?: L [\d.-]+ [\d.-]+)+) Z/g),
  ).map((match) => {
    const points = [
      [Number(match[1]), Number(match[2])],
      ...Array.from(match[3].matchAll(/L ([\d.-]+) ([\d.-]+)/g)).map(
        (point) => [Number(point[1]), Number(point[2])],
      ),
    ];
    return Math.abs(
      points.reduce((sum, point, index) => {
        const next = points[(index + 1) % points.length];
        return sum + point[0] * next[1] - next[0] * point[1];
      }, 0) / 2,
    );
  });
  return polygons.reduce((sum, area) => sum + area, 0);
}

function svgPathContainsPoint(path: string, x: number, y: number) {
  const polygons = Array.from(
    path.matchAll(/M ([\d.-]+) ([\d.-]+)((?: L [\d.-]+ [\d.-]+)+) Z/g),
  ).map((match) => [
    [Number(match[1]), Number(match[2])],
    ...Array.from(match[3].matchAll(/L ([\d.-]+) ([\d.-]+)/g)).map(
      (point) => [Number(point[1]), Number(point[2])],
    ),
  ]);
  return polygons.some((points) => {
    let inside = false;
    for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
      const [xi, yi] = points[i];
      const [xj, yj] = points[j];
      if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi)
        inside = !inside;
    }
    return inside;
  });
}

test("扬州当前可玩五郡每座城的固定锚点都严格落在自己的城池辖区内", () => {
  const base = { province: "扬州", x: 0, y: 0, controller: "", public_support: 50, unrest: 0, military_pressure: 0, population: 100, status: "", stationed_army_ids: [] };
  const boundaries = getCommanderyBoundaryBlocks([
    { ...base, id: "danyang", name: "丹阳" },
    { ...base, id: "jiujiang", name: "九江" },
    { ...base, id: "wu", name: "吴郡" },
    { ...base, id: "kuaiji", name: "会稽" },
    { ...base, id: "yuzhang", name: "豫章" },
  ]);
  const cities = getCityTerritoryBlocks([
    { id: "city:jianye", name: "秣陵", commandery_id: "danyang", province_id: "扬州", x: 0, y: 0, is_commandery_capital: true },
    { id: "city:wuhu", name: "芜湖", commandery_id: "danyang", province_id: "扬州", x: 0, y: 0, is_commandery_capital: false },
    { id: "city:shouchun", name: "寿春", commandery_id: "jiujiang", province_id: "扬州", x: 0, y: 0, is_commandery_capital: true },
    { id: "city:hefei", name: "合肥", commandery_id: "jiujiang", province_id: "扬州", x: 0, y: 0, is_commandery_capital: false },
    { id: "city:wanling", name: "宛陵", commandery_id: "danyang", province_id: "扬州", x: 0, y: 0, is_commandery_capital: true },
    { id: "city:wu", name: "吴", commandery_id: "wu", province_id: "扬州", x: 0, y: 0, is_commandery_capital: true },
    { id: "city:qu-e", name: "曲阿", commandery_id: "wu", province_id: "扬州", x: 0, y: 0, is_commandery_capital: false },
    { id: "city:kuaiji", name: "山阴", commandery_id: "kuaiji", province_id: "扬州", x: 0, y: 0, is_commandery_capital: true },
    { id: "city:nanchang", name: "南昌", commandery_id: "yuzhang", province_id: "扬州", x: 0, y: 0, is_commandery_capital: true },
    { id: "city:chaisang", name: "柴桑", commandery_id: "yuzhang", province_id: "扬州", x: 0, y: 0, is_commandery_capital: false },
  ], boundaries);
  assert.equal(cities.length, 10);
  assert.ok(cities.every((city) => city.hasHistoricalAnchor));
  for (const city of cities) {
    assert.ok(
      svgPathContainsPoint(city.d, city.cx, city.cy),
      `${city.city.id} 的锚点必须落在自己的辖区内`,
    );
  }
  assert.deepEqual(
    cities.filter((city) => ["city:wu", "city:qu-e"].includes(city.city.id)).map((city) => ({ id: city.city.id, x: city.cx, y: city.cy })),
    [{ id: "city:wu", x: 1440, y: 710 }, { id: "city:qu-e", x: 1420, y: 755 }],
  );
});

test("交州龙编与广信均固定在合并后城池辖区的腹地", () => {
  const base = { province: "交州", x: 0, y: 0, controller: "", public_support: 50, unrest: 0, military_pressure: 0, population: 100, status: "", stationed_army_ids: [] };
  const boundaries = getCommanderyBoundaryBlocks([
    { ...base, id: "jiaozhi", name: "交趾" }, { ...base, id: "cangwu", name: "苍梧" },
  ]);
  const cities = getCityTerritoryBlocks([
    { id: "city:jiaozhi", name: "羸娄", commandery_id: "jiaozhi", province_id: "交州", x: 0, y: 0, is_commandery_capital: true },
    { id: "city:longbian", name: "龙编", commandery_id: "jiaozhi", province_id: "交州", x: 0, y: 0, is_commandery_capital: false },
    { id: "city:guangxin", name: "广信", commandery_id: "cangwu", province_id: "交州", x: 0, y: 0, is_commandery_capital: true },
    { id: "city:wuzhou", name: "猛陵", commandery_id: "cangwu", province_id: "交州", x: 0, y: 0, is_commandery_capital: false },
  ], boundaries);
  assert.deepEqual(
    cities.filter((city) => ["city:longbian", "city:guangxin"].includes(city.city.id)).map((city) => ({ id: city.city.id, x: city.cx, y: city.cy })),
    [{ id: "city:longbian", x: 780, y: 945 }, { id: "city:guangxin", x: 1035, y: 890 }],
  );
  assert.ok(cities.every((city) => svgPathContainsPoint(city.d, city.cx, city.cy)));
});

test("徐州只保留彭城、下邳、广陵三座城，城池辖区即母郡范围", () => {
  const base = { province: "徐州", x: 0, y: 0, controller: "", public_support: 50, unrest: 0, military_pressure: 0, population: 100, status: "", stationed_army_ids: [] };
  const boundaries = getCommanderyBoundaryBlocks([
    { ...base, id: "xiapi", name: "下邳" }, { ...base, id: "guangling", name: "广陵" },
    { ...base, id: "pengcheng", name: "彭城" },
  ]);
  const cities = getCityTerritoryBlocks([
    { id: "city:xiapi", name: "下邳", commandery_id: "xiapi", province_id: "徐州", x: 0, y: 0, is_commandery_capital: true },
    { id: "city:guangling", name: "广陵", commandery_id: "guangling", province_id: "徐州", x: 0, y: 0, is_commandery_capital: true },
    { id: "city:pengcheng", name: "彭城", commandery_id: "pengcheng", province_id: "徐州", x: 0, y: 0, is_commandery_capital: true },
  ], boundaries);
  assert.equal(cities.length, 3);
  assert.ok(cities.every((city) => city.hasHistoricalAnchor && svgPathContainsPoint(city.d, city.cx, city.cy)));
});

test("青州两块主郡界内的补城锚点均不越界", () => {
  const base = { province: "青州", x: 0, y: 0, controller: "", public_support: 50, unrest: 0, military_pressure: 0, population: 100, status: "", stationed_army_ids: [] };
  const boundaries = getCommanderyBoundaryBlocks([{ ...base, id: "linzi", name: "临淄" }, { ...base, id: "beihai", name: "北海" }]);
  const cities = getCityTerritoryBlocks([
    { id: "city:linzi", name: "临淄", commandery_id: "linzi", province_id: "青州", x: 0, y: 0, is_commandery_capital: true },
    { id: "city:ju", name: "莒", commandery_id: "linzi", province_id: "青州", x: 0, y: 0, is_commandery_capital: false },
    { id: "city:dongpingling", name: "东平陵", commandery_id: "linzi", province_id: "青州", x: 0, y: 0, is_commandery_capital: false },
    { id: "city:linji", name: "临济", commandery_id: "beihai", province_id: "青州", x: 0, y: 0, is_commandery_capital: true },
  ], boundaries);
  assert.equal(cities.length, 4);
  assert.ok(cities.every((city) => city.hasHistoricalAnchor && svgPathContainsPoint(city.d, city.cx, city.cy)));
});

test("豫州只保留三座主城，锚点均在自己母郡腹地", () => {
  const base = { province: "豫州", x: 0, y: 0, controller: "", public_support: 50, unrest: 0, military_pressure: 0, population: 100, status: "", stationed_army_ids: [] };
  const boundaries = getCommanderyBoundaryBlocks([
    { ...base, id: "xuchang", name: "许昌/颍川" },
    { ...base, id: "runan", name: "汝南" },
    { ...base, id: "qiaoxian", name: "沛国" },
  ]);
  const cities = getCityTerritoryBlocks([
    { id: "city:xuchang", name: "许", commandery_id: "xuchang", province_id: "豫州", x: 0, y: 0, is_commandery_capital: true },
    { id: "city:runan", name: "平舆", commandery_id: "runan", province_id: "豫州", x: 0, y: 0, is_commandery_capital: true },
    { id: "city:qiaoxian", name: "相", commandery_id: "qiaoxian", province_id: "豫州", x: 0, y: 0, is_commandery_capital: true },
  ], boundaries);
  assert.equal(cities.length, 3);
  assert.ok(cities.every((city) => city.hasHistoricalAnchor && svgPathContainsPoint(city.d, city.cx, city.cy)));
});

test("兖州只保留陈留、东郡两座主城，泰山范围并入濮阳辖区", () => {
  const base = { province: "兖州", x: 0, y: 0, controller: "", public_support: 50, unrest: 0, military_pressure: 0, population: 100, status: "", stationed_army_ids: [] };
  const boundaries = getCommanderyBoundaryBlocks([
    { ...base, id: "chenliu", name: "陈留" },
    { ...base, id: "dongjun", name: "东郡/濮阳" },
  ]);
  const dongjun = boundaries.find((boundary) => boundary.node?.id === "dongjun");
  const cities = getCityTerritoryBlocks([
    { id: "city:chenliu", name: "陈留", commandery_id: "chenliu", province_id: "兖州", x: 0, y: 0, is_commandery_capital: true },
    { id: "city:dongjun", name: "濮阳", commandery_id: "dongjun", province_id: "兖州", x: 0, y: 0, is_commandery_capital: true },
  ], boundaries);
  assert.equal(cities.length, 2);
  assert.ok(cities.every((city) => city.hasHistoricalAnchor && svgPathContainsPoint(city.d, city.cx, city.cy)));
  assert.equal(dongjun?.d, `${ANNOTATED_CITY_BLOCKS["濮阳"].d} ${ANNOTATED_CITY_BLOCKS["泰山"].d}`);
});

test("司隶三块既有郡界各保留一座郡治，函谷关不再切分弘农城池辖区", () => {
  const base = { province: "司隶", x: 0, y: 0, controller: "", public_support: 50, unrest: 0, military_pressure: 0, population: 100, status: "", stationed_army_ids: [] };
  const boundaries = getCommanderyBoundaryBlocks([
    { ...base, id: "changan", name: "长安" },
    { ...base, id: "luoyang", name: "洛阳" },
    { ...base, id: "tongguan", name: "弘农/潼关" },
  ]);
  const cities = getCityTerritoryBlocks([
    { id: "city:changan", name: "长安", commandery_id: "changan", province_id: "司隶", x: 0, y: 0, is_commandery_capital: true },
    { id: "city:luoyang", name: "洛阳", commandery_id: "luoyang", province_id: "司隶", x: 0, y: 0, is_commandery_capital: true },
    { id: "city:tongguan", name: "弘农", commandery_id: "tongguan", province_id: "司隶", x: 0, y: 0, is_commandery_capital: true },
  ], boundaries);
  assert.equal(cities.length, 3);
  assert.ok(cities.every((city) => city.hasHistoricalAnchor && svgPathContainsPoint(city.d, city.cx, city.cy)));
  const hongnong = boundaries.find((boundary) => boundary.node?.id === "tongguan")!;
  const hongnongCity = cities.find((city) => city.city.id === "city:tongguan")!;
  assert.ok(Math.abs(svgPathArea(hongnongCity.d) - svgPathArea(hongnong.d)) < 0.2);
});

test("冀州只保留邺、常山、勃海三座主城，南皮与渤海两块合为勃海辖区", () => {
  const base = { province: "冀州", x: 0, y: 0, controller: "", public_support: 50, unrest: 0, military_pressure: 0, population: 100, status: "", stationed_army_ids: [] };
  const boundaries = getCommanderyBoundaryBlocks([
    { ...base, id: "ye", name: "邺" },
    { ...base, id: "changshan", name: "常山/中山" },
    { ...base, id: "nanpi", name: "南皮" },
  ]);
  const cities = getCityTerritoryBlocks([
    { id: "city:ye", name: "邺", commandery_id: "ye", province_id: "冀州", x: 0, y: 0, is_commandery_capital: true },
    { id: "city:changshan", name: "常山", commandery_id: "changshan", province_id: "冀州", x: 0, y: 0, is_commandery_capital: true },
    { id: "city:nanpi", name: "南皮", commandery_id: "nanpi", province_id: "冀州", x: 0, y: 0, is_commandery_capital: true },
  ], boundaries);
  const nanpi = boundaries.find((boundary) => boundary.node?.id === "nanpi")!;
  assert.equal(cities.length, 3);
  assert.ok(cities.every((city) => city.hasHistoricalAnchor && svgPathContainsPoint(city.d, city.cx, city.cy)));
  assert.deepEqual(
    cities.find((city) => city.city.id === "city:changshan") && {
      x: cities.find((city) => city.city.id === "city:changshan")!.cx,
      y: cities.find((city) => city.city.id === "city:changshan")!.cy,
    },
    { x: 1172, y: 334 },
  );
  assert.equal(nanpi.d, `${ANNOTATED_CITY_BLOCKS["南皮"].d} ${ANNOTATED_CITY_BLOCKS["渤海"].d}`);
});

test("并州六郡均复用北部大界拆出的曲折辖区，六座主城不再压缩为小碎片", () => {
  const base = { province: "并州", x: 0, y: 0, controller: "", public_support: 50, unrest: 0, military_pressure: 0, population: 100, status: "", stationed_army_ids: [] };
  const boundaries = getCommanderyBoundaryBlocks([
    { ...base, id: "taiyuan", name: "太原郡/晋阳" }, { ...base, id: "shangdang", name: "上党郡/长子" },
    { ...base, id: "jiuyuan", name: "五原郡/九原" }, { ...base, id: "yunzhong", name: "云中郡/云中" },
    { ...base, id: "xihe", name: "西河郡/离石" }, { ...base, id: "yanmen", name: "雁门郡/阴馆" },
  ]);
  const cities = getCityTerritoryBlocks([
    { id: "city:taiyuan", name: "晋阳", commandery_id: "taiyuan", province_id: "并州", x: 0, y: 0, is_commandery_capital: true },
    { id: "city:shangdang", name: "长子", commandery_id: "shangdang", province_id: "并州", x: 0, y: 0, is_commandery_capital: true },
    { id: "city:jiuyuan", name: "九原", commandery_id: "jiuyuan", province_id: "并州", x: 0, y: 0, is_commandery_capital: true },
    { id: "city:yunzhong", name: "云中", commandery_id: "yunzhong", province_id: "并州", x: 0, y: 0, is_commandery_capital: true },
    { id: "city:xihe", name: "离石", commandery_id: "xihe", province_id: "并州", x: 0, y: 0, is_commandery_capital: true },
    { id: "city:yanmen", name: "阴馆", commandery_id: "yanmen", province_id: "并州", x: 0, y: 0, is_commandery_capital: true },
  ], boundaries);
  assert.equal(boundaries.filter((boundary) => boundary.node).length, 6);
  assert.equal(cities.length, 6);
  for (const city of cities) {
    assert.ok(city.d.startsWith("M "));
    assert.ok(boundaries.find((boundary) => boundary.node?.id === city.city.commandery_id)?.d.startsWith("M "));
    assert.ok(city.hasHistoricalAnchor);
  }
  assert.deepEqual(
    cities.find((city) => city.city.id === "city:xihe") && {
      x: cities.find((city) => city.city.id === "city:xihe")!.cx,
      y: cities.find((city) => city.city.id === "city:xihe")!.cy,
    },
    { x: 928, y: 398 },
  );
});

test("凉州保留河西四郡与陇右两郡，酒泉和敦煌由旧张掖大块分出", () => {
  const base = { province: "凉州", x: 0, y: 0, controller: "", public_support: 50, unrest: 0, military_pressure: 0, population: 100, status: "", stationed_army_ids: [] };
  const boundaries = getCommanderyBoundaryBlocks([
    { ...base, id: "wuwei", name: "武威郡/姑臧" }, { ...base, id: "zhangye", name: "张掖郡" },
    { ...base, id: "jiuquan", name: "酒泉郡/禄福" }, { ...base, id: "dunhuang", name: "敦煌郡/敦煌" },
    { ...base, id: "tianshui", name: "汉阳郡/冀" }, { ...base, id: "longxi", name: "陇西郡/狄道" },
  ]);
  const cities = getCityTerritoryBlocks([
    { id: "city:wuwei", name: "姑臧", commandery_id: "wuwei", province_id: "凉州", x: 0, y: 0, is_commandery_capital: true },
    { id: "city:zhangye", name: "张掖", commandery_id: "zhangye", province_id: "凉州", x: 0, y: 0, is_commandery_capital: true },
    { id: "city:jiuquan", name: "禄福", commandery_id: "jiuquan", province_id: "凉州", x: 0, y: 0, is_commandery_capital: true },
    { id: "city:dunhuang", name: "敦煌", commandery_id: "dunhuang", province_id: "凉州", x: 0, y: 0, is_commandery_capital: true },
    { id: "city:tianshui", name: "冀", commandery_id: "tianshui", province_id: "凉州", x: 0, y: 0, is_commandery_capital: true },
    { id: "city:longxi", name: "狄道", commandery_id: "longxi", province_id: "凉州", x: 0, y: 0, is_commandery_capital: true },
  ], boundaries);
  assert.equal(boundaries.filter((boundary) => boundary.node).length, 6);
  assert.equal(cities.length, 6);
  assert.deepEqual(
    cities.filter((city) => ["city:zhangye", "city:tianshui", "city:jiuquan", "city:dunhuang"].includes(city.city.id)).map((city) => ({ id: city.city.id, x: city.cx, y: city.cy })),
    [
      { id: "city:zhangye", x: 570, y: 225 }, { id: "city:jiuquan", x: 470, y: 248 },
      { id: "city:dunhuang", x: 330, y: 248 }, { id: "city:tianshui", x: 840, y: 445 },
    ],
  );
});

test("幽州以广阳、涿、渔阳、右北平、辽西、辽东六郡承接北方可玩疆域", () => {
  const base = { province: "幽州", x: 0, y: 0, controller: "", public_support: 50, unrest: 0, military_pressure: 0, population: 100, status: "", stationed_army_ids: [] };
  const boundaries = getCommanderyBoundaryBlocks([
    { ...base, id: "ji", name: "广阳郡/蓟" }, { ...base, id: "zhuojun", name: "涿郡/涿" },
    { ...base, id: "yuyang", name: "渔阳郡" }, { ...base, id: "youbeiping", name: "右北平郡/土垠" },
    { ...base, id: "liaoxi", name: "辽西郡/阳乐" }, { ...base, id: "liaodong", name: "辽东郡/襄平" },
  ]);
  const cities = getCityTerritoryBlocks([
    { id: "city:ji", name: "蓟", commandery_id: "ji", province_id: "幽州", x: 0, y: 0, is_commandery_capital: true },
    { id: "city:zhuojun", name: "涿", commandery_id: "zhuojun", province_id: "幽州", x: 0, y: 0, is_commandery_capital: true },
    { id: "city:yuyang", name: "渔阳", commandery_id: "yuyang", province_id: "幽州", x: 0, y: 0, is_commandery_capital: true },
    { id: "city:youbeiping", name: "土垠", commandery_id: "youbeiping", province_id: "幽州", x: 0, y: 0, is_commandery_capital: true },
    { id: "city:liaoxi", name: "阳乐", commandery_id: "liaoxi", province_id: "幽州", x: 0, y: 0, is_commandery_capital: true },
    { id: "city:liaodong", name: "襄平", commandery_id: "liaodong", province_id: "幽州", x: 0, y: 0, is_commandery_capital: true },
  ], boundaries);
  assert.equal(boundaries.filter((boundary) => boundary.node).length, 6);
  assert.equal(cities.length, 6);
  assert.ok(cities.every((city) => city.hasHistoricalAnchor && svgPathContainsPoint(city.d, city.cx, city.cy)));
  assert.deepEqual(
    cities.filter((city) => ["city:yuyang", "city:liaoxi"].includes(city.city.id)).map((city) => ({ id: city.city.id, x: city.cx, y: city.cy })),
    [{ id: "city:yuyang", x: 1400, y: 235 }, { id: "city:liaoxi", x: 1480, y: 285 }],
  );
});

test("城池辖区按真实 city_id 将所属郡界无重叠地完全瓜分，不以郡级资源重复计数", () => {
  const nodes = [
    {
      id: "jiangxia",
      name: "江夏",
      province: "荆州",
      x: 66,
      y: 57,
      controller: "liu_qi",
      public_support: 55,
      unrest: 10,
      military_pressure: 60,
      population: 100,
      status: "",
      stationed_army_ids: [],
    },
  ];
  const cities = getCityTerritoryBlocks(
    [
      {
        id: "city:jiangxia",
        name: "西陵",
        commandery_id: "jiangxia",
        province_id: "荆州",
        province: "荆州",
        x: 66,
        y: 57,
        controller: "liu_qi",
        strategic_role: "郡治城",
        is_commandery_capital: true,
        fortification: 70,
        grain_stock: 80,
        siege_status: "未围",
        population: 100,
        public_support: 55,
        unrest: 10,
        military_pressure: 60,
        status: "",
        stationed_army_ids: [],
      },
      {
        id: "city:xiakou",
        name: "夏口",
        commandery_id: "jiangxia",
        province_id: "荆州",
        province: "荆州",
        x: 67,
        y: 56,
        controller: "liu_qi",
        strategic_role: "港埠",
        is_commandery_capital: false,
        fortification: 45,
        grain_stock: 30,
        siege_status: "未围",
        population: 100,
        public_support: 55,
        unrest: 10,
        military_pressure: 60,
        status: "",
        stationed_army_ids: [],
      },
    ],
    getCommanderyBoundaryBlocks(nodes),
  );
  assert.equal(cities.length, 2);
  assert.notEqual(cities[0].d, cities[1].d);
  assert.match(cities[0].d, /^M /);
  assert.match(cities[0].boundaryD, / Q /);
  const boundary = getCommanderyBoundaryBlocks(nodes).find(
    (block) => block.node?.id === "jiangxia",
  )!;
  assert.ok(
    Math.abs(
      svgPathArea(cities[0].d) +
        svgPathArea(cities[1].d) -
        svgPathArea(boundary.d),
    ) < 0.2,
  );
});

test("益州永安郡以固定峡江锚点分出永安与白帝，不再使用临时偏移", () => {
  const boundary = getCommanderyBoundaryBlocks([
    {
      id: "yongan",
      name: "永安/白帝",
      province: "益州",
      x: 60,
      y: 70,
      controller: "liu_zhang",
      public_support: 50,
      unrest: 0,
      military_pressure: 0,
      population: 10,
      status: "",
      stationed_army_ids: [],
    },
  ]);
  const cities = getCityTerritoryBlocks(
    [
      {
        id: "city:yongan",
        name: "永安",
        commandery_id: "yongan",
        province_id: "益州",
        province: "益州",
        x: 60,
        y: 70,
        controller: "liu_zhang",
        strategic_role: "关隘治所",
        is_commandery_capital: true,
        fortification: 70,
        grain_stock: 80,
        siege_status: "未围",
        population: 10,
        public_support: 50,
        unrest: 0,
        military_pressure: 0,
        status: "",
        stationed_army_ids: [],
      },
      {
        id: "city:baidi",
        name: "白帝",
        commandery_id: "yongan",
        province_id: "益州",
        province: "益州",
        x: 61,
        y: 69,
        controller: "liu_zhang",
        strategic_role: "关隘",
        is_commandery_capital: false,
        fortification: 70,
        grain_stock: 80,
        siege_status: "未围",
        population: 10,
        public_support: 50,
        unrest: 0,
        military_pressure: 0,
        status: "",
        stationed_army_ids: [],
      },
    ],
    boundary,
  );
  assert.deepEqual(
    cities.map((city) => [city.city.id, city.cx, city.cy]),
    [
      ["city:yongan", 888, 675],
      ["city:baidi", 927, 655],
    ],
  );
  assert.ok(cities.every((city) => city.hasHistoricalAnchor));
  assert.ok(cities.every((city) => svgPathArea(city.d) > 100));
});

test("主地图文字由程序图层接管，不再依赖底图文字", () => {
  assert.deepEqual(STATIC_MAP_LABEL_POLICY, {
    provinceLabels: "overlay",
    commanderyLabels: "overlay",
    cityLabels: "overlay",
  });
});

test("城镇交互块按游戏节点名称匹配标注边界，未入局标注不会参与点击", () => {
  const cityBlocks = getCityInteractionBlocks([
    {
      id: "chengdu",
      name: "成都/蜀郡",
      province: "益州",
      x: 40,
      y: 68,
      controller: "liu_zhang",
      public_support: 50,
      unrest: 0,
      military_pressure: 0,
      population: 10,
      status: "",
      stationed_army_ids: [],
    },
    {
      id: "jiangling",
      name: "江陵",
      province: "荆州",
      x: 55,
      y: 68,
      controller: "liu_qi",
      public_support: 50,
      unrest: 0,
      military_pressure: 0,
      population: 10,
      status: "",
      stationed_army_ids: [],
    },
    {
      id: "unknown",
      name: "不存在",
      province: "益州",
      x: 1,
      y: 1,
      controller: "liu_zhang",
      public_support: 50,
      unrest: 0,
      military_pressure: 0,
      population: 10,
      status: "",
      stationed_army_ids: [],
    },
  ]);

  assert.deepEqual(
    cityBlocks.map((block) => block.city),
    ["成都", "江陵"],
  );
  assert.equal(cityBlocks[0].d, annotated.CITY_BLOCKS["成都"].d);
  assert.equal(cityBlocks[0].node.id, "chengdu");
});

test("郡域边界覆盖标注里的常用重要郡，但不会给无游戏节点郡伪造城镇节点", () => {
  const boundaryBlocks = getCommanderyBoundaryBlocks([
    {
      id: "chengdu",
      name: "成都/蜀郡",
      province: "益州",
      x: 40,
      y: 68,
      controller: "liu_zhang",
      public_support: 50,
      unrest: 0,
      military_pressure: 0,
      population: 10,
      status: "",
      stationed_army_ids: [],
    },
    {
      id: "jiangling",
      name: "江陵",
      province: "荆州",
      x: 55,
      y: 68,
      controller: "liu_qi",
      public_support: 50,
      unrest: 0,
      military_pressure: 0,
      population: 10,
      status: "",
      stationed_army_ids: [],
    },
  ]);

  assert.equal(
    boundaryBlocks.length,
    // 汉中、牂牁、南郡、长沙、豫章、丹阳、东郡、勃海、交趾、南海各合并一组原手绘块。
    Object.keys(ANNOTATED_CITY_BLOCKS).length - 10,
  );
  assert.equal(
    boundaryBlocks.filter((block) => block.commanderyName === "牂牁郡").length,
    1,
  );
  assert.equal(
    boundaryBlocks.find((block) => block.city === "成都")?.node?.id,
    "chengdu",
  );
  assert.equal(
    boundaryBlocks.find((block) => block.city === "梓潼")?.node,
    undefined,
  );
  assert.ok(boundaryBlocks.some((block) => block.city === "九真"));
  assert.ok(boundaryBlocks.some((block) => block.city === "交趾"));
  assert.equal(boundaryBlocks.some((block) => block.city === "日南"), false);
  assert.ok(boundaryBlocks.some((block) => block.city === "番禺"));
  assert.equal(boundaryBlocks.some((block) => block.city === "桂阳"), false);
  assert.equal(
    boundaryBlocks.find((block) => block.city === "梓潼")?.d,
    annotated.CITY_BLOCKS["梓潼"].d,
  );
  assert.equal(
    boundaryBlocks.some((block) => block.city === "上庸"),
    false,
  );
});

test("牂牁郡只保留一条郡界，夜郎与且兰归同一郡城池范围", () => {
  const blocks = getCommanderyBoundaryBlocks([
    {
      id: "yelang",
      name: "夜郎",
      province: "益州",
      x: 38,
      y: 80,
      controller: "liu_zhang",
      public_support: 50,
      unrest: 0,
      military_pressure: 0,
      population: 10,
      status: "",
      stationed_army_ids: [],
    },
    {
      id: "qielan",
      name: "且兰",
      province: "益州",
      x: 42,
      y: 73,
      controller: "liu_zhang",
      public_support: 50,
      unrest: 0,
      military_pressure: 0,
      population: 10,
      status: "",
      stationed_army_ids: [],
    },
  ]);
  assert.equal(
    blocks.filter((block) => block.commanderyName === "牂牁郡").length,
    1,
  );
  const cities = getCityTerritoryBlocks(
    [
      {
        id: "city:yelang",
        name: "夜郎",
        commandery_id: "yelang",
        province_id: "益州",
        province: "益州",
        x: 38,
        y: 80,
        controller: "liu_zhang",
        strategic_role: "郡治城",
        is_commandery_capital: true,
        fortification: 50,
        grain_stock: 10,
        siege_status: "未围",
        population: 10,
        public_support: 50,
        unrest: 0,
        military_pressure: 0,
        status: "",
        stationed_army_ids: [],
      },
      {
        id: "city:qielan",
        name: "且兰",
        commandery_id: "yelang",
        province_id: "益州",
        province: "益州",
        x: 42,
        y: 73,
        controller: "liu_zhang",
        strategic_role: "关隘",
        is_commandery_capital: false,
        fortification: 50,
        grain_stock: 10,
        siege_status: "未围",
        population: 10,
        public_support: 50,
        unrest: 0,
        military_pressure: 0,
        status: "",
        stationed_army_ids: [],
      },
    ],
    blocks,
  );
  assert.equal(cities.length, 2);
  assert.ok(cities.every((city) => svgPathArea(city.d) > 100));
});

test("208年八月南郡复用江陵与襄阳原手绘郡界，四城只在该母范围内分割", () => {
  const nodes = [
    { id: "jiangling", name: "江陵/南郡", province: "荆州" },
    { id: "xiangyang", name: "襄阳", province: "荆州" },
  ].map((node) => ({
    ...node, x: 0, y: 0, controller: "", public_support: 50, unrest: 0,
    military_pressure: 0, population: 100, status: "", stationed_army_ids: [],
  }));
  const blocks = getCommanderyBoundaryBlocks(nodes);
  const nanjun = blocks.find((block) => block.city === "南郡");
  assert.ok(nanjun);
  assert.equal(nanjun?.commanderyName, "南郡");
  assert.equal(nanjun?.d, `${ANNOTATED_CITY_BLOCKS["江陵"].d} ${ANNOTATED_CITY_BLOCKS["襄阳"].d}`);
  const cities = getCityTerritoryBlocks([
    { id: "city:jiangling", name: "江陵", commandery_id: "jiangling", province_id: "荆州", x: 60, y: 65, is_commandery_capital: true },
    { id: "city:xiangyang", name: "襄阳", commandery_id: "jiangling", province_id: "荆州", x: 60, y: 55, is_commandery_capital: false },
    { id: "city:fancheng", name: "樊城", commandery_id: "jiangling", province_id: "荆州", x: 61, y: 55, is_commandery_capital: false },
    { id: "city:yiling", name: "夷陵", commandery_id: "jiangling", province_id: "荆州", x: 48, y: 66, is_commandery_capital: false },
  ], blocks);
  assert.equal(cities.length, 4);
  assert.ok(cities.every((city) => city.hasHistoricalAnchor && svgPathArea(city.d) > 1));
});

test("长沙唯一城池完整承接长沙与零陵的合并郡界，不生成伪造内部城界", () => {
  const base = { province: "荆州", x: 0, y: 0, controller: "", public_support: 50, unrest: 0, military_pressure: 0, population: 100, status: "", stationed_army_ids: [] };
  const blocks = getCommanderyBoundaryBlocks([{ ...base, id: "jingnan", name: "长沙" }]);
  const changsha = blocks.find((block) => block.node?.id === "jingnan")!;
  const cities = getCityTerritoryBlocks([
    { id: "city:jingnan", name: "长沙", commandery_id: "jingnan", province_id: "荆州", x: 0, y: 0, is_commandery_capital: true },
  ], blocks);
  assert.equal(changsha.d, `${ANNOTATED_CITY_BLOCKS["长沙"].d} ${ANNOTATED_CITY_BLOCKS["零陵"].d}`);
  assert.equal(cities[0].d, changsha.d);
  assert.equal(cities[0].boundaryD, "");
});

test("郡图层渲染所有标注郡界，城镇图层为每个郡补一个历史城镇点位", () => {
  const nodes = [
    {
      id: "wuwei",
      name: "武威",
      province: "凉州",
      x: 0,
      y: 0,
      controller: "",
      public_support: 50,
      unrest: 0,
      military_pressure: 0,
      population: 100,
      status: "",
      stationed_army_ids: [],
    },
    {
      id: "jianye",
      name: "建业",
      province: "扬州",
      x: 0,
      y: 0,
      controller: "",
      public_support: 50,
      unrest: 0,
      military_pressure: 0,
      population: 100,
      status: "",
      stationed_army_ids: [],
    },
  ];

  const commanderyBlocks = getCommanderyBoundaryBlocks(nodes);
  const townBlocks = getTownBlocks(nodes);

  assert.equal(
    commanderyBlocks.length,
    Object.keys(ANNOTATED_CITY_BLOCKS).length - 10,
  );
  assert.equal(
    commanderyBlocks.find((block) => block.city === "丹阳")?.commanderyName,
    "丹阳郡",
  );
  assert.equal(
    commanderyBlocks.find((block) => block.city === "蓟县")?.commanderyName,
    "广阳郡",
  );
  assert.equal(
    commanderyBlocks.find((block) => block.city === "濮阳")?.commanderyName,
    "东郡",
  );
  // 以当前地图事实层为准，补入的郡城必须计入城镇图层。
  assert.equal(townBlocks.length, Object.keys(ANNOTATED_CITY_BLOCKS).length - 2);
  assert.equal(townBlocks.some((block) => block.city === "日南"), false);
  assert.equal(townBlocks.some((block) => block.city === "桂阳"), false);
  assert.equal(
    townBlocks.find((block) => block.townName === "姑藏")?.node?.id,
    "wuwei",
  );
  assert.equal(
    townBlocks.find((block) => block.townName === "秣陵")?.node?.id,
    "jianye",
  );
  assert.equal(
    townBlocks.find((block) => block.townName === "梓潼")?.node,
    undefined,
  );
  assert.equal(
    townBlocks.find((block) => block.townName === "梓潼")?.townKind,
    "historical-town",
  );
  assert.equal(
    townBlocks.find((block) => block.townName === "姑藏")?.townKind,
    "game-city",
  );
});

test("郡图层默认边界合并为唯一线段路径，避免相邻郡重复描边", () => {
  const boundaryBlocks = getCommanderyBoundaryBlocks([]);
  const sharedPath = getSharedCityBoundaryPath(boundaryBlocks);
  const segments =
    sharedPath.match(
      /M -?\d+ -?\d+ (?:L -?\d+ -?\d+|Q -?\d+ -?\d+ -?\d+ -?\d+)/g,
    ) || [];

  assert.match(sharedPath, /^M -?\d+ -?\d+ (?:L|Q) /);
  assert.match(sharedPath, / Q /);
  assert.equal(new Set(segments).size, segments.length);
});

test("郡域悬停描边复用共享墨线的曲线段，不退化为直线多边形", () => {
  const block = getCommanderyBoundaryBlocks([]).find(
    (candidate) => candidate.city === "江夏",
  )!;
  const hoveredPath = getCurvedCommanderyBoundaryPath(block);
  const sharedPath = getSharedCityBoundaryPath([block]);

  assert.equal(hoveredPath, sharedPath);
  assert.match(hoveredPath, / Q /);
  assert.notEqual(hoveredPath, block.d);
});

test("补强城池进入游戏节点后会从边界-only 转为可点击城池", () => {
  const strategicNodes = [
    "九原",
    "南皮",
    "谯县",
    "宛城",
    "梓潼",
    "上庸",
    "夜郎",
    "且兰",
  ].map((name) => ({
    id: name,
    name,
    province: annotated.CITY_BLOCKS[name].province,
    x: 0,
    y: 0,
    controller: "",
    public_support: 50,
    unrest: 0,
    military_pressure: 0,
    population: 100,
    status: "",
    stationed_army_ids: [],
  }));

  const blocks = getCityBoundaryBlocks(strategicNodes);

  assert.deepEqual(
    new Set(
      blocks
        .filter((block) =>
          strategicNodes.some((node) => node.name === block.city),
        )
        .map((block) => block.city),
    ),
    new Set(["梓潼", "上庸", "夜郎", "且兰", "宛城", "谯县", "九原", "南皮"]),
  );
  assert.equal(blocks.filter((block) => block.node).length, 8);
});

test("第二批严谨补强城池均有可交互标注边界", () => {
  const strategicNames = [
    "张掖",
    "天水",
    "北海",
    "广陵",
    "交趾",
    "会稽",
    "吴郡",
    "长沙/荆南",
    "涿郡",
    "右北平",
    "泰山",
    "彭城",
  ];
  const strategicNodes = strategicNames.map((name) => ({
    id: name,
    name,
    province: "",
    x: 0,
    y: 0,
    controller: "",
    public_support: 50,
    unrest: 0,
    military_pressure: 0,
    population: 100,
    status: "",
    stationed_army_ids: [],
  }));

  const blocks = getCityBoundaryBlocks(strategicNodes);

  assert.deepEqual(
    strategicNames.map((name) => resolveAnnotatedCityName(name)),
    [
      "张掖",
      "天水",
      "北海",
      "广陵",
      "交趾",
      "会稽",
      "吴郡",
      "长沙",
      "涿郡",
      "右北平",
      "泰山",
      "彭城",
    ],
  );
  assert.deepEqual(
    new Set(blocks.filter((block) => block.node).map((block) => block.city)),
    new Set([
      "张掖",
      "天水",
      "涿郡",
      "右北平",
      "北海",
      "泰山",
      "彭城",
      "广陵",
      "长沙",
      "吴郡",
      "会稽",
      "交趾",
    ]),
  );
});

test("复合地名和明确历史别名会映射到标注城镇名", () => {
  assert.equal(resolveAnnotatedCityName("成都/蜀郡"), "成都");
  assert.equal(resolveAnnotatedCityName("江陵/南郡"), "江陵");
  assert.equal(resolveAnnotatedCityName("合肥/庐江"), "合肥");
  assert.equal(resolveAnnotatedCityName("邺"), "邺城");
  assert.equal(resolveAnnotatedCityName("蓟"), "蓟县");
  assert.equal(resolveAnnotatedCityName("武威"), "姑藏");
  assert.equal(resolveAnnotatedCityName("建业"), "秣陵");
  assert.equal(resolveAnnotatedCityName("汉中"), "南郑");
  assert.equal(resolveAnnotatedCityName("不存在"), null);
});

test("主操作页非游戏节点城池会接入代表游戏节点", () => {
  const strategicNodes = [
    { id: "jingnan", name: "长沙/荆南", province: "荆州" },
    { id: "yuzhang", name: "豫章", province: "扬州" },
    { id: "danyang", name: "丹阳", province: "扬州" },
    { id: "nanhai", name: "南海", province: "交州" },
    { id: "cangwu", name: "苍梧", province: "交州" },
    { id: "yulin", name: "郁林", province: "交州" },
    { id: "hepu", name: "合浦", province: "交州" },
  ].map((node) => ({
    ...node,
    x: 0,
    y: 0,
    controller: "",
    public_support: 50,
    unrest: 0,
    military_pressure: 0,
    population: 100,
    status: "",
    stationed_army_ids: [],
  }));

  const townBlocks = getTownBlocks(strategicNodes);
  const commanderyBlocks = getCommanderyBoundaryBlocks(strategicNodes);
  const expected = new Map([
    ["武陵", "jingnan"],
    ["豫章", "yuzhang"],
    ["丹阳", "danyang"],
    ["合浦", "hepu"],
    ["苍梧", "cangwu"],
    ["郁林", "yulin"],
  ]);

  for (const [city, nodeId] of expected) {
    assert.equal(
      townBlocks.find((block) => block.city === city)?.node?.id,
      nodeId,
    );
    assert.equal(
      townBlocks.find((block) => block.city === city)?.townKind,
      "game-city",
    );
    assert.equal(
      commanderyBlocks.find((block) => block.city === city)?.node?.id,
      nodeId,
    );
  }
});
