#!/bin/sh
# alertmanager-entrypoint.sh
#
# ITEM 2: Renders the Alertmanager config template before starting the process.
#
# Why this exists:
#   Alertmanager YAML parser does NOT perform shell-style ${VAR} substitution.
#   The previous alertmanager.yml had ${SLACK_WEBHOOK_URL:default} which was
#   never evaluated — the literal placeholder string was used as the webhook URL.
#
# What this does:
#   1. Validates SLACK_WEBHOOK_URL is set and not empty.
#   2. Runs envsubst to render alertmanager.yml.template → alertmanager.yml.
#   3. Validates the rendered file contains no unresolved ${...} placeholders.
#   4. Validates the rendered file is valid YAML (via amtool check-config).
#   5. Starts Alertmanager.
#
# Required environment variables:
#   SLACK_WEBHOOK_URL  - Full Slack incoming webhook URL (e.g. https://hooks.slack.com/...)

set -eu

TEMPLATE="/etc/alertmanager/alertmanager.yml.template"
OUTPUT="/etc/alertmanager/alertmanager.yml"

echo "[alertmanager-entrypoint] Checking SLACK_WEBHOOK_URL..."

if [ -z "${SLACK_WEBHOOK_URL:-}" ]; then
    echo "[alertmanager-entrypoint] ERROR: SLACK_WEBHOOK_URL is not set or empty."
    echo "[alertmanager-entrypoint] Set SLACK_WEBHOOK_URL to a valid Slack incoming webhook URL."
    exit 1
fi

# Sanity-check: webhook must start with https://
case "${SLACK_WEBHOOK_URL}" in
    https://*)
        ;;
    *)
        echo "[alertmanager-entrypoint] ERROR: SLACK_WEBHOOK_URL must start with https://"
        echo "[alertmanager-entrypoint] Got: ${SLACK_WEBHOOK_URL}"
        exit 1
        ;;
esac

echo "[alertmanager-entrypoint] Rendering config template..."
envsubst < "${TEMPLATE}" > "${OUTPUT}"

# Verify no unresolved placeholders remain
if grep -q '\${' "${OUTPUT}"; then
    echo "[alertmanager-entrypoint] ERROR: Rendered config still contains unresolved placeholders:"
    grep '\${' "${OUTPUT}"
    exit 1
fi

echo "[alertmanager-entrypoint] Config rendered successfully."

# Optionally validate with amtool (available in prom/alertmanager image)
if command -v amtool > /dev/null 2>&1; then
    echo "[alertmanager-entrypoint] Validating config with amtool..."
    amtool check-config "${OUTPUT}"
fi

echo "[alertmanager-entrypoint] Starting Alertmanager..."
exec /bin/alertmanager \
    --config.file="${OUTPUT}" \
    --storage.path=/alertmanager \
    "$@"
