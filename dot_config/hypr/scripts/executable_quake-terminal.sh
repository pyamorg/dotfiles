#!/usr/bin/env bash
# ~/.config/hypr/scripts/quake-terminal.sh
#
# Si el terminal "quake" ya está corriendo, solo alterna su visibilidad
# (lo desliza dentro/fuera). Si no existe todavía, lo lanza y lo asigna
# a su workspace especial.

if hyprctl clients -j | grep -q '"class": "quake-term"'; then
    hyprctl dispatch togglespecialworkspace quake
else
    kitty --class quake-term &
    # pequeña espera para que la ventana exista antes de moverla
    sleep 0.3
    hyprctl dispatch togglespecialworkspace quake
fi
