# AGENTS.md

Guía para agentes que trabajen en este repo de dotfiles. Todo (comentarios,
mensajes de notificación, textos de menú) va **en español**.

## Flujo obligatorio

Los ficheros de este repo son la fuente; `$HOME` es el destino. **Nunca edites
`~/.config/...` directamente**: se sobrescribe en el siguiente `chezmoi apply`.

```bash
cd ~/.local/share/chezmoi
# editar dot_config/...
chezmoi apply
```

Convenciones de chezmoi: `dot_config/` → `~/.config/`, prefijo `executable_`
para scripts, sufijo `.tmpl` para plantillas, `private_` para permisos 600.
`.chezmoiignore` excluye lo que no debe salir al home (`install-packages.sh`,
`system/`, este fichero).

Recargas tras aplicar:

| Qué tocaste | Cómo recargar |
| --- | --- |
| `dot_config/waybar/**` | `pkill -x waybar; nohup waybar >/tmp/waybar.log 2>&1 &` |
| `dot_config/hypr/hyprland.lua.tmpl` | `hyprctl reload && hyprctl configerrors` |
| Scripts de `dot_config/hypr/scripts/` | nada, se leen en cada invocación |

`pkill -SIGUSR2 waybar` a veces mata la barra en vez de recargarla; es más
fiable relanzarla.

## Hyprland con configuración en Lua

Hyprland 0.56 con `hyprland.lua`, API `hl.*`. Stub de referencia en
`/usr/share/hypr/stubs/hl.meta.lua`.

- `hyprctl keyword` **no funciona** ("keyword can't work with non-legacy
  parsers"). Para cambios en caliente: `hyprctl eval 'hl.config({ ... })'`.
- `hyprctl binds -j` muestra los binds de Lua como `dispatcher: "__lua"` con
  un `arg` numérico opaco, y los `code:NN` con `key` vacío: no se pueden
  identificar por comando. Solo sirve para contar y ver `modmask`.
- Los atajos con letras usan `code:NN` (keycode X11) porque el usuario escribe
  en **Dvorak**: así el atajo cae siempre en la misma tecla física.
- Layer rules: sin `ignore_alpha` el blur difumina toda la franja de la barra,
  incluidos los huecos transparentes entre cápsulas. Con `ignore_alpha = 0.5`
  solo se difumina lo opaco (las cápsulas tienen alfa 0.85).

## Menús desplegables (rofi)

Las cápsulas de waybar abren menús de rofi anclados bajo la barra. Tema común:
`dot_config/rofi/menu.rasi`.

- rofi 2.0 es nativo Wayland (layer-shell): **no** hace falta window rule.
- `-format i` devuelve el índice de la fila: nunca parsees el texto pintado.
- `-mesg` exige que `message` esté en `mainbox { children }`.
- Validar un tema: `rofi -theme X -dump-theme >/dev/null`.
- Los boxes de rofi no honran `width`; solo `window`. En un box no expandible
  el listview colapsa a 0 salvo con `fixed-height: true; dynamic: true`.
- Hacía falta doble clic para elegir: se arregla con `me-accept-entry:
  "MousePrimary"` en `config.rasi`.
- El "click fuera para cerrar" de rofi **solo existe en el backend XCB**
  (`rofi_view_temp_click_to_exit` delega en `proxy->temp_click_to_exit`). En
  Wayland se suple desde el compositor: binds de ratón `non_consuming` que
  comparan `hl.get_cursor_pos()` con `hl.get_layers({ namespace = "rofi" })`
  y hacen `pkill -x rofi` si el clic cae fuera. Está al final de
  `hyprland.lua.tmpl`.

## Sliders de volumen y brillo

Son módulos nativos de waybar dentro de grupos con drawer: `group/audio`
(`pulseaudio` + `pulseaudio/slider`) y `group/power` (`battery` +
`backlight/slider`), ambos con `transition-left-to-right: false`. **No hay
slider para el micrófono**: waybar solo enlaza
`pa_context_set_sink_volume_by_index`, así que la entrada se ajusta con la
rueda sobre su cápsula (`on-scroll-up/down` con `wpctl`).

Se intentó emular un slider dentro de rofi (relanzándolo con `-kb-custom-1/2`
atados a la rueda) y queda feo: descartado.

## Iconos Nerd Font

Trampa recurrente: al escribir glifos desde herramientas de edición se cuelan
bytes erróneos (`ef bf bd`, el carácter de reemplazo) o codepoints distintos
al buscado. **Comprueba siempre con `hexdump -C`** después de editar una línea
con iconos. Usa el set nf-md (`U+F0xxx`); algunos nf-fa salen invisibles con
la JetBrainsMono NF instalada. `fc-list ":charset=f0582"` dice si la fuente
tiene un codepoint, pero no si el que escribiste es el que creías.

## Verificación sin poder usar el ratón

No hay forma de simular clics (`/dev/uinput` es root-only, no hay `ydotool`
ni `wtype`). Estrategias que sí funcionan:

- Capturar la barra o el menú: `grim -g "X,Y WxH" /tmp/x.png` y mirar la
  imagen. Ancho de pantalla: `hyprctl monitors -j | jq -r '.[0].width'`.
- Abrir un menú sin bloquear: `(setsid script.sh &); sleep 1.5; grim ...;
  pkill -x rofi`.
- Abrir un drawer de waybar: `hyprctl dispatch movecursor X Y` en pasos
  sucesivos (un solo salto no genera el evento de motion).
- Los módulos custom se pueden probar a mano: `script.sh --status`.

## Hardware (LG Gram 14Z90N-V, i5-1035G7)

- `intel_pstate` con HWP; **no existe** `/sys/firmware/acpi/platform_profile`,
  así que power-profiles-daemon aportaría poco (solo tocaría el EPP).
- Módulo `lg_laptop` cargado: `/sys/devices/platform/lg-laptop/` expone
  `battery_care_limit`, `fan_mode`, `fn_lock`, `usb_charge`, `reader_mode`.
  Son root:root; `system/99-lg-laptop.rules` los pasa a grupo `wheel`.
- Batería `CMB0`. VPN WireGuard `pyam-minipyam` en NetworkManager.
- No hay agente de polkit corriendo: `pkexec` no sirve, usa udev o sudo.

## Mapa de scripts (`dot_config/hypr/scripts/`)

| Script | Qué hace |
| --- | --- |
| `net-status.sh` | Estado de red para waybar (`custom/network`); refleja la VPN con icono y clase `.vpn`. `--toggle` apaga/enciende el wifi |
| `wifi-menu.sh` | Menú de redes, VPNs y ajustes. Rescan en segundo plano |
| `bluetooth-menu.sh` | Dispositivos, escaneo, emparejado |
| `audio-menu.sh` | `output`/`input`: elige dispositivo y mueve los flujos activos |
| `power-menu.sh` | Caffeine y tope de carga; el brillo es el slider del drawer |
| `battery-watch.sh` | Bucle que al 15% baja el brillo y avisa; lo restaura al enchufar |
| `proc-menu.sh` | `cpu`/`mem`: top 12, Enter mata el proceso |
| `music.sh` | Reproductor; esconde la cápsula tras 5 min en pausa |
| `dnd.sh` | Silencio de notificaciones (swaync) |
| `clipboard-menu.sh` | Historial de cliphist |
| `control-center.sh` | Menú raíz con todo lo anterior (Super+C) |
| `caffeine.sh` | Inhibidor de suspensión |

Patrón de los módulos custom: `script.sh --status` imprime
`{"text","class","tooltip"}` y `script.sh` a secas alterna y manda
`pkill -RTMIN+N waybar` para refrescar al instante. Señales en uso: 8
caffeine, 9 red, 10 dnd.

## Rendimiento

`nmcli device wifi list` lanza un escaneo y bloquea varios segundos: usa
siempre `--rescan no` y lanza el rescan aparte en segundo plano. Cualquier
script que waybar ejecute por `interval` debe tardar menos de ~100 ms.
