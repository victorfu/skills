# Implicit (model-initiated) invocation

No skill in this plugin starts on its own. Each one runs only when the user invokes it by name.

## Why this is out of scope

These skills write: they label issues, push branches, open PRs and post review replies. A pasted URL or a review notification is not a request to do any of that. Letting the model decide when to start would turn reading an issue into a side effect.

The build enforces it: `tools/build.py` rejects a skill whose `agents/openai.yaml` lacks `policy.allow_implicit_invocation: false`, and adds `disable-model-invocation: true` to every Claude Code `SKILL.md`.

Read-only use is already covered without implicit invocation: invoke the skill and say "assess only".

## Prior requests

- None recorded.
