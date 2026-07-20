(function () {
  function pointKey(point) {
    return `${point.x},${point.y}`;
  }

  function distance(a, b) {
    return Math.hypot(a.x - b.x, a.y - b.y);
  }

  function dedupePoints(points) {
    const seen = new Set();
    const out = [];
    for (const point of points || []) {
      if (!point || !Number.isFinite(point.x) || !Number.isFinite(point.y)) continue;
      const key = pointKey(point);
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({ x: point.x, y: point.y });
    }
    return out;
  }

  const SINGLE_CITY_PROVINCE_CAPITALS = {};

  function getSingleCityProvince(city) {
    for (const [province, capital] of Object.entries(SINGLE_CITY_PROVINCE_CAPITALS)) {
      if (capital === city) return province;
    }
    return null;
  }

  function getCityBoundaryPoints(city, cityPoints, provincePoints) {
    const points = cityPoints && cityPoints[city];
    if (points && points.length >= 3) return points;

    const province = getSingleCityProvince(city);
    const provinceBoundary = province && provincePoints && provincePoints[province];
    if (provinceBoundary && provinceBoundary.length >= 3) return provinceBoundary;

    return points || [];
  }

  function median(values) {
    if (!values.length) return 0;
    const sorted = values.slice().sort((a, b) => a - b);
    const middle = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
  }

  function removeOutlierClusters(points) {
    if (points.length < 6) return points;
    const nearestDistances = points.map((point, index) => {
      let best = Infinity;
      for (let i = 0; i < points.length; i += 1) {
        if (i === index) continue;
        best = Math.min(best, distance(point, points[i]));
      }
      return best;
    });
    const threshold = Math.max(80, median(nearestDistances) * 4);
    const visited = new Set();
    const components = [];
    for (let i = 0; i < points.length; i += 1) {
      if (visited.has(i)) continue;
      const stack = [i];
      const component = [];
      visited.add(i);
      while (stack.length) {
        const current = stack.pop();
        component.push(current);
        for (let j = 0; j < points.length; j += 1) {
          if (visited.has(j)) continue;
          if (distance(points[current], points[j]) > threshold) continue;
          visited.add(j);
          stack.push(j);
        }
      }
      components.push(component);
    }
    components.sort((a, b) => b.length - a.length);
    const largest = components[0];
    if (!largest) return points;
    largest.sort((a, b) => a - b);
    return largest.map((index) => points[index]);
  }

  function orientation(a, b, c) {
    return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
  }

  function edgesIntersect(a, b, c, d) {
    if (
      (a.x === c.x && a.y === c.y) ||
      (a.x === d.x && a.y === d.y) ||
      (b.x === c.x && b.y === c.y) ||
      (b.x === d.x && b.y === d.y)
    ) {
      return false;
    }
    return orientation(a, b, c) * orientation(a, b, d) < 0 &&
      orientation(c, d, a) * orientation(c, d, b) < 0;
  }

  function pathSelfIntersectionCount(points) {
    const ordered = points || [];
    let count = 0;
    for (let i = 0; i < ordered.length; i += 1) {
      const a = ordered[i];
      const b = ordered[(i + 1) % ordered.length];
      for (let j = i + 1; j < ordered.length; j += 1) {
        if (Math.abs(i - j) <= 1 || (i === 0 && j === ordered.length - 1)) continue;
        const c = ordered[j];
        const d = ordered[(j + 1) % ordered.length];
        if (edgesIntersect(a, b, c, d)) count += 1;
      }
    }
    return count;
  }

  function nearestNeighborCycle(points) {
    if (points.length < 3) return points;
    const start = points.reduce((best, point) =>
      point.y < best.y || (point.y === best.y && point.x < best.x) ? point : best,
    points[0]);
    const remaining = points.filter((point) => point !== start);
    const ordered = [start];
    while (remaining.length) {
      const last = ordered[ordered.length - 1];
      let bestIndex = 0;
      let bestDistance = distance(last, remaining[0]);
      for (let i = 1; i < remaining.length; i += 1) {
        const candidateDistance = distance(last, remaining[i]);
        if (candidateDistance < bestDistance) {
          bestIndex = i;
          bestDistance = candidateDistance;
        }
      }
      ordered.push(remaining.splice(bestIndex, 1)[0]);
    }
    return ordered;
  }

  function twoOptUncross(points) {
    const ordered = points.slice();
    if (ordered.length < 4) return ordered;
    let improved = true;
    let guard = 0;
    while (improved && guard < 1000) {
      improved = false;
      guard += 1;
      for (let i = 0; i < ordered.length; i += 1) {
        const a = ordered[i];
        const b = ordered[(i + 1) % ordered.length];
        for (let j = i + 2; j < ordered.length; j += 1) {
          if (i === 0 && j === ordered.length - 1) continue;
          const c = ordered[j];
          const d = ordered[(j + 1) % ordered.length];
          if (!edgesIntersect(a, b, c, d)) continue;
          ordered.splice(i + 1, j - i, ...ordered.slice(i + 1, j + 1).reverse());
          improved = true;
        }
      }
    }
    return ordered;
  }

  function twoOptShorten(points) {
    const ordered = points.slice();
    if (ordered.length < 4) return ordered;
    let improved = true;
    let guard = 0;
    while (improved && guard < 1000) {
      improved = false;
      guard += 1;
      for (let i = 0; i < ordered.length; i += 1) {
        const a = ordered[i];
        const b = ordered[(i + 1) % ordered.length];
        for (let j = i + 2; j < ordered.length; j += 1) {
          if (i === 0 && j === ordered.length - 1) continue;
          const c = ordered[j];
          const d = ordered[(j + 1) % ordered.length];
          const currentLength = distance(a, b) + distance(c, d);
          const swappedLength = distance(a, c) + distance(b, d);
          if (swappedLength >= currentLength - 0.001) continue;
          ordered.splice(i + 1, j - i, ...ordered.slice(i + 1, j + 1).reverse());
          improved = true;
        }
      }
    }
    return ordered;
  }

  function maxEdgeLength(points) {
    if (points.length < 2) return 0;
    let max = 0;
    for (let i = 0; i < points.length; i += 1) {
      max = Math.max(max, distance(points[i], points[(i + 1) % points.length]));
    }
    return max;
  }

  function totalEdgeLength(points) {
    if (points.length < 2) return 0;
    let total = 0;
    for (let i = 0; i < points.length; i += 1) {
      total += distance(points[i], points[(i + 1) % points.length]);
    }
    return total;
  }

  function rotateToTopLeft(points) {
    if (points.length < 2) return points;
    let startIndex = 0;
    for (let i = 1; i < points.length; i += 1) {
      if (points[i].y < points[startIndex].y || (points[i].y === points[startIndex].y && points[i].x < points[startIndex].x)) {
        startIndex = i;
      }
    }
    return points.slice(startIndex).concat(points.slice(0, startIndex));
  }

  function orderPolygonPoints(points) {
    const unique = removeOutlierClusters(dedupePoints(points));
    if (unique.length < 3) return unique;
    return rotateToTopLeft(twoOptShorten(twoOptUncross(nearestNeighborCycle(unique))));
  }

  function scoreProvinceCandidate(points) {
    return {
      crossings: pathSelfIntersectionCount(points),
      maxEdge: maxEdgeLength(points),
      totalLength: totalEdgeLength(points),
    };
  }

  function compareProvinceCandidates(left, right) {
    if (left.score.crossings !== right.score.crossings) return left.score.crossings - right.score.crossings;
    if (Math.abs(left.score.maxEdge - right.score.maxEdge) > 0.001) return left.score.maxEdge - right.score.maxEdge;
    return left.score.totalLength - right.score.totalLength;
  }

  function orderProvincePoints(points) {
    const unique = removeOutlierClusters(dedupePoints(points));
    if (unique.length < 3) return unique;
    const candidates = [
      twoOptUncross(unique),
      twoOptShorten(twoOptUncross(nearestNeighborCycle(unique))),
    ].map((candidate) => ({
      points: rotateToTopLeft(candidate),
      score: scoreProvinceCandidate(candidate),
    }));
    candidates.sort(compareProvinceCandidates);
    return candidates[0].points;
  }

  function pointsToSvgPath(points) {
    const ordered = orderPolygonPoints(points);
    if (ordered.length < 3) return null;
    return ordered.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`).join(" ") + " Z";
  }

  function provincePointsToSvgPath(points) {
    const ordered = orderProvincePoints(points);
    if (ordered.length < 3) return null;
    return ordered.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`).join(" ") + " Z";
  }

  window.annotationPathUtils = {
    dedupePoints,
    getCityBoundaryPoints,
    getSingleCityProvince,
    orderProvincePoints,
    orderPolygonPoints,
    pathSelfIntersectionCount,
    pointsToSvgPath,
    provincePointsToSvgPath,
    removeOutlierClusters,
  };
}());
