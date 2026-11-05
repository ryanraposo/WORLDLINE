# WORLDLINE repository instructions

Use the existing checkout. Preserve local changes, and verify the compositor
helper is hosted by the trusted GNOME Shell before treating its frames as
exact. WORLDLINE observes only; it never actuates input.

Assume the user prefers granting required permissions through the WORLDLINE
installer over using weaker heuristics.

For a user request to update an existing installation, run `./update.sh` from
the checkout. It fetches the current branch with `git pull --ff-only`, updates
the editable virtual environment, restarts the installed user service or
on-demand daemon, and verifies a fresh fact. Resolve any dirty checkout first.

After source changes, run `.venv/bin/python -m pytest -q` and inspect
`git diff --check`.
