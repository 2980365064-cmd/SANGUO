#!/usr/bin/env python3
"""Generate a terrain-first 208 CE Three Kingdoms map from /tmp/han-maps GeoJSON."""

from __future__ import annotations

import json
import math
import random
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path("/tmp/han-maps")
OUT_DIR = Path("/Users/zhuanzmima0000/Desktop/SANGUO/output")
OUT = OUT_DIR / "sanguo_208_terrain_map.png"
CACHE = ROOT / "_natural_earth_cache"

WIDTH, HEIGHT = 2600, 1780
LON_MIN, LON_MAX = 78.0, 146.0
LAT_MIN, LAT_MAX = 5.0, 53.0

FONT_HEI = "/System/Library/Fonts/STHeiti Medium.ttc"
FONT_SONG = "/System/Library/Fonts/Supplemental/Songti.ttc"


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


F_TITLE = font(FONT_SONG, 58)
F_SUB = font(FONT_HEI, 28)
F_LABEL = font(FONT_HEI, 20)
F_SMALL = font(FONT_HEI, 17)
F_LEGEND = font(FONT_HEI, 22)


def download(name: str, url: str) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / name
    if not path.exists():
        urllib.request.urlretrieve(url, path)
    return path


def lonlat_to_xy(lon: float, lat: float) -> tuple[float, float]:
    x = (lon - LON_MIN) / (LON_MAX - LON_MIN) * WIDTH
    y = (LAT_MAX - lat) / (LAT_MAX - LAT_MIN) * HEIGHT
    return x, y


def coords_to_points(coords: list[list[float]]) -> list[tuple[float, float]]:
    return [lonlat_to_xy(float(lon), float(lat)) for lon, lat, *_ in coords]


def iter_polygons(geometry: dict):
    kind = geometry.get("type")
    coords = geometry.get("coordinates", [])
    if kind == "Polygon":
        yield coords
    elif kind == "MultiPolygon":
        yield from coords


def iter_lines(geometry: dict):
    kind = geometry.get("type")
    coords = geometry.get("coordinates", [])
    if kind == "LineString":
        yield coords
    elif kind == "MultiLineString":
        yield from coords


def bbox_visible(points: list[tuple[float, float]]) -> bool:
    if not points:
        return False
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return max(xs) >= -80 and min(xs) <= WIDTH + 80 and max(ys) >= -80 and min(ys) <= HEIGHT + 80


def parchment() -> Image.Image:
    rng = np.random.default_rng(208)
    base = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    base[:, :] = np.array([224, 210, 176], dtype=np.uint8)
    noise = rng.normal(0, 12, (HEIGHT, WIDTH, 1))
    y = np.linspace(-1, 1, HEIGHT)[:, None]
    x = np.linspace(-1, 1, WIDTH)[None, :]
    vignette = ((x * x + y * y) * 38)[:, :, None]
    arr = np.clip(base + noise - vignette, 0, 255).astype(np.uint8)
    img = Image.fromarray(arr, "RGB").filter(ImageFilter.GaussianBlur(0.45))
    d = ImageDraw.Draw(img, "RGBA")
    d.rectangle([34, 34, WIDTH - 34, HEIGHT - 34], outline=(102, 70, 45, 170), width=5)
    d.rectangle([58, 58, WIDTH - 58, HEIGHT - 58], outline=(143, 100, 62, 130), width=2)
    for _ in range(2300):
        px = rng.integers(35, WIDTH - 35)
        py = rng.integers(35, HEIGHT - 35)
        r = int(rng.integers(1, 3))
        col = (112, 75, 41, int(rng.integers(18, 42)))
        d.ellipse([px - r, py - r, px + r, py + r], fill=col)
    return img


def smooth_line(points: list[tuple[float, float]], steps: int = 18) -> list[tuple[float, float]]:
    if len(points) < 3:
        return points
    out = []
    for i in range(len(points) - 1):
        p0 = points[max(0, i - 1)]
        p1 = points[i]
        p2 = points[i + 1]
        p3 = points[min(len(points) - 1, i + 2)]
        for j in range(steps):
            t = j / steps
            t2, t3 = t * t, t * t * t
            x = 0.5 * (
                2 * p1[0]
                + (-p0[0] + p2[0]) * t
                + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3
            )
            y = 0.5 * (
                2 * p1[1]
                + (-p0[1] + p2[1]) * t
                + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3
            )
            out.append((x, y))
    out.append(points[-1])
    return out


def draw_geojson_polygons(draw: ImageDraw.ImageDraw, path: Path, fill, outline, width=1):
    data = json.loads(path.read_text())
    for feat in data.get("features", []):
        for rings in iter_polygons(feat.get("geometry", {})):
            if not rings:
                continue
            outer = coords_to_points(rings[0])
            if len(outer) >= 3 and bbox_visible(outer):
                draw.polygon(outer, fill=fill, outline=outline)


def mask_from_geojson(path: Path, fill: int = 255) -> Image.Image:
    mask = Image.new("L", (WIDTH, HEIGHT), 0)
    d = ImageDraw.Draw(mask)
    data = json.loads(path.read_text())
    for feat in data.get("features", []):
        for rings in iter_polygons(feat.get("geometry", {})):
            if rings:
                outer = coords_to_points(rings[0])
                if len(outer) >= 3 and bbox_visible(outer):
                    d.polygon(outer, fill=fill)
    return mask


def draw_geojson_lines(draw: ImageDraw.ImageDraw, path: Path, fill, width=2):
    data = json.loads(path.read_text())
    for feat in data.get("features", []):
        for line in iter_lines(feat.get("geometry", {})):
            pts = coords_to_points(line)
            if len(pts) >= 2 and bbox_visible(pts):
                draw.line(smooth_line(pts, 5), fill=fill, width=width, joint="curve")


FACTION_BY_CITY = {
    # Cao Cao, including surrendered northern Jingzhou around Red Cliff.
    **{c: "曹操" for c in [
        "北平", "中山", "蓟城", "钜鹿", "甘陵", "平原", "济北", "北海", "琅琊", "下邳",
        "小沛", "广陵", "南皮", "邺城", "晋阳", "上党", "河内", "濮阳", "陈留", "谯郡",
        "许昌", "汝南", "宛城", "洛阳", "弘农", "长安", "上庸", "襄阳", "江陵", "寿春",
    ]},
    **{c: "孙权" for c in ["建业", "吴郡", "会稽", "庐江", "豫章", "建安", "长沙", "桂阳", "零陵", "武陵"]},
    **{c: "刘备/刘琦" for c in ["新野", "江夏"]},
    **{c: "刘璋" for c in ["成都", "梓潼", "江州", "永安", "建宁", "越巂", "永昌", "牂牁"]},
    **{c: "张鲁" for c in ["汉中", "武都"]},
    **{c: "马腾韩遂" for c in ["武威", "金城", "安定", "天水"]},
    "襄平": "公孙康",
    **{c: "士燮" for c in ["交趾", "南海", "合浦"]},
    "夷洲": "未详",
}

PALETTE = {
    "曹操": (118, 166, 111, 138),
    "孙权": (81, 151, 138, 145),
    "刘备/刘琦": (206, 177, 76, 155),
    "刘璋": (172, 132, 86, 142),
    "张鲁": (155, 143, 88, 140),
    "马腾韩遂": (178, 177, 142, 130),
    "公孙康": (146, 171, 128, 130),
    "士燮": (118, 166, 135, 132),
    "未详": (180, 180, 165, 105),
}

OUTLINES = {
    "曹操": (114, 178, 107, 205),
    "孙权": (65, 173, 161, 215),
    "刘备/刘琦": (222, 184, 56, 230),
    "刘璋": (205, 139, 69, 210),
    "张鲁": (179, 165, 77, 205),
    "马腾韩遂": (207, 203, 155, 200),
    "公孙康": (153, 188, 141, 195),
    "士燮": (91, 170, 126, 195),
    "未详": (172, 172, 155, 155),
}

MAJOR_FACTION_SEATS = {
    "曹操": "许昌",
    "孙权": "建业",
    "刘备/刘琦": "江夏",
    "刘璋": "成都",
    "张鲁": "汉中",
    "马腾韩遂": "武威",
    "公孙康": "襄平",
    "士燮": "交趾",
}

MOUNTAIN_RANGES = [
    ("天山", [(79, 42), (86, 42.6), (93, 42.0), (99, 41.1)]),
    ("昆仑", [(78.5, 36.0), (86, 36.4), (94, 35.8), (101, 35.0)]),
    ("喜马拉雅", [(79, 29.5), (86, 29.1), (93, 28.4), (100, 27.9)]),
    ("祁连", [(94, 39.4), (98, 38.5), (102, 37.2)]),
    ("秦岭", [(104, 34.0), (108, 33.8), (112, 33.6)]),
    ("太行", [(112, 39.8), (113, 37.5), (113.4, 35.6)]),
    ("阴山", [(106, 41.0), (112, 41.3), (118, 41.6)]),
    ("南岭", [(108, 25.5), (113, 25.4), (117, 25.8)]),
    ("长白", [(124, 42.2), (128, 42.1), (131, 41.4)]),
    ("台湾山脉", [(121, 25), (121.1, 23.5), (120.8, 22.3)]),
    ("日本山地", [(134, 35.0), (137, 36.2), (141, 39.0)]),
]


def fractal_noise(width: int, height: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    result = np.zeros((height, width), dtype=np.float32)
    weight_sum = 0.0
    for scale, weight in [(16, 0.55), (32, 0.28), (80, 0.13), (180, 0.07)]:
        small_w = max(2, width // scale)
        small_h = max(2, height // scale)
        small = rng.random((small_h, small_w), dtype=np.float32)
        img = Image.fromarray((small * 255).astype(np.uint8), "L").resize((width, height), Image.Resampling.BICUBIC)
        result += np.asarray(img, dtype=np.float32) / 255.0 * weight
        weight_sum += weight
    result /= weight_sum
    result = (result - result.min()) / (result.max() - result.min())
    return result


def terrain_base(land_path: Path) -> Image.Image:
    tw, th = WIDTH // 2, HEIGHT // 2
    lon = np.linspace(LON_MIN, LON_MAX, tw, dtype=np.float32)[None, :]
    lat = np.linspace(LAT_MAX, LAT_MIN, th, dtype=np.float32)[:, None]
    noise = fractal_noise(tw, th, 208)
    fine = fractal_noise(tw, th, 1208)

    elev = 0.10 + noise * 0.34
    elev += np.clip((103 - lon) / 20, 0, 1) * 0.22
    elev += np.clip((lat - 38) / 12, 0, 1) * 0.10
    elev += np.clip((28 - lat) / 10, 0, 1) * 0.08

    for _name, points in MOUNTAIN_RANGES:
        samples = []
        for a, b in zip(points, points[1:]):
            for t in np.linspace(0, 1, 18):
                samples.append((a[0] * (1 - t) + b[0] * t, a[1] * (1 - t) + b[1] * t))
        strength = 0.42 if _name in {"喜马拉雅", "昆仑", "天山"} else 0.24
        width = 1.15 if _name in {"喜马拉雅", "昆仑", "天山"} else 0.75
        ridge = np.zeros_like(elev)
        for mlon, mlat in samples[::2]:
            dist2 = ((lon - mlon) / width) ** 2 + ((lat - mlat) / (width * 0.72)) ** 2
            ridge = np.maximum(ridge, np.exp(-dist2))
        elev += ridge * strength

    elev = np.clip(elev + (fine - 0.5) * 0.10, 0, 1)
    gy, gx = np.gradient(elev)
    shade = np.clip(0.74 + gx * -2.4 + gy * -1.6, 0.42, 1.25)

    moisture = np.clip(1.04 - (lon - 106) / 34 + (30 - np.abs(lat - 28)) / 34 + (fine - 0.5) * 0.35, 0, 1)
    arid = np.clip((105 - lon) / 23 + (lat - 35) / 20, 0, 1)

    low_green = np.array([83, 128, 70], dtype=np.float32)
    forest = np.array([42, 103, 62], dtype=np.float32)
    steppe = np.array([154, 146, 91], dtype=np.float32)
    desert = np.array([181, 151, 88], dtype=np.float32)
    highland = np.array([126, 115, 92], dtype=np.float32)
    snow = np.array([226, 225, 206], dtype=np.float32)

    color = low_green[None, None, :] * (0.65 + moisture[:, :, None] * 0.35)
    color = color * (1 - arid[:, :, None] * 0.65) + desert[None, None, :] * (arid[:, :, None] * 0.65)
    forest_mix = np.clip(moisture - 0.58, 0, 1) * np.clip(0.70 - elev, 0, 1) * 1.4
    color = color * (1 - forest_mix[:, :, None]) + forest[None, None, :] * forest_mix[:, :, None]
    high_mix = np.clip((elev - 0.48) * 1.7, 0, 1)
    color = color * (1 - high_mix[:, :, None]) + highland[None, None, :] * high_mix[:, :, None]
    snow_mix = np.clip((elev - 0.78) * 5.5, 0, 1)
    color = color * (1 - snow_mix[:, :, None]) + snow[None, None, :] * snow_mix[:, :, None]
    color *= shade[:, :, None]

    ocean_noise = fractal_noise(tw, th, 5208)
    ocean = np.zeros((th, tw, 3), dtype=np.float32)
    ocean[:, :] = np.array([72, 124, 145], dtype=np.float32)
    ocean += ocean_noise[:, :, None] * np.array([22, 26, 22], dtype=np.float32)
    ocean *= np.clip(0.92 + (lat - 5) / 80, 0.85, 1.08)[:, :, None]

    land_mask = mask_from_geojson(land_path).resize((tw, th), Image.Resampling.BILINEAR)
    mask = np.asarray(land_mask, dtype=np.float32)[:, :, None] / 255.0
    arr = ocean * (1 - mask) + color * mask
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    img = Image.fromarray(arr, "RGB").resize((WIDTH, HEIGHT), Image.Resampling.BICUBIC).convert("RGBA")

    coast = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    cd = ImageDraw.Draw(coast, "RGBA")
    draw_geojson_polygons(cd, land_path, fill=(0, 0, 0, 0), outline=(41, 58, 44, 145), width=1)
    img.alpha_composite(coast)
    return img


def draw_mountains(layer: Image.Image):
    d = ImageDraw.Draw(layer, "RGBA")
    rng = random.Random(208)
    for name, ll in MOUNTAIN_RANGES:
        pts = smooth_line([lonlat_to_xy(*p) for p in ll], 14)
        d.line(pts, fill=(44, 48, 38, 130), width=3)
        for i in range(0, len(pts), 9):
            x, y = pts[i]
            size = rng.randint(10, 18)
            d.line([(x - size, y + size * 0.6), (x, y - size), (x + size, y + size * 0.6)],
                   fill=(235, 232, 207, 82), width=2)
            d.line([(x - size, y + size * 0.6), (x, y - size), (x + size, y + size * 0.6)],
                   fill=(48, 51, 42, 100), width=1)
        lx, ly = lonlat_to_xy(*ll[len(ll) // 2])
        d.text((lx + 8, ly - 28), name, fill=(38, 34, 26, 155), font=F_SMALL, stroke_width=1, stroke_fill=(226, 220, 184, 105))


def draw_manual_rivers(layer: Image.Image):
    d = ImageDraw.Draw(layer, "RGBA")
    rivers = {
        "黄河": [(96, 35.8), (101, 36.5), (105, 36.1), (107.5, 34.7), (111, 34.8), (113.5, 35.5), (117.5, 37.7), (119.0, 37.6)],
        "长江": [(91, 31.8), (98, 31.5), (103, 30.7), (107, 30.6), (111.5, 30.4), (115.5, 30.9), (119.4, 31.3), (121.6, 31.2)],
        "汉水": [(106, 33.3), (109, 32.8), (111.5, 31.2), (114.2, 30.6)],
        "珠江": [(104, 24.5), (108, 23.6), (112.5, 23.0), (114.1, 22.5)],
        "湄公河": [(100.5, 31.5), (99.8, 27.5), (100.4, 23.5), (101.2, 19.5), (102.5, 15.0), (104, 11.5)],
        "辽河": [(120, 43.4), (122.1, 42.0), (123.5, 40.7), (121.8, 40.0)],
    }
    for name, ll in rivers.items():
        pts = smooth_line([lonlat_to_xy(*p) for p in ll], 16)
        d.line(pts, fill=(77, 123, 142, 95), width=9)
        d.line(pts, fill=(41, 91, 119, 155), width=3)
        tx, ty = pts[len(pts) // 2]
        d.text((tx + 5, ty + 5), name, fill=(43, 82, 98, 155), font=F_SMALL)


def draw_regions(base: Image.Image):
    reg = json.loads((ROOT / "eserica-region.geojson").read_text())
    region_layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    d = ImageDraw.Draw(region_layer, "RGBA")
    for feat in reg["features"]:
        city = feat["properties"]["city"]
        faction = FACTION_BY_CITY.get(city, "未详")
        for rings in iter_polygons(feat["geometry"]):
            outer = coords_to_points(rings[0])
            if len(outer) >= 3:
                d.line(outer + [outer[0]], fill=(22, 23, 18, 88), width=4)
                d.line(outer + [outer[0]], fill=OUTLINES[faction], width=2)
    region_layer = region_layer.filter(ImageFilter.GaussianBlur(0.15))
    base.alpha_composite(region_layer)


def draw_cities(base: Image.Image):
    cities = json.loads((ROOT / "eserica-city.geojson").read_text())
    d = ImageDraw.Draw(base, "RGBA")
    for feat in cities["features"]:
        city = feat["properties"]["city"]
        lon, lat = feat["geometry"]["coordinates"][:2]
        x, y = lonlat_to_xy(lon, lat)
        if -20 <= x <= WIDTH + 20 and -20 <= y <= HEIGHT + 20:
            faction = FACTION_BY_CITY.get(city, "未详")
            marker = OUTLINES[faction]
            d.polygon([(x, y - 9), (x + 8, y), (x, y + 9), (x - 8, y)], fill=(35, 30, 22, 230))
            d.polygon([(x, y - 6), (x + 5, y), (x, y + 6), (x - 5, y)], fill=marker)
            fill = (28, 24, 18, 230)
            if faction == "刘备/刘琦":
                fill = (86, 56, 0, 245)
            d.text((x + 9, y - 12), city, fill=fill, font=F_LABEL, stroke_width=2, stroke_fill=(235, 226, 191, 150))

    city_xy = {}
    for feat in cities["features"]:
        city = feat["properties"]["city"]
        city_xy[city] = lonlat_to_xy(*feat["geometry"]["coordinates"][:2])
    for faction, city in MAJOR_FACTION_SEATS.items():
        if city not in city_xy:
            continue
        x, y = city_xy[city]
        d.rounded_rectangle([x - 40, y - 48, x + 72, y - 20], radius=6, fill=(21, 18, 13, 150), outline=OUTLINES[faction], width=2)
        d.text((x - 31, y - 47), faction, fill=(246, 236, 194, 235), font=F_LABEL)


def draw_overlay_text(base: Image.Image):
    d = ImageDraw.Draw(base, "RGBA")
    title = "建安十三年（208）三国势力图"
    subtitle = "赤壁前后势力示意｜范围：西至青藏高原，东至日本，北至蒙古，南至泰国"
    d.rounded_rectangle([82, 62, 920, 184], radius=12, fill=(25, 22, 17, 128), outline=(236, 215, 154, 80), width=2)
    d.text((105, 82), title, fill=(240, 228, 184, 245), font=F_TITLE, stroke_width=2, stroke_fill=(23, 20, 16, 210))
    d.text((108, 153), subtitle, fill=(231, 219, 180, 230), font=F_SUB)
    d.text((110, HEIGHT - 112), "底图：/tmp/han-maps/eserica-region.geojson + eserica-city.geojson；区域为游戏/爱好资料示意，并非严格历史行政区划。",
           fill=(239, 230, 191, 215), font=F_SMALL, stroke_width=2, stroke_fill=(18, 18, 14, 120))

    lx, ly = WIDTH - 420, 115
    d.rounded_rectangle([lx - 24, ly - 22, WIDTH - 86, ly + 312], radius=10, fill=(23, 20, 15, 142), outline=(228, 208, 142, 105), width=2)
    d.text((lx, ly), "势力标记", fill=(239, 228, 183, 235), font=F_LEGEND)
    y = ly + 40
    for name in ["曹操", "孙权", "刘备/刘琦", "刘璋", "张鲁", "马腾韩遂", "公孙康", "士燮"]:
        d.polygon([(lx + 17, y - 2), (lx + 34, y + 10), (lx + 17, y + 22), (lx, y + 10)], fill=(35, 30, 22, 235))
        d.polygon([(lx + 17, y + 1), (lx + 29, y + 10), (lx + 17, y + 19), (lx + 5, y + 10)], fill=OUTLINES[name])
        d.text((lx + 46, y - 4), name, fill=(239, 228, 183, 235), font=F_LABEL)
        y += 33


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    land = download(
        "ne_10m_land.geojson",
        "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_land.geojson",
    )
    rivers = download(
        "ne_10m_rivers_lake_centerlines.geojson",
        "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_rivers_lake_centerlines.geojson",
    )
    lakes = download(
        "ne_10m_lakes.geojson",
        "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_lakes.geojson",
    )

    img = terrain_base(land)
    d = ImageDraw.Draw(img, "RGBA")
    draw_geojson_polygons(d, lakes, fill=(79, 133, 151, 205), outline=(38, 74, 88, 150), width=1)

    texture = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    td = ImageDraw.Draw(texture, "RGBA")
    rng = random.Random(208)
    for _ in range(5200):
        lon = rng.uniform(82, 129)
        lat = rng.uniform(18, 46)
        x, y = lonlat_to_xy(lon, lat)
        col = rng.choice([(19, 71, 34, 35), (27, 91, 47, 28), (103, 118, 63, 24), (80, 65, 39, 20)])
        if 21 < lat < 38 and lon > 103:
            td.ellipse([x - 2, y - 2, x + 2, y + 2], fill=col)
        else:
            td.line([(x, y), (x + rng.uniform(-12, 12), y + rng.uniform(-5, 5))], fill=col, width=1)
    img.alpha_composite(texture.filter(ImageFilter.GaussianBlur(0.25)))

    draw_mountains(img)
    draw_geojson_lines(d, rivers, fill=(34, 88, 118, 170), width=3)
    draw_manual_rivers(img)
    draw_regions(img)
    draw_cities(img)
    draw_overlay_text(img)

    # Subtle vignette and frame, keeping the focus on terrain instead of parchment.
    edge = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    ed = ImageDraw.Draw(edge, "RGBA")
    for i in range(110):
        ed.rectangle([i, i, WIDTH - i, HEIGHT - i], outline=(0, 0, 0, max(0, 72 - i // 2)), width=1)
    ed.rectangle([26, 26, WIDTH - 26, HEIGHT - 26], outline=(216, 193, 129, 130), width=3)
    img.alpha_composite(edge)

    img = img.convert("RGB")
    img.save(OUT, quality=95)
    print(OUT)


if __name__ == "__main__":
    main()
