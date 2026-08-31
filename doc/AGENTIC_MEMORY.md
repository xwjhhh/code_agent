# Agentic Memory Retrieval

The coding agent now uses two bounded decisions around long-term memory:

```text
task -> memory router
         |-- skip      -> DefaultAgent
         `-- retrieve  -> vector recall + rerank
                              -> relevance grader
                                   |-- useful -> inject context
                                   `-- weak   -> rewrite query (max 2)
```

The router and grader use the existing `TextModel.query_text` interface and
return JSON. A malformed or unavailable model response falls back to the
previous behavior: retrieve when routing fails, and keep recalled context when
grading fails. This makes memory advisory without blocking a coding run.

`MemoryManager.retrieve_agentic()` is shared by the CLI and FastAPI paths.
Its result records `route_action`, `grade_relevant`, `grade_reason`, and
`rewrite_count` in the run snapshot. The frontend timeline also displays the
`memory_route_decided`, `memory_relevance_graded`, and
`memory_query_rewritten` events.

The Bash-only coding loop remains unchanged. Memory is deliberately not added
as a shell tool, so protected test files, the exact pytest command, and the
submission gate keep their existing invariants.
