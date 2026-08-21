# Issue tracker

GitHub issues on `Crimvel/Murmur` (private). Use `gh` CLI.

- Create: `gh issue create --title ... --body ... --label ...`
- Claim: assign yourself (`gh issue edit N --add-assignee @me`).
- Close with resolution comment: `gh issue comment N --body ...` then `gh issue close N`.

## When a skill says "publish to the issue tracker"

Create a GitHub issue with an appropriate label.

## When a skill says "fetch the relevant ticket"

`gh issue view N` (add `--comments` for history).

## Wayfinding operations

- **Map**: single issue labelled `wayfinder:map`. Canonical artifact; body per wayfinder template.
- **Tickets**: GitHub sub-issues of the map (`gh api` sub-issue endpoints; fallback: body line `Map: #<map>`), label `wayfinder:<type>`.
- **Blocking**: GitHub issue dependencies (`blocked_by`) via `gh api`. If unavailable, body line `Blocked by #N`.
- **Frontier query**: open, unassigned wayfinder tickets whose blockers are all closed:
  `gh issue list --state open --no-assignee` filtered to `wayfinder:*` labels, minus blocked ones.
- **Claim**: assign to yourself before work. Assignee = claim.
- **Resolve**: post answer as comment, close issue, append gist + link to map's Decisions-so-far (edit map issue body).

## Labels

`wayfinder:map`, `wayfinder:research`, `wayfinder:prototype`, `wayfinder:grilling`, `wayfinder:task` plus triage labels (see triage-labels.md).
