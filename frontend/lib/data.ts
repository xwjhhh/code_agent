export type RunStatus = "passed" | "failed" | "running" | "reviewing";

export type TraceEvent = {
  id: number;
  label: string;
  summary: string;
  time: string;
  kind: "done" | "failed" | "active";
  detail?: string;
};

export type Run = {
  id: string;
  title: string;
  slug: string;
  status: RunStatus;
  model: string;
  steps: number;
  tokens: string;
  cost: string;
  tests: string;
  score?: string;
  created: string;
};

export const runs: Run[] = [
  { id: "run_01HZX2", title: "Two Sum", slug: "two-sum", status: "passed", model: "Claude Sonnet 4", steps: 5, tokens: "8,420", cost: "$0.09", tests: "6 / 6", score: "9.4", created: "2 min ago" },
  { id: "run_01HZW8", title: "LRU Cache", slug: "lru-cache", status: "failed", model: "GPT-4o", steps: 12, tokens: "15,882", cost: "$0.21", tests: "4 / 7", created: "18 min ago" },
  { id: "run_01HZVQ", title: "Merge Intervals", slug: "merge-intervals", status: "passed", model: "Claude Sonnet 4", steps: 8, tokens: "11,120", cost: "$0.14", tests: "8 / 8", score: "8.8", created: "1 hour ago" },
  { id: "run_01HZUP", title: "Dijkstra Shortest Path", slug: "dijkstra", status: "reviewing", model: "Claude Sonnet 4", steps: 9, tokens: "12,482", cost: "$0.17", tests: "10 / 10", created: "3 hours ago" },
];

export const solutionCode = `from collections import defaultdict


def longest_substring(s: str) -> int:
    """Return the length of the longest substring without repeats."""
    last_seen: dict[str, int] = {}
    left = 0
    longest = 0

    for right, char in enumerate(s):
        if char in last_seen:
            left = max(left, last_seen[char] + 1)
        last_seen[char] = right
        longest = max(longest, right - left + 1)

    return longest
`;

export const testCode = `import pytest

from solution import longest_substring


@pytest.mark.parametrize("value, expected", [
    ("abcabcbb", 3),
    ("bbbbb", 1),
    ("pwwkew", 3),
    ("", 0),
    ("a", 1),
    ("abba", 2),
    ("dvdf", 3),
    ("你好世界你", 4),
])
def test_longest_substring(value, expected):
    assert longest_substring(value) == expected
`;

export const trace: TraceEvent[] = [
  { id: 1, label: "Understand problem", summary: "Need O(n) sliding window.", time: "14:02:11", kind: "done", detail: "The left pointer must never move backwards when a duplicate is found." },
  { id: 2, label: "Write solution.py", summary: "+ 18 lines", time: "14:02:14", kind: "done", detail: "$ python - <<'PY'\n# wrote solution.py\nPY\nFile updated successfully" },
  { id: 3, label: "Generate tests", summary: "+ 8 cases", time: "14:02:17", kind: "done", detail: "Examples, empty input, repeated patterns, unicode, and a pointer regression case." },
  { id: 4, label: "Run pytest", summary: "8 passed", time: "14:02:20", kind: "done", detail: "$ python -m pytest -q\n8 passed in 0.03s" },
  { id: 5, label: "Analyze edge cases", summary: "Reviewing pointer movement", time: "14:02:22", kind: "done", detail: "Compared the window invariant against abba and dvdf before finalizing." },
  { id: 6, label: "Reviewer", summary: "Score 9.4 / 10", time: "14:02:27", kind: "active", detail: "Correctness and complexity review is ready. Hidden online judge tests are not guaranteed." },
];

export const testCases = [
  { name: "empty_string", input: '""', expected: "0", status: "passed" },
  { name: "single_character", input: '"a"', expected: "1", status: "passed" },
  { name: "duplicate_characters", input: '"abba"', expected: "2", status: "passed" },
  { name: "normal_case", input: '"abcabcbb"', expected: "3", status: "passed" },
  { name: "repeated_pattern", input: '"pwwkew"', expected: "3", status: "passed" },
  { name: "unicode", input: '"你好世界你"', expected: "4", status: "passed" },
  { name: "pointer_regression", input: '"dvdf"', expected: "3", status: "passed" },
  { name: "long_input", input: '"abcdefghijklmnopqrstuvwxyz"', expected: "26", status: "passed" },
];

export const reviewerScores = [
  { label: "Correctness", value: 10 },
  { label: "Complexity", value: 9 },
  { label: "Code quality", value: 9 },
  { label: "Test coverage", value: 8 },
];

export const currentRun = runs[0];
