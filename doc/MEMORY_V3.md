# Memory V3

The memory bank stores reasoning, not raw trajectories. Raw trajectories remain
under `trajectories/` for audit; only generalized guidance is retrieved into a
new coding run.

## Top-level Types

`experience_type` is the primary type and has only two values:

- `success`: why a verified solution worked and when to reuse the decision.
- `failure`: an observed failure, the repair, and the evidence that the repair
  passed.

The old `category` field (`strategy`, `recovery`, `optimization`) remains a
secondary compatibility tag. It must not decide whether a memory is trusted.

## Failure Evidence

A normal failure memory is created only from one contiguous episode:

```text
test_failed -> solution edit -> test_passed
```

Repeated failures before the final pass are folded into one
`RecoveryEpisode`. A failed test without an edit, or a final failed run, does
not create a failure memory.

The LeetCode Hot 100 bootstrap set is an explicit exception: the 32 curated
failure patterns were marked as verified after the user reviewed and confirmed
them as initial recovery experience. Future task runs can replace or enrich
these seeds with concrete episode evidence.

## Consolidation and Retrieval

Embedding search recalls possible duplicates and relevant memories. Before a
candidate is stored, an LLM judges whether it expresses the same causal rule;
the cosine threshold is only the fallback when that judge is unavailable.

Retrieval keeps two signals separate:

```text
score = 0.6 * similarity(current_task, source_task)
      + 0.4 * similarity(query, memory_text)
```

This avoids confusing similar wording with a genuinely similar task.
