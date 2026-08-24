#!/usr/bin/env bash
# Selector de dispositivos bluetooth para la waybar.
# Muestra emparejados y descubiertos, conecta o desconecta al elegir.
set -euo pipefail

THEME="$HOME/.config/rofi/menu.rasi"

powered=$(bluetoothctl show | awk '/Powered:/ {print $2; exit}')

names=()
rows=()

if [[ $powered != "yes" ]]; then
    names+=("__toggle__")
    rows+=("󰂲  Activar el bluetooth")
else
    # El escaneo se deja corriendo en segundo plano: el menú se pinta ya con
    # lo conocido y la siguiente apertura tendrá la lista al día.
    bluetoothctl --timeout 10 scan on >/dev/null 2>&1 &

    connected=$(bluetoothctl devices Connected | awk '{print $2}')

    while read -r _ mac name; do
        [[ -z $mac ]] && continue
        if [[ $'\n'$connected$'\n' == *$'\n'"$mac"$'\n'* ]]; then
            rows+=("󰂱  $name")
        else
            rows+=("󰂯  $name")
        fi
        names+=("$mac")
    done < <(bluetoothctl devices)

    names+=("__toggle__")
    rows+=("󰂲  Desactivar el bluetooth")
fi

names+=("__manager__")
rows+=("󱁻  Gestor de bluetooth…")

choice=$(printf '%s\n' "${rows[@]}" |
    rofi -dmenu -i -theme "$THEME" -p "󰂯  Bluetooth" -format i -no-custom) || exit 0

selected=${names[$choice]}

case $selected in
__toggle__)
    [[ $powered == "yes" ]] && bluetoothctl power off || bluetoothctl power on
    exit 0
    ;;
__manager__)
    exec blueman-manager
    ;;
esac

label=${rows[$choice]:3}

if bluetoothctl info "$selected" | grep -q "Connected: yes"; then
    bluetoothctl disconnect "$selected" >/dev/null
    notify-send -a waybar -i bluetooth "Bluetooth" "Desconectado $label"
    exit 0
fi

# Un dispositivo nuevo hay que emparejarlo y confiar en él antes de conectar.
if ! bluetoothctl info "$selected" | grep -q "Paired: yes"; then
    bluetoothctl pair "$selected" >/dev/null 2>&1 || true
    bluetoothctl trust "$selected" >/dev/null 2>&1 || true
fi

if bluetoothctl connect "$selected" >/dev/null 2>&1; then
    notify-send -a waybar -i bluetooth "Bluetooth" "Conectado $label"
else
    notify-send -a waybar -u critical -i bluetooth "Bluetooth" "No se pudo conectar a $label"
fi
