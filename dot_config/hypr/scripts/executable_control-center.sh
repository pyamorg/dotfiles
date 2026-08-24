#!/usr/bin/env bash
# Menú raíz: da acceso por teclado a los mismos paneles que las cápsulas
# de la barra.
set -euo pipefail

THEME="$HOME/.config/rofi/menu.rasi"
SCRIPTS="$HOME/.config/hypr/scripts"

rows=(
    "󰤨  Red y VPN"
    "󰂯  Bluetooth"
    "󰕾  Salida de audio"
    "󰍬  Entrada de audio"
    "󰅍  Portapapeles"
    "󰁹  Energía y brillo"
    "󰂛  Silenciar notificaciones"
    "󰍛  Procesos por CPU"
    "󰘚  Procesos por memoria"
    "󰐥  Apagar…"
)
actions=(
    "$SCRIPTS/wifi-menu.sh"
    "$SCRIPTS/bluetooth-menu.sh"
    "$SCRIPTS/audio-menu.sh output"
    "$SCRIPTS/audio-menu.sh input"
    "$SCRIPTS/clipboard-menu.sh"
    "$SCRIPTS/power-menu.sh"
    "$SCRIPTS/dnd.sh"
    "$SCRIPTS/proc-menu.sh cpu"
    "$SCRIPTS/proc-menu.sh mem"
    "wlogout -b 5"
)

choice=$(printf '%s\n' "${rows[@]}" |
    rofi -dmenu -i -theme "$THEME" -p "󰕮  Control" -format i -no-custom \
        -theme-str 'listview { lines: 10; }') || exit 0

# exec para que el submenú herede el proceso y el bind de cierre siga valiendo.
exec ${actions[$choice]}
