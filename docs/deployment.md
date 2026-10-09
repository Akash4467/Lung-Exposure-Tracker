# Deployment runbook (AWS, demo environment)

How to take the backend from this repo to `https://<you>.duckdns.org` on AWS, and how to run it after that. Every step is something you run; nothing here happens automatically until you set it up.

## What gets created

```
GitHub push to main
  └─ Actions: tests → build ARM images → GHCR
        └─ deploy job (OIDC, no stored AWS keys)
              ├─ uploads the release bundle to S3 (releases/<sha>.tgz)
              └─ SSM Run Command on the server: deploy.sh <sha>
EC2 t4g.small (ARM, Amazon Linux 2023), Elastic IP, ap-south-1
  ├─ root disk 20 GB (encrypted)    ├─ data disk 10 GB (encrypted, survives the instance) → /data
  └─ Docker Compose: Caddy (HTTPS) → API ×2 · worker · migrate (one-shot) · Postgres+PostGIS · Valkey
AWS around it: SQS ×2 + DLQs · EventBridge Scheduler (hourly tick) · S3 (backups, releases)
               CloudWatch logs (/lung/demo, 14 days) + alarms → email · SSM (config + secrets) · IAM
Off but written: ALB + ACM + Route 53 (needs a real domain), RDS (envs/scale)
```

No SSH port is open. You reach the server with **SSM Session Manager**.

## Cost estimate (ap-south-1, approximate; check the AWS pricing calculator)

| Item | ~USD/month |
| --- | --- |
| EC2 t4g.small (on-demand, 24/7) | ~12 |
| Public IPv4 (Elastic IP) | ~3.6 |
| EBS gp3, 30 GB total | ~2.5 |
| S3, SQS, EventBridge, SSM, CloudWatch (light use) | ~0-2 |
| **Total** | **~18-20**: $100 of credits lasts about 5 months |

Turned off on purpose: NAT gateway (~$32), ALB (~$16-20), RDS (~$15+), ElastiCache (~$12+).

## One-time setup

### 0. You need

- An AWS account and the AWS CLI signed in with an admin user or role (`aws sts get-caller-identity` works).
- OpenTofu 1.10+ (`tofu`), or use Docker: `docker run --rm -it -v "$PWD:/w" -w /w ghcr.io/opentofu/opentofu:1.10 ...`.
- The repo pushed to GitHub.
- A free [DuckDNS](https://www.duckdns.org) account: create a subdomain (e.g. `lung-demo`) and copy your token.

### 1. State bucket (once per AWS account)

```bash
cd infra/bootstrap
tofu init && tofu apply          # note the state_bucket output
```

### 2. The environment

```bash
cd infra/envs/demo
cp demo.tfvars.example demo.tfvars        # git-ignored; set github_repo, domain, alarm_email
tofu init -backend-config="bucket=<state_bucket>"
tofu plan -var-file=demo.tfvars           # read it: about 66 resources, nothing destroyed
tofu apply -var-file=demo.tfvars
tofu output                               # public_ip, instance_id, bucket, deploy_role_arn
```

- If the account already has a GitHub OIDC provider, set `create_github_oidc_provider = false`.
- **`github_repo` must match GitHub's OIDC subject exactly.** Check with `gh api repos/<owner>/<repo>/actions/oidc/customization/sub`: if it says `"use_immutable_subject": true` (new repos), use the IDs form from `sub_claim_prefix`, e.g. `owner@12345/repo@67890`. A mismatch shows in the deploy job as `Not authorized to perform sts:AssumeRoleWithWebIdentity`.
- Confirm the "AWS Notification - Subscription Confirmation" email so alarms reach you.

### 3. Point DuckDNS at the server

On duckdns.org, set your subdomain's IP to `public_ip`. Caddy needs this **before** the first deploy, so it can get the HTTPS certificate. After that, `lung-duckdns.timer` keeps the record current.

### 4. Secrets (SSM SecureStrings, never in git or state)

```bash
AWS_REGION=ap-south-1 deploy/scripts/put-secrets.sh demo
```

It asks for each value. Press Enter to generate (Postgres password, JWT secret) or to keep an existing one.

| Name | Needed? | Notes |
| --- | --- | --- |
| `POSTGRES_PASSWORD` | yes | generate |
| `JWT_SECRET` | yes | generate; 32+ characters, separate from your local one |
| `BREVO_API_KEY`, `MAIL_FROM` | yes | API refuses to start in production without Brevo. Use a **new** key, not one that was ever pasted anywhere |
| `ACME_EMAIL` | yes | Let's Encrypt expiry notices |
| `DUCKDNS_TOKEN` | yes | keeps DNS current |
| `ORS_API_KEY` | optional | real commute routes |
| `GOOGLE_CLIENT_IDS`, `FCM_PROJECT_ID`, FCM service-account JSON | later | layer 5 (app) |
| `GHCR_USER`, `GHCR_TOKEN` | only for private images | a token with `read:packages` |

### 5. GitHub

1. **Settings → Environments → New environment `demo`.** Optionally add yourself as a required reviewer, so every deploy waits for a click.
2. **Settings → Secrets and variables → Actions → Variables**, then add:

| Variable | Value |
| --- | --- |
| `AWS_REGION` | `ap-south-1` |
| `AWS_DEPLOY_ROLE_ARN` | `tofu output deploy_role_arn` |
| `INSTANCE_ID` | `tofu output instance_id` |
| `RELEASE_BUCKET` | `tofu output bucket` |
| `DOMAIN` | e.g. `lung-demo.duckdns.org` |
| `DEPLOY_ENABLED` | `true` (set last) |
| `BUILD_RUNNER` | optional: `ubuntu-24.04-arm` if available to your repo (native ARM builds are much faster than emulation) |

3. After the first build, either make the `lung-api` and `lung-postgres` packages **public** (GitHub → your profile → Packages → package settings), or set `GHCR_USER`/`GHCR_TOKEN` in step 4.

### 6. First deploy

Push to `main` (or **Actions → ci-cd → Run workflow**). The pipeline runs tests → builds images → deploys → checks `https://<domain>/health`. The first deploy takes longest (image pulls and certificate issuance).

## Day-to-day

| Task | How |
| --- | --- |
| Deploy | Merge to `main` |
| Watch a deploy | GitHub Actions log (the server's deploy output is printed there) |
| Logs | CloudWatch → Log groups → `/lung/demo` (one stream per container) |
| Shell on the server | `aws ssm start-session --target <instance_id>`, then `sudo -i; cd /opt/lung/current` |
| Status | `docker compose -p lung -f /opt/lung/current/compose.prod.yml --env-file /opt/lung/.env ps` |
| Roll back | Re-run the workflow for the previous good commit. A failed deploy already rolls itself back to the previous release |
| Change a secret | `put-secrets.sh demo`, then redeploy (re-run the latest workflow) |
| Backups | Nightly at 02:00 IST to `s3://<bucket>/postgres/YYYY/MM/DD/`. Kept 30 days, plus 7 days of overwritten versions |
| Back up now | On the server: `bash /opt/lung/current/scripts/backup.sh` |
| Restore | On the server: `bash /opt/lung/current/scripts/restore.sh latest --yes` (stops API/worker, restores, starts them) |
| Failed jobs | A message in `lung-demo-*-dlq` fires an alarm email. Inspect it in the SQS console and redrive after fixing |

### What a deploy does (`deploy/scripts/deploy.sh`)

1. Renders `/opt/lung/.env` (mode 600) from SSM `/lung/demo/*`.
2. Pulls the images tagged with the commit.
3. `up --wait`: Postgres healthy → **migrations** (one-shot) → API ×2 and worker healthy → Caddy.
4. If anything stays unhealthy, it prints the logs and **starts the previous release again**.
5. Points `/opt/lung/current` at the release, installs the backup and DuckDNS timers, keeps the 5 newest releases and prunes old images.

During a deploy, Caddy holds requests until a new API replica is up. Locally we measured **0 failed requests out of 272**, with the slowest waiting 11 s.

### Health signals

| Signal | Meaning |
| --- | --- |
| `GET /health` (public) | API process is up |
| `GET /status` (public) | API up **and** air data fresh: `{"status":"ok","air_age_min":27}`; 503 `stale` if no area was fetched for 2.5 h, `unavailable` if the database is down. Nothing about users; cached 1 min |
| `/ready` | Not exposed publicly; the server's own deep check (DB, cache, queue) |
| Worker health check | Heartbeat file touched every poll; unhealthy if stale over 2 min |
| Infra alarms | DLQ not empty · EC2 system check (auto-recover) · instance check (auto-reboot) · CPU > 80% · CPU credits < 20 |
| App alarms | **api-5xx** (≥ 5 server errors in 5 min) · **air-data-stale** (no air fetched for 2 h; silence counts) · **jobs-failing** (> 10 failed jobs in an hour) |
| Uptime check | GitHub Action `uptime.yml` calls `/status` every 15 min from outside AWS; a failed run emails you. Set the repo variable `STATUS_URL` to turn it on |
| Dashboard | CloudWatch → Dashboards → `lung-demo`: requests and 5xx, response time, areas fetched and alerts sent, failures, queue backlog, CPU, and a table of warnings and errors by event |

### Metrics (from the logs, no agent)

CloudWatch metric filters on `/lung/demo` turn the app's JSON log lines into metrics in the `Lung/demo` namespace (`infra/modules/monitoring/app.tf`):

| Metric | Log line |
| --- | --- |
| `ApiRequests`, `Api5xx`, `ApiLatencyMs` | `event = request` (status, ms) |
| `AirFetched` | `event = fetched` (one per area per hour) |
| `JobFailed` | `event = job_failed` |
| `UpstreamFailed` | `openaq_failed`, `cpcb_failed`, geocoder failures, `fcm_send_failed`, `email_send_failed`, route fallbacks |
| `AlertsSent` | `event = alert_sent` |

All within the free tier: 7 of 10 custom metrics, 9 of 10 alarms (with 2 DLQs), 1 of 3 dashboards. Renaming one of these log events breaks its metric: `tests/alarms.tftest.hcl` checks the patterns.

### When an alarm emails you

| Alarm | First look |
| --- | --- |
| air-data-stale | `/status` age; worker container healthy? Logs: `event = tick` each hour, then `fetched`. Open-Meteo reachable from the server? |
| api-5xx | Dashboard log table, then Logs Insights: `filter level = "error" \| sort @timestamp desc` |
| jobs-failing | Logs: `event = job_failed` (stack traces included); the DLQ fills after 5 tries |
| uptime (GitHub) | Is the instance running? `/health` vs `/status`: up but stale is the worker; nothing at all is Caddy, DNS (DuckDNS) or the certificate |

## Security summary

- Ports 80/443 only. No SSH; Session Manager is audited in CloudTrail.
- IMDSv2 required. Encrypted disks and bucket. The bucket blocks public access and denies non-TLS requests.
- Secrets live only in SSM SecureStrings and a root-only `.env` on the server, never in git, images, tfstate or GitHub.
- GitHub deploys through OIDC, limited to this repo's `demo` environment. The role can only upload releases and run the stock shell document on instances tagged `lung-env=demo`.
- The instance role is scoped to its own queues, bucket prefixes, `/lung/demo/*` parameters and its log group.
- `make infra-check` / CI run `tofu test` assertions that keep these properties from regressing.

## Moving up later (`infra/envs/scale`)

When there's a real domain and more users: buy a domain into Route 53, then apply `envs/scale`. That switches on the ALB + ACM (TLS at the ALB; Caddy serves `:80`, `TLS_MODE=alb`) and RDS (restore the latest dump into it, then point `DATABASE_URL` at it). Roughly +$35-45/month.

## Tearing it down

```bash
# 1. Last backup: bash /opt/lung/current/scripts/backup.sh (on the server)
# 2. In infra/modules/compute: set protect = false (or protect_instance = false), and remove
#    prevent_destroy from the data volume. Both are there so nobody deletes the database by accident.
cd infra/envs/demo && tofu apply -var-file=demo.tfvars && tofu destroy -var-file=demo.tfvars
# 3. The S3 bucket must be emptied first (versioned): aws s3 rm s3://<bucket> --recursive, plus old versions
```
