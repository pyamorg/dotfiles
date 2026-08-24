#!/usr/bin/env bash
# ~/.config/hypr/scripts/quake-terminal.sh
#
# Terminal desplegable estilo Quake en un workspace especial.
#
# Clave: SIEMPRE se hace exactamente UN togglespecialworkspace por
# pulsación, tanto si acabamos de lanzarla como si ya existía.
#
# OJO (Hyprland 0.55+ con la config en Lua): "hyprctl dispatch" envuelve
# su argumento en hl.dispatch(...), así que hay que pasarle una expresión
# Lua. La sintaxis antigua ("dispatch togglespecialworkspace quake") ya
# no parsea y fallaba en silencio: de ahí que dejara de abrir y cerrar.

WS="quake"
CLASS="quake-term"

# Comparación exacta contra el campo .class. Un "grep quake-term" suelto
# también hacía match con el TÍTULO de otras ventanas (por ejemplo la
# terminal desde la que se edita este script), rompiendo la detección.
quake_exists() {
    hyprctl clients -j | jq -e --arg c "$CLASS" 'any(.[]; .class == $c)' >/dev/null 2>&1
}

if ! quake_exists; then
    # No existe todavía → lanzarla en el workspace especial, en silencio
    hyprctl dispatch \
        "hl.dsp.exec_cmd(\"kitty --class ${CLASS}\", { workspace = \"special:${WS} silent\" })" >/dev/null

    # Esperar a que la ventana exista de verdad (máx ~3s) en vez de un
    # sleep fijo, que fallaba en arranques lentos.
    for _ in $(seq 1 30); do
        if quake_exists; then break; fi
        sleep 0.1
    done
fi

hyprctl dispatch "hl.dsp.workspace.toggle_special(\"${WS}\")" >/dev/null
