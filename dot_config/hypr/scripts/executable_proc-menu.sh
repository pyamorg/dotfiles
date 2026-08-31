#!/usr/bin/env bash
# Los procesos que más consumen, con opción de terminarlos.
#   proc-menu.sh cpu  -> ordenado por CPU
#   proc-menu.sh mem  -> ordenado por memoria
set -euo pipefail

THEME="$HOME/.config/rofi/menu.rasi"

case "${1:-cpu}" in
mem) sort_key=-%mem prompt="  Memoria" ;;
*) sort_key=-%cpu prompt="  CPU" ;;
esac

pids=()
rows=()

while read -r pid cpu mem cmd; do
    pids+=("$pid")
    rows+=("$(printf '%5s%%  %5s%%  %s' "$cpu" "$mem" "${cmd:0:28}")")
done < <(ps -eo pid=,%cpu=,%mem=,comm= --sort="$sort_key" | head -12)

pids+=("__monitor__")
rows+=("󰍛  Abrir btop…")

choice=$(printf '%s\n' "${rows[@]}" |
    rofi -dmenu -i -theme "$THEME" -p "$prompt" -format i -no-custom \
        -mesg "  CPU     RAM    Proceso  ·  Enter para terminarlo") || exit 0

selected=${pids[$choice]}

[[ $selected == "__monitor__" ]] && exec kitty -e btop

name=$(ps -p "$selected" -o comm= 2>/dev/null || true)
[[ -z $name ]] && exit 0

kill "$selected" 2>/dev/null &&
    notify-send -a waybar "Proceso terminado" "$name ($selected)" ||
    notify-send -a waybar -i dialog-error "No se pudo terminar" "$name ($selected)"
