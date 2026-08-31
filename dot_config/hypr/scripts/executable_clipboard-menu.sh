#!/usr/bin/env bash
# Historial del portapapeles (cliphist) con el mismo tema que el resto de menús.
set -euo pipefail

THEME="$HOME/.config/rofi/menu.rasi"

if ! command -v cliphist >/dev/null; then
    notify-send -a waybar -i dialog-error "Portapapeles" \
        "Falta cliphist: sudo pacman -S cliphist"
    exit 1
fi

entry=$(cliphist list |
    rofi -dmenu -i -theme "$THEME" -p "󰅍  Portapapeles" \
        -theme-str 'listview { lines: 12; }' -no-custom) || exit 0

[[ -z $entry ]] && exit 0

# cliphist decode necesita la línea íntegra: lleva delante el id del elemento.
cliphist decode <<<"$entry" | wl-copy
