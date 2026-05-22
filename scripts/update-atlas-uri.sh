#!/usr/bin/env bash
# Update Atlas URI in local .env and platform team_settings after rotating the password.
# Usage: ./scripts/update-atlas-uri.sh 'mongodb+srv://user:pass@cluster.mongodb.net/'

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
URI="${1:-}"

if [ -z "$URI" ]; then
  echo "Usage: $0 'mongodb+srv://user:password@cluster.mongodb.net/'" >&2
  exit 1
fi

AGENT_ID="10948768-5eb6-4d9e-a432-51796998697a"

# Update .env
ENV_FILE="$ROOT/.env"
touch "$ENV_FILE"
if grep -q '^ATLAS_MONGODB_URI=' "$ENV_FILE"; then
  sed -i '' "s|^ATLAS_MONGODB_URI=.*|ATLAS_MONGODB_URI=$URI|" "$ENV_FILE"
else
  echo "ATLAS_MONGODB_URI=$URI" >> "$ENV_FILE"
fi

# Update team_settings in local MongoDB
mongosh --quiet "mongodb://localhost:27017/agent_platform" --eval "
  db.team_settings.updateOne(
    { _id: '$AGENT_ID' },
    { \$set: { 'integration_keys.ATLAS_MONGODB_URI': '$URI', updated_at: new Date() } }
  )
"

echo "Updated ATLAS_MONGODB_URI in .env and team_settings for agent $AGENT_ID"
echo "Restart Cursor (MCP) and refresh the Trip agent Settings tab if the platform is running."
