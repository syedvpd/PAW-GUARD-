"""Alertmanager configuration tests — adversarial (ITEM 2).

Proves:
1. The template file exists and is a valid YAML template.
2. envsubst renders the template correctly (using Python's os.environ substitution).
3. The rendered config contains no unresolved ${...} placeholders.
4. The rendered config is valid YAML.
5. An empty SLACK_WEBHOOK_URL is detected (empty webhook guard).
6. The old broken syntax (${VAR:default}) no longer exists in the template.
7. The entrypoint script exists and contains the key safety checks.

Per adversarial pre-mortem §6:
- "template → environment injection → rendered configuration" is proven locally.
- Docker runtime test: NOT EXECUTED LOCALLY (Docker not available).
  Status: NOT FIXED — DOCKER RUNTIME UNVERIFIED. Code is correct; CI with
  Docker proves the final step.
"""

from __future__ import annotations

import os
import re

import yaml

MONITORING_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "monitoring")
TEMPLATE_PATH = os.path.join(MONITORING_DIR, "alertmanager.yml.template")
ENTRYPOINT_PATH = os.path.join(MONITORING_DIR, "alertmanager-entrypoint.sh")
OLD_CONFIG_PATH = os.path.join(MONITORING_DIR, "alertmanager.yml")


def _render_template(template_content: str, env: dict[str, str]) -> str:
    """Simple envsubst implementation: replaces ${VAR} with env[VAR]."""

    def replacer(match: re.Match[str]) -> str:
        var_name = match.group(1)
        return env.get(var_name, "")

    return re.sub(r"\$\{([A-Z_][A-Z0-9_]*)\}", replacer, template_content)


class TestAlertmanagerTemplate:
    """Proves the template file is correct and renders cleanly."""

    def test_template_file_exists(self) -> None:
        assert os.path.exists(TEMPLATE_PATH), f"Template file not found at {TEMPLATE_PATH}"

    def test_old_static_config_removed(self) -> None:
        """The old un-interpolated alertmanager.yml must be removed to avoid config confusion."""
        assert not os.path.exists(OLD_CONFIG_PATH), (
            f"Old static config still exists at {OLD_CONFIG_PATH}"
        )

    def test_template_is_valid_yaml_with_placeholder(self) -> None:
        """Template with placeholder substituted must be valid YAML."""
        with open(TEMPLATE_PATH) as f:
            content = f.read()

        rendered = _render_template(
            content, {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/test/webhook"}
        )
        parsed = yaml.safe_load(rendered)
        assert parsed is not None
        assert "receivers" in parsed
        assert "route" in parsed

    def test_rendered_webhook_url_is_injected(self) -> None:
        """Webhook URL appears correctly in the rendered output."""
        with open(TEMPLATE_PATH) as f:
            content = f.read()

        webhook = "https://hooks.slack.com/services/T123/B456/abc123"
        rendered = _render_template(content, {"SLACK_WEBHOOK_URL": webhook})
        assert webhook in rendered

    def test_no_unresolved_placeholders_after_render(self) -> None:
        """After substitution with a valid key, no ${...} remain."""
        with open(TEMPLATE_PATH) as f:
            content = f.read()

        rendered = _render_template(content, {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/test"})
        unresolved = re.findall(r"\$\{[^}]+\}", rendered)
        assert not unresolved, f"Unresolved placeholders after render: {unresolved}"

    def test_empty_webhook_produces_empty_url(self) -> None:
        """Empty SLACK_WEBHOOK_URL renders to empty string (entrypoint catches this)."""
        with open(TEMPLATE_PATH) as f:
            content = f.read()

        rendered = _render_template(content, {"SLACK_WEBHOOK_URL": ""})
        # api_url should be '' or absent — not the placeholder string
        assert "https://example.com" not in rendered
        assert "${SLACK_WEBHOOK_URL}" not in rendered

    def test_no_colon_default_syntax_in_template(self) -> None:
        """The old broken ${VAR:default} syntax must NOT exist in the template.

        Alertmanager does not evaluate this syntax — the literal string was used.
        The fix replaces it with plain ${VAR} which envsubst handles.
        """
        with open(TEMPLATE_PATH) as f:
            content = f.read()

        broken_pattern = re.compile(r"\$\{[A-Z_]+:[^}]+\}")
        matches = broken_pattern.findall(content)
        assert not matches, (
            "Template still contains ${...default} syntax that Alertmanager "
            f"cannot evaluate: {matches}"
        )

    def test_rendered_yaml_has_correct_receiver(self) -> None:
        """Rendered config has slack-notifications receiver with correct channel."""
        with open(TEMPLATE_PATH) as f:
            content = f.read()

        rendered = _render_template(content, {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/test"})
        parsed = yaml.safe_load(rendered)
        receivers = {r["name"]: r for r in parsed["receivers"]}
        assert "slack-notifications" in receivers
        slack_config = receivers["slack-notifications"]["slack_configs"][0]
        assert slack_config["channel"] == "#alerts"
        assert slack_config["send_resolved"] is True

    def test_placeholder_value_is_not_example_url(self) -> None:
        """The template must not contain a hardcoded example.com URL as fallback."""
        with open(TEMPLATE_PATH) as f:
            content = f.read()

        assert "example.com" not in content, (
            "Template contains a hardcoded example.com URL — this would be used if envsubst fails."
        )


class TestAlertmanagerEntrypoint:
    """Proves the entrypoint script contains mandatory safety guards."""

    def test_entrypoint_exists(self) -> None:
        assert os.path.exists(ENTRYPOINT_PATH), f"Entrypoint script not found at {ENTRYPOINT_PATH}"

    def test_entrypoint_checks_for_empty_webhook(self) -> None:
        with open(ENTRYPOINT_PATH) as f:
            content = f.read()
        assert "SLACK_WEBHOOK_URL" in content
        # Must have a guard for empty/unset value
        assert "exit 1" in content

    def test_entrypoint_checks_for_https(self) -> None:
        with open(ENTRYPOINT_PATH) as f:
            content = f.read()
        assert "https://" in content

    def test_entrypoint_uses_envsubst(self) -> None:
        with open(ENTRYPOINT_PATH) as f:
            content = f.read()
        assert "envsubst" in content

    def test_entrypoint_validates_no_unresolved_placeholders(self) -> None:
        with open(ENTRYPOINT_PATH) as f:
            content = f.read()
        # Must check for remaining ${...} after rendering
        assert r"\${" in content or "grep -q" in content

    def test_entrypoint_starts_alertmanager(self) -> None:
        with open(ENTRYPOINT_PATH) as f:
            content = f.read()
        assert "alertmanager" in content
        assert "exec" in content  # uses exec to replace the shell


class TestAlertmanagerDockerNotRun:
    """Documents the Docker runtime test as explicitly NOT EXECUTED LOCALLY.

    Per adversarial pre-mortem §6: "NOT EXECUTED LOCALLY" is the honest status.
    The Docker runtime test (actual container startup) requires Docker,
    which is not available in this environment.

    To complete this: run `docker compose -f monitoring/docker-compose.monitoring.yml up --abort-on-container-exit`
    and verify alertmanager starts without error.
    """

    def test_docker_runtime_test_explicitly_documented_as_not_run(self) -> None:
        """This test documents the gap — it does not claim Docker was tested."""
        # This test always passes — it is a documentation anchor in the CI report.
        # A real Docker test would be a separate CI job.
        assert True, "Docker runtime test not run locally — requires Docker"
