"""Finite supervision must expose failures without silently replaying paid work."""
from pathlib import Path
import subprocess

import pytest

import memory_supervision


def test_render_uses_finite_supervision_and_real_systemd_parser(tmp_path,monkeypatch):
    monkeypatch.setattr(memory_supervision,'profile',lambda _: {})
    profile=tmp_path/'profile with space.json'
    env=tmp_path/'selected.env'
    env.touch()
    units=memory_supervision.render(profile,Path('/usr/bin/python3'),env,calendar='daily')
    service=units['hmk-memory-worker.service']
    assert 'Restart=no' in service and 'Type=oneshot' in service
    assert 'RemainAfterExit' not in service and 'SuccessExitStatus' not in service
    assert 'KillMode=control-group' in service
    for name,content in units.items():
        (tmp_path/name).write_text(content)
    result=subprocess.run(['systemd-analyze','--user','verify',
        str(tmp_path/'hmk-memory-worker.service'),str(tmp_path/'hmk-memory-worker.timer')],
        capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert list(memory_supervision.render(profile,Path('/usr/bin/python3'),env))==['hmk-memory-worker.service']


def test_unit_escaping_is_context_specific():
    assert memory_supervision.quoted('/a$B%/x')=='"/a$B%%/x"'
    assert memory_supervision.quoted('/a$B%/x',expand_environment=True)=='"/a$$B%%/x"'
    with pytest.raises(ValueError,match='single-line'):
        memory_supervision.quoted('/a\nExecStart=bad')
