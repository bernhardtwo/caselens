#!/usr/bin/env bash
# Provision CaseLens on Azure Container Apps + PostgreSQL Flexible Server (spec-0005, ADR-0004).
# This does NOT build or push images; see docs/deploy/azure.md for the full runbook.
# The bootstrap (init-db + ingest + seed) is idempotent; the az resource creates are not, so to
# start over run: az group delete --name "$RG".
set -euo pipefail

# ---- Parameters (override via environment) ----
RG="${RG:-caselens-rg}"
LOCATION="${LOCATION:-eastus}"
ACA_ENV="${ACA_ENV:-caselens-env}"
API_APP="${API_APP:-caselens-api}"
WEB_APP="${WEB_APP:-caselens-web}"
BOOTSTRAP_JOB="${BOOTSTRAP_JOB:-caselens-bootstrap}"
API_IMAGE="${API_IMAGE:-ghcr.io/bernhardtwo/caselens-api:latest}"
WEB_IMAGE="${WEB_IMAGE:-ghcr.io/bernhardtwo/caselens-web:latest}"

PG_SERVER="${PG_SERVER:-caselens-pg}"   # must be globally unique; override if the name is taken
PG_DB="${PG_DB:-caselens}"
PG_ADMIN_USER="${PG_ADMIN_USER:-caselens}"
PG_VERSION="${PG_VERSION:-16}"

# ---- Required secrets (export before running) ----
: "${CO_API_KEY:?export CO_API_KEY (your Cohere key)}"
: "${PG_ADMIN_PASSWORD:?export PG_ADMIN_PASSWORD (a strong Postgres admin password)}"
ACCESS_TOKEN="${ACCESS_TOKEN:-}"       # optional; empty leaves the demo access gate off
ALLOW_CLIENT_IP="${ALLOW_CLIENT_IP:-}" # optional; your public IP, only if you bootstrap locally

PG_FQDN="${PG_SERVER}.postgres.database.azure.com"
DATABASE_URL="postgresql://${PG_ADMIN_USER}:${PG_ADMIN_PASSWORD}@${PG_FQDN}:5432/${PG_DB}?sslmode=require"

echo "==> Registering providers and the containerapp extension"
az extension add --name containerapp --upgrade --only-show-errors
az provider register --namespace Microsoft.App --wait
az provider register --namespace Microsoft.OperationalInsights --wait
az provider register --namespace Microsoft.DBforPostgreSQL --wait

echo "==> Resource group: $RG ($LOCATION)"
az group create --name "$RG" --location "$LOCATION" --only-show-errors >/dev/null

echo "==> PostgreSQL Flexible Server: $PG_SERVER (Burstable B1ms, v$PG_VERSION)"
az postgres flexible-server create \
  --resource-group "$RG" --name "$PG_SERVER" --location "$LOCATION" \
  --tier Burstable --sku-name Standard_B1ms --version "$PG_VERSION" \
  --storage-size 32 \
  --admin-user "$PG_ADMIN_USER" --admin-password "$PG_ADMIN_PASSWORD" \
  --database-name "$PG_DB" \
  --public-access None --yes --only-show-errors

echo "==> Allowlisting pgvector (azure.extensions = vector)"
az postgres flexible-server parameter set \
  --resource-group "$RG" --server-name "$PG_SERVER" \
  --name azure.extensions --value vector --only-show-errors >/dev/null

echo "==> Firewall: allow Azure services (the 0.0.0.0 rule)"
az postgres flexible-server firewall-rule create \
  --resource-group "$RG" --name "$PG_SERVER" \
  --rule-name AllowAzureServices \
  --start-ip-address 0.0.0.0 --end-ip-address 0.0.0.0 --only-show-errors >/dev/null

if [ -n "$ALLOW_CLIENT_IP" ]; then
  echo "==> Firewall: allow client IP $ALLOW_CLIENT_IP (for a local bootstrap run)"
  az postgres flexible-server firewall-rule create \
    --resource-group "$RG" --name "$PG_SERVER" \
    --rule-name AllowClientIP \
    --start-ip-address "$ALLOW_CLIENT_IP" --end-ip-address "$ALLOW_CLIENT_IP" --only-show-errors >/dev/null
fi

echo "==> Container Apps environment: $ACA_ENV"
az containerapp env create \
  --resource-group "$RG" --name "$ACA_ENV" --location "$LOCATION" --only-show-errors >/dev/null

echo "==> API app (internal ingress, port 8000): $API_APP"
# Public ghcr images need no registry credentials. The gate secret is set only when ACCESS_TOKEN
# is non-empty, otherwise the API runs open.
API_SECRETS=("co-api-key=$CO_API_KEY" "database-url=$DATABASE_URL")
API_ENV=("CO_API_KEY=secretref:co-api-key" "DATABASE_URL=secretref:database-url")
if [ -n "$ACCESS_TOKEN" ]; then
  API_SECRETS+=("access-token=$ACCESS_TOKEN")
  API_ENV+=("ACCESS_TOKEN=secretref:access-token")
fi
az containerapp create \
  --resource-group "$RG" --name "$API_APP" --environment "$ACA_ENV" \
  --image "$API_IMAGE" \
  --ingress internal --target-port 8000 --transport http \
  --min-replicas 0 --max-replicas 1 --cpu 0.5 --memory 1.0Gi \
  --secrets "${API_SECRETS[@]}" \
  --env-vars "${API_ENV[@]}" --only-show-errors >/dev/null

API_FQDN=$(az containerapp show --resource-group "$RG" --name "$API_APP" \
  --query properties.configuration.ingress.fqdn -o tsv)
echo "    API internal FQDN: $API_FQDN"

echo "==> Web app (external ingress, port 3000): $WEB_APP"
az containerapp create \
  --resource-group "$RG" --name "$WEB_APP" --environment "$ACA_ENV" \
  --image "$WEB_IMAGE" \
  --ingress external --target-port 3000 \
  --min-replicas 0 --max-replicas 1 --cpu 0.5 --memory 1.0Gi \
  --env-vars "API_INTERNAL_URL=https://$API_FQDN" --only-show-errors >/dev/null

echo "==> Bootstrap job (run-to-completion): $BOOTSTRAP_JOB"
az containerapp job create \
  --resource-group "$RG" --name "$BOOTSTRAP_JOB" --environment "$ACA_ENV" \
  --image "$API_IMAGE" \
  --trigger-type Manual \
  --replica-timeout 1800 --replica-retry-limit 1 \
  --replica-completion-count 1 --parallelism 1 \
  --cpu 0.5 --memory 1.0Gi \
  --secrets "co-api-key=$CO_API_KEY" "database-url=$DATABASE_URL" \
  --env-vars "CO_API_KEY=secretref:co-api-key" "DATABASE_URL=secretref:database-url" \
  --command "/bin/sh" "-c" \
  "set -e; until caselens-rag init-db; do echo 'waiting for postgres'; sleep 3; done; caselens-rag ingest; caselens-seed" \
  --only-show-errors >/dev/null

echo "==> Starting the bootstrap job"
az containerapp job start --resource-group "$RG" --name "$BOOTSTRAP_JOB" --only-show-errors >/dev/null

WEB_FQDN=$(az containerapp show --resource-group "$RG" --name "$WEB_APP" \
  --query properties.configuration.ingress.fqdn -o tsv)

echo
echo "Done. Public console: https://$WEB_FQDN"
echo "The bootstrap runs once in the background. Check it with:"
echo "  az containerapp job execution list -g \"$RG\" --name \"$BOOTSTRAP_JOB\" -o table"
echo "Tear everything down (stop billing) with:"
echo "  az group delete --name \"$RG\" --yes --no-wait"
