# Working rules for every session

`SPEC.md` is the single source of truth. These rules are copied from it and are mandatory.

## Start of every session

1. Read `CLAUDE.md`, `SPEC.md` and `PROGRESS.md`.
2. Start services: `service postgresql start` and `service redis-server start` (or `docker compose up -d db redis`).
3. Check for open branches and PRs. If a functionality is in progress or waiting to merge, finish and merge it before anything new.
4. Then take the next unchecked item in `PROGRESS.md`.

## Git workflow (no exceptions)

1. Start from an up-to-date `main` and create one feature branch for one functionality only, named as in the backlog (e.g. `feat/f11-readback`).
2. Implement the functionality with its tests on that branch. Nothing else goes on it.
3. Run the local quality gate (`make check`), then open a PR to `main` describing what changed and how it was tested.
   `gh pr` commands are blocked in cloud sessions. Open every PR with `bash scripts/open_pr.sh "<title>" <body-file>`, which calls `gh api repos/{owner}/{repo}/pulls -f title=... -F body=@file` with an explicit body. Never use a tool that adds its own footer to PR text.
   After creating a PR, read it back (`bash scripts/preflight.sh --pr N`, done by `open_pr.sh` and again by `merge.sh`); if the title or body mentions the coding assistant, PATCH it before merging. The cloud session's GitHub proxy appends such a footer on PR create and on `gh api` PATCH; the GitHub update-pull-request tool writes the body exactly, so use it for the PATCH and then re-run the read-back.
4. Merge locally, never with GitHub's merge button: `git checkout main && git merge --no-ff <branch>`, then `git push origin main`. Delete the local branch. (Remote branch deletion is refused by the proxy; Sandeep cleans those up.)
5. Only then start the next functionality. At most one open feature branch at any moment.

## Commit identity (every commit, including merges)

- Author and committer: `Sandeep Sakilam <sakilamsandeep@gmail.com>`.
- `git config user.name "Sandeep Sakilam"` and `git config user.email "sakilamsandeep@gmail.com"`.
- Before every push: `git log --format='%an <%ae> | %cn <%ce>' main..HEAD` must show only that identity on both sides.

## No AI-assistant mentions

- No commit title or message, merge message, PR title or PR description may mention the coding assistant used to write the code (by product or company name).
- No co-author trailers, no "Generated with" lines, no session links.
- Before every push: `git log --format='%B' main..HEAD | grep -i claude` must return nothing.
- PR text: `bash scripts/preflight.sh --pr N` reads the PR back from GitHub and fails if its title or body mentions the coding assistant. Run it after opening a PR and after any edit; `merge.sh` runs it again before merging. Do not name the working-rules file in PR text (its file name contains the forbidden word); call it "the working rules".

## Working style

- Don't stop to ask. When something is unclear, choose the option most consistent with the design principles in `SPEC.md`, add one line to `DECISIONS.md` (date, question, choice, reason), and continue. Stop only before an action that can't be undone outside the repo (spending real money, messaging real people).
- Every outside service (Sarvam, fallback AI, Account Aggregator, payment gateway, WhatsApp, KYC, storage) has an interface, a mock adapter and a real adapter, chosen by an environment variable. The real adapter turns on when its keys are in `.env`. Tests always use mocks and never call real APIs. Sandbox or mock data is labelled on screen as "Sandbox".
- Never commit secrets. Every required key is listed in `.env.example` with a comment saying where to get it.
- Keep single commands under 10 minutes; run long ones in the background.
- `make e2e` starts the API on port 8010 against `ktp_e2e` (reset from migrations) and the web preview on 4173.
- Money is integer paise, never floats. Timestamps stored in UTC, shown in IST.
- Schema changes: edit `backend/app/db/models.py`, then `uv run alembic revision --autogenerate --rev-id 00NN -m "..."`; give new NOT NULL columns a `server_default` in the migration.
- AI reads, rules decide: AI output is schema-validated data only and never changes a score directly.

## Definition of done (each functionality)

- Code and tests written.
- Local quality gate passes: ruff, mypy and pytest (backend); eslint, tsc and vitest (frontend); Playwright for any user flow it touches.
- Docs updated where relevant.
- `PROGRESS.md` ticked in the same PR, and its "Current" line updated.
- PR opened, merged locally into `main` with `--no-ff`, pushed, local branch deleted.

## Tasks only Sandeep can do

Keep these listed in `README.md` under "What Sandeep must provide"; build everything else with mocks meanwhile.

## Helper scripts

- `python3 scripts/tick.py F07` ticks a backlog item and updates the "Current" line.
- `bash scripts/preflight.sh` runs the identity and wording checks for the branch.
- `bash scripts/ship.sh F07 "<message>"` ticks, runs `make check`, commits, preflights and pushes the branch.
- `bash scripts/open_pr.sh "<title>" <body-file>` opens the PR through the REST API and checks its text.
- `bash scripts/merge.sh <branch> "<title>"` re-checks the PR text, merges locally with `--no-ff`, re-checks commits, pushes `main`, deletes the local branch.
