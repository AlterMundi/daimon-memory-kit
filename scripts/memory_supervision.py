"""Render a receiving systemd oneshot and optional daily timer; activate nothing."""
import argparse
from pathlib import Path

from memory_runtime import profile


def quoted(value, *, expand_environment=False):
    value = str(value)
    if '\n' in value or '\r' in value or '\x00' in value:
        raise ValueError('unit arguments must be single-line strings')
    value=value.replace('\\','\\\\').replace('"','\\"').replace('%','%%')
    if expand_environment:
        value=value.replace('$','$$')
    return '"'+value+'"'


def render(profile_path, interpreter, environment_file, *, calendar=None):
    """Use existing environment credential injection; no secret values in units.

    An environment file is a receiving secret reference, not a new token store
    convention. The operator supplies its existing selected-provider material.
    No service restart, timer enablement, hook or private source selection follows.
    """
    for p in (profile_path,interpreter,environment_file):
        if not Path(p).is_absolute():
            raise ValueError('absolute receiving paths required')
    profile(profile_path)
    command = ' '.join(quoted(x,expand_environment=True) for x in (interpreter,Path(__file__).with_name('memory_runtime.py'),
                                          'run','--profile',profile_path))
    service = f'''[Unit]
Description=Finite HMK capture, reconciliation and index worker

[Service]
Type=oneshot
UMask=0077
EnvironmentFile={quoted(environment_file)}
ExecStart={command}
Restart=no
TimeoutStartSec=30min
KillMode=control-group
Nice=10

# Exit 0: owned streams idle. Exit 2: pending work. Exit 1: launch failure.
# A completed oneshot is normally inactive. Inspect Result and ExecMainStatus.
# Keep journals and canonical memories when reverting this configuration.
'''
    result={'hmk-memory-worker.service':service}
    if calendar is not None:
        if not calendar.strip() or any(c in calendar for c in '\r\n\x00%'):
            raise ValueError('explicit single-line systemd calendar required')
        result['hmk-memory-worker.timer']=f'''[Unit]
Description=Selected daily HMK batch invocation

[Timer]
OnCalendar={calendar}
Persistent=true
Unit=hmk-memory-worker.service

[Install]
WantedBy=timers.target
'''
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',type=Path,required=True)
    parser.add_argument('--interpreter',type=Path,required=True)
    parser.add_argument('--environment-file',type=Path,required=True)
    parser.add_argument('--calendar',help='Render only; requires selected receiving activation before enablement')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    units=render(args.profile,args.interpreter,args.environment_file,calendar=args.calendar)
    args.output.mkdir(parents=True,exist_ok=True,mode=0o700)
    # Refuse changed existing files before writing any file in this rendering.
    for name,content in units.items():
        path=args.output/name
        if path.exists() and path.read_text()!=content:
            raise ValueError('rendered unit differs; preserve prior configuration separately')
    for name,content in units.items():
        path=args.output/name
        if not path.exists():
            with path.open('x') as f:
                f.write(content)
            path.chmod(0o600)
    print('Rendered receiving units; nothing installed, enabled or started.')


if __name__=='__main__':
    main()
