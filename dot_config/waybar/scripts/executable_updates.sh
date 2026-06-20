#!/usr/bin/env bash
# ~/.config/waybar/scripts/updates.sh
#
# Imprime estado en JSON de forma continua para que Waybar pueda
# mostrar un indicador de "cargando" mientras checkupdates corre.
#
# chezmoi: este archivo vive como
#   dot_config/waybar/scripts/executable_updates.sh
# y se gestiona/aplica con permisos de ejecución automáticamente
# (sin necesidad de chmod manual ni de .chezmoiscripts).

INTERVAL=3600  # segundos entre comprobaciones (1h)

while true; do
    # 1. Estado de carga (se muestra de inmediato)
    echo '{"text":"","class":"loading","tooltip":"Comprobando actualizaciones..."}'

    # 2. Comprobación real (puede tardar unos segundos)
    count=$(checkupdates 2>/dev/null | wc -l)

    # 3. Resultado final
    if [ "$count" -eq 0 ]; then
        echo '{"text":" 0","class":"updated","tooltip":"Sistema actualizado"}'
    else
        echo "{\"text\":\" ${count}\",\"class\":\"pending\",\"tooltip\":\"${count} actualizaciones disponibles\nClick para actualizar\"}"
    fi

    sleep "$INTERVAL"
done
