#!/usr/bin/env bash
# Vigilante de batería: por debajo del umbral baja el brillo y avisa; al
# enchufar la corriente devuelve el brillo que había.
# Se lanza desde el autostart de Hyprland.
set -euo pipefail

BAT=/sys/class/power_supply/CMB0
LOW=15      # % de batería a partir del cual se actúa
CRITICAL=5  # % para el segundo aviso, más insistente
DIM=20      # % de brillo al que se baja
INTERVAL=60 # segundos entre comprobaciones
STATE="${XDG_RUNTIME_DIR:-/tmp}/battery-watch.state"

brightness_pct() {
    echo $(($(brightnessctl get) * 100 / $(brightnessctl max)))
}

[[ -r $BAT/capacity ]] || exit 0

while :; do
    cap=$(<"$BAT/capacity")
    status=$(<"$BAT/status")
    saved=$(cat "$STATE" 2>/dev/null || echo "")

    if [[ $status == "Discharging" ]]; then
        if ((cap <= LOW)) && [[ -z $saved ]]; then
            # Guarda el brillo actual para poder devolverlo al enchufar.
            brightness_pct >"$STATE"
            ((cap > DIM)) && brightnessctl -q set "$DIM%"
            notify-send -a waybar -u critical -i battery-caution \
                "Batería al $cap%" "Brillo reducido. Conecta el cargador."
            echo "$cap" >"${STATE}.last"
        elif ((cap <= CRITICAL)) && [[ $(cat "${STATE}.last" 2>/dev/null || echo 100) -gt $CRITICAL ]]; then
            notify-send -a waybar -u critical -i battery-empty \
                "Batería al $cap%" "El equipo se suspenderá en breve."
            echo "$cap" >"${STATE}.last"
        fi
    elif [[ -n $saved ]]; then
        # Ha vuelto la corriente: restaura y olvida el estado.
        brightnessctl -q set "$saved%"
        rm -f "$STATE" "${STATE}.last"
        notify-send -a waybar -i battery-charging \
            "Cargando" "Brillo restaurado al $saved%"
    fi

    sleep "$INTERVAL"
done
