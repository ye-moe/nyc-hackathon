#!/bin/sh
# Start a private Chrome for jev: its own empty profile (none of your logins),
# no window, remote debugging on JEV_CHROME_PORT (default 9333). Leave it running.
PORT="${JEV_CHROME_PORT:-9333}"
exec "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new \
  --remote-debugging-port="$PORT" --user-data-dir="${TMPDIR:-/tmp}/jev-chrome" \
  --no-first-run --no-default-browser-check about:blank
