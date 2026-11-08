"""Diagnostic rerun: isolate launched test apps; preserve installer guard tests."""
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

root = Path(sys.argv[1]).resolve()
sys.path[:0] = [str(root), str(root/'scripts')]
import smoke_windows_installer as smoke

original = subprocess.Popen
def isolated_child(args, *rest, **kwargs):
    env = kwargs.get('env')
    argv = [str(value) for value in args] if isinstance(args, (list, tuple)) else []
    launch = (argv and Path(argv[0]).name.casefold() == 'cscript.exe') or ('elitelab' in argv and 'serve' in argv)
    if env and launch:
        env = dict(env)
        env['ELITELAB_INSTANCE_DIR'] = str(Path(env['USERPROFILE'])/'.elitelab')
        kwargs['env'] = env
        print('Diagnostic isolation applied only to app launch:', Path(argv[0]).name, flush=True)
    return original(args, *rest, **kwargs)

with patch.object(subprocess, 'Popen', isolated_child):
    smoke.smoke(Path(sys.argv[2]).resolve())
