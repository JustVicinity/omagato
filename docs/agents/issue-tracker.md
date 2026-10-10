# Issue tracker: GitHub

OmaGato issues and specs live in `JustVicinity/omagato` on GitHub. Use `gh` from this repository, or pass `--repo JustVicinity/omagato`.

- Read: `gh issue view <number> --json number,title,body,labels,comments`.
- List: `gh issue list --state open --json number,title,body,labels`.
- Create: `gh issue create --title "..." --body-file <file>`.
- Update labels: `gh issue edit <number> --add-label <label>` or `--remove-label <label>`.
- Resolve: comment with the outcome, then close the issue.

When a skill says “publish to the issue tracker,” create a GitHub issue. When it says “fetch the relevant ticket,” read that issue.

## Pull requests as a triage surface

**PRs as a request surface: no.** External pull requests are not included in the issue triage queue.
