# PR body

Read this before writing the PR body. The target repo's own PR template wins: fill its sections, and add the sections below that it lacks. Every statement comes from the task record.

~~~markdown
## Problem

<what was wrong, and the evidence that it is real: the reproduction, the failing check or the code path>

## Change

<the fix, shown in the smallest view that makes it clear>

## Evidence

- **Before:** <failing test run, output or screenshot>
- **After:** <the same check passing>

## Impact

<who is affected, what changes for them, and how each part was confirmed or why it stays unverified>

## Review

<reviewer, findings and how each was settled, limitations>

## Merge risk

**Reversible:** <yes, by reverting | no, because ...>

**Blast radius:** <what could break for whom if this is wrong>

Closes #<number>
~~~

## Sections

- **Change.** Pick one view by what changed: a `diff` sketch of the logic for a behavior change, a call tree for control flow, a shallow file tree for a layout change, and two or three sentences when the change is small. Keep only the lines that carry the point; the full diff is one tab away.
- **Evidence.** Show the same check before and after. An executed check outranks a description of one; a screenshot outranks both when the change is visual. Label code-inspection evidence as such, and list here any command that was planned and not run.
- **Merge risk.** A change is reversible when reverting the commit restores the old behavior. A data migration, a deleted public API, a changed wire or storage format and a published artifact are not. Take the blast radius from the Impact field.
- **Issue link.** Use `Closes` or `Refs` as SKILL.md section 5 describes.

The Change, Evidence and Merge risk shape is adapted from the `pr` skill in [mattpocock/skills](https://github.com/mattpocock/skills), which credits Humanlayer's `show-me`.
