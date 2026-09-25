# resume-builder

Before starting work, read [docs/ROADMAP.md](docs/ROADMAP.md). It says what is done, what to build next, where the details are, and the conventions and test commands.

## Standing instructions from the owner

These apply to every session, including a request as short as "do the next roadmap item".

1. **Build the next roadmap item completely.** Take the first unchecked piece in the roadmap checklist and finish all of it: spec, implementation, tests, the skill's `SKILL.md`, and docs. Follow the roadmap's cycle and conventions.
2. **Approvals are given in advance.** The owner has approved your recommendations and any spec, plan or doc in review. Do not stop to ask for sign-off: choose the option you would recommend, set the spec's status to `Approved`, and carry on. Still ask before anything destructive, or when you are truly blocked.
3. **Update the roadmap when the piece is done.** Tick it and add its spec and PR links. Summarize what shipped, and add the notes that later pieces need. Update the architecture spec wherever a shared contract changed.
4. **Open the pull request yourself** once the full test suite passes. Do not open it as a draft: the Codex review bot (`chatgpt-codex-connector`) reviews a pull request when it is opened or marked ready, or when someone comments `@codex review`.
5. **Merge only after Codex has reviewed and its first round is resolved.** Wait for the Codex review of the pull request. A 👍 reaction instead of comments means no findings. For every comment in that first review:
   - verify the finding against the code, since some are wrong;
   - fix the real ones, with a test, and push;
   - reply on the thread with what you changed, or why the finding does not hold;
   - resolve the thread.

   Then merge, with CI green on the latest commit. Read any later Codex rounds too, and fix anything serious before merging, but they do not block the merge.
