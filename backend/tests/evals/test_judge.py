"""Unit tests for the eval's scoring (runs in the normal suite; no LLM calls)."""

from tests.evals.test_extraction_eval import judge


def test_judge_requires_all_expected_items() -> None:
    case = {"expect": [{"kind": "event", "date": "2026-10-01", "time": "18:00"}]}
    assert judge(case, [{"kind": "event", "date": "2026-10-01", "time": "18:00"}])
    assert not judge(case, [{"kind": "task", "date": "2026-10-01", "time": "18:00"}])
    assert not judge(case, [])


def test_judge_nothing_expected_and_extras() -> None:
    assert judge({"expect": []}, [])
    assert not judge({"expect": []}, [{"kind": "task", "date": None, "time": None}])
    two = [{"kind": "task", "date": None, "time": None}] * 2
    assert not judge({"expect": [{"kind": "task"}]}, two)
    assert judge({"expect": [{"kind": "task"}], "allow_extra": True}, two)
    assert judge(
        {"expect": [{"kind": "any", "date": "2026-10-03"}]}, [{"kind": "task", "date": "2026-10-03", "time": None}]
    )
