#!/usr/bin/env bash
# Selector de red wifi para la waybar.
# Lista las redes al alcance, se conecta a la elegida y pide contraseña
# con rofi solo si la red no está guardada.
set -euo pipefail

THEME="$HOME/.config/rofi/menu.rasi"

iface=$(nmcli -t -f DEVICE,TYPE device | awk -F: '$2=="wifi"{print $1; exit}')
[[ -z $iface ]] && {
    notify-send -a waybar "Wifi" "No hay ninguna interfaz inalámbrica"
    exit 1
}

radio=$(nmcli radio wifi)

# El escaneo tarda varios segundos: se lanza en segundo plano y el menú se
# pinta al instante con la lista cacheada, ya refrescada por el rescan previo.
[[ $radio == "enabled" ]] && nmcli device wifi rescan >/dev/null 2>&1 &

names=()
rows=()

if [[ $radio != "enabled" ]]; then
    names+=("__toggle__")
    rows+=("󰖩  Activar el wifi")
else
    # Una fila por SSID, quedándose con la señal más fuerte de cada uno.
    while IFS= read -r line; do
        inuse=${line%%:*}
        rest=${line#*:}
        signal=${rest%%:*}
        rest=${rest#*:}
        security=${rest%%:*}
        ssid=${rest#*:}
        ssid=${ssid//\\:/:}

        [[ -z $ssid ]] && continue
        [[ " ${names[*]} " == *" $ssid "* ]] && continue

        if ((signal >= 75)); then icon="󰤨"
        elif ((signal >= 50)); then icon="󰤥"
        elif ((signal >= 25)); then icon="󰤢"
        else icon="󰤟"; fi

        [[ -n $security ]] && lock="󰌾" || lock=" "
        [[ $inuse == "*" ]] && mark="󰄬" || mark=" "

        names+=("$ssid")
        rows+=("$mark $icon $lock  $ssid  ($signal%)")
    done < <(nmcli -t -f IN-USE,SIGNAL,SECURITY,SSID device wifi list --rescan no |
        sort -t: -k1,1r -k2,2nr) # la conectada primero, luego por señal

    names+=("__rescan__")
    rows+=("󰑐  Buscar redes de nuevo")
    names+=("__toggle__")
    rows+=("󰖪  Desactivar el wifi")
fi

while IFS=: read -r active name; do
    [[ $active == "yes" ]] && mark="󰄬" || mark=" "
    names+=("__vpn__$name")
    rows+=("$mark 󰖂  VPN $name")
done < <(nmcli -t -f NAME,TYPE,ACTIVE connection show |
    awk -F: '$2=="vpn" || $2=="wireguard" {print $3":"$1}')

names+=("__editor__")
rows+=("󱁻  Ajustes de red…")

[[ ${#rows[@]} -eq 0 ]] && exit 0

choice=$(printf '%s\n' "${rows[@]}" |
    rofi -dmenu -i -theme "$THEME" -p "󰤨  Wifi" -format i -no-custom) || exit 0

selected=${names[$choice]}

case $selected in
__rescan__)
    nmcli device wifi rescan >/dev/null 2>&1 || true
    exec "$0"
    ;;
__toggle__)
    [[ $radio == "enabled" ]] && nmcli radio wifi off || nmcli radio wifi on
    pkill -RTMIN+9 waybar 2>/dev/null || true
    exit 0
    ;;
__editor__)
    exec nm-connection-editor
    ;;
__vpn__*)
    vpn=${selected#__vpn__}
    if nmcli -t -f NAME,ACTIVE connection show | grep -qxF "$vpn:yes"; then
        nmcli connection down id "$vpn" >/dev/null
        notify-send -a waybar -i network-vpn "VPN" "Desconectada $vpn"
    elif nmcli connection up id "$vpn" >/dev/null 2>&1; then
        notify-send -a waybar -i network-vpn "VPN" "Conectada $vpn"
    else
        notify-send -a waybar -i network-error "VPN" "No se pudo conectar a $vpn"
    fi
    pkill -RTMIN+9 waybar 2>/dev/null || true
    exit 0
    ;;
esac

# Si ya existe el perfil, reutilizarlo: no hace falta contraseña.
if nmcli -t -f NAME connection show | sed 's/\\:/:/g' | grep -qxF "$selected"; then
    if nmcli connection up id "$selected" ifname "$iface" >/dev/null 2>&1; then
        notify-send -a waybar -i network-wireless "Wifi" "Conectado a $selected"
    else
        notify-send -a waybar -i network-error "Wifi" "No se pudo conectar a $selected"
    fi
    pkill -RTMIN+9 waybar 2>/dev/null || true
    exit 0
fi

security=$(nmcli -t -f SSID,SECURITY device wifi list |
    sed 's/\\:/:/g' | awk -F: -v s="$selected" '$1==s{print $2; exit}')

if [[ -n $security ]]; then
    password=$(rofi -dmenu -password -theme "$THEME" \
        -theme-str 'listview { enabled: false; } entry { placeholder: "Contraseña…"; }' \
        -p "󰌾  $selected" </dev/null || true)
    [[ -z $password ]] && exit 0
    result=$(nmcli device wifi connect "$selected" password "$password" ifname "$iface" 2>&1) || true
else
    result=$(nmcli device wifi connect "$selected" ifname "$iface" 2>&1) || true
fi

if [[ $result == *successfully* ]]; then
    notify-send -a waybar -i network-wireless "Wifi" "Conectado a $selected"
else
    notify-send -a waybar -i network-error "Wifi" "$result"
fi
pkill -RTMIN+9 waybar 2>/dev/null || true
