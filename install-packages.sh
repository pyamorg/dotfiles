#!/usr/bin/env bash
#
# install-packages.sh
# Va en la RAÍZ de tu repo de dotfiles (no en el instalador genérico).
# El instalador genérico (04-post-install.sh) lo detecta y lo ejecuta
# solo si existe, después de aplicar tus dotfiles con chezmoi.
#
# Se ejecuta como tu usuario normal (no root) — yay ya está instalado
# en este punto por el instalador genérico.

set -euo pipefail

echo "--> Paquetes oficiales personales..."
sudo pacman -S --needed --noconfirm \
    swaync rofi-calc pacman-contrib \
    zsh \
    gnome-calendar gnome-online-accounts gnome-keyring \
    python-requests gnome-system-monitor nvtop \
    kitty thunar btop qt5ct qt6ct \
    qt6-declarative qt6-5compat qt6-multimedia qt6-multimedia-ffmpeg \
    gst-plugins-base gst-plugins-good gst-plugins-bad gst-plugins-ugly fzf

# Dependencias que invocan directamente los dotfiles (waybar, hyprland,
# hypridle y los scripts de ~/.config/hypr/scripts).
echo "--> Dependencias de la barra y los atajos..."
sudo pacman -S --needed --noconfirm \
    waybar jq \
    grim slurp wl-clipboard hyprpicker \
    hypridle hyprlock hyprpaper \
    brightnessctl \
    network-manager-applet blueman pavucontrol \
    cliphist playerctl \
    ttf-jetbrains-mono-nerd

# Estas hoy entran como dependencias de otros paquetes, pero los dotfiles las
# usan de forma directa: hay que pedirlas explícitamente o pueden no estar.
#   python-gobject/evolution-data-server -> calendar-menu.py
#   imagemagick/librsvg                  -> theme.sh
echo "--> Dependencias directas de los scripts (no dejarlas como transitivas)..."
sudo pacman -S --needed --noconfirm \
    python-gobject evolution-data-server \
    imagemagick librsvg

echo "--> Paquetes AUR personales..."
yay -S --needed --noconfirm wlogout quickshell

echo "--> Cambiando shell a zsh..."
chsh -s /usr/bin/zsh

echo "--> Instalando Oh My Zsh (clonado manual, no toca tu .zshrc gestionado por chezmoi)..."
if [ ! -d "$HOME/.oh-my-zsh" ]; then
    git clone --depth=1 https://github.com/ohmyzsh/ohmyzsh.git "$HOME/.oh-my-zsh"
fi

echo "--> Instalando lockscreen Quickshell (qylock)..."
if [ ! -d "$HOME/.local/share/quickshell-lockscreen" ]; then
    tmpdir=$(mktemp -d)
    git clone https://github.com/Darkkal44/qylock.git "$tmpdir/qylock"
    (cd "$tmpdir/qylock" && chmod +x quickshell.sh && ./quickshell.sh)
    rm -rf "$tmpdir"
fi

echo "--> Configurando auto-desbloqueo de gnome-keyring con SDDM..."
if ! grep -q pam_gnome_keyring /etc/pam.d/sddm 2>/dev/null; then
    sudo sed -i '/^auth.*include.*system-login/a auth       optional     pam_gnome_keyring.so' /etc/pam.d/sddm
    sudo sed -i '/^session.*include.*system-login/a session    optional     pam_gnome_keyring.so auto_start' /etc/pam.d/sddm
fi

echo "--> Permisos de los knobs del LG Gram (tope de carga, ventilador)..."
rules="$(dirname "$0")/system/99-lg-laptop.rules"
if [ -e /sys/devices/platform/lg-laptop ] && [ -f "$rules" ]; then
    sudo install -m 644 "$rules" /etc/udev/rules.d/99-lg-laptop.rules
    sudo udevadm control --reload
    sudo udevadm trigger --subsystem-match=platform
fi

echo "--> Preferencia de modo oscuro (dconf, necesita sesión real)..."
dconf write /org/gnome/desktop/interface/color-scheme "'prefer-dark'"
dconf write /org/gnome/desktop/interface/gtk-theme "'Adwaita-dark'"

echo
echo "=================================================================="
echo "  install-packages.sh completo."
echo "  Reinicia sesión para que el cambio de shell (zsh) tenga efecto."
echo "=================================================================="
