"""
Generar mapa meteorológico de Islas Baleares con base OpenStreetMap + datos Open-Meteo

- Intenta obtener una imagen estática OSM por bbox (1 request)
- Si falla, usa tiles OSM con User-Agent y pequeño delay
- Proyección Web Mercator normalizada para dibujar puntos
- Muestra y guarda como mapa_baleares_openmeteo.png

Requisitos: requests, Pillow
"""

import math
import os
import io
import sys
import time
import unicodedata
from datetime import datetime
from typing import Tuple, List, Dict

import requests
from PIL import Image, ImageDraw, ImageFont

# ------------------ Configuración ------------------
WIDTH, HEIGHT = 1200, 800
# Bounding box aproximado Baleares (lat_min, lat_max, lon_min, lon_max)
LAT_MIN, LAT_MAX = 38.5, 40.2
LON_MIN, LON_MAX = 1.0, 4.5
# Zoom de tiles respaldo
ZOOM = 8
OSM_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
OSM_STATIC_URL = "https://staticmap.openstreetmap.de/staticmap.php"
USER_AGENT = "MeteoDeLesIlles/1.0 (contacto: soporte@meteodelesilles.local)"

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})

# Ciudades con coordenadas (lat, lon) aproximadas
CIUDADES: List[Dict] = [
    # Mallorca (principales)
    {"nombre": "Palma", "lat": 39.569, "lon": 2.650},
    {"nombre": "Calvià", "lat": 39.563, "lon": 2.506},
    {"nombre": "Sóller", "lat": 39.766, "lon": 2.715},
    {"nombre": "Inca", "lat": 39.721, "lon": 2.910},
    {"nombre": "Alcúdia", "lat": 39.853, "lon": 3.121},
    {"nombre": "Pollença", "lat": 39.877, "lon": 3.016},
    {"nombre": "Manacor", "lat": 39.570, "lon": 3.209},
    {"nombre": "Felanitx", "lat": 39.469, "lon": 3.147},

    # Mallorca (adicionales, se mostrarán si no hay solape)
    {"nombre": "Llucmajor", "lat": 39.490, "lon": 2.883},
    {"nombre": "Marratxí", "lat": 39.626, "lon": 2.708},
    {"nombre": "Sa Pobla", "lat": 39.769, "lon": 3.022},
    {"nombre": "Binissalem", "lat": 39.688, "lon": 2.842},
    {"nombre": "Campos", "lat": 39.433, "lon": 3.018},
    {"nombre": "Santanyí", "lat": 39.355, "lon": 3.128},
    {"nombre": "Capdepera", "lat": 39.702, "lon": 3.435},
    {"nombre": "Artà", "lat": 39.693, "lon": 3.350},
    {"nombre": "Muro", "lat": 39.736, "lon": 3.057},
    {"nombre": "Sineu", "lat": 39.642, "lon": 3.010},
    {"nombre": "Porreres", "lat": 39.517, "lon": 3.021},

    # Menorca (principales)
    {"nombre": "Maó", "lat": 39.889, "lon": 4.262},
    {"nombre": "Ciutadella", "lat": 40.001, "lon": 3.839},
    {"nombre": "Es Mercadal", "lat": 39.994, "lon": 4.093},
    # Menorca extra (si cabe)
    {"nombre": "Alaior", "lat": 39.933, "lon": 4.140},
    {"nombre": "Es Castell", "lat": 39.877, "lon": 4.294},

    # Ibiza y Formentera (principales)
    {"nombre": "Eivissa", "lat": 38.907, "lon": 1.420},
    {"nombre": "Sant Antoni", "lat": 38.980, "lon": 1.303},
    {"nombre": "Santa Eulària", "lat": 38.984, "lon": 1.535},
    {"nombre": "La Savina", "lat": 38.727, "lon": 1.408},
    # Ibiza/Formentera extra (si cabe)
    {"nombre": "Sant Josep", "lat": 38.921, "lon": 1.295},
    {"nombre": "Sant Joan", "lat": 39.078, "lon": 1.512},
    {"nombre": "Sant Francesc", "lat": 38.710, "lon": 1.413},
]

# ------------------ Web Mercator utilidades ------------------
TILE_SIZE = 256
RADIUS = 6378137.0
ORIGIN_SHIFT = math.pi * RADIUS


def lon_to_merc_x(lon: float) -> float:
    return math.radians(lon) * RADIUS


def lat_to_merc_y(lat: float) -> float:
    lat = max(min(lat, 89.9), -89.9)
    return RADIUS * math.log(math.tan(math.pi / 4.0 + math.radians(lat) / 2.0))


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


# ------------------ Descarga base estática ------------------

def build_base_map_static(lat_min: float, lat_max: float, lon_min: float, lon_max: float,
                          width: int, height: int) -> Tuple[Image.Image, Dict[str, float]]:
    params = {
        "bbox": f"{lon_min},{lat_min},{lon_max},{lat_max}",
        "size": f"{width}x{height}",
        "maptype": "mapnik"
    }
    r = session.get(OSM_STATIC_URL, params=params, timeout=25)
    r.raise_for_status()
    img = Image.open(io.BytesIO(r.content)).convert("RGB")

    # Precalcular límites en metros Mercator para transformar lon/lat -> píxel
    min_x = lon_to_merc_x(lon_min)
    max_x = lon_to_merc_x(lon_max)
    min_y = lat_to_merc_y(lat_min)
    max_y = lat_to_merc_y(lat_max)
    transform = {"min_x": min_x, "max_x": max_x, "min_y": min_y, "max_y": max_y, "width": width, "height": height}
    return img, transform


# ------------------ Descarga de tiles (respaldo) ------------------

def download_tile(z: int, x: int, y: int) -> Image.Image:
    url = OSM_TILE_URL.format(z=z, x=x, y=y)
    try:
        r = session.get(url, timeout=15)
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content)).convert("RGB")
    except Exception:
        img = Image.new("RGB", (TILE_SIZE, TILE_SIZE), color=(230, 230, 230))
        draw = ImageDraw.Draw(img)
        draw.line((0, 0, TILE_SIZE, TILE_SIZE), fill=(200, 200, 200))
        draw.line((0, TILE_SIZE, TILE_SIZE, 0), fill=(200, 200, 200))
        return img


def build_base_map_tiles(lat_min: float, lat_max: float, lon_min: float, lon_max: float, zoom: int,
                         width: int, height: int) -> Tuple[Image.Image, Dict[str, float]]:
    px_min_x, px_max_y = lonlat_to_pixel(lon_min, lat_min, zoom)
    px_max_x, px_min_y = lonlat_to_pixel(lon_max, lat_max, zoom)

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
            tile = download_tile(zoom, tx, ty)
            dx = (tx - tile_x_min) * TILE_SIZE
            dy = (ty - tile_y_min) * TILE_SIZE
            canvas.paste(tile, (dx, dy))
            time.sleep(0.2)  # ser respetuoso

    crop_left = int(px_min_x - tile_x_min * TILE_SIZE)
    crop_top = int(px_min_y - tile_y_min * TILE_SIZE)
    crop_right = crop_left + int(bbox_width)
    crop_bottom = crop_top + int(bbox_height)
    canvas = canvas.crop((crop_left, crop_top, crop_right, crop_bottom))

    base_map = canvas.resize((width, height), Image.Resampling.LANCZOS)

    # Transform Mercator bounds para proyección consistente
    min_x = lon_to_merc_x(lon_min)
    max_x = lon_to_merc_x(lon_max)
    min_y = lat_to_merc_y(lat_min)
    max_y = lat_to_merc_y(lat_max)
    transform = {"min_x": min_x, "max_x": max_x, "min_y": min_y, "max_y": max_y, "width": width, "height": height}
    return base_map, transform


def project_point_mercator(lon: float, lat: float, transform: Dict[str, float]) -> Tuple[int, int]:
    min_x = transform["min_x"]
    max_x = transform["max_x"]
    min_y = transform["min_y"]
    max_y = transform["max_y"]
    width = transform["width"]
    height = transform["height"]

    x_m = lon_to_merc_x(lon)
    y_m = lat_to_merc_y(lat)

    x = int((x_m - min_x) / (max_x - min_x) * width)
    y = int((max_y - y_m) / (max_y - min_y) * height)  # invertido porque y-pantalla crece hacia abajo
    return x, y


# ------------------ Datos Open-Meteo ------------------
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def fetch_openmeteo(lat: float, lon: float) -> Dict:
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": ["temperature_2m", "relative_humidity_2m", "wind_speed_10m"],
        "timezone": "Europe/Madrid"
    }
    try:
        r = session.get(OPEN_METEO_URL, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        current = data.get("current", {})
        t = current.get("temperature_2m")
        return {
            "temp": None if t is None else round(float(t), 1),
        }
    except Exception:
        return {"temp": None, "humedad": None, "viento": None}


# ------------------ Dibujo ------------------

def strip_accents(text: str) -> str:
    try:
        return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    except Exception:
        return text

def sanitize_text(text: str) -> str:
    t = strip_accents(text)
    # Evitar símbolos no ASCII comunes en fuentes por defecto
    t = t.replace("°C", " C")
    t = t.replace("ºC", " C")
    t = t.replace("°", "")
    t = t.replace("º", "")
    return t

def strip_accents(text: str) -> str:
    try:
        return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    except Exception:
        return text

def temp_to_color(temp: float) -> Tuple[int, int, int]:
    # Paleta similar a ejemplo: morado (-10) -> azul -> cian -> verde -> amarillo -> naranja -> rojo -> fucsia (50)
    stops = [
        (-10, (132, 0, 168)),
        (-5, (44, 0, 184)),
        (0, (0, 90, 200)),
        (3, (0, 150, 200)),
        (6, (0, 180, 170)),
        (9, (0, 200, 120)),
        (12, (80, 200, 60)),
        (15, (150, 200, 0)),
        (18, (200, 180, 0)),
        (21, (230, 150, 0)),
        (24, (240, 120, 0)),
        (27, (240, 90, 0)),
        (30, (240, 60, 0)),
        (33, (230, 30, 0)),
        (36, (220, 0, 0)),
        (39, (220, 0, 40)),
        (42, (230, 0, 100)),
        (45, (240, 0, 150)),
        (47, (250, 0, 180)),
        (50, (255, 0, 220)),
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


def draw_marker(draw: ImageDraw.ImageDraw, x: int, y: int, text_lines: List[str], fonts: Dict, temp_value: float = None):
    # Punto de ubicación
    color = temp_to_color(temp_value)
    draw.ellipse([(x-5, y-5), (x+5, y+5)], fill=color, outline="#ffffff")

    visible = [t for t in text_lines if t]
    if not visible:
        return

    # Caja compacta en función de líneas (solo temperatura)
    text_max = max(len(t) for t in visible)
    box_w = max(52, text_max * 9 + 14)
    line_h = 18
    padding_v = 6
    box_h = padding_v * 2 + line_h * len(visible)

    box_x = x + 12 if x + 12 + box_w < WIDTH - 10 else x - 12 - box_w
    box_y = y - box_h // 2

    # Sombra y fondo
    # Fondo del badge con el color de la temperatura y texto negro
    draw.rectangle([(box_x + 2, box_y + 2), (box_x + box_w + 2, box_y + box_h + 2)], fill=(120, 120, 120))
    draw.rectangle([(box_x, box_y), (box_x + box_w, box_y + box_h)], outline=(40, 40, 40), fill=color, width=2)

    # Texto (temperatura)
    ty = box_y + padding_v
    for i, line in enumerate(visible):
        draw.text((box_x + 8, ty), line, fill="#000000", font=fonts["small"]) 
        ty += line_h


def main():
    print("Construyendo mapa base OSM (estático)...")
    try:
        base_map, transform = build_base_map_static(LAT_MIN, LAT_MAX, LON_MIN, LON_MAX, WIDTH, HEIGHT)
    except Exception as e:
        print(f"[Aviso] Static OSM falló: {e}. Probando tiles de respaldo...")
        base_map, transform = build_base_map_tiles(LAT_MIN, LAT_MAX, LON_MIN, LON_MAX, ZOOM, WIDTH, HEIGHT)

    img = base_map.convert("RGB")
    draw = ImageDraw.Draw(img)

    # Fuentes
    try:
        font_big = ImageFont.truetype("arial.ttf", 28)
        font_small = ImageFont.truetype("arial.ttf", 16)
    except Exception:
        font_big = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # Barra de título
    title = sanitize_text("Meteo de les Illes - Mapa actual")
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")
    draw.rectangle([(0, 0), (WIDTH, 50)], fill=(255, 255, 255))
    draw.text((20, 12), title, fill="#0d47a1", font=font_big)
    draw.text((WIDTH - 240, 16), fecha, fill="#263238", font=font_small)

    print("Añadiendo ciudades y datos (Open-Meteo)...")
    placed_boxes: List[tuple] = []  # lista de bounding boxes para evitar solapes
    margin = 4
    for c in CIUDADES:
        x, y = project_point_mercator(c["lon"], c["lat"], transform)
        meteo = fetch_openmeteo(c["lat"], c["lon"]) 
        temp_val = meteo.get("temp")
        text = sanitize_text("Sin datos") if temp_val is None else sanitize_text(f"{temp_val}°C")

        # Calcular caja estimada (antes de dibujar) para evitar solapes
        try:
            fw, fh = font_small.getsize(text)
        except Exception:
            fw, fh = (len(text) * 9, 16)
        box_w = max(52, fw + 14)
        box_h = 18 + 12  # line_h + padding
        box_x = x + 12 if x + 12 + box_w < WIDTH - 10 else x - 12 - box_w
        box_y = y - box_h // 2
        candidate = (box_x - margin, box_y - margin, box_x + box_w + margin, box_y + box_h + margin)

        overlaps = False
        for bx in placed_boxes:
            if not (candidate[2] < bx[0] or candidate[0] > bx[2] or candidate[3] < bx[1] or candidate[1] > bx[3]):
                overlaps = True
                break
        if overlaps:
            continue  # no dibujar este municipio si solapa

        placed_boxes.append(candidate)
        draw_marker(draw, x, y, [text], {"small": font_small}, temp_value=temp_val)

    # Leyenda de colores (tipo barra inferior)
    legend_h = 55
    legend_top = HEIGHT - legend_h - 12
    legend_left = 110
    legend_right = WIDTH - 110
    draw.rectangle([(legend_left - 10, legend_top - 10), (legend_right + 10, HEIGHT - 12 + 10)], fill=(255, 255, 255), outline=(180, 180, 180))
    # Escala -10 a 50 en segmentos
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
    # Ticks y etiqueta
    try:
        font_legend = ImageFont.truetype("arial.ttf", 14)
    except Exception:
        font_legend = ImageFont.load_default()
    for t in [-10, -7, -5, -3, 0, 3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36, 39, 42, 45, 47, 50]:
        x = legend_left + int((t - min_t) / (max_t - min_t) * (legend_right - legend_left))
        draw.line([(x, legend_top + 20), (x, legend_top + 24)], fill=(40, 40, 40))
        draw.text((x - 8, legend_top + 26), str(t), fill=(40, 40, 40), font=font_legend)
    draw.text(((legend_left + legend_right)//2 - 40, legend_top - 18), sanitize_text("Temp. °C"), fill=(40, 40, 40), font=font_legend)

    out_name = "mapa_baleares_openmeteo.png"
    img.save(out_name)
    print(f"[OK] Mapa guardado: {out_name}")
    # Evitar abrir ventana en entornos CI (GitHub Actions define CI=true)
    if os.environ.get("CI", "").lower() not in ("true", "1"):  # solo mostrar si no es CI
        try:
            img.show()
        except Exception:
            pass


if __name__ == "__main__":
    main()
