#!/usr/bin/env bash
set -euo pipefail

# Prefer prod/dev compose if you have them, else fallback to docker-compose.yaml
if [[ -f "compose/docker-compose.dev.yml" ]]; then
  COMPOSE="docker compose -f compose/docker-compose.dev.yml"
elif [[ -f "docker-compose.yaml" ]]; then
  COMPOSE="docker compose -f docker-compose.yaml"
elif [[ -f "docker-compose.yml" ]]; then
  COMPOSE="docker compose -f docker-compose.yml"
else
  echo "No compose file found."
  exit 1
fi

echo "Starting services..."
$COMPOSE up -d

echo "Services status:"
$COMPOSE ps
