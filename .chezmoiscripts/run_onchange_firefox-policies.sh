#!/usr/bin/env bash
set -euo pipefail

TMP_POLICIES="$(mktemp)"
cat > "$TMP_POLICIES" << 'EOF'
{
  "policies": {
    "SearchEngines": {
      "Default": "DuckDuckGo"
    },
    "ExtensionSettings": {
      "uBlock0@raymondhill.net": {
        "installation_mode": "force_installed",
        "install_url": "https://addons.mozilla.org/firefox/downloads/latest/ublock-origin/latest.xpi",
        "default_area": "navbar"
      },
      "{446900e4-71c2-419f-a6a7-df9c091e268b}": {
        "installation_mode": "force_installed",
        "install_url": "https://addons.mozilla.org/firefox/downloads/latest/bitwarden-password-manager/latest.xpi",
        "default_area": "navbar"
      },
      "addon@darkreader.org": {
        "installation_mode": "force_installed",
        "install_url": "https://addons.mozilla.org/firefox/downloads/latest/darkreader/latest.xpi",
        "default_area": "navbar"
      }
    },
    "DisableTelemetry": true,
    "DisableFirefoxStudies": true,
    "DisablePocket": true,
    "UserMessaging": {
      "SkipOnboarding": true
    },
    "OverrideFirstRunPage": "",
    "DontCheckDefaultBrowser": true,
    "OfferToSaveLogins": false,
    "PasswordManagerEnabled": false,
    "Homepage": {
      "StartPage": "previous-session"
    }
  }
}
EOF

DEST=/etc/firefox/policies/policies.json

if cmp -s "$TMP_POLICIES" "$DEST" 2>/dev/null; then
    rm -f "$TMP_POLICIES"
    exit 0
fi

# chezmoi captura la salida de los scripts, asi que un sudo interactivo se
# quedaria colgado con el prompt invisible y bloqueando el lock de estado.
if ! sudo -n true 2>/dev/null; then
    rm -f "$TMP_POLICIES"
    echo "Hace falta sudo para escribir $DEST y aqui no se puede pedir la contrasena." >&2
    echo "Ejecuta 'sudo -v' y repite 'chezmoi apply'." >&2
    exit 1
fi

sudo -n install -Dm644 "$TMP_POLICIES" "$DEST"
rm -f "$TMP_POLICIES"

echo "policies.json de Firefox actualizado en $DEST"
