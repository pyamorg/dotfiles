#!/usr/bin/env bash
# Silenciar notificaciones (modo no molestar de swaync).
#   dnd.sh --status  -> JSON para waybar
#   dnd.sh           -> alterna
set -euo pipefail

WAYBAR_SIGNAL=10

if [[ ${1:-} == "--status" ]]; then
    if [[ $(swaync-client -D 2>/dev/null) == "true" ]]; then
        printf '{"text":"󰂛","class":"active","tooltip":"Notificaciones silenciadas"}\n'
    else
        printf '{"text":"󰂚","class":"inactive","tooltip":"Silenciar notificaciones"}\n'
    fi
    exit 0
fi

swaync-client -d >/dev/null
pkill -RTMIN+"$WAYBAR_SIGNAL" waybar 2>/dev/null || true
