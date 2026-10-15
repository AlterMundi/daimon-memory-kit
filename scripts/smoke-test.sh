#!/bin/bash
# Smoke test for DaimonMemoryKit base.
# NOT validated here: plugin+Hermes integration — that requires Hermes installed
# and is tested manually. See docs/dialogue-handoff.md for manual steps.
set -e
TMP=$(mktemp -d)
trap "rm -rf $TMP" EXIT

REPO="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"

echo "[1] bootstrap workspace with scripts + plugins"
python3 "$REPO/scripts/bootstrap_workspace.py" --workspace "$TMP/ws" --with-wiki-templates

echo "[2] hmk wrapper is executable (regression 1C)"
test -x "$TMP/ws/scripts/hmk" || { echo "FAIL: hmk not executable"; exit 1; }

test -x "$TMP/ws/scripts/dmk" || { echo "FAIL: dmk not executable"; exit 1; }

echo "[3] init via dmk; read/write via compatible hmk"
cd "$TMP/ws" && ./scripts/dmk memoryctl.py init >/dev/null

echo "[4] add-text + search + pack"
./scripts/hmk memoryctl.py add-text --shelf library --title "smoke" --raw "test content for smoke check" --tags smoke >/dev/null
./scripts/hmk memoryctl.py search --query "smoke" --limit 3 | grep -q "smoke" || { echo "FAIL: search did not return smoke entry"; exit 1; }
./scripts/hmk memoryctl.py pack --query "smoke" --limit 3 >/dev/null

echo "[5] retired Obsidian option creates no generated vault"
test ! -e "$TMP/ws/wiki" || { echo "FAIL: obsolete vault created"; exit 1; }
test ! -e "$TMP/ws/scripts/export_obsidian.py" || { echo "FAIL: obsolete exporter installed"; exit 1; }

echo "[7] HMK provider + librarian present, legacy handoff absent"
test -f "$TMP/ws/hermes-home/plugins/hmk-memory/__init__.py" || { echo "FAIL: HMK provider missing"; exit 1; }
test -f "$TMP/ws/hermes-home/skills/memory/librarian/SKILL.md" || { echo "FAIL: librarian missing"; exit 1; }
test ! -e "$TMP/ws/hermes-home/plugins/dialogue-handoff" || { echo "FAIL: legacy plugin installed"; exit 1; }
test ! -e "$TMP/ws/agent-memory/state/DIALOGUE-HANDOFF.md" || { echo "FAIL: shared handoff created"; exit 1; }
test ! -e "$TMP/ws/hermes-home/memories/MEMORY.md" || { echo "FAIL: native memory created"; exit 1; }
test ! -e "$TMP/ws/hermes-home/memories/USER.md" || { echo "FAIL: native profile created"; exit 1; }
test -f "$TMP/ws/scripts/continuityctl.py" || { echo "FAIL: continuityctl missing"; exit 1; }

echo "[8] continuityctl syntax OK + native re-entry guidance runs"
python3 -m py_compile "$TMP/ws/scripts/continuityctl.py"
./scripts/hmk continuityctl.py rehydrate --skip-retrieval >/dev/null

echo "[9] --upgrade preserves user data (DB) while refreshing tooling"
./scripts/hmk memoryctl.py add-text --shelf library --title "user-data" --raw "important user content" --tags u >/dev/null
python3 "$REPO/scripts/bootstrap_workspace.py" --workspace "$TMP/ws" --upgrade
test ! -e "$TMP/ws/hermes-home/plugins/dialogue-handoff" || { echo "FAIL: upgrade reinstalled handoff"; exit 1; }
./scripts/dmk memoryctl.py search --query "important" --limit 3 | grep -q "user-data" || { echo "FAIL: user data lost on upgrade"; exit 1; }

echo ""
echo "SMOKE TEST PASSED (kit base)"
echo "NOTE: plugin+Hermes integration is NOT validated here. See docs/dialogue-handoff.md for manual verification steps."
