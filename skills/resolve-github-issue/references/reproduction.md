# Reproduction strategies

Read this when the issue's steps do not reproduce the problem directly. The goal is one command you have actually run that fails because of this defect and will pass once it is fixed. That command becomes the regression check.

## Ways to get a failing command

Try them roughly in this order and stop at the first that works:

1. A test at whichever level reaches the defect: unit, integration or end-to-end.
2. A script or CLI call with a fixture input, compared with the expected output.
3. A request script against a locally running server.
4. A replay of the payload, log or input file attached to the issue, fed through the affected code path.
5. A small harness that calls the affected function with the rest of the system stubbed out.
6. A comparison of two versions or configurations on the same input, when the issue says it used to work. With a known good revision, `git bisect run` with that command finds the commit that introduced it.
7. A loop over many generated inputs, when the output is only sometimes wrong.
8. A headless browser script, when the defect is only visible in the UI.

## Intermittent failures

Raise the failure rate until it is usable: repeat the trigger many times, run it concurrently, add load or delays around the suspected window, and pin time, random seeds and external state where possible. Record the observed rate; a fix is verified against the same loop.

## What makes the command good enough

- It asserts the reporter's symptom, not merely that nothing crashed.
- It gives the same result on every run, or fails at a stated rate.
- It finishes in seconds and runs without a person.

Shrink the scenario while it still fails, removing one input, step or setting at a time. What remains is the regression test.

## When nothing works

Record what you tried and why each attempt did not reach the defect. Then either establish the defect by complete control-flow or data-flow evidence, stating that it was not reproduced, or return NEEDS_INFO naming the smallest missing piece: the environment, a captured input or log, or the exact version.

Remove temporary logging and throwaway harnesses before review. Give temporary log lines a unique marker when you add them so one search finds them all.
