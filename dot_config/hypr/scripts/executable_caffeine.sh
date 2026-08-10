#!/usr/bin/env bash
# ~/.config/hypr/scripts/caffeine.sh
# Alterna el modo "caffeine" (bloquea que el sistema se suspenda/apague
# la pantalla automáticamente).

PIDFILE="${XDG_RUNTIME_DIR:-/tmp}/caffeine-inhibitor.pid"

# Función: comprueba si el inhibidor sigue vivo de verdad
caffeine_is_active() {
    [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null
}

# Limpia un PID huérfano (proceso muerto pero pidfile presente)
if [ -f "$PIDFILE" ] && ! kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    rm -f "$PIDFILE"
fi

if caffeine_is_active; then
    # Modo caffeine activo → desactivar
    kill "$(cat "$PIDFILE")"
    wait "$(cat "$PIDFILE")" 2>/dev/null || true
    rm -f "$PIDFILE"
    # Reanudar hypridle
    pkill -CONT hypridle 2>/dev/null || true
    notify-send \
        --icon=dialog-information \
        --urgency=normal \
        "Caffeine desactivado" \
        "El auto-apagado y la suspensión vuelven a estar activos" \
        -t 3000
else
    # Pausar hypridle ANTES de activar el inhibidor — hypridle llama
    # directamente a systemctl suspend saltándose los inhibidores de systemd
    pkill -STOP hypridle 2>/dev/null || true

    # Modo caffeine inactivo → activar
    systemd-inhibit \
        --what=idle:sleep:handle-lid-switch \
        --who="Caffeine (waybar)" \
        --why="Modo Caffeine activado manualmente" \
        --mode=block \
        sleep infinity &
    echo $! > "$PIDFILE"

    # Pequeña pausa para confirmar que el proceso arrancó bien
    sleep 0.3
    if caffeine_is_active; then
        notify-send \
            --icon=dialog-information \
            --urgency=normal \
            "☕ Caffeine activado" \
            "La pantalla y el sistema no se apagarán solos.\nClic derecho en la batería para desactivar." \
            -t 4000
    else
        rm -f "$PIDFILE"
        pkill -CONT hypridle 2>/dev/null || true
        notify-send \
            --icon=dialog-error \
            --urgency=critical \
            "Caffeine falló" \
            "No se pudo activar el inhibidor. Revisa systemd-inhibit." \
            -t 5000
    fi
fi
