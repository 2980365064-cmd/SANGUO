import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import vm from "node:vm";
import polygonClipping from "polygon-clipping";

const source = fs.readFileSync(new URL("../public/annotation_path_utils.js", import.meta.url), "utf8");
const sandbox = { window: {} };
vm.runInNewContext(source, sandbox);
const { getCityBoundaryPoints, orderPolygonPoints, pathSelfIntersectionCount, pointsToSvgPath, provincePointsToSvgPath } = sandbox.window.annotationPathUtils;

function pathToPoints(path) {
  const values = path.match(/[ML] \d+ \d+/g) || [];
  return values.map((item) => {
    const [, x, y] = item.split(" ");
    return { x: Number(x), y: Number(y) };
  });
}

function maxEdgeLength(points) {
  return points.reduce((max, point, index) => {
    const next = points[(index + 1) % points.length];
    return Math.max(max, Math.hypot(point.x - next.x, point.y - next.y));
  }, 0);
}

function maxStraightRun(points) {
  let run = 0;
  let maxRun = 0;
  for (let i = 0; i < points.length; i += 1) {
    const a = points[i];
    const b = points[(i + 1) % points.length];
    const c = points[(i + 2) % points.length];
    const ab = Math.hypot(b.x - a.x, b.y - a.y);
    const bc = Math.hypot(c.x - b.x, c.y - b.y);
    if (!ab || !bc) continue;
    const cos = ((b.x - a.x) * (c.x - b.x) + (b.y - a.y) * (c.y - b.y)) / (ab * bc);
    if (cos > 0.996) {
      run += ab;
    } else {
      maxRun = Math.max(maxRun, run + ab);
      run = 0;
    }
  }
  return Math.max(maxRun, run);
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

function orientation(a, b, c) {
  return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
}

function properSegmentsIntersect(a, b, c, d) {
  return orientation(a, b, c) * orientation(a, b, d) < 0 && orientation(c, d, a) * orientation(c, d, b) < 0;
}

function ringArea(ring) {
  let area = 0;
  for (let i = 0; i < ring.length - 1; i += 1) {
    area += ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1];
  }
  return Math.abs(area) / 2;
}

function toMultiPolygon(points) {
  const ring = points.map((point) => [point.x, point.y]);
  ring.push(ring[0]);
  return [[ring]];
}

function polygonsHaveForbiddenOverlap(a, b) {
  const overlap = polygonClipping.intersection(toMultiPolygon(a), toMultiPolygon(b));
  const area = overlap.reduce((sum, polygon) => sum + ringArea(polygon[0]), 0);
  return area > 1;
}

function segmentSamplesStayInsideProvince(cityPoints, provincePoints) {
  return cityPoints.every((point, index) => {
    const next = cityPoints[(index + 1) % cityPoints.length];
    return [0.25, 0.5, 0.75].every((t) => pointInPolygon({
      x: point.x + (next.x - point.x) * t,
      y: point.y + (next.y - point.y) * t,
    }, provincePoints, 1.5));
  });
}

test("益州城池乱序标注点会整理成无自交 SVG 路径", () => {
  const data = JSON.parse(fs.readFileSync(new URL("../public/annotation_data.json", import.meta.url), "utf8"));
  const yiCities = ["成都", "梓潼", "江州", "南郑", "上庸"];

  for (const city of yiCities) {
    const ordered = orderPolygonPoints(data.cityPoints[city]);
    assert.ok(ordered.length >= 3, `${city} should keep enough boundary points`);
    assert.equal(pathSelfIntersectionCount(ordered), 0, `${city} should not contain crossing edges`);
    assert.match(pointsToSvgPath(data.cityPoints[city]), /^M \d+ \d+ L /);
  }
});

test("导出的益州城池 SVG 常量不再包含交叉边", async () => {
  const { CITY_BLOCKS } = await import("../public/标注数据_SVG.js");

  for (const city of ["成都", "梓潼", "江州", "南郑", "上庸"]) {
    assert.equal(pathSelfIntersectionCount(pathToPoints(CITY_BLOCKS[city].d)), 0, `${city} exported path should not cross itself`);
  }
});

test("导出的益州城池 SVG 常量不包含成都到上庸式长跳线", async () => {
  const { CITY_BLOCKS } = await import("../public/标注数据_SVG.js");

  for (const city of ["成都", "梓潼", "江州", "南郑", "上庸"]) {
    assert.ok(maxEdgeLength(pathToPoints(CITY_BLOCKS[city].d)) < 80, `${city} exported path should not contain long jump edges`);
  }
});

test("导出的所有城池 SVG 常量不包含离群点长跳边", async () => {
  const { CITY_BLOCKS } = await import("../public/标注数据_SVG.js");

  for (const [city, block] of Object.entries(CITY_BLOCKS)) {
    assert.ok(maxEdgeLength(pathToPoints(block.d)) < 90, `${city} exported path should not contain long jump edges`);
  }
  assert.doesNotMatch(CITY_BLOCKS["宛城"].d, /777 657/);
});

test("新增城池边界避免算法切分造成的长直线", async () => {
  const { CITY_BLOCKS } = await import("../public/标注数据_SVG.js");
  const addedCities = ["张掖", "天水", "北海", "广陵", "交趾", "会稽", "吴郡", "长沙", "涿郡", "右北平", "泰山", "彭城"];

  for (const city of addedCities) {
    assert.ok(maxStraightRun(pathToPoints(CITY_BLOCKS[city].d)) < 240, `${city} should not keep an excessive mechanical straight border`);
  }
});

test("补强城池的显示中心落在更接近历史城址的州内位置", async () => {
  const { CITY_BLOCKS } = await import("../public/标注数据_SVG.js");

  assert.ok(CITY_BLOCKS["交趾"].cx < 900, "交趾 should sit in the left side of 交州 on this base map");
  assert.ok(CITY_BLOCKS["交趾"].cy < 960, "交趾 should sit in the middle of 交州 instead of the southern sea edge");
  assert.ok(CITY_BLOCKS["交趾"].cx < CITY_BLOCKS["番禺"].cx, "交趾 should sit west of 番禺");
  assert.ok(CITY_BLOCKS["长沙"].cx > 1070, "长沙 should sit near 临湘/今长沙, east of the old western placement");
  assert.ok(CITY_BLOCKS["长沙"].cy > CITY_BLOCKS["江陵"].cy, "长沙 should sit south of 江陵");
  assert.ok(CITY_BLOCKS["吴郡"].cx > CITY_BLOCKS["秣陵"].cx, "吴郡 should sit east of 秣陵");
  assert.ok(CITY_BLOCKS["会稽"].cy > CITY_BLOCKS["吴郡"].cy, "会稽 should sit south of 吴郡");
  assert.ok(CITY_BLOCKS["泰山"].cx > CITY_BLOCKS["濮阳"].cx, "泰山 should sit east of 濮阳 toward modern Tai'an");
  assert.ok(CITY_BLOCKS["泰山"].cy < CITY_BLOCKS["彭城"].cy, "泰山 should sit north of 彭城");
});

test("城池边界必须留在所属州界内，且同州城池不能出现非共享重叠", async () => {
  const { CITY_BLOCKS, PROVINCE_BLOCKS } = await import("../public/标注数据_SVG.js");
  const byProvince = new Map();

  for (const [city, block] of Object.entries(CITY_BLOCKS)) {
    const cityPoints = pathToPoints(block.d);
    const provincePoints = pathToPoints(PROVINCE_BLOCKS[block.province].d);
    assert.ok(cityPoints.every((point) => pointInPolygon(point, provincePoints, 1.5)), `${city} should stay inside ${block.province}`);
    assert.ok(segmentSamplesStayInsideProvince(cityPoints, provincePoints), `${city} boundary segments should stay inside ${block.province}`);
    assert.ok(pointInPolygon({ x: block.cx, y: block.cy }, provincePoints, 1.5), `${city} center should stay inside ${block.province}`);
    assert.ok(pointInPolygon({ x: block.labelX, y: block.labelY }, provincePoints, 1.5), `${city} label should stay inside ${block.province}`);
    assert.ok(pointInPolygon({ x: block.cx, y: block.cy }, cityPoints, 1.5), `${city} center should stay inside its city boundary`);
    assert.ok(pointInPolygon({ x: block.labelX, y: block.labelY }, cityPoints, 1.5), `${city} label should stay inside its city boundary`);
    byProvince.set(block.province, [...(byProvince.get(block.province) || []), [city, cityPoints]]);
  }

  for (const [province, cities] of byProvince.entries()) {
    for (let i = 0; i < cities.length; i += 1) {
      for (let j = i + 1; j < cities.length; j += 1) {
        assert.equal(polygonsHaveForbiddenOverlap(cities[i][1], cities[j][1]), false, `${province}: ${cities[i][0]} and ${cities[j][0]} should only touch/share borders`);
      }
    }
  }
});

test("州界标注点会整理成没有长跳边的 SVG 路径", () => {
  const data = JSON.parse(fs.readFileSync(new URL("../public/annotation_data.json", import.meta.url), "utf8"));

  for (const [province, points] of Object.entries(data.provincePoints)) {
    const path = provincePointsToSvgPath(points);
    assert.match(path, /^M \d+ \d+ L /, `${province} should export a valid path`);
    const pathPoints = pathToPoints(path);
    assert.equal(pathSelfIntersectionCount(pathPoints), 0, `${province} province path should not cross itself`);
    assert.ok(maxEdgeLength(pathPoints) < 100, `${province} province path should not contain long jump edges`);
  }
});

test("导出的所有州界 SVG 常量不包含长跳边", async () => {
  const { PROVINCE_BLOCKS } = await import("../public/标注数据_SVG.js");

  for (const [province, block] of Object.entries(PROVINCE_BLOCKS)) {
    assert.equal(pathSelfIntersectionCount(pathToPoints(block.d)), 0, `${province} exported province path should not cross itself`);
    assert.ok(maxEdgeLength(pathToPoints(block.d)) < 100, `${province} exported province path should not contain long jump edges`);
  }
});

test("已补强州不再把单一城池边界复用为完整州界", async () => {
  const data = JSON.parse(fs.readFileSync(new URL("../public/annotation_data.json", import.meta.url), "utf8"));
  const { CITY_BLOCKS, PROVINCE_BLOCKS } = await import("../public/标注数据_SVG.js");
  const formerlySingleCityProvinces = {
    "凉州": "姑藏",
    "交州": "番禺",
    "青州": "临淄",
    "徐州": "下邳",
  };

  for (const [province, city] of Object.entries(formerlySingleCityProvinces)) {
    assert.notDeepEqual(getCityBoundaryPoints(city, data.cityPoints, data.provincePoints), data.provincePoints[province]);
    assert.equal(CITY_BLOCKS[city].province, province);
    assert.notEqual(CITY_BLOCKS[city].d, PROVINCE_BLOCKS[province].d);
  }
});

test("预览页没有 localStorage 时会回退读取标注数据文件", () => {
  const html = fs.readFileSync(new URL("../public/预览效果.html", import.meta.url), "utf8");
  const toolHtml = fs.readFileSync(new URL("../public/标注工具.html", import.meta.url), "utf8");

  assert.match(html, /async function loadData\(\)/);
  assert.match(html, /\.\/annotation_data\.json/);
  assert.match(html, /\.\/标注数据_交接\.json/);
  assert.match(html, /useStorage/);
  assert.match(html, /if \(await loadData\(\)\)/);
  assert.match(html, /annotation_path_utils\.js\?v=/);
  assert.match(toolHtml, /annotation_path_utils\.js\?v=/);
});
