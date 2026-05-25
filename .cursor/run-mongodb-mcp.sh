#!/usr/bin/env bash
# Loads MongoDB connection string from the project .env file for Cursor MCP.
# Default: mongodb://127.0.0.1:55440/?directConnection=true

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [ -f "$ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

export MDB_MCP_CONNECTION_STRING="${ATLAS_MONGODB_URI:-${MONGODB_URI:-mongodb://127.0.0.1:55440/?directConnection=true}}"

exec npx -y mongodb-mcp-server@latest
