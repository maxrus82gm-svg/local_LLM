# Claude workspace rules

- Follow the canonical [owner rules](Documents/000_Задачи%20для%20агента.md), including DEC-UL-20261119-WORKSPACE-EVIDENCE-ENTER-015.
- Write project files only under M:\GitHub\local_LLM. Verify resolved paths and reject reparse-point escapes. Use task-local scratch for TEMP/TMP, caches, browser profiles, and builds.
- A write or live change outside the workspace requires direct owner authorization for the exact path, operation, and scope. Related, authorized read-only diagnostics are allowed.
- Use read-only Git. Prepare local manifests and sanitized WorkEvidence for owner-controlled publication. Clean up only task-owned temporary evidence after independent acceptance and explicit owner cleanup approval.
