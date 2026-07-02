#!/bin/zsh

set -euo pipefail

context_mode_bin="$(command -v context-mode)"
context_mode_target="$(python3 - <<'PY' "$context_mode_bin"
import pathlib
import sys

print(pathlib.Path(sys.argv[1]).resolve())
PY
)"
package_root="$(cd "$(dirname "$context_mode_target")" && pwd)"

check_binding() {
  node - <<'NODE' "$package_root"
const path = require('node:path');

const packageRoot = process.argv[2];
const bindingPath = path.join(packageRoot, 'node_modules', 'better-sqlite3');

try {
  require(bindingPath);
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  if (
    message.includes('NODE_MODULE_VERSION') ||
    message.includes('compiled against a different Node.js version') ||
    message.includes('Cannot find module') ||
    message.includes('MODULE_NOT_FOUND')
  ) {
    process.exit(42);
  }
  throw error;
}
NODE
}

if check_binding; then
  :
else
  status=$?
  if [[ "$status" -ne 42 ]]; then
    exit "$status"
  fi

  (
    cd "$package_root"
    npm rebuild better-sqlite3
  ) >&2
fi

exec "$context_mode_bin" "$@"
