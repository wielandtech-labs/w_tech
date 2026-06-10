# AGENTS.md — deployment & conventions for the WielandTech website

This repository builds the website image; the deployment manifests live in
`wielandtech-labs/w_homelab` under `clusters/{dev,qa,prod}/apps/website/`.
App development setup is in the README — this file covers how changes ship.

## Image tags drive deployments

`.github/workflows/docker-build.yml` publishes to
`ghcr.io/wielandtech-labs/w_tech`:

| Event | Tag | Deploys to |
|---|---|---|
| Push to `main` | `YYYYMMDD-HHMMSS-<shortsha>` | **Production** — https://wielandtech.com (via Flux image automation + `flux/image-updates/prod` fast-forward) |
| Push to any other branch | `dev-YYYYMMDD-HHMMSS-<shortsha>` | **Dev** — https://dev.wielandtech.com (auto-tracks newest dev tag) |
| Same-repo pull request | `pr-<number>-<shortsha>` | **Review app** — https://pr-<number>.review.wielandtech.com |

Never change these tag formats — Flux ImagePolicies and the review-app
automation parse them.

**Merging to `main` IS a production deploy.** Merge only after the change was
verified on its review app or in dev/QA, and run `/code-review` first.

## Promotion ladder

1. Open a PR → a `chore(review): deploy website pr-N` PR appears in w_homelab;
   merge it to deploy the review app. Closing the PR triggers cleanup.
2. Merge/push a branch → dev auto-deploys the newest `dev-*` tag.
3. Promote to QA (https://qa.wielandtech.com) — never hand-edit
   `clusters/qa/**` tags:
   ```bash
   gh workflow run promote.yaml -R wielandtech-labs/w_homelab -f app=website -f to_env=qa
   ```
4. Merge to `main` → prod. Post-merge deploy verification in w_homelab gates
   the rollout.

Rollback = revert the environment's HelmRelease image tag in w_homelab via PR
(or re-promote a known-good tag for QA).

## Build & infra notes

- Builds run on the shared org runner pool (`runs-on: homelab-dind`) with
  buildx `driver: remote` against the in-cluster buildkitd — there is no
  local Docker daemon, so `docker run` and service containers do NOT work.
- The review-app dispatch still sends the legacy `w-tech-review-app` event;
  the homelab workflow supports it (defaults to `app=website`). The generic
  successor is `event_type: review-app` with `app` in the payload — migrate
  when convenient.
- Secrets (Django key, DB, OAuth, email) are SealedSecrets in w_homelab —
  never commit secrets or `.env` files here.
- Environment docs: `docs/onboarding-new-app.md` and `AGENTS.md` in
  `wielandtech-labs/w_homelab`.
