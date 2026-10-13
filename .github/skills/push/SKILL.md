---
name: push
description: "Review and push the current branch changes to GitHub. Use when the user invokes /push or asks to create a branch, commit changes, and push them."
argument-hint: "Optional branch name"
user-invocable: true
---

# Push Changes to GitHub

Guide the user through reviewing the current branch changes, creating a named branch, committing the pending changes with the user's message, and pushing that branch to the connected GitHub repository.

## Procedure

1. Inspect the repository before making changes:
   - Identify the current branch, upstream (if set), working-tree status, staged and unstaged diffs, untracked files, and configured remotes and push URLs.
   - Report all changes on the current branch that are not in its upstream/base, plus all staged, unstaged, and untracked changes. List every affected file and summarize its actual changes. Include branch-only commits and call out when no upstream/base can be determined; do not imply the branch is unchanged in that case.
   - Review diffs before staging. Do not expose secret values in the report. If a change appears to contain credentials, private keys, or other sensitive material, do not stage or push it; explain the concern and ask the user how to proceed.
   - Do not discard, reset, stash, or overwrite user changes.
2. After presenting the change list, ask what branch name to create unless the user already supplied one. If the user supplied a name, confirm it is a valid Git branch name and does not already exist, then create and switch to it from the current branch (`git switch -c <branch>`). This preserves the current branch's commits and working-tree changes. If validation fails or the name already exists, explain why and ask for another name; do not silently choose or reuse a branch.
3. Once the new branch is created, ask for the exact commit message unless the user has already provided one. Do not commit before receiving it. When pending changes exist, stage and commit the reviewed changes using that message. Include tracked modifications and intended untracked files; do not stage sensitive files. Do not create an empty commit. If there are no pending changes, explain that there is nothing new to commit; do not invent a commit.
4. Resolve the destination before pushing:
   - Use the configured upstream's push remote when it clearly identifies a GitHub repository; otherwise use the sole configured GitHub push remote.
   - If there is no clear GitHub destination, multiple plausible destinations, or the remote is not GitHub, ask the user which repository/remote to use. Never guess.
   - Check authentication without reading, printing, or requesting tokens/passwords. Prefer `gh auth status --hostname github.com` when GitHub CLI is installed. If it is unavailable, use a non-mutating access check such as `git ls-remote` against the selected remote; report an authentication failure and ask the user to sign in/configure Git Credential Manager, then retry the check. Never inspect credential stores or put credentials in command arguments, URLs, or chat.
5. Push only the newly created branch to the resolved remote (for example, `git push -u <remote> <branch>`). Do not force-push, push tags, or push other branches. If the push fails, report the error and stop; do not claim success or use a force option to get around it.
6. Report the branch, commit (if created), destination repository, and push result. If any requested operation is blocked, state exactly what is needed to continue.

## Interaction Requirements

- The change inventory comes before asking for a branch name or creating a branch.
- Create the requested branch only after its name is known; ask for the commit message only after the branch exists.
- Treat a user's provided branch name or commit message as satisfying the corresponding question.
- Ask concise questions when a necessary choice is unclear, especially branch name, commit message, or push destination.
