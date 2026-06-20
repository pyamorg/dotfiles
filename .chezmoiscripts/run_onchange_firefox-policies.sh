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

sudo mkdir -p /etc/firefox/policies
sudo cp "$TMP_POLICIES" /etc/firefox/policies/policies.json
rm -f "$TMP_POLICIES"

echo "policies.json de Firefox actualizado en /etc/firefox/policies/"
