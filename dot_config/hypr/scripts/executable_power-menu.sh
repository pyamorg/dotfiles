#!/usr/bin/env bash
# Ajustes rápidos de energía desde el módulo de batería:
# niveles de brillo y modo caffeine.
set -euo pipefail

THEME="$HOME/.config/rofi/menu.rasi"
CAFFEINE="$HOME/.config/hypr/scripts/caffeine.sh"
# Knob del modulo lg_laptop: 80 conserva la bateria, 100 carga completa.
CARE="/sys/devices/platform/lg-laptop/battery_care_limit"

max=$(brightnessctl max)
cur=$(brightnessctl get)
pct=$((cur * 100 / max))

if "$CAFFEINE" --status | grep -q '"class":"active"'; then
    caffeine_row="� 󰅶  Caffeine"
else
    caffeine_row="  󰅶  Caffeine"
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

if [[ -r $CARE ]]; then
    care=$(<"$CARE")
    [[ $care == "80" ]] && mark="󰄬" || mark=" "
    rows+=("$mark 󰂄  Tope de carga al 80%")
    actions+=("__care__")
fi

choice=$(printf '%s\n' "${rows[@]}" |
    rofi -dmenu -i -theme "$THEME" -p "󰁹  Energía" -format i -no-custom \
        -mesg "Batería al $(cat /sys/class/power_supply/CMB0/capacity 2>/dev/null || echo '?')%") || exit 0

selected=${actions[$choice]}

case $selected in
__caffeine__)
    exec "$CAFFEINE"
    ;;
__care__)
    [[ $care == "80" ]] && target=100 || target=80
    if echo "$target" >"$CARE" 2>/dev/null; then
        notify-send -a waybar -i battery "Batería" "Tope de carga al $target%"
    else
        notify-send -a waybar -u critical -i battery "Batería" \
            "Sin permiso de escritura en $CARE. Instala system/99-lg-laptop.rules."
    fi
    exit 0
    ;;
esac

brightnessctl set "$selected%" >/dev/null
