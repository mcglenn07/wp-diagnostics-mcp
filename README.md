# wp-diagnostics-mcp

An [MCP](https://modelcontextprotocol.io) server that gives an AI assistant direct diagnostic access to a local WordPress install — plugin, PHP, and environment info, debug-log tailing, a guarded read-only SQL query tool, and a pair of tools built specifically for Gravity Forms support work.

Built against a real [Local by Flywheel](https://localwp.com) WordPress site running the Gravity Forms / Gravity PDF stack, as a portfolio project pairing hands-on WordPress support experience with MCP server development.

## Tools

| Tool | Description |
|---|---|
| `wp_list_plugins` | List all installed plugins with status and version. |
| `wp_php_info` | PHP version, WordPress version, and WP-CLI environment info. |
| `wp_error_log` | Tail the last N lines of `wp-content/debug.log`. |
| `wp_db_query` | Run a single read-only `SELECT` against the WordPress database. Rejects anything that isn't exactly one `SELECT` statement. |
| `gravity_forms_recent_errors` | Recent Gravity Forms entries with notes marked `sub_type='error'` — notification, payment gateway, and feed add-on failures. |
| `gf_list_loggers` | List every plugin registered with Gravity Forms' logging framework and whether logging is enabled for each. |
| `gf_addon_log` | Tail the log file for a specific enabled Gravity Forms add-on, by slug. |

## Why it looks the way it does

Local by Flywheel doesn't put `php` or `wp` on `PATH` — each site is pinned to its own bundled PHP version, and WP-CLI ships as a single `.phar` inside the Local.app bundle. `wp-config.php` also sets `DB_HOST` to plain `localhost`, but Local runs each site's MySQL on its own per-site socket rather than the system default, so a bare CLI call fails with a database connection error even though WP-CLI itself is reachable.

`server.py` centralizes all of that into one `run_wp_cli()` helper that points the PHP binary, `mysqli`/`pdo_mysql`, and the `mysql` client (for `wp db query`, which shells out to it directly) at the correct per-site socket. Five of the seven tools are thin wrappers around a specific WP-CLI command. `wp_error_log` reads `debug.log` directly, and `gf_addon_log` asks WP-CLI for the add-on's log path, then reads that file.

## Setup

Requires [`uv`](https://docs.astral.sh/uv/) and a running Local by Flywheel site.

```bash
uv sync
cp local_config.example.py local_config.py
```

Fill in `local_config.py` with your own site's paths (`PHP_BIN`, `WP_CLI_PHAR`, `SITE_PATH`, `DB_SOCKET`, `MYSQL_BIN_DIR`) — see the comments in `local_config.example.py` for how to find each one. This file is gitignored since these paths are specific to one Local installation and site, not portable as-is.

Register it with an MCP client (e.g. Claude Desktop's `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "wp-diagnostics": {
      "command": "uv",
      "args": ["--directory", "/path/to/wp-diagnostics-mcp", "run", "server.py"]
    }
  }
}
```

## Scope

Local-only diagnostics for a single WordPress install. `wp_db_query` is intentionally read-only — it rejects any statement that isn't a single `SELECT` — since this is meant for inspection, not administration.
