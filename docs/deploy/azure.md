# Deploy to Azure Container Apps

Runbook for hosting CaseLens on Azure (spec-0005, ADR-0004). It provisions one Azure Container Apps
environment with two apps (a public web and an internal API), an Azure Database for PostgreSQL
Flexible Server with pgvector, and a one-shot bootstrap that loads the schema, corpus, and seed data.
Run the steps yourself; the script never runs automatically.

```
Browser  ->  caselens-web (ACA, external ingress :3000)
                 |  same-origin /api proxy -> API_INTERNAL_URL
                 v
             caselens-api (ACA, internal ingress :8000)  ->  PostgreSQL Flexible Server (pgvector)
                 ^
             caselens-bootstrap (ACA job, run once) -------/
```

Images live on the GitHub Container Registry as public packages, so Azure pulls them with no
registry credentials:

- `ghcr.io/bernhardtwo/caselens-api:latest`
- `ghcr.io/bernhardtwo/caselens-web:latest`

## Prerequisites

- Azure CLI (`az`) and an Azure subscription with quota for Container Apps and PostgreSQL.
- Docker (to build and push the images).
- A GitHub Personal Access Token (classic) with `write:packages`, for pushing to ghcr.
- A Cohere API key (`CO_API_KEY`).

```bash
az login
az account set --subscription "<your-subscription-id>"   # if you have more than one
```

## 1. Build and push the images to ghcr

Azure Container Apps runs `linux/amd64`, so build for that platform explicitly.

```bash
cd /home/bernard/projects/caselens

echo "$GHCR_PAT" | docker login ghcr.io -u bernhardtwo --password-stdin

# API build context is the repo root (it ships data/corpus for the bootstrap ingest).
docker build --platform linux/amd64 -f apps/api/Dockerfile -t ghcr.io/bernhardtwo/caselens-api:latest .
# Web build context is apps/web.
docker build --platform linux/amd64 -f apps/web/Dockerfile -t ghcr.io/bernhardtwo/caselens-web:latest apps/web

docker push ghcr.io/bernhardtwo/caselens-api:latest
docker push ghcr.io/bernhardtwo/caselens-web:latest
```

New ghcr packages are private by default. Make both public so Azure can pull them anonymously:
GitHub profile -> Packages -> `caselens-api` -> Package settings -> Danger Zone -> Change
visibility -> Public, then repeat for `caselens-web`. (If you prefer to keep them private, see
"Private images" at the end.)

## 2. Provision Azure and trigger the bootstrap

Export the required values and run the script. Optional overrides (`RG`, `LOCATION`, `PG_SERVER`,
`ACCESS_TOKEN`, etc.) are read from the environment; see the top of the script.

```bash
export CO_API_KEY="<your-cohere-key>"
export PG_ADMIN_PASSWORD="<a-strong-password>"   # 8-128 chars, 3 of: upper, lower, digit, symbol
export ACCESS_TOKEN="<demo-token>"               # optional; omit to run the demo open
# export PG_SERVER="caselens-pg-bv"              # set a globally-unique name if the default is taken

bash infra/deploy/azure-deploy.sh
```

The script provisions, in order: the resource group, the Postgres Flexible Server (Burstable B1ms,
v16), the pgvector allowlist (`azure.extensions=vector`) and the "allow Azure services" firewall
rule, the Container Apps environment, the internal API app and the public web app (with their
secrets), and finally the bootstrap job, which it starts. It prints the public console URL at the end.

`ACCESS_TOKEN`, `CO_API_KEY`, and `DATABASE_URL` are stored as ACA secrets and referenced as env
vars (`secretref:`), never baked into the images. The web only receives `API_INTERNAL_URL`, pointing
at the API's internal FQDN.

## 3. Verify the bootstrap

The bootstrap job runs `init-db` (retried until Postgres answers), then `ingest`, then `seed`, all
idempotent, so re-running it never duplicates data.

```bash
az containerapp job execution list -g caselens-rg --name caselens-bootstrap -o table
# Expect the latest execution to reach "Succeeded". To read its logs (container name == job name):
az containerapp job logs show -g caselens-rg --name caselens-bootstrap \
  --container caselens-bootstrap --execution <execution-name>
```

To re-run it later (for example after a redeploy):

```bash
az containerapp job start -g caselens-rg --name caselens-bootstrap
```

## 4. Open the console and check secrets

```bash
# Public URL:
az containerapp show -g caselens-rg -n caselens-web \
  --query properties.configuration.ingress.fqdn -o tsv
# -> open https://<that-fqdn>

# Secret names on the API (values stay hidden):
az containerapp secret list -g caselens-rg -n caselens-api -o table
```

If you set `ACCESS_TOKEN`, the console asks for it once; paste the same token. The first request
may cold-start the apps (they scale to zero when idle). The tenant/role switcher remains the in-app
control once you are in.

## 5. Tear everything down

Delete the whole resource group when done so nothing keeps billing:

```bash
az group delete --name caselens-rg --yes --no-wait
```

## Cloud-agnostic note

The same two images run unchanged on Google Cloud Run with Cloud SQL for PostgreSQL (pgvector
enabled): point `DATABASE_URL` at the Cloud SQL instance, deploy `caselens-api` and `caselens-web`
as Cloud Run services, and run the bootstrap as a Cloud Run Job. The container, not the cloud, is
the unit of delivery.

## Private images (alternative)

If you keep the ghcr packages private, give each app registry credentials instead of making them
public:

```bash
az containerapp registry set -g caselens-rg -n caselens-api \
  --server ghcr.io --username bernhardtwo --password "$GHCR_PAT"
az containerapp registry set -g caselens-rg -n caselens-web \
  --server ghcr.io --username bernhardtwo --password "$GHCR_PAT"
```
