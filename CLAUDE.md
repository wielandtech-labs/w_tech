# CLAUDE.md

Django 5 portfolio/blog site (`wielandtech.com`). Dev setup and project
structure are in the README.

**Deployment-critical:** merging to `main` publishes a prod-format image tag,
which Flux auto-deploys to production. Verify changes on the PR's review app
(`https://pr-<n>.review.wielandtech.com`) or in dev/QA before merging, and
run `/code-review` on the diff. Full tag scheme, promotion ladder, and infra
notes: see `AGENTS.md` in this repo; deployment manifests live in
`wielandtech-labs/w_homelab` under `clusters/{dev,qa,prod}/apps/website/`.
