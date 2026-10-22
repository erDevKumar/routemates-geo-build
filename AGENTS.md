# routemates-geo-build: agent rules

Infra spec: `Routemates PRD/infra/` (index `00_infrastructure_stack_index.md`). PRD: `Routemates PRD/prd/`.

## Binding (security, every layer)
- Before designing or writing anything, read `docs/rules/security/00_index.md` and the S-files it routes you to. Apply its checklist to every PR.
- Ask of every feature: **what can a logged-in, fully authorised trip member do to another member with this?**
- A deviation from an S-rule needs a row naming the rule, the reason and the revisit trigger. Never omit it silently.
- A new lesson that changes a rule gets a dated edit upstream (PRD repo / Global Workspace), then `scripts/sync-rules.sh`.

## Repo rules
- No secrets in git. Only SOPS ciphertext (`*.enc.*`). gitleaks runs in CI.
- Legacy V2 repos (`RouteMates`, `RMatesBESBoot`) are reference only. Take the useful parts, the PRD wins, and never copy V2 secrets.

- **Branch rule (user, standing until changed, 2026-10-22):** every change goes to the `development` branch (cut from `main`). No per-WP PRs or feature branches; worktrees allowed for parallel agents but push only to `development`. `main` is untouched until the user decides the merge.
