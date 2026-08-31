#!/usr/bin/env python3
"""El tiempo en la barra: cápsula compacta y tooltip con la previsión.

Los datos salen de wttr.in (formato j1, descripciones en español). La
respuesta se guarda en caché: si la red falla se pinta lo último bueno en
vez de dejar el hueco vacío.

La ubicación sale de ~/.config/hypr/weather-city (o de $WEATHER_CITY). Si el
fichero está vacío o pone "auto", wttr.in geolocaliza por IP.

  (nada)    JSON para la cápsula "custom/weather" de waybar
  --tooltip imprime solo el tooltip (para verlo con pango-view)
  --city    pregunta la ubicación por rofi y la guarda
"""

import html
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import requests

CITY_FILE = Path.home() / ".config/hypr/weather-city"
DEFAULT_CITY = "Madrid"
LANG = "es"
CACHE = Path(os.environ.get("XDG_RUNTIME_DIR") or "/tmp") / "waybar-weather.json"
CACHE_TTL = 900
TIMEOUT = 8
DAYS = 3
HOUR_STEP = 3
WAYBAR_SIGNAL = 12
THEME = Path.home() / ".config/rofi/menu.rasi"

# Iconos nf-md escritos como escapes: al pegar glifos directamente se cuelan
# bytes de reemplazo con demasiada facilidad.
I_SUN = "\U000f0599"
I_MOON = "\U000f0594"
I_PARTLY = "\U000f0595"
I_PARTLY_NIGHT = "\U000f0f31"
I_CLOUD = "\U000f0590"
I_FOG = "\U000f0591"
I_RAIN = "\U000f0597"
I_POUR = "\U000f0596"
I_SLEET = "\U000f067f"
I_SNOW = "\U000f0598"
I_STORM = "\U000f067e"
I_WIND = "\U000f059d"
I_DROP = "\U000f058e"
I_THERM = "\U000f050f"
I_EYE = "\U000f0208"
I_SUNRISE = "\U000f059c"
I_SUNSET = "\U000f059b"
I_PIN = "\U000f034e"
I_OFFLINE = "\U000f0159"

C_TEXT = "#cdd6f4"
C_MUTED = "#6c7086"
C_SUB = "#a6adc8"
C_ACCENT = "#b4befe"
C_RED = "#f38ba8"
C_PEACH = "#fab387"
C_YELLOW = "#f9e2af"
C_GREEN = "#a6e3a1"
C_TEAL = "#94e2d5"
C_SKY = "#89dceb"
C_SAPPHIRE = "#74c7ec"

# La paleta real la genera chezmoi desde .chezmoidata/colors.yaml; los
# valores de arriba sólo sirven de red si el fichero aún no existe.
try:
    _p = json.loads((Path.home() / ".config/hypr/colors.json").read_text())
    C_TEXT, C_MUTED, C_SUB = _p["text"], _p["overlay0"], _p["subtext0"]
    C_ACCENT, C_RED, C_PEACH = _p["accent3"], _p["red"], _p["peach"]
    C_YELLOW, C_GREEN, C_TEAL = _p["yellow"], _p["green"], _p["teal"]
    C_SKY, C_SAPPHIRE = _p["sky"], _p["sapphire"]
except (OSError, ValueError, KeyError):
    pass

# Códigos de wttr.in agrupados -> (icono de día, icono de noche, clase CSS).
GROUPS = [
    ({113}, (I_SUN, I_MOON, "clear")),
    ({116}, (I_PARTLY, I_PARTLY_NIGHT, "partly")),
    ({119, 122}, (I_CLOUD, I_CLOUD, "cloud")),
    ({143, 248, 260}, (I_FOG, I_FOG, "fog")),
    ({176, 263, 266, 281, 284, 293, 296, 299, 353}, (I_RAIN, I_RAIN, "rain")),
    ({302, 305, 308, 311, 314, 356, 359}, (I_POUR, I_POUR, "rain")),
    ({182, 185, 317, 320, 350, 362, 365, 374, 377}, (I_SLEET, I_SLEET, "sleet")),
    ({179, 227, 230, 323, 326, 329, 332, 335, 338, 368, 371}, (I_SNOW, I_SNOW, "snow")),
    ({200, 386, 389, 392, 395}, (I_STORM, I_STORM, "storm")),
]

DAY_ABBR = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
MONTH_ABBR = ["ene", "feb", "mar", "abr", "may", "jun",
              "jul", "ago", "sep", "oct", "nov", "dic"]


def icon_for(code, is_day=True):
    code = int(code)
    for codes, (day, night, cls) in GROUPS:
        if code in codes:
            return (day if is_day else night), cls
    return I_CLOUD, "cloud"


def temp_color(t):
    for limit, color in ((0, C_SKY), (10, C_SAPPHIRE), (18, C_TEAL),
                         (25, C_GREEN), (30, C_YELLOW), (35, C_PEACH)):
        if t <= limit:
            return color
    return C_RED


def wind_dir(point):
    """NNW -> NNO: en castellano el oeste es O, no W."""
    return point.replace("W", "O")


def rain_bar(pct, width=5):
    # Por debajo del 10% la barra sobra: un bloque entero por un 1% engaña.
    if pct < 10:
        return " " * width
    filled = max(1, round(pct * width / 100))
    return "\u2588" * filled + "\u2591" * (width - filled)


def hhmm(text):
    """'06:12 AM' -> '06:12'."""
    try:
        return datetime.strptime(text.strip(), "%I:%M %p").strftime("%H:%M")
    except ValueError:
        return text.strip()


def span(text, color=None, weight=None, size=None, escape=True):
    body = html.escape(str(text)) if escape else str(text)
    attrs = ""
    if color:
        attrs += f' color="{color}"'
    if weight:
        attrs += f' weight="{weight}"'
    if size:
        attrs += f' size="{size}"'
    return f"<span{attrs}>{body}</span>" if attrs else body


# --------------------------------------------------------------------------
# Datos
# --------------------------------------------------------------------------

def city():
    """Ubicación configurada; cadena vacía = que wttr.in tire de la IP."""
    valor = os.environ.get("WEATHER_CITY")
    if valor is None:
        try:
            valor = CITY_FILE.read_text()
        except OSError:
            valor = DEFAULT_CITY
    valor = valor.strip()
    return "" if valor.lower() in ("", "auto", "ip") else valor


def download(place):
    resp = requests.get(f"https://wttr.in/{quote(place)}?format=j1&lang={LANG}",
                        timeout=TIMEOUT, headers={"User-Agent": "curl/8"})
    resp.raise_for_status()
    return resp.json()


def fetch():
    """Devuelve (datos, edad en segundos). Cae a la caché si no hay red."""
    place = city()
    cached = None
    if CACHE.exists():
        try:
            cached = json.loads(CACHE.read_text())
        except ValueError:
            cached = None
        # Un cambio de ubicación invalida la caché aunque siga fresca.
        if cached and cached.get("city") != place:
            cached = None
        if cached and time.time() - cached["ts"] < CACHE_TTL:
            return cached["data"], time.time() - cached["ts"]
    try:
        data = download(place)
        CACHE.write_text(json.dumps({"ts": time.time(), "city": place, "data": data}))
        return data, 0
    except (requests.RequestException, ValueError, OSError):
        if cached:
            return cached["data"], time.time() - cached["ts"]
        return None, None


def desc(node):
    """Descripción en español si wttr.in la trae, si no la inglesa."""
    for key in (f"lang_{LANG}", "weatherDesc"):
        value = node.get(key)
        if value:
            return value[0]["value"].strip()
    return ""


def place_name(data):
    """El sitio que wttr.in dice haber resuelto, no lo que pidió el usuario."""
    try:
        return data["nearest_area"][0]["areaName"][0]["value"].strip()
    except (KeyError, IndexError, TypeError):
        return city() or "por IP"


def day_label(index, iso):
    fecha = datetime.strptime(iso, "%Y-%m-%d")
    nombre = {0: "hoy", 1: "mañana"}.get(index, DAY_ABBR[fecha.weekday()])
    return f"{nombre} {fecha.day} {MONTH_ABBR[fecha.month - 1]}"


def is_daytime(when, sunrise, sunset):
    return hhmm(sunrise) <= when.strftime("%H:%M") <= hhmm(sunset)


# --------------------------------------------------------------------------
# Pintado
# --------------------------------------------------------------------------

def build_tooltip(data, age):
    now = datetime.now()
    cur = data["current_condition"][0]
    astro = data["weather"][0]["astronomy"][0]
    sunrise, sunset = hhmm(astro["sunrise"]), hhmm(astro["sunset"])
    icon, _ = icon_for(cur["weatherCode"], is_daytime(now, sunrise, sunset))
    temp, feels = int(cur["temp_C"]), int(cur["FeelsLikeC"])

    lineas = [
        f"{span(I_PIN, C_ACCENT, escape=False)} {span(place_name(data), C_TEXT, weight='bold')}"
        f"  {span(now.strftime('%H:%M'), C_MUTED)}",
        f"{span(icon, temp_color(temp), size='xx-large', escape=False)}  "
        f"{span(f'{temp}°', C_TEXT, size='xx-large')}"
        f"   {span(desc(cur), C_SUB)}"
        f"   {span(f'{I_THERM} {feels}°', C_MUTED, escape=False)}",
        "",
    ]

    # <tt> fuerza la monoespaciada: sin ella las columnas se descuadran.
    detalles = (
        f"{I_WIND} {int(cur['windspeedKmph']):>3} km/h {wind_dir(cur['winddir16Point']):<3}   "
        f"{I_DROP} {int(cur['humidity']):>3}%   "
        f"{I_EYE} {int(cur['visibility']):>2} km   "
        f"{I_SUNRISE} {sunrise}   {I_SUNSET} {sunset}"
    )
    lineas.append(f"<tt>{span(detalles, C_SUB)}</tt>")

    cuerpo = []
    for i, day in enumerate(data["weather"][:DAYS]):
        astro = day["astronomy"][0]
        amanece, anochece = hhmm(astro["sunrise"]), hhmm(astro["sunset"])
        minima, maxima = int(day["mintempC"]), int(day["maxtempC"])
        cuerpo.append("")
        cuerpo.append(
            span(f"{day_label(i, day['date']):<16}", C_ACCENT, weight="bold")
            + span("mín ", C_MUTED)
            + span(f"{minima:>3}°", temp_color(minima))
            + span("   máx ", C_MUTED)
            + span(f"{maxima}°", temp_color(maxima))
        )
        for hour in day["hourly"]:
            reloj = int(hour["time"]) // 100
            if reloj % HOUR_STEP or (i == 0 and reloj < now.hour):
                continue
            momento = datetime.strptime(f"{day['date']} {reloj:02d}", "%Y-%m-%d %H")
            ic, _ = icon_for(hour["weatherCode"], is_daytime(momento, amanece, anochece))
            t = int(hour["FeelsLikeC"])
            lluvia = max(int(hour["chanceofrain"]), int(hour["chanceofsnow"]))
            color_lluvia = C_SAPPHIRE if lluvia >= 30 else C_MUTED
            cuerpo.append(
                span(f"{reloj:02d}h ", C_MUTED)
                + span(f"{ic} ", temp_color(t), escape=False)
                + span(f"{t:>3}°  ", temp_color(t))
                + span(rain_bar(lluvia), color_lluvia)
                + span(f"{lluvia:>4}%  ", color_lluvia)
                + span(desc(hour)[:24], C_SUB)
            )
    lineas.append(f"<tt>{chr(10).join(cuerpo)}</tt>")

    if age and age > CACHE_TTL:
        lineas.append("")
        lineas.append(span(f"{I_OFFLINE} sin conexión · datos de hace "
                           f"{int(age // 60)} min", C_YELLOW, escape=False))
    return "\n".join(lineas)


def build_status(data, age):
    if data is None:
        return {"text": f"{I_OFFLINE} --°", "class": ["weather", "offline"],
                "tooltip": "Sin datos del tiempo: no hay red ni caché"}
    cur = data["current_condition"][0]
    astro = data["weather"][0]["astronomy"][0]
    icon, cls = icon_for(cur["weatherCode"],
                         is_daytime(datetime.now(), astro["sunrise"], astro["sunset"]))
    return {
        "text": f"{icon}  {int(cur['temp_C'])}°",
        "alt": cls,
        "class": ["weather", cls] + (["stale"] if age and age > CACHE_TTL else []),
        "tooltip": build_tooltip(data, age),
    }


def set_city():
    """Pregunta la ubicación por rofi, la comprueba y la guarda."""
    actual = city()
    mesg = ("Ciudad, código postal o coordenadas. "
            "Vacío o <b>auto</b> para localizar por IP.")
    proc = subprocess.run(
        ["rofi", "-dmenu", "-i", "-markup-rows", "-theme", str(THEME),
         "-theme-str", "window { width: 480px; location: north; anchor: north; }"
                       "listview { enabled: false; }",
         "-p", "\U000f034e  Ubicación", "-mesg", mesg, "-filter", actual],
        input="", text=True, capture_output=True)
    if proc.returncode != 0:
        return
    nueva = proc.stdout.strip()
    destino = "" if nueva.lower() in ("", "auto", "ip") else nueva
    if destino:
        try:
            download(destino)
        except (requests.RequestException, ValueError):
            notify("Ubicación no válida", f"wttr.in no encuentra «{nueva}»", True)
            return
    CITY_FILE.write_text(destino + "\n")
    CACHE.unlink(missing_ok=True)
    subprocess.run(["pkill", f"-RTMIN+{WAYBAR_SIGNAL}", "waybar"], check=False)
    notify("El tiempo", f"Ubicación: {destino or 'automática por IP'}")


def notify(title, body="", error=False):
    subprocess.run(["notify-send", "-a", "waybar",
                    "-i", "dialog-error" if error else "weather-few-clouds",
                    title, body], check=False)


def main():
    if "--city" in sys.argv:
        set_city()
        return
    data, age = fetch()
    if "--tooltip" in sys.argv:
        print(build_tooltip(data, age) if data else "Sin datos")
        return
    print(json.dumps(build_status(data, age), ensure_ascii=False))


if __name__ == "__main__":
    main()
