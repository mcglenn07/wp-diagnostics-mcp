import json
import os
import subprocess

from pathlib import Path
from typing import Literal
from mcp.server.mcpserver import MCPServer

# Machine-specific paths (PHP_BIN, WP_CLI_PHAR, SITE_PATH, DB_SOCKET,
# MYSQL_BIN_DIR) live in local_config.py, which is gitignored — see
# local_config.example.py for the template and what each value means.
#
# Local (by Flywheel) doesn't put `wp` or `php` on your PATH — each site
# is pinned to its own bundled PHP version, and WP-CLI ships as a single
# .phar inside the Local.app bundle rather than a system install, so we
# call the interpreter directly on the .phar instead of relying on `wp`.
# wp-config.php also sets DB_HOST to plain "localhost", which tells PHP's
# mysql drivers to connect over the *default* socket — but Local doesn't
# run MySQL on that default socket, each site gets its own under a
# per-site run directory, so a bare PHP binary needs to be pointed at the
# right socket explicitly. `wp db query` additionally shells out to the
# real `mysql` client by bare name (not through PHP), so its bundled
# location needs to be on PATH too.
from local_config import (
    DB_SOCKET,
    MYSQL_BIN_DIR,
    PHP_BIN,
    SITE_PATH,
    WP_CLI_PHAR,
)

mcp = MCPServer("wp-diagnostics")

log_file = Path(SITE_PATH) / "wp-content" / "debug.log"


def run_wp_cli(args: list[str]) -> str:
    """Run a WP-CLI command against the site and return its combined output.

    Every diagnostic tool below is really just a specific WP-CLI command
    with a specific --format. Centralizing the subprocess call here means
    each tool function is a one-liner, and there's exactly one place that
    knows how to reach this WordPress install.
    """
    env = os.environ.copy()
    env["PATH"] = f"{MYSQL_BIN_DIR}:{env.get('PATH', '')}"
    # `wp db query` builds some of its own internal `mysql` calls (e.g. to
    # check SQL modes) straight from DB_HOST in wp-config.php, ignoring any
    # --socket flag we pass on the command line. DB_HOST is "localhost", so
    # the `mysql` client falls back to its compiled-in default socket unless
    # this env var — which it reads for exactly this case — points it at
    # the real one.
    env["MYSQL_UNIX_PORT"] = DB_SOCKET

    result = subprocess.run(
        [
            PHP_BIN,
            f"-dmysqli.default_socket={DB_SOCKET}",
            f"-dpdo_mysql.default_socket={DB_SOCKET}",
            WP_CLI_PHAR,
            f"--path={SITE_PATH}",
            *args,
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    # WP-CLI reports failures (bad DB creds, unknown command, etc.) via
    # stderr + a non-zero exit code, not exceptions — surface stderr
    # instead of swallowing it, so the caller sees why a command failed.
    if result.returncode != 0:
        return f"wp-cli error: {result.stderr.strip()}"
    return result.stdout.strip()


def format_as_table(output: str) -> str:
    """Reformat wp-cli's tab-separated `db query` output as a Markdown table.

    `wp db query` has no --format=json option (it shells out straight to the
    mysql client), so its output is just tab-separated text with a header
    row. Markdown tables render as actual tables in most MCP clients, so
    it's worth the reformat rather than dumping raw tabs.
    """
    if output.startswith("wp-cli error:") or not output.strip():
        return output

    rows = [line.split("\t") for line in output.splitlines()]
    header, *data_rows = rows

    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    lines += ["| " + " | ".join(row) + " |" for row in data_rows]
    return "\n".join(lines)


@mcp.tool()
def wp_list_plugins() -> str:
    """List all installed WordPress plugins with their status and version."""
    output = run_wp_cli(["plugin", "list", "--format=json"])
    if output.startswith("wp-cli error:"):
        return output

    plugins = json.loads(output)
    lines = [
        f"{p['name']} — {p['status']} (v{p['version']})" for p in plugins
    ]
    return "\n".join(lines)


@mcp.tool()
def wp_php_info() -> str:
    """Return PHP version, WordPress version, and WP-CLI environment info for this site."""
    cli_info = run_wp_cli(["--info"])
    wp_version = run_wp_cli(["core", "version", "--extra"])
    return f"{cli_info}\n\n--- WordPress ---\n{wp_version}"


@mcp.tool()
def wp_error_log(lines: int = 50) -> str:
    """Return the last N lines of wp-content/debug.log for this site."""
    # Read the log file
    if log_file.exists():
        with open(log_file, 'r', encoding='utf-8') as infile:
            list_of_lines = [
                line.strip() for line in infile
            ]

            return "\n".join(list_of_lines[-lines:])
    else:
        return "No debug.log found — is WP_DEBUG_LOG enabled?"


@mcp.tool()
def wp_db_query(sql: str) -> str:
    """Run a read-only SQL SELECT query against the WordPress database."""

    sql = sql.strip()

    if not sql:
        return "SQL query cannot be empty."

    # Remove trailing semicolon for validation.
    normalized = sql.rstrip(";").strip().lower()

    if not normalized.startswith("select "):
        return "Only SELECT queries are allowed."

    # Prevent multiple statements.
    if ";" in normalized:
        return "Multiple SQL statements are not allowed."

    return format_as_table(run_wp_cli(["db", "query", sql]))


@mcp.tool()
def gravity_forms_recent_errors(limit: int = 20) -> str:
    """Return recent Gravity Forms entries with notes marked as errors.

    Covers anything that writes an entry note with sub_type='error' - core
    GF notification-send failures, payment gateway failures (Stripe,
    PayPal), feed add-on failures (Mailchimp, etc.). Does NOT cover Gravity
    PDF, since it logs to its own file rather than entry notes - use
    gf_addon_log() for that instead.
    """
    sql = (
        "SELECT entry_id, value, date_created FROM wp_gf_entry_notes "
        f"WHERE sub_type = 'error' ORDER BY date_created DESC LIMIT {limit}"
    )
    return format_as_table(run_wp_cli(["db", "query", sql]))


@mcp.tool()
def gf_list_loggers() -> str:
    """List every plugin registered with Gravity Forms' logging framework, and whether logging is currently enabled for each."""
    php_code = (
        '$settings = GFLogging::get_instance()->get_plugin_settings();'
        'foreach ( GFLogging::get_instance()->get_supported_plugins() as $slug => $name ) {'
        '    $status = ! empty( $settings[$slug]["enable"] ) ? "enabled" : "disabled";'
        '    echo "$slug: $name ($status)\n";'
        '}'
    )
    return run_wp_cli(["eval", php_code])


def get_enabled_gf_loggers() -> tuple[str, ...]:
    """Return the slugs of GF-ecosystem plugins with logging enabled right now.

    Runs once, at import time, so `gf_addon_log`'s `slug` parameter can be
    typed as a dropdown of only the currently-enabled options. That also
    means it's a snapshot as of server start, not live per-call like
    gf_list_loggers() is - a plugin enabled after the server starts won't
    show up in the dropdown until the server restarts.
    """
    php_code = (
        'foreach ( GFLogging::get_instance()->get_plugin_settings() as $slug => $s ) '
        '{ if ( ! empty( $s["enable"] ) ) { echo "$slug\n"; } }'
    )
    output = run_wp_cli(["eval", php_code])
    if output.startswith("wp-cli error:") or not output.strip():
        return ()
    return tuple(output.splitlines())


# Literal[] needs at least one value, so fall back to a placeholder if
# nothing is enabled (e.g. Local isn't running yet when the server starts) -
# gf_addon_log below still handles that value gracefully as "no such logger".
_ENABLED_GF_SLUGS = get_enabled_gf_loggers() or ("no-loggers-currently-enabled",)
GfLoggerSlug = Literal[_ENABLED_GF_SLUGS]  # type: ignore[valid-type]


@mcp.tool()
def gf_addon_log(slug: GfLoggerSlug, lines: int = 50) -> str:
    """Return the last N lines of a Gravity Forms add-on's log file."""

    # `slug` is now constrained by the Literal type above, so the MCP
    # framework itself rejects anything outside the enabled list before
    # this function body ever runs - the old regex guard is redundant.
    php_code = f'echo GFLogging::get_instance()->get_log_file_name( "{slug}" );'
    log_path = run_wp_cli(["eval", php_code])
    
    if not log_path:
        return "No such logger. Try gf_list_loggers() to see valid slugs."

    gf_log_file = Path(log_path)

    # Read the log file
    if gf_log_file.exists():
        with open(gf_log_file, 'r', encoding='utf-8') as infile:
            list_of_lines = [
                line.strip() for line in infile
            ]

            return "\n".join(list_of_lines[-lines:])
    else:
        return "No debug file found."



if __name__ == "__main__":
    mcp.run()
