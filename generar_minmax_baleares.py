"""
Mapas de temperaturas mínimas y máximas diarias de las Islas Baleares
- Base OpenStreetMap (tiles o estático)
- Datos Open-Meteo (daily: temperature_2m_min, temperature_2m_max)
- Badges coloreados por temperatura, texto negro, anti-solape
"""

import io
import os
import math
import time
from datetime import datetime
from typing import List, Dict, Tuple

import requests
from PIL import Image, ImageDraw, ImageFont

# Parámetros generales
WIDTH, HEIGHT = 1200, 800
LAT_MIN, LAT_MAX = 38.5, 40.2
LON_MIN, LON_MAX = 1.0, 4.5
ZOOM = 8
TILE_SIZE = 256
OSM_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
OSM_STATIC_URL = "https://staticmap.openstreetmap.de/staticmap.php"
USER_AGENT = "MeteoDeLesIlles/1.0 (minmax)"

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})

CIUDADES: List[Dict] = [
    {"nombre": "Palma", "lat": 39.569, "lon": 2.650},
    {"nombre": "Calvià", "lat": 39.563, "lon": 2.506},
    {"nombre": "Sóller", "lat": 39.766, "lon": 2.715},
    {"nombre": "Inca", "lat": 39.721, "lon": 2.910},
    {"nombre": "Alcúdia", "lat": 39.853, "lon": 3.121},
    {"nombre": "Pollença", "lat": 39.877, "lon": 3.016},
    {"nombre": "Manacor", "lat": 39.570, "lon": 3.209},
    {"nombre": "Felanitx", "lat": 39.469, "lon": 3.147},
    {"nombre": "Llucmajor", "lat": 39.490, "lon": 2.883},
    {"nombre": "Santanyí", "lat": 39.355, "lon": 3.128},
    {"nombre": "Maó", "lat": 39.889, "lon": 4.262},
    {"nombre": "Ciutadella", "lat": 40.001, "lon": 3.839},
    {"nombre": "Es Mercadal", "lat": 39.994, "lon": 4.093},
    {"nombre": "Eivissa", "lat": 38.907, "lon": 1.420},
    {"nombre": "Sant Antoni", "lat": 38.980, "lon": 1.303},
    {"nombre": "Santa Eulària", "lat": 38.984, "lon": 1.535},
    {"nombre": "La Savina", "lat": 38.727, "lon": 1.408},
]

# Mercator helpers
RADIUS = 6378137.0

def lon_to_merc_x(lon: float) -> float:
    return math.radians(lon) * RADIUS

def lat_to_merc_y(lat: float) -> float:
    lat = max(min(lat, 89.9), -89.9)
    return RADIUS * math.log(math.tan(math.pi/4.0 + math.radians(lat)/2.0))

def lonlat_to_tile(lon: float, lat: float, zoom: int) -> Tuple[float, float]:
    lat_rad = math.radians(lat)
    n = 2.0 ** zoom
    xtile = (lon + 180.0) / 360.0 * n
    ytile = (1.0 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2.0 * n
    return xtile, ytile

def tile_to_pixel(xtile: float, ytile: float) -> Tuple[float, float]:
    return xtile * TILE_SIZE, ytile * TILE_SIZE

def lonlat_to_pixel(lon: float, lat: float, zoom: int) -> Tuple[float, float]:
    xtile, ytile = lonlat_to_tile(lon, lat, zoom)
    return tile_to_pixel(xtile, ytile)

# Base map builders

def build_base_map_static(width: int, height: int):
    params = {"bbox": f"{LON_MIN},{LAT_MIN},{LON_MAX},{LAT_MAX}", "size": f"{width}x{height}", "maptype": "mapnik"}
    r = session.get(OSM_STATIC_URL, params=params, timeout=25)
    r.raise_for_status()
    img = Image.open(io.BytesIO(r.content)).convert("RGB")
    transform = {
        "min_x": lon_to_merc_x(LON_MIN),
        "max_x": lon_to_merc_x(LON_MAX),
        "min_y": lat_to_merc_y(LAT_MIN),
        "max_y": lat_to_merc_y(LAT_MAX),
        "width": width,
        "height": height,
    }
    return img, transform

def download_tile(z, x, y):
    url = OSM_TILE_URL.format(z=z, x=x, y=y)
    try:
        r = session.get(url, timeout=15)
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content)).convert("RGB")
    except Exception:
        return Image.new("RGB", (TILE_SIZE, TILE_SIZE), color=(235, 235, 235))

def build_base_map_tiles(width: int, height: int):
    px_min_x, px_max_y = lonlat_to_pixel(LON_MIN, LAT_MIN, ZOOM)
    px_max_x, px_min_y = lonlat_to_pixel(LON_MAX, LAT_MAX, ZOOM)
    bbox_width = px_max_x - px_min_x
    bbox_height = px_max_y - px_min_y

    tile_x_min = int(px_min_x // TILE_SIZE)
    tile_x_max = int(px_max_x // TILE_SIZE)
    tile_y_min = int(px_min_y // TILE_SIZE)
    tile_y_max = int(px_max_y // TILE_SIZE)

    canvas_px_width = (tile_x_max - tile_x_min + 1) * TILE_SIZE
    canvas_px_height = (tile_y_max - tile_y_min + 1) * TILE_SIZE
    canvas = Image.new("RGB", (canvas_px_width, canvas_px_height), color=(255, 255, 255))

    for tx in range(tile_x_min, tile_x_max + 1):
        for ty in range(tile_y_min, tile_y_max + 1):
            tile = download_tile(ZOOM, tx, ty)
            dx = (tx - tile_x_min) * TILE_SIZE
            dy = (ty - tile_y_min) * TILE_SIZE
            canvas.paste(tile, (dx, dy))
            time.sleep(0.2)

    crop_left = int(px_min_x - tile_x_min * TILE_SIZE)
    crop_top = int(px_min_y - tile_y_min * TILE_SIZE)
    crop_right = crop_left + int(bbox_width)
    crop_bottom = crop_top + int(bbox_height)
    canvas = canvas.crop((crop_left, crop_top, crop_right, crop_bottom))

    base_map = canvas.resize((width, height), Image.Resampling.LANCZOS)
    transform = {
        "min_x": lon_to_merc_x(LON_MIN),
        "max_x": lon_to_merc_x(LON_MAX),
        "min_y": lat_to_merc_y(LAT_MIN),
        "max_y": lat_to_merc_y(LAT_MAX),
        "width": width,
        "height": height,
    }
    return base_map, transform

# Palette

def temp_to_color(temp: float) -> Tuple[int, int, int]:
    stops = [
        (-10, (132, 0, 168)), (-5, (44, 0, 184)), (0, (0, 90, 200)), (3, (0, 150, 200)), (6, (0, 180, 170)),
        (9, (0, 200, 120)), (12, (80, 200, 60)), (15, (150, 200, 0)), (18, (200, 180, 0)), (21, (230, 150, 0)),
        (24, (240, 120, 0)), (27, (240, 90, 0)), (30, (240, 60, 0)), (33, (230, 30, 0)), (36, (220, 0, 0)),
        (39, (220, 0, 40)), (42, (230, 0, 100)), (45, (240, 0, 150)), (47, (250, 0, 180)), (50, (255, 0, 220)),
    ]
    if temp is None:
        return (200, 200, 200)
    t = max(-10, min(50, temp))
    for i in range(len(stops) - 1):
        t0, c0 = stops[i]
        t1, c1 = stops[i + 1]
        if t0 <= t <= t1:
            f = 0 if t1 == t0 else (t - t0) / (t1 - t0)
            r = int(c0[0] + f * (c1[0] - c0[0]))
            g = int(c0[1] + f * (c1[1] - c0[1]))
            b = int(c0[2] + f * (c1[2] - c0[2]))
            return (r, g, b)
    return stops[-1][1]

# Badges

def draw_badge(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, temp: float, font: ImageFont.FreeTypeFont, placed: List[Tuple[int, int, int, int]]) -> bool:
    color = temp_to_color(temp)
    # Size estimate
    try:
        fw, fh = font.getsize(text)
    except Exception:
        fw, fh = (len(text) * 9, 16)
    box_w = max(46, fw + 12)
    box_h = 16 + 10
    box_x = x + 10 if x + 10 + box_w < WIDTH - 10 else x - 10 - box_w
    box_y = y - box_h // 2
    candidate = (box_x - 3, box_y - 3, box_x + box_w + 3, box_y + box_h + 3)
    for bx in placed:
        if not (candidate[2] < bx[0] or candidate[0] > bx[2] or candidate[3] < bx[1] or candidate[1] > bx[3]):
            return False
    # Draw pin and badge
    draw.ellipse([(x-4, y-4), (x+4, y+4)], fill=color, outline="#ffffff")
    draw.rectangle([(box_x + 2, box_y + 2), (box_x + box_w + 2, box_y + box_h + 2)], fill=(120, 120, 120))
    draw.rectangle([(box_x, box_y), (box_x + box_w, box_y + box_h)], outline=(40, 40, 40), fill=color, width=2)
    draw.text((box_x + 6, box_y + 5), text, fill="#000000", font=font)
    placed.append(candidate)
    return True

# Open-Meteo daily
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

def fetch_minmax(lat: float, lon: float) -> Tuple[float, float]:
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": ["temperature_2m_min", "temperature_2m_max"],
        "timezone": "Europe/Madrid"
    }
    try:
        r = session.get(OPEN_METEO_URL, params=params, timeout=20)
        r.raise_for_status()
        d = r.json().get("daily", {})
        tmin = d.get("temperature_2m_min", [None])[0]
        tmax = d.get("temperature_2m_max", [None])[0]
        return (None if tmin is None else float(tmin), None if tmax is None else float(tmax))
    except Exception:
        return (None, None)

# Render

def render_map(kind: str, out_name: str):
    try:
        base, transform = build_base_map_static(WIDTH, HEIGHT)
    except Exception:
        base, transform = build_base_map_tiles(WIDTH, HEIGHT)
    img = base.convert("RGB")
    draw = ImageDraw.Draw(img)

    try:
        font_big = ImageFont.truetype("arial.ttf", 28)
        font_small = ImageFont.truetype("arial.ttf", 16)
    except Exception:
        font_big = ImageFont.load_default()
        font_small = ImageFont.load_default()

    title = "Meteo de les Illes - Temperaturas " + ("mínimas" if kind == "min" else "máximas")
    fecha = datetime.now().strftime("%d/%m/%Y")
    draw.rectangle([(0, 0), (WIDTH, 50)], fill=(255, 255, 255))
    draw.text((20, 12), title, fill="#0d47a1", font=font_big)
    draw.text((WIDTH - 220, 16), fecha, fill="#263238", font=font_small)

    placed: List[Tuple[int, int, int, int]] = []
    for c in CIUDADES:
        x_m = (lon_to_merc_x(c["lon"]) - transform["min_x"]) / (transform["max_x"] - transform["min_x"]) * WIDTH
        y_m = (transform["max_y"] - lat_to_merc_y(c["lat"])) / (transform["max_y"] - transform["min_y"]) * HEIGHT
        x, y = int(x_m), int(y_m)
        tmin, tmax = fetch_minmax(c["lat"], c["lon"]) 
        temp = tmin if kind == "min" else tmax
        text = "Sin datos" if temp is None else f"{round(temp,1)}°C"
        draw_badge(draw, x, y, text, temp, font_small, placed)

    # Leyenda
    legend_h = 55
    legend_top = HEIGHT - legend_h - 12
    legend_left = 110
    legend_right = WIDTH - 110
    draw.rectangle([(legend_left - 10, legend_top - 10), (legend_right + 10, HEIGHT - 12 + 10)], fill=(255, 255, 255), outline=(180, 180, 180))
    min_t, max_t = -10, 50
    segments = 30
    seg_w = int((legend_right - legend_left) / segments)
    for i in range(segments):
        t0 = min_t + (max_t - min_t) * (i / segments)
        t1 = min_t + (max_t - min_t) * ((i + 1) / segments)
        color = temp_to_color((t0 + t1) / 2)
        x0 = legend_left + i * seg_w
        x1 = legend_left + (i + 1) * seg_w
        draw.rectangle([(x0, legend_top), (x1, legend_top + 20)], fill=color, outline=color)
    try:
        font_legend = ImageFont.truetype("arial.ttf", 14)
    except Exception:
        font_legend = ImageFont.load_default()
    for t in [-10, -7, -5, -3, 0, 3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36, 39, 42, 45, 47, 50]:
        x = legend_left + int((t - min_t) / (max_t - min_t) * (legend_right - legend_left))
        draw.line([(x, legend_top + 20), (x, legend_top + 24)], fill=(40, 40, 40))
        draw.text((x - 8, legend_top + 26), str(t), fill=(40, 40, 40), font=font_legend)
    draw.text(((legend_left + legend_right)//2 - 50, legend_top - 18), "Temp. °C", fill=(40, 40, 40), font=font_legend)

    img.save(out_name)
    # Evitar abrir ventana en CI
    if os.environ.get("CI", "").lower() not in ("true", "1"):
        try:
            img.show()
        except Exception:
            pass


def main():
    render_map("min", "mapa_baleares_min.png")
    render_map("max", "mapa_baleares_max.png")


if __name__ == "__main__":
    main()
