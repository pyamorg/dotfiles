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
`theme.sh`, `system/`, este fichero).

`chezmoi apply` sin argumentos se cuelga en este repo (algún prompt): usa
`chezmoi apply --no-tty --force ~/.config/<ruta>`.

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

## Colores: una sola paleta

**No hay colores literales en los configs.** Todo sale de
`.chezmoidata/colors.yaml`, que chezmoi expone como `{{ .colors.X }}` en
cualquier plantilla. Ficheros enganchados: `waybar/{style.css,config.jsonc}`,
`rofi/{config,menu}.rasi`, `swaync/style.css`, `wlogout/{style.css,icons/*.svg}`,
`kitty/kitty.conf`, `hypr/{hyprland.lua,hyprlock.conf}` y
`hypr/colors.json` (este último para los scripts, que no pueden ser
plantillas: `calendar-menu.py` lleva `{{` en un `-theme-str` de rofi).

Las claves son **roles, no colores**: `accent`/`accent2`/`accent3` salen del
tono dominante del fondo; los neutros (`crust`…`text`) son una rampa teñida
con ese mismo tono; los semánticos (`red`, `yellow`, `green`…) mantienen su
tono fijo para no perder significado. En los CSS se conservan los nombres
locales de siempre (`@blue` = `accent`, `@mauve` = `accent2`,
`@lavender` = `accent3`) para no tocar el cuerpo de las hojas.

`./theme.sh` (raíz del repo, ignorado por chezmoi) regenera el yaml:

```bash
./theme.sh --dry-run          # enseña la paleta en color, sin escribir
./theme.sh                    # usa el fondo de hyprpaper.conf
./theme.sh ~/Pictures/x.jpg   # usa otra imagen
./theme.sh --reset            # vuelve a Catppuccin Mocha
```

Saca el histograma con ImageMagick (`-colors 16`), pondera cada tono por
`píxeles × saturación²` para descartar grises, escribe el yaml, hace
`chezmoi apply` **sólo de los ficheros del tema** (aplicar directorios
enteros arrastraría cambios ajenos, p.ej. el bloque de HyprMod en
`hyprland.lua`), regenera los PNG de wlogout con `rsvg-convert` y recarga
waybar, swaync, hyprland y kitty.

## Notificaciones

`timeout-critical` en `swaync/config.json` estaba a **0 = no expira nunca**;
por eso los avisos se quedaban en pantalla hasta cerrarlos a mano. Ahora son
8 s. Además **swaync ignora el `-t` de `notify-send` en las críticas**
(verificado: con `-t 2000` seguía en pantalla a los 3,5 s), así que la única
palanca es la config.

Regla: `-u critical` sólo para lo que de verdad interrumpe (batería baja).
Un fallo de conexión o un comando que no está instalado va con urgencia
normal y `-i dialog-error`.

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
| `calendar-menu.py` | Agenda de los calendarios CalDAV (evolution-data-server): reloj de la barra (`--clock`) con rejilla mensual en el tooltip, cápsula del próximo evento, menú con detalle, alta rápida en español, borrado y visibilidad de calendarios |
| `Weather.py` | Tiempo de wttr.in (j1, `lang=es`) con caché de 15 min: icono según cielo/día-noche y tooltip con detalles y previsión de 3 días. `--tooltip` lo imprime suelto |
| `dnd.sh` | Silencio de notificaciones (swaync) |
| `clipboard-menu.sh` | Historial de cliphist |
| `control-center.sh` | Menú raíz con todo lo anterior (Super+C) |
| `caffeine.sh` | Inhibidor de suspensión |

Patrón de los módulos custom: `script.sh --status` imprime
`{"text","class","tooltip"}` y `script.sh` a secas alterna y manda
`pkill -RTMIN+N waybar` para refrescar al instante. Señales en uso: 8
caffeine, 9 red, 10 dnd, 11 agenda, 12 tiempo.

Si el módulo emite JSON con `json.dumps`, hace falta `ensure_ascii=False`: con
los escapes `\uXXXX` los iconos fuera del BMP salen como pares subrogados y
waybar descarta el módulo entero sin decir nada.

## Calendarios

Los eventos salen de evolution-data-server, las mismas cuentas CalDAV de
Nextcloud que usa GNOME Calendar (`~/.config/evolution/sources/*.source`). Se
leen con `gi.repository.ECal` y `EDataServer`; no hace falta khal ni
vdirsyncer. Detalles que costaron:

- El callback de `generate_instances_sync` recibe un `ICalGLib.Component`, no
  un `ECal.Component`: no tiene `get_icalcomponent()`.
- Cada instancia trae su propia zona horaria, así que `set_default_timezone()`
  no cambia nada; hay que convertir con `as_timet_with_zone(t.get_timezone())`.
- Los eventos nuevos se guardan en UTC para no tener que emitir un VTIMEZONE.

El reloj de la barra **no** es el módulo `clock` nativo, sino `custom/clock`
(el mismo script con `--clock`): el nativo pinta el mes en el tooltip pero no
sabe colorear días sueltos, y aquí cada día lleva un punto por calendario con
eventos. Notas:

- Sin `interval`: el script imprime en bucle y duerme `60 - segundo actual`,
  así la hora nunca se retrasa. `restart-interval: 5` lo resucita si muere.
- **El bucle no llama nunca a evolution-data-server.** Pinta el tooltip desde
  la caché (`load_events(offline=True)`) y quien la refresca es `--status`,
  que corre en su propio proceso. Leer de EDS puede tardar minutos si un
  backend está sincronizando, y eso congelaba la hora en pantalla.
- El 3er argumento de `ECal.Client.connect_sync` son los *segundos a esperar
  a que el backend esté online*, no un timeout de error: con 15 y cuatro
  calendarios se pagaban 60 s antes de leer nada. Para leer va 0.
- Un backend CalDAV enfermo deja las llamadas síncronas colgadas para
  siempre (visto: `Personal` bloqueó un `--status` durante 23 minutos, y
  reiniciar `evolution-calendar-factory` no bastó). Por eso cada llamada va
  envuelta en `deadline()`, un `Gio.Cancellable` que se cancela solo a los
  `CALL_LIMIT` segundos: el calendario que no responde se salta y los demás
  siguen.
- El menú usa `events_for_ui()`: pinta la caché aunque esté vieja y lanza el
  refresco aparte, para abrir siempre al instante.
- Los puntos de la rejilla son `•` (U+2022), de ancho normal en la
  monoespaciada; `●` sería *wide* y descuadraría las columnas.
- Los dos meses van en columnas (`side_by_side`), no apilados: apilados el
  tooltip salía estrechísimo y larguísimo.
- Para ver el tooltip sin poder hacer hover:
  `calendar-menu.py --tooltip | pango-view --markup -q -o /tmp/tt.png /dev/stdin`.

## Rendimiento

`nmcli device wifi list` lanza un escaneo y bloquea varios segundos: usa
siempre `--rescan no` y lanza el rescan aparte en segundo plano. Cualquier
script que waybar ejecute por `interval` debe tardar menos de ~100 ms.
