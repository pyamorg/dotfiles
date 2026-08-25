#!/usr/bin/env bash
# Selector de dispositivo de audio para la waybar.
#   audio-menu.sh output   -> altavoces / salida
#   audio-menu.sh input    -> micrófono / entrada
# El volumen no está aquí: es el slider que se despliega al pasar el ratón.
# Cambia el dispositivo por defecto y mueve además los flujos que ya
# estaban sonando, que si no se quedan en el dispositivo anterior.
set -euo pipefail

THEME="$HOME/.config/rofi/menu.rasi"

case "${1:-output}" in
input)
    kind=sources
    prompt="󰍬  Entrada"
    default=$(pactl get-default-source)
    set_default=set-default-source
    move=move-source-output
    streams=source-outputs
    mixer_tab=4 # pestaña "Dispositivos de entrada" de pavucontrol
    ;;
*)
    kind=sinks
    prompt="󰓃  Salida"
    default=$(pactl get-default-sink)
    set_default=set-default-sink
    move=move-sink-input
    streams=sink-inputs
    mixer_tab=5 # pestaña "Dispositivos de salida"
    ;;
esac

# Los ".monitor" son bucles de captura de la salida, no micrófonos reales.
mapfile -t devices < <(
    pactl -f json list "$kind" |
        jq -r '.[] | select(.name | endswith(".monitor") | not)
               | "\(.name)\t\(.description)"'
)

[[ ${#devices[@]} -eq 0 ]] && {
    notify-send -a waybar "Audio" "No hay dispositivos disponibles"
    exit 0
}

names=()
rows=()
for dev in "${devices[@]}"; do
    name=${dev%%$'\t'*}
    desc=${dev#*$'\t'}
    names+=("$name")
    if [[ $name == "$default" ]]; then
        rows+=("󰄬  $desc")
    else
        rows+=("   $desc")
    fi
done

names+=("__mixer__")
rows+=("󰤽  Abrir mezclador…")

choice=$(printf '%s\n' "${rows[@]}" |
    rofi -dmenu -i -theme "$THEME" -p "$prompt" -format i -no-custom) || exit 0

selected=${names[$choice]}

if [[ $selected == "__mixer__" ]]; then
    exec pavucontrol --tab="$mixer_tab"
fi

pactl "$set_default" "$selected"

# Reengancha los flujos activos al dispositivo nuevo.
while read -r id _; do
    [[ -n $id ]] && pactl "$move" "$id" "$selected" 2>/dev/null || true
done < <(pactl list short "$streams")

notify-send -a waybar -i audio-card "$prompt" "${devices[$choice]#*$'\t'}"
