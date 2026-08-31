#!/usr/bin/env python3
"""Agenda de los calendarios CalDAV en waybar y rofi.

Los eventos salen de evolution-data-server, es decir de las mismas cuentas
que ya usa GNOME Calendar (Nextcloud: Personal, Work, Activism...). No hay
que configurar nada aparte: se leen las fuentes marcadas como visibles.

  --clock   bucle continuo: reloj de la barra con el mes en el tooltip
  --tooltip imprime solo ese tooltip (lo usa --clock en otro proceso)
  --status  JSON para la cápsula "custom/agenda" de waybar
  --sync    fuerza un refresco contra el servidor y recarga la caché
  (nada)    abre el menú interactivo de rofi
"""

import argparse
import calendar
import html
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path

# gi + ECal ocupan 46 MiB de RSS; el bucle del reloj no los necesita, así que
# se cargan solo cuando de verdad hay que hablar con evolution-data-server.
ECal = EDataServer = ICalGLib = Gio = None


def load_gi():
    global ECal, EDataServer, ICalGLib, Gio
    if ECal is None:
        import gi
        gi.require_version("EDataServer", "1.2")
        gi.require_version("ECal", "2.0")
        from gi.repository import (ECal as _ecal, EDataServer as _eds,
                                   ICalGLib as _ical, Gio as _gio)
        ECal, EDataServer, ICalGLib, Gio = _ecal, _eds, _ical, _gio

# Iconos nf-md escritos como escapes: al pegar glifos directamente se cuelan
# bytes de reemplazo con demasiada facilidad.
I_CAL = "\U000f00ed"
I_NEW = "\U000f00f1"
I_DONE = "\U000f00ef"
I_TODAY = "\U000f00f3"
I_SYNC = "\U000f04e6"
I_CLOCK = "\U000f0954"
I_PIN = "\U000f034e"
I_VIDEO = "\U000f0567"
I_COPY = "\U000f018f"
I_TRASH = "\U000f01b4"
I_BACK = "\U000f004d"
I_EYE = "\U000f0208"
I_OPEN = "\U000f03cc"

C_TEXT = "#cdd6f4"
C_MUTED = "#6c7086"
C_SUB = "#a6adc8"
C_ACCENT = "#b4befe"
C_WARN = "#f9e2af"
C_LIVE = "#a6e3a1"
C_SURF = "#313244"
C_BASE = "#11111b"

# La paleta real la genera chezmoi desde .chezmoidata/colors.yaml; los
# valores de arriba sólo sirven de red si el fichero aún no existe.
try:
    _p = json.loads((Path.home() / ".config/hypr/colors.json").read_text())
    C_TEXT, C_MUTED, C_SUB = _p["text"], _p["overlay0"], _p["subtext0"]
    C_ACCENT, C_WARN, C_LIVE = _p["accent3"], _p["yellow"], _p["green"]
    C_SURF, C_BASE = _p["surface0"], _p["crust"]
except (OSError, ValueError, KeyError):
    pass

HOME = Path.home()
THEME = HOME / ".config/rofi/menu.rasi"
CACHE = Path(os.environ.get("XDG_RUNTIME_DIR") or "/tmp") / "waybar-agenda.json"
CACHE_TTL = 120
DAYS_AHEAD = 21
CONNECT_TIMEOUT = 15
# Tope por llamada a evolution-data-server: un calendario que no responde no
# puede llevarse por delante a los demás.
CALL_LIMIT = 10
WAYBAR_SIGNAL = 11
# Más allá de esto la cápsula de la barra no anuncia nada: es un recordatorio
# de lo inmediato, la agenda completa está en el menú.
STATUS_HORIZON = 14 * 3600

DAY_NAMES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
DAY_ABBR = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
MONTH_NAMES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]
MONTH_ABBR = [m[:3] for m in MONTH_NAMES]

MEETING_RE = re.compile(r"https?://\S*(?:meet|zoom|jitsi|teams|whereby|bbb|webex)\S*", re.I)
URL_RE = re.compile(r"https?://\S+")


# --------------------------------------------------------------------------
# Lectura de evolution-data-server
# --------------------------------------------------------------------------

def registry():
    load_gi()
    return EDataServer.SourceRegistry.new_sync(None)


def calendar_sources(reg):
    """Fuentes de calendario habilitadas, ordenadas por nombre."""
    out = []
    for src in reg.list_sources(EDataServer.SOURCE_EXTENSION_CALENDAR):
        if not src.get_enabled():
            continue
        ext = src.get_extension(EDataServer.SOURCE_EXTENSION_CALENDAR)
        out.append({
            "uid": src.get_uid(),
            "name": src.get_display_name(),
            "color": ext.get_color() or C_ACCENT,
            "selected": bool(ext.get_selected()),
            "source": src,
        })
    out.sort(key=lambda c: c["name"].lower())
    return out


class deadline:
    """Cancellable que se cancela solo pasados N segundos.

    Un backend CalDAV enfermo deja las llamadas síncronas colgadas para
    siempre; sin esto, un solo calendario bloquea la agenda entera.
    """

    def __init__(self, seconds=CALL_LIMIT):
        self.cancellable = Gio.Cancellable()
        self._timer = threading.Timer(seconds, self.cancellable.cancel)
        self._timer.daemon = True

    def __enter__(self):
        self._timer.start()
        return self.cancellable

    def __exit__(self, *_exc):
        self._timer.cancel()
        return False


def _connect(src, wait=0):
    """El 2º argumento son los segundos a esperar a que el backend esté online,
    no un timeout de error: con >0 se pagan enteros por cada calendario antes
    de devolver nada. Para leer basta la caché local de EDS, así que 0."""
    with deadline() as cancel:
        return ECal.Client.connect_sync(src, ECal.ClientSourceType.EVENTS, wait, cancel)


def _epoch(itime):
    """ICalTime -> epoch. Las instancias llegan con su propia zona horaria."""
    if itime is None:
        return None
    if itime.is_date():
        return int(datetime(itime.get_year(), itime.get_month(), itime.get_day()).timestamp())
    tz = itime.get_timezone()
    if tz is not None:
        return int(itime.as_timet_with_zone(tz))
    # Hora flotante: se interpreta como hora local.
    return int(datetime(
        itime.get_year(), itime.get_month(), itime.get_day(),
        itime.get_hour(), itime.get_minute(), itime.get_second(),
    ).timestamp())


def _prop(comp, kind):
    prop = comp.get_first_property(kind)
    return prop.get_value_as_string() if prop else None


def cache_range():
    """Desde el 1 del mes (lo pinta la rejilla) hasta el fin de la agenda."""
    today = date.today()
    last = grid_months()[-1]
    last = last.replace(day=calendar.monthrange(last.year, last.month)[1])
    return today.replace(day=1), max(last, today + timedelta(days=DAYS_AHEAD))


def fetch_events(first=None, last=None):
    if first is None or last is None:
        first, last = cache_range()
    reg = registry()
    start = int(datetime.combine(first, dtime.min).timestamp())
    end = int(datetime.combine(last, dtime.max).timestamp())
    events = []

    for cal in calendar_sources(reg):
        if not cal["selected"]:
            continue
        try:
            client = _connect(cal["source"])
        except Exception:
            continue

        def collect(comp, istart, iend, *_ignored, _cal=cal):
            events.append({
                "summary": comp.get_summary() or "(sin título)",
                "start": _epoch(istart),
                "end": _epoch(iend) or _epoch(istart),
                "allday": bool(istart.is_date()),
                "calendar": _cal["name"],
                "color": _cal["color"],
                "source": _cal["uid"],
                "uid": comp.get_uid(),
                "location": comp.get_location() or "",
                "description": (comp.get_description() or "").strip(),
                "url": _prop(comp, ICalGLib.PropertyKind.URL_PROPERTY) or "",
            })
            return True

        try:
            with deadline() as cancel:
                client.generate_instances_sync(start, end, cancel, collect)
        except Exception:
            continue

    events.sort(key=lambda e: (e["start"], e["summary"].lower()))
    return events


def load_events(force=False, offline=False):
    """offline=True nunca habla con EDS: sirve la caché tal cual esté.

    Leer de EDS puede tardar minutos si un backend está sincronizando, y el
    reloj de la barra no puede permitirse esperar.
    """
    if not force and CACHE.exists():
        try:
            if offline or time.time() - CACHE.stat().st_mtime < CACHE_TTL:
                return json.loads(CACHE.read_text())
        except (OSError, ValueError):
            pass
    if offline:
        return []
    events = fetch_events()
    try:
        CACHE.write_text(json.dumps(events))
    except OSError:
        pass
    return events


def spawn_refresh():
    """Relee los calendarios en otro proceso, sin esperarlo."""
    subprocess.Popen([sys.executable, os.path.realpath(__file__), "--status"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)


def events_for_ui():
    """Eventos para pintar algo ya: la caché si existe, aunque esté vieja."""
    if CACHE.exists():
        stale = time.time() - CACHE.stat().st_mtime > CACHE_TTL
        events = load_events(offline=True)
        if stale:
            spawn_refresh()
        return events
    return load_events()


def refresh_remote():
    """Pide a cada calendario que sincronice contra el servidor."""
    reg = registry()
    for cal in calendar_sources(reg):
        try:
            client = _connect(cal["source"], CONNECT_TIMEOUT)
            if client.check_refresh_supported():
                client.refresh_sync(None)
        except Exception:
            continue
    return load_events(force=True)


# --------------------------------------------------------------------------
# Formato
# --------------------------------------------------------------------------

def day_label(day):
    today = date.today()
    delta = (day - today).days
    if delta == 0:
        return "Hoy"
    if delta == 1:
        return "Mañana"
    if delta == -1:
        return "Ayer"
    if 0 < delta < 7:
        return DAY_NAMES[day.weekday()].capitalize()
    return f"{DAY_ABBR[day.weekday()]} {day.day} {MONTH_ABBR[day.month - 1]}"


def day_heading(day):
    """Cabecera de grupo: la fecha aparte solo si day_label no la lleva ya."""
    label = day_label(day)
    if any(char.isdigit() for char in label):
        return f"{DAY_NAMES[day.weekday()].capitalize()} {day.day} de {MONTH_NAMES[day.month - 1]}", ""
    return label, f"{day.day} {MONTH_NAMES[day.month - 1]}"


def when_text(ev):
    start = datetime.fromtimestamp(ev["start"])
    end = datetime.fromtimestamp(ev["end"])
    if ev["allday"]:
        days = max(1, (end.date() - start.date()).days)
        if days > 1:
            return f"{day_label(start.date())} → {day_label(end.date() - timedelta(days=1))}"
        return f"{day_label(start.date())} · todo el día"
    return f"{day_label(start.date())} · {start:%H:%M}–{end:%H:%M}"


def relative(seconds):
    if seconds < 60:
        return "ahora"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"en {minutes} min"
    hours = minutes / 60
    if hours < 24:
        return f"en {hours:.0f} h" if hours >= 2 else f"en {minutes} min"
    return f"en {int(hours // 24)} d"


def esc(text):
    return html.escape(str(text), quote=False)


def ellipsis(text, width):
    text = " ".join(str(text).split())
    return text if len(text) <= width else text[: width - 1] + "…"


def meeting_url(ev):
    blob = " ".join((ev.get("url", ""), ev.get("location", ""), ev.get("description", "")))
    match = MEETING_RE.search(blob) or URL_RE.search(blob)
    return match.group(0).rstrip(".,;)") if match else ""


# --------------------------------------------------------------------------
# Módulo de waybar
# --------------------------------------------------------------------------

def cmd_status(_args):
    try:
        events = load_events()
    except Exception:
        events = []

    now = time.time()
    today = date.today()
    live = [e for e in events if e["start"] <= now < e["end"] and not e["allday"]]
    ahead = [e for e in events if e["start"] > now]
    todays = [e for e in events if datetime.fromtimestamp(e["start"]).date() == today]

    nxt = live[0] if live else (ahead[0] if ahead else None)
    if nxt is None or (not live and nxt["start"] - now > STATUS_HORIZON):
        print(json.dumps({"text": "", "tooltip": "", "class": "empty"}))
        return

    if live:
        head = f"{I_CLOCK} ahora"
        klass = "live"
    elif nxt["allday"]:
        head = I_TODAY
        klass = "soon" if nxt["start"] - now < 3600 else "upcoming"
    else:
        head = f"{I_CLOCK} {datetime.fromtimestamp(nxt['start']):%H:%M}"
        klass = "soon" if nxt["start"] - now < 3600 else "upcoming"

    lines = [f"<b>{esc(nxt['summary'])}</b>", f"<i>{esc(when_text(nxt))}</i>"]
    if not live:
        lines[1] += f"  ({relative(nxt['start'] - now)})"
    if nxt["location"]:
        lines.append(f"{I_PIN} {esc(ellipsis(nxt['location'], 48))}")
    lines.append("")
    lines.append(f"<b>{esc(day_label(today))} · {len(todays)} evento(s)</b>")
    for ev in todays[:6]:
        stamp = "todo el día" if ev["allday"] else f"{datetime.fromtimestamp(ev['start']):%H:%M}"
        mark = I_DONE if ev["end"] <= now else "·"
        lines.append(f"{mark} <span color='{ev['color']}'>{stamp}</span>  {esc(ellipsis(ev['summary'], 40))}")

    # ensure_ascii=False: con los escapes \uXXXX los iconos fuera del BMP salen
    # como pares subrogados y waybar descarta el módulo entero.
    print(json.dumps({
        "text": f"{head}  {ellipsis(nxt['summary'], 24)}",
        "tooltip": "\n".join(lines),
        "class": klass,
    }, ensure_ascii=False))


# --------------------------------------------------------------------------
# Reloj con el mes en el tooltip
# --------------------------------------------------------------------------

CELL = 4  # ancho de cada casilla de la rejilla, en caracteres


def grid_months():
    """Mes actual y el siguiente: en columnas caben los dos siempre."""
    today = date.today()
    first = today.replace(day=1)
    last = calendar.monthrange(today.year, today.month)[1]
    return [first, today.replace(day=last) + timedelta(days=1)]


def days_with_events(events, month):
    """{día del mes: [colores]}, contando también los eventos de varios días."""
    marks = {}
    for ev in events:
        first = datetime.fromtimestamp(ev["start"]).date()
        last = datetime.fromtimestamp(ev["end"]).date()
        # Un evento de día completo termina a las 00:00 del día siguiente.
        if ev["allday"] and last > first:
            last -= timedelta(days=1)
        day = first
        while day <= last:
            if day.month == month.month and day.year == month.year:
                colours = marks.setdefault(day.day, [])
                if ev["color"] not in colours:
                    colours.append(ev["color"])
            day += timedelta(days=1)
    return marks


def month_grid(events, month=None):
    """Rejilla del mes: número arriba, un punto por calendario debajo.

    Todas las líneas miden exactamente CELL*7 caracteres visibles, para poder
    pegar dos meses uno al lado del otro sin descuadrar nada.
    """
    month = month or date.today()
    today = date.today()
    marks = days_with_events(events, month)
    width = CELL * 7

    title = f"{MONTH_NAMES[month.month - 1].capitalize()} {month.year}"
    lines = [f"<b><span color='{C_ACCENT}'>{title.center(width)}</span></b>",
             f"<span color='{C_MUTED}'>"
             + "".join(f"{d:>3} " for d in DAY_ABBR) + "</span>"]

    for week in calendar.Calendar(firstweekday=0).monthdatescalendar(month.year, month.month):
        numbers, dots = "", ""
        for day in week:
            if day.month != month.month:
                numbers += " " * CELL
                dots += " " * CELL
                continue
            # Alineado a la derecha en 3 + un espacio: así el punto de debajo
            # cae bajo el dígito tanto en los días de una cifra como de dos.
            cell = f"{day.day:>3}"
            if day == today:
                numbers += f"<span bgcolor='{C_ACCENT}' color='{C_BASE}'><b>{cell}</b></span> "
            elif day < today:
                numbers += f"<span color='{C_MUTED}'>{cell}</span> "
            else:
                numbers += f"<span color='{C_TEXT}'>{cell}</span> "
            colours = marks.get(day.day, [])[:3]
            painted = "".join(f"<span color='{c}'>•</span>" for c in colours)
            dots += " " * (3 - len(colours)) + painted + " "
        lines.append(numbers)
        lines.append(dots)

    return lines


def side_by_side(blocks, gap=3):
    """Pega bloques monoespaciados en columnas, rellenando el más corto."""
    blank = " " * (CELL * 7)
    tall = max(len(b) for b in blocks)
    joint = " " * gap
    return [joint.join(b[i] if i < len(b) else blank for b in blocks)
            for i in range(tall)]


def legend(events):
    seen = {}
    for ev in events:
        seen.setdefault(ev["calendar"], ev["color"])
    return "  ".join(f"<span color='{c}'>•</span> {esc(n)}" for n, c in seen.items())


def tooltip_markup():
    try:
        events = load_events(offline=True)
    except Exception:
        events = []

    now = time.time()
    today = date.today()
    grids = [month_grid(events, m) for m in grid_months()]
    # Los meses van en columnas, no apilados: apilados el tooltip salía
    # estrechísimo y larguísimo.
    body = side_by_side(grids)
    width = max(CELL * 7 * len(grids) + 3 * (len(grids) - 1), 46)
    rule = f"<span color='{C_MUTED}'>{'─' * width}</span>"

    todays = [e for e in events if datetime.fromtimestamp(e["start"]).date() == today]
    week_end = datetime.combine(today + timedelta(days=7), dtime.min).timestamp()
    soon = [e for e in events if now <= e["start"] < week_end]

    left = f" {I_CAL}  {len(todays)} hoy · {len(soon)} en 7 días"
    right = f"{today.day} {MONTH_NAMES[today.month - 1][:3]} "
    pad = max(1, width - len(left) - len(right))
    lines = [f"<span bgcolor='{C_SURF}' color='{C_SUB}'>{esc(left)}"
             f"{' ' * pad}<b>{esc(right)}</b></span>", ""]
    lines += body
    lines.append(rule)

    if todays:
        for ev in todays[:5]:
            stamp = "todo el día" if ev["allday"] else f"{datetime.fromtimestamp(ev['start']):%H:%M}"
            body_txt = esc(ellipsis(ev["summary"], 32))
            if ev["end"] <= now:
                body_txt = f"<span color='{C_MUTED}'>{body_txt}</span>"
            elif ev["start"] <= now:
                body_txt = f"<span color='{C_LIVE}'><b>{body_txt}</b></span>"
            lines.append(f" <span color='{ev['color']}'>•</span> "
                         f"<span color='{C_SUB}'>{stamp:>11}</span>  {body_txt}")
    else:
        lines.append(f" <span color='{C_MUTED}'>Hoy no hay nada en la agenda</span>")

    marks = legend(events)
    if marks:
        lines.append("")
        lines.append(f" <span color='{C_MUTED}'>{marks}</span>")

    lines.append(rule)
    lines.append(f" <span color='{C_MUTED}'>Clic: agenda  Clic derecho: GNOME Calendar</span>")

    # <tt> fuerza la monoespaciada: sin ella la rejilla se descuadra.
    return f"<tt>{chr(10).join(lines)}</tt>"


def cmd_tooltip(_args=None):
    print(tooltip_markup())


def cmd_clock(_args=None):
    """Bucle continuo para waybar: imprime el reloj cada minuto en punto.

    Todo lo que hay aquí lee sólo la caché: quien la refresca es --status,
    que corre en su propio proceso. Una llamada a EDS desde este bucle
    congelaba la hora minutos enteros si un backend estaba sincronizando.
    """
    if not CACHE.exists():
        spawn_refresh()
    while True:
        print(json.dumps({"text": datetime.now().strftime("%H:%M  %d/%m"),
                          "tooltip": tooltip_markup()}, ensure_ascii=False), flush=True)
        time.sleep(60 - datetime.now().second)


# --------------------------------------------------------------------------
# rofi
# --------------------------------------------------------------------------

THEME_STR = (
    "window { width: 480px; location: north; anchor: north; x-offset: 0px; }"
    "listview { lines: 13; }"
)


def rofi(rows, prompt, mesg=None, lines=None, selected=None):
    """Lanza rofi y devuelve el índice elegido (o None)."""
    theme = THEME_STR if lines is None else THEME_STR.replace("lines: 13", f"lines: {lines}")
    cmd = [
        "rofi", "-dmenu", "-i", "-markup-rows", "-format", "i", "-no-custom",
        "-theme", str(THEME), "-theme-str", theme, "-p", prompt,
    ]
    if mesg:
        cmd += ["-mesg", mesg]
    if selected:
        cmd += ["-selected-row", str(selected)]
    proc = subprocess.run(cmd, input="\n".join(rows), text=True, capture_output=True)
    if proc.returncode != 0:
        return None
    try:
        return int(proc.stdout.strip())
    except ValueError:
        return None


def rofi_input(prompt, mesg=None, placeholder=""):
    cmd = [
        "rofi", "-dmenu", "-i", "-markup-rows", "-theme", str(THEME),
        "-theme-str", THEME_STR + f"listview {{ enabled: false; }} entry {{ placeholder: \"{placeholder}\"; }}",
        "-p", prompt,
    ]
    if mesg:
        cmd += ["-mesg", mesg]
    proc = subprocess.run(cmd, input="", text=True, capture_output=True)
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def notify(title, body="", error=False):
    subprocess.run(
        ["notify-send", "-a", "waybar",
         "-i", "dialog-error" if error else "calendar", title, body],
        check=False,
    )


def poke_waybar():
    CACHE.unlink(missing_ok=True)
    subprocess.run(["pkill", f"-RTMIN+{WAYBAR_SIGNAL}", "waybar"], check=False)


def copy(text):
    subprocess.run(["wl-copy", "--", text], check=False)


def spawn(argv):
    subprocess.Popen(argv, start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# --------------------------------------------------------------------------
# Menú principal
# --------------------------------------------------------------------------

def build_rows(events):
    """Devuelve (filas de rofi, acciones paralelas)."""
    now = time.time()
    rows, actions = [], []
    current_day = None
    first_pending = None
    # La caché arranca el día 1 del mes porque la rejilla del reloj lo necesita;
    # la agenda solo mira de hoy en adelante.
    floor = datetime.combine(date.today(), dtime.min).timestamp()
    events = [e for e in events if e["end"] >= floor]

    for ev in events:
        day = datetime.fromtimestamp(ev["start"]).date()
        if day != current_day:
            current_day = day
            title, sub = day_heading(day)
            row = f"<span color='{C_ACCENT}'><b>{esc(title)}</b></span>"
            if sub:
                row += f"<span color='{C_MUTED}'>  ·  {esc(sub)}</span>"
            rows.append(row)
            actions.append(("noop", None))

        past = ev["end"] <= now
        if not past and first_pending is None:
            first_pending = len(rows)
        live = ev["start"] <= now < ev["end"]
        if ev["allday"]:
            stamp = "· · ·"
        else:
            stamp = f"{datetime.fromtimestamp(ev['start']):%H:%M}"

        bullet = "●" if live else ("○" if past else "●")
        title = esc(ellipsis(ev["summary"], 38))
        if live:
            title = f"<b>{title}</b>"
        colour = C_MUTED if past else C_TEXT
        stamp_colour = C_LIVE if live else (C_MUTED if past else C_SUB)
        rows.append(
            f"<span color='{ev['color']}'>{bullet}</span> "
            f"<span color='{stamp_colour}'>{stamp}</span>  "
            f"<span color='{colour}'>{title}</span>"
        )
        actions.append(("event", ev))

    if not rows:
        rows.append(f"<span color='{C_MUTED}'>Sin eventos en los próximos {DAYS_AHEAD} días</span>")
        actions.append(("noop", None))

    rows.append(f"<span color='{C_MUTED}'>───────────────</span>")
    actions.append(("noop", None))
    for icon, label, action in (
        (I_NEW, "Nuevo evento", "new"),
        (I_EYE, "Calendarios", "calendars"),
        (I_SYNC, "Sincronizar", "sync"),
        (I_OPEN, "Abrir GNOME Calendar", "gnome"),
    ):
        rows.append(f"{icon}  {label}")
        actions.append((action, None))
    return rows, actions, first_pending or 0


def header(events):
    today = date.today()
    now = time.time()
    todays = [e for e in events if datetime.fromtimestamp(e["start"]).date() == today]
    left = len([e for e in todays if e["end"] > now])
    name = f"{DAY_NAMES[today.weekday()].capitalize()}, {today.day} de {MONTH_NAMES[today.month - 1]}"
    if not todays:
        tail = "sin nada en la agenda"
    elif left:
        tail = f"{left}/{len(todays)} pendientes"
    else:
        tail = f"{len(todays)} evento(s), ya pasados"
    return f"<b>{esc(name)}</b>  <span color='{C_MUTED}'>·  {esc(tail)}</span>"


def menu(events):
    while True:
        rows, actions, selected = build_rows(events)
        idx = rofi(rows, f"{I_CAL}  Agenda", header(events), selected=selected)
        if idx is None:
            return
        kind, payload = actions[idx]
        if kind == "noop":
            continue
        if kind == "event":
            event_menu(payload)
        elif kind == "new":
            if new_event(events):
                events = load_events(force=True)
        elif kind == "calendars":
            if calendars_menu():
                events = load_events(force=True)
                poke_waybar()
        elif kind == "sync":
            notify("Agenda", "Sincronizando calendarios…", "low")
            events = refresh_remote()
            poke_waybar()
        elif kind == "gnome":
            spawn(["gnome-calendar", f"--date={date.today():%Y-%m-%d}"])
            return


# --------------------------------------------------------------------------
# Detalle de un evento
# --------------------------------------------------------------------------

def event_menu(ev):
    url = meeting_url(ev)
    while True:
        mesg = [f"<b>{esc(ev['summary'])}</b>",
                f"<span color='{C_SUB}'>{I_CLOCK} {esc(when_text(ev))}</span>",
                f"<span color='{ev['color']}'>●</span> <span color='{C_MUTED}'>{esc(ev['calendar'])}</span>"]
        if ev["location"]:
            mesg.insert(2, f"<span color='{C_SUB}'>{I_PIN} {esc(ellipsis(ev['location'], 54))}</span>")
        if ev["description"]:
            mesg.append(f"<span color='{C_MUTED}'>{esc(ellipsis(ev['description'], 110))}</span>")

        rows, actions = [], []
        if url:
            rows.append(f"{I_VIDEO}  Abrir enlace")
            actions.append("open-url")
            rows.append(f"{I_COPY}  Copiar enlace")
            actions.append("copy-url")
        rows.append(f"{I_COPY}  Copiar el evento")
        actions.append("copy")
        if ev["location"]:
            rows.append(f"{I_PIN}  Copiar la ubicación")
            actions.append("copy-loc")
        rows.append(f"{I_OPEN}  Ver ese día en GNOME Calendar")
        actions.append("gnome")
        rows.append(f"<span color='#f38ba8'>{I_TRASH}  Eliminar</span>")
        actions.append("delete")
        rows.append(f"{I_BACK}  Volver")
        actions.append("back")

        idx = rofi(rows, f"{I_CAL}  Evento", "\n".join(mesg), lines=len(rows))
        if idx is None:
            return
        action = actions[idx]
        if action == "back":
            return
        if action == "open-url":
            spawn(["xdg-open", url])
            return
        if action == "copy-url":
            copy(url)
            notify("Agenda", "Enlace copiado", "low")
            return
        if action == "copy":
            copy(f"{ev['summary']}\n{when_text(ev)}"
                 + (f"\n{ev['location']}" if ev["location"] else ""))
            notify("Agenda", "Evento copiado", "low")
            return
        if action == "copy-loc":
            copy(ev["location"])
            notify("Agenda", "Ubicación copiada", "low")
            return
        if action == "gnome":
            spawn(["gnome-calendar", f"--date={datetime.fromtimestamp(ev['start']):%Y-%m-%d}"])
            return
        if action == "delete":
            if confirm_delete(ev):
                return


def confirm_delete(ev):
    mesg = (f"<b>{esc(ellipsis(ev['summary'], 46))}</b>\n"
            f"<span color='{C_WARN}'>Se borrará del calendario "
            f"{esc(ev['calendar'])}, también en el servidor.</span>")
    idx = rofi([f"{I_BACK}  Cancelar", f"<span color='#f38ba8'>{I_TRASH}  Sí, eliminar</span>"],
               f"{I_TRASH}  Confirmar", mesg, lines=2)
    if idx != 1:
        return False
    try:
        reg = registry()
        src = reg.ref_source(ev["source"])
        client = _connect(src, CONNECT_TIMEOUT)
        client.remove_object_sync(ev["uid"], None, ECal.ObjModType.ALL,
                                  ECal.OperationFlags.NONE, None)
    except Exception as err:
        notify("Agenda", f"No se pudo eliminar: {err}", True)
        return False
    notify("Agenda", "Evento eliminado", "low")
    poke_waybar()
    return True


# --------------------------------------------------------------------------
# Visibilidad de calendarios
# --------------------------------------------------------------------------

def calendars_menu():
    changed = False
    while True:
        cals = calendar_sources(registry())
        rows = []
        for cal in cals:
            mark = I_DONE if cal["selected"] else " "
            colour = C_TEXT if cal["selected"] else C_MUTED
            rows.append(f"{mark} <span color='{cal['color']}'>●</span> "
                        f"<span color='{colour}'>{esc(cal['name'])}</span>")
        rows.append(f"{I_BACK}  Volver")
        idx = rofi(rows, f"{I_EYE}  Calendarios",
                   f"<span color='{C_MUTED}'>Enter muestra u oculta un calendario</span>",
                   lines=len(rows))
        if idx is None or idx == len(rows) - 1:
            return changed
        cal = cals[idx]
        ext = cal["source"].get_extension(EDataServer.SOURCE_EXTENSION_CALENDAR)
        ext.set_selected(not cal["selected"])
        try:
            cal["source"].write_sync(None)
        except Exception as err:
            notify("Agenda", f"No se pudo guardar: {err}", True)
            continue
        changed = True


# --------------------------------------------------------------------------
# Alta rápida de eventos
# --------------------------------------------------------------------------

QUICK_HELP = ("<b>Ejemplos</b>\n"
              "<span color='#a6adc8'>mañana 18:00 Cena con Ana\n"
              "jueves 9:30-11 Dentista\n"
              "12/10 Cumpleaños de Marta\n"
              "en 45m Llamar al banco</span>")

WEEKDAY_WORDS = {
    "lunes": 0, "martes": 1, "miercoles": 2, "miércoles": 2, "jueves": 3,
    "viernes": 4, "sabado": 5, "sábado": 5, "domingo": 6,
}
TIME_RE = re.compile(r"^(\d{1,2})(?:[:.h](\d{2})?)?$", re.I)
RANGE_RE = re.compile(r"^(\d{1,2})(?:[:.h](\d{2}))?-(\d{1,2})(?:[:.h](\d{2}))?$", re.I)
DATE_RE = re.compile(r"^(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?$")
IN_RE = re.compile(r"^(\d{1,3})\s*(m|min|h|hora|horas)$", re.I)


def _hm(hour, minute):
    return int(hour), int(minute or 0)


def parse_quick(text):
    """'mañana 18:00 Cena' -> (inicio, fin, todo_el_día, título)."""
    words = text.split()
    day = date.today()
    start_hm = end_hm = None
    i = 0

    while i < len(words):
        raw = words[i]
        low = raw.lower().strip(",")
        if low in ("hoy",):
            day, i = date.today(), i + 1
            continue
        if low in ("mañana", "manana"):
            day, i = date.today() + timedelta(days=1), i + 1
            continue
        if low == "pasado" and i + 1 < len(words) and words[i + 1].lower() in ("mañana", "manana"):
            day, i = date.today() + timedelta(days=2), i + 2
            continue
        if low in WEEKDAY_WORDS:
            target = WEEKDAY_WORDS[low]
            ahead = (target - date.today().weekday()) % 7 or 7
            day, i = date.today() + timedelta(days=ahead), i + 1
            continue
        if low == "en" and i + 1 < len(words):
            match = IN_RE.match(" ".join(words[i + 1:i + 3])) or IN_RE.match(words[i + 1])
            if match:
                delta = int(match.group(1)) * (60 if match.group(2).lower().startswith("h") else 1)
                moment = datetime.now() + timedelta(minutes=delta)
                day = moment.date()
                start_hm = (moment.hour, moment.minute)
                i += 2 if IN_RE.match(words[i + 1]) else 3
                continue
        match = DATE_RE.match(low)
        if match:
            dd, mm, yy = int(match.group(1)), int(match.group(2)), match.group(3)
            year = date.today().year if yy is None else (int(yy) + 2000 if len(yy) == 2 else int(yy))
            try:
                day = date(year, mm, dd)
            except ValueError:
                break
            if yy is None and day < date.today():
                day = day.replace(year=year + 1)
            i += 1
            continue
        match = RANGE_RE.match(low)
        if match and start_hm is None:
            start_hm = _hm(match.group(1), match.group(2))
            end_hm = _hm(match.group(3), match.group(4))
            i += 1
            continue
        match = TIME_RE.match(low)
        if match and start_hm is None and int(match.group(1)) <= 23:
            start_hm = _hm(match.group(1), match.group(2))
            i += 1
            continue
        break

    summary = " ".join(words[i:]).strip()
    if not summary:
        return None
    if start_hm is None:
        start = datetime.combine(day, dtime.min)
        return start, start + timedelta(days=1), True, summary
    start = datetime.combine(day, dtime(*start_hm))
    end = datetime.combine(day, dtime(*end_hm)) if end_hm else start + timedelta(hours=1)
    if end <= start:
        end += timedelta(days=1)
    return start, end, False, summary


def pick_calendar():
    cals = [c for c in calendar_sources(registry()) if c["selected"]]
    if not cals:
        notify("Agenda", "No hay calendarios visibles", True)
        return None
    if len(cals) == 1:
        return cals[0]
    rows = [f"<span color='{c['color']}'>●</span>  {esc(c['name'])}" for c in cals]
    idx = rofi(rows, f"{I_CAL}  ¿En qué calendario?", None, lines=len(rows))
    return None if idx is None else cals[idx]


def create_event(cal, start, end, allday, summary):
    src = registry().ref_source(cal["uid"])
    client = _connect(src, CONNECT_TIMEOUT)
    utc = ICalGLib.Timezone.get_utc_timezone()
    comp = ICalGLib.Component.new_vevent()
    comp.set_summary(summary)
    comp.set_uid(str(uuid.uuid4()))
    comp.set_dtstamp(ICalGLib.Time.new_current_with_zone(utc))
    if allday:
        comp.set_dtstart(ICalGLib.Time.new_from_timet_with_zone(int(start.timestamp()), 1, None))
        comp.set_dtend(ICalGLib.Time.new_from_timet_with_zone(int(end.timestamp()), 1, None))
    else:
        comp.set_dtstart(ICalGLib.Time.new_from_timet_with_zone(int(start.timestamp()), 0, utc))
        comp.set_dtend(ICalGLib.Time.new_from_timet_with_zone(int(end.timestamp()), 0, utc))
    client.create_object_sync(comp, ECal.OperationFlags.NONE, None)


def new_event(events):
    text = rofi_input(f"{I_NEW}  Nuevo evento", QUICK_HELP, "mañana 18:00 Cena con Ana")
    if not text:
        return False
    parsed = parse_quick(text)
    if parsed is None:
        notify("Agenda", "No he entendido el evento", True)
        return False
    start, end, allday, summary = parsed
    cal = pick_calendar()
    if cal is None:
        return False
    preview = {"summary": summary, "start": int(start.timestamp()),
               "end": int(end.timestamp()), "allday": allday}
    idx = rofi([f"{I_DONE}  Crear", f"{I_BACK}  Cancelar"],
               f"{I_NEW}  Confirmar",
               f"<b>{esc(summary)}</b>\n<span color='{C_SUB}'>{I_CLOCK} {esc(when_text(preview))}</span>"
               f"\n<span color='{cal['color']}'>●</span> <span color='{C_MUTED}'>{esc(cal['name'])}</span>",
               lines=2)
    if idx != 0:
        return False
    try:
        create_event(cal, start, end, allday, summary)
    except Exception as err:
        notify("Agenda", f"No se pudo crear: {err}", True)
        return False
    notify("Agenda", f"{summary}\n{when_text(preview)}", "low")
    poke_waybar()
    return True


# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clock", action="store_true", help="bucle del reloj")
    parser.add_argument("--tooltip", action="store_true", help="tooltip del reloj")
    parser.add_argument("--status", action="store_true", help="JSON para waybar")
    parser.add_argument("--sync", action="store_true", help="fuerza la sincronización")
    args = parser.parse_args()

    if args.clock:
        cmd_clock(args)
        return
    if args.tooltip:
        cmd_tooltip(args)
        return
    if args.status:
        cmd_status(args)
        return
    if args.sync:
        refresh_remote()
        poke_waybar()
        return
    try:
        menu(events_for_ui())
    except Exception as err:
        notify("Agenda", f"No se pudieron leer los calendarios: {err}", True)
        sys.exit(1)


if __name__ == "__main__":
    main()
