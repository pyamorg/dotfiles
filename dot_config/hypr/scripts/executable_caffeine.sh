#!/usr/bin/env bash
# ~/.config/hypr/scripts/caffeine.sh
# Alterna el modo "caffeine" (bloquea que el sistema se suspenda/apague
# la pantalla automáticamente). Guarda el PID del inhibidor para poder
# matarlo limpiamente al desactivar.

PIDFILE="${XDG_RUNTIME_DIR:-/tmp}/caffeine-inhibitor.pid"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    # Modo caffeine activo → desactivar
    kill "$(cat "$PIDFILE")"
    rm -f "$PIDFILE"
    notify-send -i dialog-information "Caffeine desactivado" "El auto-apagado vuelve a estar activo" -t 3000
else
    # Modo caffeine inactivo → activar
    systemd-inhibit \
        --what=idle:sleep:handle-lid-switch \
        --who="Caffeine" \
        --why="Modo Caffeine activo desde waybar" \
        --mode=block \
        sleep infinity &
    echo $! > "$PIDFILE"
    notify-send -i dialog-information "☕ Caffeine activado" "La pantalla y el sistema no se apagarán solos" -t 3000
fi
