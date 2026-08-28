from pathlib import Path

import pytest

from code_agent.reviewer import Reviewer


class FakeReviewModel:
    def query_text(self, messages):
        assert messages[0]["role"] == "system"
        assert "solution" in messages[1]["content"]
        return "时间复杂度：O(n)"


def test_reviewer_reads_verified_files(tmp_path: Path):
    solution = tmp_path / "solution.py"
    tests = tmp_path / "test_solution.py"
    cases = tmp_path / "test_cases.json"
    solution.write_text("def solve(): return 1", encoding="utf-8")
    tests.write_text("def test_solve(): assert solve() == 1", encoding="utf-8")
    cases.write_text('{"cases": [{"input": "x", "expected_output": "1"}]}', encoding="utf-8")
    result = {
        "status": "success",
        "verified": True,
        "solution_path": str(solution),
        "test_path": str(tests),
        "test_cases_path": str(cases),
        "last_test_output": "1 passed",
    }

    review = Reviewer(FakeReviewModel()).review("实现 solve", result)

    assert review == {"status": "completed", "local_verification": "passed", "content": "时间复杂度：O(n)"}


def test_reviewer_rejects_unverified_result(tmp_path: Path):
    with pytest.raises(ValueError, match="local verification"):
        Reviewer(FakeReviewModel()).review(
            "实现 solve",
            {"status": "success", "verified": False, "solution_path": str(tmp_path / "solution.py")},
        )
