#!/usr/bin/env bash
# Server-side deploy, run by .github/workflows/deploy.yml (or by hand) from the deploy checkout:
#   APP_VERSION=<tag-or-sha> bash infra/deploy/deploy.sh
#
# Steps: back up Postgres → build images → start/replace containers (the API applies migrations on
# start) → wait for the API to be healthy → register the Telegram webhook → load LLM prices →
# make sure the Grafana read-only role exists → smoke test → prune old images.
# Everything is idempotent: running it twice in a row is safe.
set -euo pipefail

cd "$(dirname "$0")/../.."
ENV_FILE=infra/.env.prod
[ -f "$ENV_FILE" ] || { echo "error: $ENV_FILE is missing (see docs/deployment.md §3)" >&2; exit 1; }

export APP_VERSION="${APP_VERSION:-0.1.0}"
DC=(docker compose -f infra/compose.prod.yml --env-file "$ENV_FILE")
KEEP_BACKUPS=5

# Reads one KEY=value line from the env file (no shell expansion of the values).
env_value() { sed -n "s/^$1=//p" "$ENV_FILE" | tail -n1 | tr -d '"'"'"' \r'; }

log() { printf '\n==> %s\n' "$*"; }

log "Backing up the database (if running)"
if [ -n "$("${DC[@]}" ps -q --status running postgres 2>/dev/null)" ]; then
  mkdir -p backups
  backup="backups/pre-deploy-$(date +%Y%m%d-%H%M%S).sql.gz"
  "${DC[@]}" exec -T postgres pg_dump -U kainem kainem | gzip > "$backup"
  echo "wrote $backup ($(du -h "$backup" | cut -f1))"
  # shellcheck disable=SC2012
  ls -1t backups/pre-deploy-*.sql.gz 2>/dev/null | tail -n +"$((KEEP_BACKUPS + 1))" | xargs -r rm -f --
else
  echo "postgres is not running yet: first deploy, nothing to back up"
fi

log "Building images for version $APP_VERSION"
"${DC[@]}" build --pull

log "Starting services"
"${DC[@]}" up -d --remove-orphans

log "Waiting for the API (migrations run on start)"
api_id=""
for _ in $(seq 1 60); do
  api_id=$("${DC[@]}" ps -q api 2>/dev/null || true)
  status=$([ -n "$api_id" ] && docker inspect --format '{{.State.Health.Status}}' "$api_id" 2>/dev/null || echo starting)
  case "$status" in
    healthy) break ;;
    unhealthy)
      echo "error: the API is unhealthy" >&2
      "${DC[@]}" logs --tail 100 api >&2
      exit 1 ;;
  esac
  sleep 5
done
if [ "${status:-}" != "healthy" ]; then
  echo "error: the API did not become healthy in time" >&2
  "${DC[@]}" logs --tail 100 api >&2
  exit 1
fi
echo "api is healthy"

log "Pointing the Telegram webhook at PUBLIC_APP_URL"
"${DC[@]}" exec -T api python -m planner.cli set-webhook

log "Loading LLM price fallback"
"${DC[@]}" exec -T api python -m planner.cli prices-sync --file prices/cloudru-2026-09-30.yaml \
  || echo "warning: prices-sync failed; proxy-reported cost still works" >&2

log "Checking configured LLM models on the proxy"
"${DC[@]}" exec -T api python -m planner.cli check-models \
  || echo "warning: a configured model is missing on the proxy; pick another via LLM_MODEL_* (readyz reports it)" >&2

log "Grafana read-only database role"
grafana_pw=$(env_value GRAFANA_PG_PASSWORD)
if [ -n "$grafana_pw" ]; then
  psql=("${DC[@]}" exec -T postgres psql -U kainem -d kainem -v ON_ERROR_STOP=1)
  if [ "$("${psql[@]}" -tAc "SELECT 1 FROM pg_roles WHERE rolname = 'grafana_reader'")" = "1" ]; then
    # The role exists: only re-grant, so views added by new migrations are readable.
    "${psql[@]}" -q <<'SQL'
DO $$
DECLARE v record;
BEGIN
    FOR v IN SELECT table_name FROM information_schema.views
             WHERE table_schema = 'public' AND table_name LIKE 'metrics_%' LOOP
        EXECUTE format('GRANT SELECT ON %I TO grafana_reader', v.table_name);
    END LOOP;
END $$;
SQL
    echo "grafana_reader exists; grants refreshed"
  else
    "${psql[@]}" -q -v password="$grafana_pw" < infra/postgres/grafana-reader.sql
    "${DC[@]}" restart grafana
    echo "grafana_reader created"
  fi
else
  echo "GRAFANA_PG_PASSWORD not set; skipping"
fi

log "Smoke test"
domain=$(env_value DOMAIN)
if [ -n "$domain" ]; then
  # First start: Caddy needs DNS to point here and ports 80/443 open to get its certificate.
  if curl -fsS --retry 12 --retry-delay 5 --retry-all-errors "https://$domain/api/readyz"; then
    echo
  else
    echo "error: https://$domain/api/readyz is not reachable. DNS not pointing at this VM, or 80/443 closed?" >&2
    "${DC[@]}" logs --tail 50 caddy >&2
    exit 1
  fi
fi

log "Pruning dangling images"
docker image prune -f > /dev/null

log "Deployed $APP_VERSION"
"${DC[@]}" ps
