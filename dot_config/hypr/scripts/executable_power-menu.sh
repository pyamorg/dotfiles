#!/usr/bin/env bash
# Ajustes rápidos de energía desde el módulo de batería:
# niveles de brillo y modo caffeine.
set -euo pipefail

THEME="$HOME/.config/rofi/menu.rasi"
CAFFEINE="$HOME/.config/hypr/scripts/caffeine.sh"

max=$(brightnessctl max)
cur=$(brightnessctl get)
pct=$((cur * 100 / max))

if "$CAFFEINE" --status | grep -q '"class":"active"'; then
    caffeine_row="󰅶  Desactivar caffeine"
else
    caffeine_row="󰾪  Activar caffeine (no apagar la pantalla)"
fi

actions=(10 25 50 75 100 "__caffeine__")
rows=()
for level in 10 25 50 75 100; do
    if ((pct >= level - 7 && pct <= level + 7)); then
        rows+=("󰄬 󰃟  Brillo $level%")
    else
        rows+=("  󰃟  Brillo $level%")
    fi
done
rows+=("$caffeine_row")

choice=$(printf '%s\n' "${rows[@]}" |
    rofi -dmenu -i -theme "$THEME" -p "󰁹  Energía" -format i -no-custom \
        -mesg "Batería al $(cat /sys/class/power_supply/CMB0/capacity 2>/dev/null || echo '?')% · brillo al $pct%") || exit 0

selected=${actions[$choice]}

if [[ $selected == "__caffeine__" ]]; then
    exec "$CAFFEINE"
fi

brightnessctl set "$selected%" >/dev/null
