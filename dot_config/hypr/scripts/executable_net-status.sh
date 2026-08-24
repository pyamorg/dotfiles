#!/usr/bin/env bash
# Estado de red para waybar. Sustituye al módulo "network" nativo para poder
# reflejar también si hay un túnel VPN levantado (icono con candado + color).
set -euo pipefail

if [[ ${1:-} == "--toggle" ]]; then
    if [[ $(nmcli radio wifi) == "enabled" ]]; then
        nmcli radio wifi off
        notify-send -a waybar -i network-wireless-disconnected "Wifi" "Desactivado"
    else
        nmcli radio wifi on
        notify-send -a waybar -i network-wireless "Wifi" "Activado"
    fi
    pkill -RTMIN+9 waybar 2>/dev/null || true
    exit 0
fi

vpn=$(nmcli -t -f NAME,TYPE,ACTIVE connection show |
    awk -F: '($2 == "vpn" || $2 == "wireguard") && $3 == "yes" { print $1; exit }') || vpn=""

link=$(nmcli -t -f DEVICE,TYPE,STATE,CONNECTION device |
    awk -F: '$3 == "connected" && $2 != "loopback" && $2 != "wireguard" && $2 != "tun" { print; exit }') || link=""

IFS=: read -r dev type _state conn <<<"$link"

case ${type:-} in
wifi)
    # --rescan no: sin esto nmcli puede lanzar un escaneo y tardar segundos.
    signal=$(nmcli -t -f ACTIVE,SIGNAL device wifi list --rescan no |
        awk -F: '$1 == "yes" { print $2; exit }')
    signal=${signal:-0}
    if [[ -n $vpn ]]; then
        icon="󰤪"
    elif ((signal >= 75)); then
        icon="󰤨"
    elif ((signal >= 50)); then
        icon="󰤥"
    elif ((signal >= 25)); then
        icon="󰤢"
    else
        icon="󰤟"
    fi
    text="$icon $signal%"
    ;;
ethernet)
    [[ -n $vpn ]] && icon="󰲛" || icon="󰈀"
    text="$icon Ethernet"
    ;;
*)
    if [[ $(nmcli radio wifi) == "disabled" ]]; then
        text="󰖪  Wifi apagado"
    else
        text="󰤭  Sin conexión"
    fi
    ;;
esac

if [[ -n ${dev:-} ]]; then
    ip=$(nmcli -t -f IP4.ADDRESS device show "$dev" | cut -d: -f2- | head -1)
    tooltip="${conn:-$dev}${ip:+ | $ip}"
else
    tooltip="Sin conexión"
fi
[[ -n $vpn ]] && tooltip+=$'\n'"󰖂  VPN $vpn"

jq -cn --arg text "$text" --arg tooltip "$tooltip" \
    --arg class "$([[ -n $vpn ]] && echo vpn || echo plain)" \
    '{text: $text, tooltip: $tooltip, class: $class}'
