#!/usr/bin/env bash
# Reproductor para waybar. Igual que el módulo mpris, pero la cápsula
# desaparece si la música lleva más de 5 minutos en pausa.
set -euo pipefail

IDLE_LIMIT=300
STAMP="${XDG_RUNTIME_DIR:-/tmp}/music-paused-since"

hide() {
    printf '{"text":"","tooltip":""}\n'
    exit 0
}

# El sello se conserva mientras siga en pausa: si se borrara al esconder la
# cápsula, volvería a aparecer en el siguiente refresco.
status=$(playerctl status 2>/dev/null) || { rm -f "$STAMP"; hide; }

case $status in
Playing)
    rm -f "$STAMP"
    icon="󰐊"
    ;;
Paused)
    now=$(date +%s)
    [[ -f $STAMP ]] || echo "$now" >"$STAMP"
    (($(<"$STAMP") + IDLE_LIMIT < now)) && hide
    icon="󰏤"
    ;;
*)
    rm -f "$STAMP"
    hide
    ;;
esac

title=$(playerctl metadata title 2>/dev/null || true)
artist=$(playerctl metadata artist 2>/dev/null || true)
album=$(playerctl metadata album 2>/dev/null || true)
[[ -z $title ]] && hide

text="$icon  $title${artist:+  ·  $artist}"
((${#text} > 45)) && text="${text:0:44}…"

jq -cn --arg text "$text" \
    --arg tooltip "$title${artist:+$'\n'$artist}${album:+ — $album}" \
    --arg class "${status,,}" \
    '{text: $text, tooltip: $tooltip, class: $class}'
