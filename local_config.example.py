# Copy this file to local_config.py and fill in the paths for your own
# Local by Flywheel install. local_config.py is gitignored since these are
# machine-specific, not project config.
#
# How to find each value:
# - PHP_BIN: Local > site > "Open Site Shell" > `which php`, or look under
#   ~/Library/Application Support/Local/lightning-services/php-*/bin/<platform>/bin/php
# - WP_CLI_PHAR: bundled inside Local.app, normally at
#   /Applications/Local.app/Contents/Resources/extraResources/bin/wp-cli/wp-cli.phar
# - SITE_PATH: the site's "app/public" folder, from Local's site details panel
# - DB_SOCKET: ~/Library/Application Support/Local/run/<site-id>/mysql/mysqld.sock
#   — the site id is in ~/Library/Application Support/Local/sites.json
# - MYSQL_BIN_DIR: sibling of PHP_BIN under lightning-services, e.g.
#   .../lightning-services/mysql-*/bin/<platform>/bin

PHP_BIN = "/path/to/php"
WP_CLI_PHAR = "/path/to/wp-cli.phar"
SITE_PATH = "/path/to/site/app/public"
DB_SOCKET = "/path/to/mysqld.sock"
MYSQL_BIN_DIR = "/path/to/mysql/bin"
