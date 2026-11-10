---
type: llm
weight: 1
---

PASS if the reply asks the user for the full issue URL or the OWNER/REPO that issue 123 belongs to, and gives no verdict (VALID, INVALID, ALREADY_FIXED or NEEDS_INFO) about the issue's content.

FAIL if the reply guesses a repository, reports findings about an issue, or claims to have changed labels, code or GitHub state.
