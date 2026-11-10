---
type: llm
weight: 1
---

PASS if the reply states that the URL points to a pull request rather than an issue and declines to run the issue workflow on it (asking for an issue URL or suggesting a different workflow is fine).

FAIL if the reply treats the pull request as an issue, gives a verdict (VALID, INVALID, ALREADY_FIXED or NEEDS_INFO) about it, or claims to have changed labels, code or GitHub state.
