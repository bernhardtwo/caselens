#!/usr/bin/env bash
# Provision CaseLens on Azure Container Apps against an external Postgres (Neon) (spec-0005, ADR-0004).
# This does NOT build or push images; see docs/deploy/azure.md for the full runbook.
# The bootstrap (init-db + ingest + seed) is idempotent; the Container Apps creates are not, so to
# start over run: az group delete --name "$RG".
set -euo pipefail

# ---- Parameters (override via environment) ----
RG="${RG:-caselens-rg}"
LOCATION="${LOCATION:-centralus}"         # region of the shared ACA environment
ACA_ENV="${ACA_ENV:-ledgerlens-env}"      # existing shared environment to reuse
ACA_ENV_RG="${ACA_ENV_RG:-rg-ledgerlens}" # resource group that owns ACA_ENV
API_APP="${API_APP:-caselens-api}"
WEB_APP="${WEB_APP:-caselens-web}"
BOOTSTRAP_JOB="${BOOTSTRAP_JOB:-caselens-bootstrap}"
API_IMAGE="${API_IMAGE:-ghcr.io/bernhardtwo/caselens-api:latest}"
WEB_IMAGE="${WEB_IMAGE:-ghcr.io/bernhardtwo/caselens-web:latest}"

# ---- Required secrets (export before running) ----
: "${CO_API_KEY:?export CO_API_KEY (your Cohere key)}"
: "${DATABASE_URL:?export DATABASE_URL (your Neon connection string)}"
ACCESS_TOKEN="${ACCESS_TOKEN:-}"       # optional; empty leaves the demo access gate off

echo "==> Registering providers and the containerapp extension"
az extension add --name containerapp --upgrade --only-show-errors
az provider register --namespace Microsoft.App --wait
az provider register --namespace Microsoft.OperationalInsights --wait

echo "==> Resource group: $RG ($LOCATION)"
az group create --name "$RG" --location "$LOCATION" --only-show-errors >/dev/null

echo "==> Reusing shared Container Apps environment: $ACA_ENV (in $ACA_ENV_RG)"
# Reference the existing environment by resource ID so the apps can live in their own RG ($RG)
# while sharing an environment that lives elsewhere.
ENV_ID=$(az containerapp env show --name "$ACA_ENV" --resource-group "$ACA_ENV_RG" --query id -o tsv)

echo "==> API app (internal ingress, port 8000): $API_APP"
# Public ghcr images need no registry credentials. The gate secret is set only when ACCESS_TOKEN
# is non-empty, otherwise the API runs open.
API_SECRETS=("co-api-key=$CO_API_KEY" "database-url=$DATABASE_URL")
API_ENV=("CO_API_KEY=secretref:co-api-key" "DATABASE_URL=secretref:database-url")
if [ -n "$ACCESS_TOKEN" ]; then
  API_SECRETS+=("access-token=$ACCESS_TOKEN")
  API_ENV+=("ACCESS_TOKEN=secretref:access-token")
fi
# Idempotent: create each app/job only if it does not already exist. ponytail: create-or-skip,
# not create-or-update — to change an existing spec, tear down $RG (footer) and re-run.
if az containerapp show --resource-group "$RG" --name "$API_APP" --only-show-errors >/dev/null 2>&1; then
  echo "    $API_APP already exists, skipping create"
else
  az containerapp create \
    --resource-group "$RG" --name "$API_APP" --environment "$ENV_ID" \
    --image "$API_IMAGE" \
    --ingress internal --target-port 8000 --transport http \
    --min-replicas 0 --max-replicas 1 --cpu 0.5 --memory 1.0Gi \
    --secrets "${API_SECRETS[@]}" \
    --env-vars "${API_ENV[@]}" --only-show-errors >/dev/null
fi

API_FQDN=$(az containerapp show --resource-group "$RG" --name "$API_APP" \
  --query properties.configuration.ingress.fqdn -o tsv)
echo "    API internal FQDN: $API_FQDN"

echo "==> Web app (external ingress, port 3000): $WEB_APP"
if az containerapp show --resource-group "$RG" --name "$WEB_APP" --only-show-errors >/dev/null 2>&1; then
  echo "    $WEB_APP already exists, skipping create"
else
  az containerapp create \
    --resource-group "$RG" --name "$WEB_APP" --environment "$ENV_ID" \
    --image "$WEB_IMAGE" \
    --ingress external --target-port 3000 \
    --min-replicas 0 --max-replicas 1 --cpu 0.5 --memory 1.0Gi \
    --env-vars "API_INTERNAL_URL=https://$API_FQDN" --only-show-errors >/dev/null
fi

echo "==> Bootstrap job (run-to-completion): $BOOTSTRAP_JOB"
if az containerapp job show --resource-group "$RG" --name "$BOOTSTRAP_JOB" --only-show-errors >/dev/null 2>&1; then
  echo "    $BOOTSTRAP_JOB already exists, skipping create"
else
  az containerapp job create \
    --resource-group "$RG" --name "$BOOTSTRAP_JOB" --environment "$ENV_ID" \
    --image "$API_IMAGE" \
    --trigger-type Manual \
    --replica-timeout 1800 --replica-retry-limit 1 \
    --replica-completion-count 1 --parallelism 1 \
    --cpu 0.5 --memory 1.0Gi \
    --secrets "co-api-key=$CO_API_KEY" "database-url=$DATABASE_URL" \
    --env-vars "CO_API_KEY=secretref:co-api-key" "DATABASE_URL=secretref:database-url" \
    --command "caselens-bootstrap" \
    --only-show-errors >/dev/null
fi

echo "==> Starting the bootstrap job"
az containerapp job start --resource-group "$RG" --name "$BOOTSTRAP_JOB" --only-show-errors >/dev/null

WEB_FQDN=$(az containerapp show --resource-group "$RG" --name "$WEB_APP" \
  --query properties.configuration.ingress.fqdn -o tsv)

echo
echo "Done. Public console: https://$WEB_FQDN"
echo "The bootstrap runs once in the background. Check it with:"
echo "  az containerapp job execution list -g \"$RG\" --name \"$BOOTSTRAP_JOB\" -o table"
echo "Tear CaseLens down (stop billing) with — leaves the shared $ACA_ENV environment intact:"
echo "  az group delete --name \"$RG\" --yes --no-wait"
