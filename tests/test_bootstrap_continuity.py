"""Disposable workspaces exercise bootstrap/upgrade configuration policy."""
import importlib.util
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bootstrap_under_test", ROOT / "scripts/bootstrap_agent.py")
assert spec is not None and spec.loader is not None
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


def test_new_workspace_selects_hmk_without_dialogue_or_native_stores(tmp_path):
    ws = tmp_path / "agent"
    bootstrap.bootstrap(ws, "agent", False)
    config = yaml.safe_load((ws / "hermes-home/config.yaml").read_text())
    assert config["memory"]["provider"] == "hmk-memory"
    assert config["memory"]["memory_enabled"] is False
    assert config["memory"]["user_profile_enabled"] is False
    assert config["plugins"]["disabled"] == ["dialogue-handoff"]
    assert config["plugins"]["enabled"] == ["hmk-memory"]
    assert (ws / "hermes-home/plugins/hmk-memory/__init__.py").is_file()
    assert (ws / "hermes-home/skills/memory/librarian/SKILL.md").is_file()
    assert not (ws / "hermes-home/plugins/dialogue-handoff").exists()
    assert not (ws / "hermes-home/memories/MEMORY.md").exists()
    assert not (ws / "hermes-home/memories/USER.md").exists()
    assert not (ws / "agent-memory/state/DIALOGUE-HANDOFF.md").exists()
    assert not (ws / "agent-memory/state/ALWAYS-CONTEXT.md").exists()


@pytest.mark.parametrize("plugins", [
    {"disabled": ["dialogue-handoff"], "enabled": ["dialogue-handoff", "hmk-memory"]},
    {"enabled": ["hmk-memory"]},
    {"enabled": None, "disabled": None},
    None,
])
@pytest.mark.parametrize("installed", [False, True])
def test_upgrade_does_not_reinstall_or_overwrite_unselected_dialogue(tmp_path, plugins, installed):
    import sqlite3
    ws = tmp_path / "agent"
    bootstrap.bootstrap(ws, "agent", False)
    config_path = ws / "hermes-home/config.yaml"
    config_path.write_text(yaml.safe_dump({
        "plugins": plugins,
        "memory": {"provider": "hmk-memory", "memory_enabled": False,
                   "user_profile_enabled": False},
    }))
    config_before = config_path.read_bytes()
    plugin = ws / "hermes-home/plugins/dialogue-handoff"
    if installed:
        plugin.mkdir()
        (plugin / "__init__.py").write_text("# independently repaired plugin\n")
    db = ws / "agent-memory/library.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE evidence (value TEXT)")
        conn.execute("INSERT INTO evidence VALUES ('curated durable data')")
    db_before = db.read_bytes()
    bootstrap.upgrade(ws)
    bootstrap.bootstrap(ws, "agent", False)  # Reruns must not revive it either.
    assert config_path.read_bytes() == config_before
    assert db.read_bytes() == db_before
    assert (ws / "hermes-home/plugins/hmk-memory/__init__.py").is_file()
    if installed:
        assert (plugin / "__init__.py").read_text() == "# independently repaired plugin\n"
        assert not (plugin / "plugin.yaml").exists()
    else:
        assert not plugin.exists()


@pytest.mark.parametrize("config_text", [
    "plugins:\n  enabled: [dialogue-handoff, hmk-memory]\n  disabled: []\n",
    "plugins:\n  enabled:\n    - dialogue-handoff\n    - hmk-memory\n",
])
def test_existing_opt_in_and_archived_native_files_are_preserved(tmp_path, config_text):
    ws = tmp_path / "agent"
    bootstrap.bootstrap(ws, "agent", False)
    config_path = ws / "hermes-home/config.yaml"
    config_path.write_text(config_text + "memory:\n  memory_enabled: true\n  user_profile_enabled: true\n")
    plugin = ws / "hermes-home/plugins/dialogue-handoff"
    plugin.mkdir()
    repaired = plugin / "__init__.py"
    repaired.write_text("# maintained outside HMK\n")
    archived = ws / "hermes-home/memories/MEMORY.md"
    archived.write_text("existing user-owned memory\n")
    before = config_path.read_bytes()
    bootstrap.upgrade(ws)
    bootstrap.bootstrap(ws, "agent", False)
    assert config_path.read_bytes() == before
    assert repaired.read_text() == "# maintained outside HMK\n"
    assert archived.read_text() == "existing user-owned memory\n"


def test_bootstrap_does_not_interpret_or_rewrite_existing_yaml(tmp_path):
    # No ad-hoc YAML parser or implicit activation: plugin compatibility is
    # independently installed; config is preserved byte-for-byte, even unknown
    # syntax must not trigger a best-effort reinstall of the legacy plugin.
    ws = tmp_path / "agent"
    bootstrap.bootstrap(ws, "agent", False)
    path = ws / "hermes-home/config.yaml"
    raw = b"# user-managed YAML\nplugins: [invalid-for-runtime\n"
    path.write_bytes(raw)
    bootstrap.upgrade(ws)
    bootstrap.bootstrap(ws, "agent", False)
    assert path.read_bytes() == raw
    assert not (ws / "hermes-home/plugins/dialogue-handoff").exists()


def test_retired_obsidian_option_creates_no_vault_and_preserves_existing_notes(tmp_path):
    ws = tmp_path / "agent"
    bootstrap.bootstrap(ws, "agent", True)
    assert not (ws / "wiki").exists()
    assert not (ws / "scripts/export_obsidian.py").exists()
    notes = ws / "wiki"
    notes.mkdir()
    retained = notes / "personal.md"
    retained.write_text("Independently authored notes.")
    bootstrap.upgrade(ws)
    assert retained.read_text() == "Independently authored notes."
