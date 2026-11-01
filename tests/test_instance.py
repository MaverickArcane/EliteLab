"""A second launch cannot create a second dashboard or touch its data."""
import contextlib
import io
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_elitelab import config
from elitelab.instance import InstanceGuard, serve


class InstanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env=patch.dict(os.environ, {"ELITELAB_INSTANCE_DIR":self.temp.name})
        env.start();self.addCleanup(env.stop)
        self.args=SimpleNamespace(host="127.0.0.1",port=19001,open_browser=True,journals=None)

    def owner(self, **changes):
        guard=InstanceGuard();self.assertTrue(guard.acquire());self.addCleanup(guard.close)
        guard.write({"pid":42,"source":os.path.normcase(str(Path(config.ROOT).resolve())),
                     "build":"test-build","url":"http://127.0.0.1:19000/",**changes})
        return guard

    def test_lock_excludes_second_owner_and_recovers_after_close(self):
        owner=self.owner()
        other=InstanceGuard();self.addCleanup(other.close)
        self.assertFalse(other.acquire())
        self.assertEqual(other.read()["pid"],42)
        other.close();owner.close()
        self.assertTrue(other.acquire())

    def test_repeat_launch_reuses_original_port_without_starting_core(self):
        self.owner()
        with patch("elitelab.instance.fingerprint",return_value="test-build"), patch(
                "elitelab.instance.health",return_value={"pid":42,"ready":True}), patch(
                "elitelab.instance.webbrowser.open") as browser, patch("elitelab.core.Core") as core, contextlib.redirect_stdout(io.StringIO()):
            serve(self.args)
        browser.assert_called_once_with("http://127.0.0.1:19000/")
        core.assert_not_called()

    def test_other_copy_or_changed_build_is_not_silently_reused(self):
        for changes in ({"source":"another-folder"},{"build":"old-build"}):
            owner=self.owner(**changes)
            with patch("elitelab.instance.fingerprint",return_value="test-build"), patch("elitelab.core.Core") as core:
                with self.assertRaisesRegex(RuntimeError,"Stop that instance"):
                    serve(self.args)
                core.assert_not_called()
            owner.close()

    def test_legacy_listener_blocks_start_before_any_module_load(self):
        with patch("elitelab.instance.fingerprint",return_value="test-build"), patch(
                "elitelab.instance.health",return_value={"ok":True}), patch("elitelab.core.Core") as core:
            with self.assertRaisesRegex(RuntimeError,"older EliteLab"):
                serve(self.args)
            core.assert_not_called()
        guard=InstanceGuard();self.addCleanup(guard.close)
        self.assertTrue(guard.acquire())


class InstanceProcessTests(unittest.TestCase):
    def test_second_cli_reuses_instance_and_quit_releases_process(self):
        import json, socket, subprocess, sys, time, urllib.request
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            env={**os.environ,'ELITELAB_INSTANCE_DIR':str(Path(directory)/'lock'),
                 'ELITELAB_DATA_DIR':str(Path(directory)/'data'),'ELITELAB_OFFLINE':'1',
                 'ELITELAB_JOURNAL_DIR':str(root/'tests'/'fixtures'/'journals')}
            flags={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
            with open(Path(directory)/'server.log','w+') as log:
                process=subprocess.Popen([sys.executable,'-m','elitelab','serve','--no-browser','--port',str(port)],
                    cwd=root,env=env,stdout=log,stderr=log,**flags)
                try:
                    base=f'http://127.0.0.1:{port}/'
                    deadline=time.monotonic()+15
                    while time.monotonic()<deadline:
                        try:
                            with urllib.request.urlopen(base+'api/health',timeout=.5) as response:status=json.load(response)
                            if status.get('ready'):break
                        except OSError:pass
                        if process.poll() is not None:
                            log.seek(0);self.fail(log.read())
                        time.sleep(.05)
                    else:self.fail('CLI did not become ready')
                    # A different requested port must still reuse the existing instance.
                    second=subprocess.run([sys.executable,'-m','elitelab','serve','--no-browser','--port',str(port+1)],
                        cwd=root,env=env,capture_output=True,text=True,timeout=10,**flags)
                    self.assertEqual(second.returncode,0,second.stderr)
                    self.assertIn('Reusing it',second.stdout)
                    self.assertEqual(status['pid'],process.pid)
                    request=urllib.request.Request(base+'api/shutdown',data=b'{}',headers={'Content-Type':'application/json'})
                    with urllib.request.urlopen(request,timeout=2) as response:self.assertTrue(json.load(response)['stopping'])
                    self.assertEqual(process.wait(timeout=8),0)
                    lock=InstanceGuard(Path(directory)/'lock')
                    try:self.assertTrue(lock.acquire())
                    finally:lock.close()
                finally:
                    if process.poll() is None:process.terminate();process.wait(timeout=5)
