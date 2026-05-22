#!/usr/bin/env bash
# Loads MongoDB connection strings from the project .env file for Cursor MCP.
# Usage: run-mongodb-mcp.sh [local|atlas]

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [ -f "$ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

TARGET="${1:-local}"

if [ "$TARGET" = "atlas" ]; then
  export MDB_MCP_CONNECTION_STRING="${ATLAS_MONGODB_URI:-}"
  VAR_NAME="ATLAS_MONGODB_URI"
else
  export MDB_MCP_CONNECTION_STRING="${MONGODB_URI:-mongodb://localhost:27017}"
  VAR_NAME="MONGODB_URI"
fi

if [ "$TARGET" = "atlas" ] && [ -z "$MDB_MCP_CONNECTION_STRING" ]; then
  echo "Error: $VAR_NAME is not set. Add it to $ROOT/.env (see .env.example)." >&2
  exit 1
fi

exec npx -y mongodb-mcp-server@latest
