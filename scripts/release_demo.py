#!/usr/bin/env python3
"""Rehearse a release with real Hermes and local workerd. No live mode exists."""

import argparse
import json
import os
import selectors
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class LocalWorker:
    def __init__(self, directory):
        self.directory = directory

    def read(self):
        with selectors.DefaultSelector() as ready:
            ready.register(self.process.stdout, selectors.EVENT_READ)
            if not ready.select(30):
                raise RuntimeError('Local Worker did not answer within 30 seconds')
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError('Local Worker exited; see the local-worker.log output')
        return json.loads(line)

    def __enter__(self):
        self.directory.mkdir()
        env = {'PATH': os.environ.get('PATH', ''), 'HOME': str(self.directory),
               'XDG_CONFIG_HOME': str(self.directory / 'config'), 'HERMES_HOME': str(self.directory / 'hermes'),
               'WRANGLER_HOME': str(self.directory / 'wrangler'), 'WRANGLER_SEND_METRICS': 'false',
               'CI': 'true', 'GOMAXPROCS': '2', 'NODE_OPTIONS': '--max-old-space-size=512'}
        self.log = (self.directory / 'local-worker.log').open('w')
        self.process = subprocess.Popen(['node', str(ROOT / 'scripts/local_worker.mjs'), str(self.directory)],
                                        cwd=self.directory, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=self.log, text=True, bufsize=1)
        try:
            self.url = self.read()['url']
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def call(self, action, project='release-demo'):
        self.process.stdin.write(json.dumps({'action': action, 'project': project}) + '\n')
        self.process.stdin.flush()
        result = self.read()
        assert result['ok'], result
        return result['result']

    def __exit__(self, *_):
        if self.process.poll() is None:
            try:
                self.process.stdin.write('{"action":"close"}\n')
                self.process.stdin.flush()
                self.process.wait(10)
            except (BrokenPipeError, subprocess.TimeoutExpired):
                self.process.kill()
                self.process.wait()
        self.process.stdin.close()
        self.process.stdout.close()
        self.log.close()


def run(answer, output):
    from scripts.mock_notify import PocketMock

    source = ROOT / '.local/hermes-source'
    if not (source / 'hermes_cli/plugins.py').is_file():
        raise SystemExit('Run scripts/fetch_hermes.py first.')
    if not (ROOT / 'worker/dist/public/index.html').is_file():
        raise SystemExit('Run node worker/scripts/isolated.mjs build first.')
    sys.path.insert(0, str(source))
    output.mkdir(parents=True, exist_ok=True)
    artifact = output / 'release-receipt.json'
    if artifact.exists():
        raise SystemExit('Use a fresh output directory; an existing release receipt will not be overwritten.')
    mock = PocketMock()
    with tempfile.TemporaryDirectory(prefix='pocket-demo-') as scratch, mock.serve() as mock_url:
        home = Path(scratch)
        (home / 'plugins').mkdir()
        (home / 'plugins/hermes-notify').symlink_to(ROOT, target_is_directory=True)
        (home / 'bundled').mkdir()
        os.environ.update(HERMES_HOME=str(home), HERMES_BUNDLED_PLUGINS=str(home / 'bundled'),
                          NOTIFY_API_TOKEN='dummy', HERMES_NOTIFY_PUBLISH_TOKEN='dummy',
                          HERMES_NOTIFY_TEST_URL=mock_url + '/api/agent', HERMES_GATEWAY_SESSION='1')
        for key in ('HERMES_YOLO_MODE', 'HERMES_SAFE_MODE', 'HERMES_ENABLE_PROJECT_PLUGINS',
                    'HERMES_QUIET', 'HERMES_CRON_SESSION', 'HERMES_SESSION_PLATFORM'):
            os.environ.pop(key, None)
        # A development-process guard catches accidental external Python traffic.
        original_connect = socket.socket.connect
        def local_only(sock, address):
            if sock.family in (socket.AF_INET, socket.AF_INET6) and address[0] not in ('127.0.0.1', '::1'):
                raise RuntimeError('Outbound network is forbidden in the rehearsal')
            return original_connect(sock, address)
        socket.socket.connect = local_only
        try:
            with LocalWorker(home / 'worker') as worker:
                os.environ['HERMES_NOTIFY_TEST_WORKER_URL'] = worker.url
                # Node is already running. The Hermes workflow must work with no
                # external executable, including Notify's CLI, available by name.
                os.environ['PATH'] = ''
                (home / 'config.yaml').write_text(json.dumps({
                    'plugins': {'enabled': ['hermes-notify'], 'isolation': 'in_process', 'entries': {
                        'hermes-notify': {'settings': {'enabled': True, 'timeout_seconds': 4,
                            'publisher_origin': 'https://pocket.example.com', 'progress_enabled': True}}}},
                    'approvals': {'mode': 'manual', 'timeout': 4}, 'security': {'approval': {'transport': 'notify'}},
                }))
                from gateway.session_context import set_session_vars, clear_session_vars
                from hermes_cli.plugins import get_plugin_manager
                from tools import approval, approval_context
                from tools.registry import registry
                manager = get_plugin_manager()
                manager.discover_and_load()
                transport = manager.get_approval_transport('notify')
                assert transport is not None, 'Plugin did not load'
                runtime = transport.present.__self__
                context = set_session_vars(session_key='release-demo-route', session_id='release-demo-session')
                approval_key = approval_context.set_current_session_key('release-demo-route')
                steps = []
                def call(tool, **args):
                    result = json.loads(registry.dispatch('notify_' + tool, args, scope=manager.scope_key, session_id='release-demo-session'))
                    assert result.get('ok'), result
                    return result
                def drain():
                    assert runtime.queue.drain(12), 'Delivery worker did not settle'
                def workspace():
                    return call('release', action='status', project='release-demo')['workspace']
                try:
                    call('release', action='begin', project='release-demo', name='Pocket release', version='1.0.0',
                         summary='Preparing the release candidate.', progress=0,
                         checks=[{'label': 'Release checks', 'status': 'running'}])
                    drain()
                    published = call('publish_app', project='release-demo')
                    assert published['publication']['phase'] == 'announced'
                    steps.append('Hermes published and registered the release App')
                    current = workspace()
                    call('release', action='update', project='release-demo', expected_revision=current['revision'],
                         status='running', stage='Ready to ship', summary='Release checks passed. Ready for approval.', progress=0.75,
                         checks=[{'label': 'Release checks', 'status': 'passed'}], notes='Rollback: restore the previous release receipt.')
                    drain()
                    phone_reply = worker.call('reply')
                    replies = call('replies', project='release-demo')
                    assert not replies['errors'] and len(replies['replies']) == 1
                    assert replies['replies'][0]['trustedAsInstruction'] is False
                    assert call('replies', project='release-demo')['replies'] == []
                    steps.append('Signed synthetic phone session replied once to the originating task')

                    actor_stop = threading.Event()
                    def phone_actor():
                        while not actor_stop.wait(0.02):
                            with mock.lock:
                                if mock.interactions:
                                    if answer != 'timeout':
                                        interaction = next(iter(mock.interactions.values()))
                                        interaction.update(status='approved' if answer == 'approve' else 'denied',
                                                           response='approve' if answer == 'approve' else 'deny')
                                    return
                    actor = threading.Thread(target=phone_actor, name='synthetic-phone', daemon=True)
                    actor.start()
                    # The exact proposed action writes only this local synthetic receipt.
                    program = 'from pathlib import Path\nPath(' + repr(str(artifact.resolve())) + ').write_text(' + repr('{"release":"1.0.0","synthetic":true}\n') + ')'
                    try:
                        decision = approval.check_execute_code_guard(program, 'local')
                    finally:
                        actor_stop.set()
                        actor.join(1)
                    drain()
                    approved = decision.get('approved') is True
                    assert approved == (answer == 'approve'), decision
                    before_action = workspace()
                    assert before_action['approval'] is not None, 'Host approval observer lost session correlation'
                    assert before_action['status'] == ('approved' if approved else 'denied'), before_action
                    assert not artifact.exists(), 'Approval alone must not execute the action'
                    steps.append('Hermes consumed the exact phone decision; no action ran before approval')
                    if approved:
                        result = subprocess.run([sys.executable, '-I', '-c', program], cwd=home,
                                                env={'PATH': os.environ.get('PATH', ''), 'HOME': str(home)},
                                                capture_output=True, text=True, timeout=5)
                        assert result.returncode == 0 and artifact.is_file(), 'Local release action failed'
                        call('release', action='finish', project='release-demo', expected_revision=before_action['revision'],
                             result='succeeded', result_summary='Local release action succeeded; receipt verified.', progress=1, stage='Shipped')
                    drain()
                    final = workspace()
                    remote = worker.call('workspace')['workspace']
                    expected = 'shipped' if approved else 'denied'
                    assert final['status'] == remote['status'] == expected
                    assert artifact.exists() == approved
                    assert len(mock.interactions) == 1 and len(mock.apps) == 1
                    assert len(mock.activities) == 1 and next(iter(mock.activities.values()))['status'] == 'ended'
                    steps.append('Worker workspace and Live Activity reached the same final state')
                    summary = {'mode': 'local-rehearsal', 'phoneAnswer': answer, 'hermesApproved': approved,
                        'releaseActionExecuted': approved, 'status': final['status'], 'workerStatus': remote['status'],
                        'appRegistrations': len(mock.apps), 'approvalPrompts': len(mock.interactions),
                        'liveActivities': len(mock.activities), 'liveActivityEnded': True,
                        'replyRoundTrip': phone_reply['authenticated'] and phone_reply['duplicateDeduplicated'],
                        'notifyCliAbsent': shutil.which('notify') is None,
                        'realNotifyRequests': 0, 'steps': steps}
                    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
                    (output / 'workspace.json').write_text(json.dumps(remote, indent=2) + '\n')
                    shutil.copy2(runtime.journal.directory / 'status.json', output / 'status.json')
                    print(json.dumps(summary, indent=2))
                    return summary
                finally:
                    approval_context.reset_current_session_key(approval_key)
                    clear_session_vars(context)
                    manager.unload('hermes-notify')
        finally:
            socket.socket.connect = original_connect
            worker_log = home / 'worker/local-worker.log'
            if worker_log.is_file():
                shutil.copy2(worker_log, output / 'local-worker.log')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--answer', choices=['approve', 'deny', 'timeout'], default='approve')
    parser.add_argument('--output', type=Path, help='Fresh output directory; defaults to .local/demo/<timestamp>-<answer>')
    args = parser.parse_args()
    output = args.output or ROOT / '.local/demo' / (time.strftime('%Y%m%d-%H%M%S') + '-' + args.answer)
    run(args.answer, output.resolve())
