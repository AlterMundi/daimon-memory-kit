from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "policies" / "memory-ownership.v1.json"
def test_policy_is_closed_and_has_one_authority_per_artifact() -> None:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    assert set(policy) == {
        "schema",
        "artifact_classes",
        "forbidden_overlaps",
    }
    assert policy["schema"] == "memory-ownership/v1"
    classes = policy["artifact_classes"]
    assert classes
    assert len({item["id"] for item in classes}) == len(classes)
    for item in classes:
        assert set(item) == {"id", "selector", "authority", "replicas"}
        assert item["authority"]["role"] == "source"
        assert all(replica["role"] != "source" for replica in item["replicas"])
        assert all(replica["rebuildable"] is True for replica in item["replicas"])


def test_wiki_authority_remains_separate_without_an_obsidian_exporter() -> None:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    by_id = {item["id"]: item for item in policy["artifact_classes"]}
    assert by_id["wiki-curated-knowledge"]["authority"]["store"] == "llm-wiki"
    assert by_id["hmk-native-memory"]["authority"]["store"] == "hmk"
    assert "hmk-projection-output" not in by_id
    assert by_id["hmk-native-memory"]["replicas"] == []
