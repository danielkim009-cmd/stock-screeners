#!/bin/bash
# Manage the stock-screener backend launchd service (port 8000).
#
# Usage: ./scripts/backend-service.sh {install|uninstall|status|restart|dev-on|dev-off|logs}
#
#   install    Copy plist to ~/Library/LaunchAgents and load it (one-time setup)
#   uninstall  Unload and remove the service
#   status     Is the service loaded? Is the API responding?
#   restart    Kick the service (e.g. after pulling code changes)
#   dev-on     Stop the service so you can run `uvicorn --reload` manually on :8000
#   dev-off    Resume the service after manual dev work
#   logs       Tail the service logs

set -euo pipefail

LABEL="com.stockscreener.backend"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLIST_SRC="$SCRIPT_DIR/$LABEL.plist"
PLIST_DST="$HOME/Library/LaunchAgents/$LABEL.plist"

check_api() {
    if curl -s --max-time 5 http://localhost:8000/api/health | grep -q '"ok"'; then
        echo "API:     responding on http://localhost:8000 ✅"
    else
        echo "API:     NOT responding on http://localhost:8000 ❌ (try: $0 logs)"
    fi
}

case "${1:-}" in
    install)
        mkdir -p "$HOME/Library/LaunchAgents"
        cp "$PLIST_SRC" "$PLIST_DST"
        launchctl unload "$PLIST_DST" 2>/dev/null || true
        launchctl load "$PLIST_DST"
        echo "Installed and loaded $LABEL. Waiting for startup..."
        sleep 3
        check_api
        ;;
    uninstall)
        launchctl unload "$PLIST_DST" 2>/dev/null || true
        rm -f "$PLIST_DST"
        echo "Service unloaded and removed."
        ;;
    status)
        if launchctl list | grep -q "$LABEL"; then
            echo "Service: loaded ✅"
        else
            echo "Service: NOT loaded ❌ (run: $0 install)"
        fi
        check_api
        ;;
    restart)
        launchctl kickstart -k "gui/$(id -u)/$LABEL"
        echo "Restarted. Waiting for startup..."
        sleep 3
        check_api
        ;;
    dev-on)
        launchctl unload "$PLIST_DST" 2>/dev/null || true
        echo "Service stopped. Port 8000 is free — run your dev server:"
        echo "  cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 8000"
        echo "When done: $0 dev-off"
        ;;
    dev-off)
        launchctl load "$PLIST_DST"
        echo "Service resumed. Waiting for startup..."
        sleep 3
        check_api
        ;;
    logs)
        tail -n 40 -f /tmp/$LABEL.out.log /tmp/$LABEL.err.log
        ;;
    *)
        grep '^#' "$0" | head -12 | sed 's/^# \{0,1\}//'
        exit 1
        ;;
esac
