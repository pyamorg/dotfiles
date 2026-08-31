#!/usr/bin/env bash
# Ajustes rápidos de energía desde la cápsula de batería.
# El brillo no está aquí: es el slider que se despliega al pasar el ratón.
set -euo pipefail

THEME="$HOME/.config/rofi/menu.rasi"
CAFFEINE="$HOME/.config/hypr/scripts/caffeine.sh"
# Knob del modulo lg_laptop: 80 conserva la bateria, 100 carga completa.
CARE="/sys/devices/platform/lg-laptop/battery_care_limit"

rows=()
actions=()

"$CAFFEINE" --status | grep -q '"class":"active"' && mark="󰄬" || mark=" "
rows+=("$mark 󰅶  Caffeine")
actions+=("__caffeine__")

if [[ -r $CARE ]]; then
    care=$(<"$CARE")
    [[ $care == "80" ]] && mark="󰄬" || mark=" "
    rows+=("$mark 󰂄  Tope de carga al 80%")
    actions+=("__care__")
fi

choice=$(printf '%s\n' "${rows[@]}" |
    rofi -dmenu -i -theme "$THEME" -p "󰁹  Energía" -format i -no-custom \
        -mesg "Batería al $(cat /sys/class/power_supply/CMB0/capacity 2>/dev/null || echo '?')%") || exit 0

case ${actions[$choice]} in
__caffeine__)
    exec "$CAFFEINE"
    ;;
__care__)
    [[ $care == "80" ]] && target=100 || target=80
    if echo "$target" >"$CARE" 2>/dev/null; then
        notify-send -a waybar -i battery "Batería" "Tope de carga al $target%"
    else
        notify-send -a waybar -i dialog-error "Batería" \
            "Sin permiso de escritura en $CARE. Instala system/99-lg-laptop.rules."
    fi
    ;;
esac
