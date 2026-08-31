#!/usr/bin/env bash
# theme.sh — deriva la paleta del escritorio del fondo de pantalla.
#
#   ./theme.sh                    usa el fondo de ~/.config/hypr/hyprpaper.conf
#   ./theme.sh ruta/al/fondo.jpg  usa esa imagen
#   ./theme.sh --reset            vuelve a Catppuccin Mocha
#   ./theme.sh --dry-run          enseña la paleta sin escribir nada
#
# Escribe .chezmoidata/colors.yaml, lanza "chezmoi apply" sobre los ficheros
# que dependen de la paleta y recarga waybar, swaync, hyprland y kitty.
#
# Vive en el repo, no en $HOME (ver .chezmoiignore).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="$REPO/.chezmoidata/colors.yaml"
HYPRPAPER="$HOME/.config/hypr/hyprpaper.conf"

dry_run=false
reset=false
wallpaper=""

for arg in "$@"; do
    case "$arg" in
        --dry-run) dry_run=true ;;
        --reset) reset=true ;;
        -h | --help)
            sed -n '2,10p' "${BASH_SOURCE[0]}" | sed 's/^# \?//'
            exit 0
            ;;
        *) wallpaper="$arg" ;;
    esac
done

if ! $reset; then
    if [[ -z $wallpaper ]]; then
        wallpaper=$(awk -F'= *' '/^[[:space:]]*path/{print $2; exit}' "$HYPRPAPER" 2>/dev/null || true)
    fi
    if [[ ! -f $wallpaper ]]; then
        echo "No encuentro el fondo de pantalla ($wallpaper). Pásalo como argumento." >&2
        exit 1
    fi
    command -v magick >/dev/null || { echo "Falta ImageMagick (pacman -S imagemagick)" >&2; exit 1; }
fi

# El histograma reduce la imagen a 16 tonos con su número de píxeles; de ahí
# salen los dos acentos. Los neutros se construyen tiñendo una rampa de grises
# con el tono dominante, que es lo que hace que el conjunto "pegue" con el fondo.
histogram=""
if ! $reset; then
    histogram=$(magick "$wallpaper" -resize 200x200^ -depth 8 -colors 16 \
        -format %c histogram:info:-)
fi

palette=$(RESET="$reset" SOURCE="${wallpaper:-catppuccin-mocha}" python3 - "$histogram" <<'PY'
import colorsys, os, re, sys

# Semánticos: el tono es intocable (rojo = error), sólo se normalizan
# saturación y luminosidad para que convivan con cualquier fondo.
SEMANTIC = {
    "red":      (343, 0.81, 0.75),
    "peach":    ( 23, 0.92, 0.75),
    "yellow":   ( 41, 0.86, 0.83),
    "green":    (115, 0.54, 0.76),
    "teal":     (170, 0.57, 0.73),
    "sky":      (189, 0.71, 0.73),
    "sapphire": (199, 0.76, 0.69),
    "pink":     (316, 0.72, 0.86),
}
# Rampa de neutros: (luminosidad, saturación). El tono lo pone el fondo.
NEUTRALS = [
    ("crust",    0.06, 0.24),
    ("mantle",   0.09, 0.22),
    ("base",     0.12, 0.20),
    ("surface0", 0.20, 0.16),
    ("surface1", 0.28, 0.14),
    ("surface2", 0.36, 0.12),
    ("overlay0", 0.50, 0.11),
    ("subtext0", 0.74, 0.18),
    ("text",     0.88, 0.24),
]

def hexof(h, s, l):
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360.0, l, s)
    return "#%02x%02x%02x" % tuple(round(c * 255) for c in (r, g, b))

def dominant_hues(histogram):
    """Devuelve dos tonos: el más 'coloreado' y otro suficientemente lejano."""
    entries = []
    for count, hx in re.findall(r"(\d+):\s*\([^)]*\)\s*#([0-9A-Fa-f]{6})", histogram):
        r, g, b = (int(hx[i:i + 2], 16) / 255 for i in (0, 2, 4))
        h, l, s = colorsys.rgb_to_hls(r, g, b)
        # Los grises y los casi-negros no dicen nada del tono: penalizarlos.
        weight = int(count) * (s ** 2) * (1 - abs(l - 0.5))
        entries.append((weight, h * 360))
    entries.sort(reverse=True)
    if not entries or entries[0][0] == 0:
        return 220.0, 267.0
    primary = entries[0][1]
    for _, hue in entries[1:]:
        if 40 < abs((hue - primary + 180) % 360 - 180) < 200:
            return primary, hue
    return primary, primary + 55

if os.environ["RESET"] == "true":
    h1, h2 = 220.0, 267.0
else:
    h1, h2 = dominant_hues(sys.argv[1])

out = {name: hexof(h1, sat, lum) for name, lum, sat in NEUTRALS}
out["accent"] = hexof(h1, 0.78, 0.73)
out["accent2"] = hexof(h2, 0.72, 0.75)
out["accent3"] = hexof(h1 + 18, 0.66, 0.79)
for name, (h, s, l) in SEMANTIC.items():
    out[name] = hexof(h, s, l)

order = [n for n, _, _ in NEUTRALS] + ["accent", "accent2", "accent3"] + list(SEMANTIC)
print("\n".join(f"{n}|{out[n]}" for n in order))
PY
)

if $dry_run; then
    echo "Fondo: ${wallpaper:-(reset)}"
    while IFS='|' read -r name hex; do
        printf '  %-9s %s  \033[48;2;%d;%d;%dm      \033[0m\n' "$name" "$hex" \
            "0x${hex:1:2}" "0x${hex:3:2}" "0x${hex:5:2}"
    done <<<"$palette"
    exit 0
fi

get() { grep "^$1|" <<<"$palette" | cut -d'|' -f2; }

cat >"$OUT" <<EOF
# .chezmoidata/colors.yaml
#
# Paleta única de todo el escritorio. chezmoi la expone como {{ .colors.X }}
# en cualquier plantilla del repo, así que un cambio aquí se propaga a
# waybar, rofi, swaync, wlogout, kitty, hyprland y hyprlock con un
# "chezmoi apply".
#
# GENERADO POR ./theme.sh — no lo edites a mano salvo que quieras un tema
# fijo; la próxima ejecución del script lo sobrescribe.
#
# Los nombres son ROLES, no colores literales: "accent" es el acento
# principal aunque acabe siendo verde. Los semánticos (red/yellow/green)
# conservan su significado pase lo que pase con el fondo.

theme:
  source: "$(if $reset; then echo catppuccin-mocha; else echo "$wallpaper"; fi)"
  mode: "dark"

colors:
  # --- Neutros, de más oscuro a más claro. Llevan el tono del fondo. ---
  crust: "$(get crust)"
  mantle: "$(get mantle)"
  base: "$(get base)"
  surface0: "$(get surface0)"
  surface1: "$(get surface1)"
  surface2: "$(get surface2)"
  overlay0: "$(get overlay0)"
  subtext0: "$(get subtext0)"
  text: "$(get text)"

  # --- Acentos derivados del color dominante del fondo. ---
  accent: "$(get accent)"
  accent2: "$(get accent2)"
  accent3: "$(get accent3)"

  # --- Semánticos: tono fijo, luminosidad normalizada. ---
  red: "$(get red)"
  peach: "$(get peach)"
  yellow: "$(get yellow)"
  green: "$(get green)"
  teal: "$(get teal)"
  sky: "$(get sky)"
  sapphire: "$(get sapphire)"
  pink: "$(get pink)"
EOF

# Sólo los ficheros que dependen de la paleta: aplicar directorios enteros
# arrastraría cambios ajenos al tema.
chezmoi apply --no-tty --force \
    ~/.config/waybar/style.css ~/.config/waybar/config.jsonc \
    ~/.config/rofi/config.rasi ~/.config/rofi/menu.rasi \
    ~/.config/swaync/style.css \
    ~/.config/wlogout/style.css ~/.config/wlogout/icons \
    ~/.config/kitty/kitty.conf \
    ~/.config/hypr/colors.json ~/.config/hypr/hyprlock.conf ~/.config/hypr/hyprland.lua

# Los botones de wlogout se pintan con PNG: GTK3 no rasteriza SVG desde que
# librsvg dejó de instalar el loader de gdk-pixbuf.
if command -v rsvg-convert >/dev/null; then
    for svg in "$HOME"/.config/wlogout/icons/*.svg; do
        rsvg-convert -w 128 -h 128 "$svg" -o "${svg%.svg}.png"
    done
fi

pkill -x waybar 2>/dev/null && (nohup waybar >/tmp/waybar.log 2>&1 &) || true
swaync-client -rs 2>/dev/null || true
hyprctl reload >/dev/null 2>&1 || true
pkill -SIGUSR1 -x kitty 2>/dev/null || true

echo "Paleta aplicada desde ${wallpaper:-Catppuccin Mocha}."
