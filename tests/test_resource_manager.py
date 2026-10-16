import importlib.util
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = load('rm_runner', 'resource-manager/scripts/runner.py')
packager = load('rm_package', 'scripts/package-resource-manager.py')


class ResourceManagerTests(unittest.TestCase):
    def test_archive_is_self_contained_and_excludes_customer_files(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / 'stack.zip'
            packager.package(archive)
            first = archive.read_bytes()
            packager.package(archive)
            self.assertEqual(first, archive.read_bytes())
            with zipfile.ZipFile(archive) as z:
                names = z.namelist()
                self.assertIn('main.tf', names)
                self.assertIn('schema.yaml', names)
                self.assertIn('bundle/src/rotation/protocol.py', names)
                self.assertIn('modules/function/main.tf', names)
                self.assertNotIn('../terraform/', z.read('main.tf').decode())
                for name in names:
                    self.assertFalse(any(x in name for x in ('.local/', '.git/', '.tfstate', '.tfvars', '.pem', '__pycache__')))

    def test_inspection_returns_only_public_architecture_metadata(self):
        query = {'region': 'us-test-1', 'image': 'iad.ocir.io/test/rotation:v1@sha256:' + 'a' * 64}
        calls = []
        def run(args, **kwargs):
            calls.append((args, kwargs))
            return 'arm64\n' if args[1:3] == ['image', 'inspect'] else ''
        output = io.StringIO()
        with patch.object(runner.sys, 'stdin', io.StringIO(json.dumps(query))), \
                patch.object(runner, 'raw', return_value=({'token': 'private-test-token'}, {})), \
                patch.object(runner, 'run', side_effect=run), contextlib.redirect_stdout(output):
            runner.inspect_image()
        self.assertEqual(json.loads(output.getvalue()), {'architecture': 'arm64', 'shape': 'GENERIC_ARM'})
        self.assertNotIn('private-test-token', json.dumps([args for args, _ in calls]))
        self.assertTrue(all(not Path(kwargs['env']['DOCKER_CONFIG']).exists() for _, kwargs in calls))

    def test_function_shape_matches_image_architecture(self):
        self.assertEqual(runner.image_shape('arm64'), 'GENERIC_ARM')
        self.assertEqual(runner.image_shape('amd64'), 'GENERIC_X86')
        with self.assertRaises(runner.DeploymentError):
            runner.image_shape('s390x')

    def test_existing_target_and_replica_are_rejected(self):
        for secret in [
            {'lifecycleState': 'ACTIVE', 'isReplica': True},
            {'lifecycleState': 'ACTIVE', 'rotationConfig': {'targetSystemDetails': {'targetSystemType': 'FUNCTION', 'functionId': 'other'}}},
            {'lifecycleState': 'UPDATING'},
        ]:
            with self.assertRaises(runner.DeploymentError):
                runner.check_target(secret, 'selected')

    def test_failed_validation_cannot_update_secret(self):
        env = {'ROTATION_REGION': 'us-test-1', 'ROTATION_FUNCTION_ID': 'fn', 'ROTATION_SECRET_ID': 'secret',
               'ROTATION_DAYS': '30', 'ROTATION_ENABLED': 'false'}
        calls = []

        def raw(method, url, *args, **kwargs):
            calls.append(method)
            if method == 'GET':
                return {'lifecycleState': 'ACTIVE'}, {'etag': 'version1'}
            return {'status': 'FAILED'}, {}

        with patch.dict(os.environ, env), patch.object(runner, 'raw', side_effect=raw), \
                patch.object(runner, 'cli', return_value={'data': {'invoke-endpoint': 'https://functions.example'}}), \
                patch.object(runner.time, 'monotonic', side_effect=[0, 601]):
            with self.assertRaises(runner.DeploymentError):
                runner.configure()
        self.assertNotIn('PUT', calls)

    def test_success_links_manual_rotation_with_etag_after_validation(self):
        env = {'ROTATION_REGION': 'us-test-1', 'ROTATION_FUNCTION_ID': 'fn', 'ROTATION_SECRET_ID': 'secret',
               'ROTATION_DAYS': '30', 'ROTATION_ENABLED': 'false'}
        calls = []
        secret = {'lifecycleState': 'ACTIVE'}

        def raw(method, url, body=None, etag=None):
            calls.append((method, body, etag))
            if method == 'POST':
                return {'status': 'VALIDATED'}, {}
            if method == 'PUT':
                secret.update(body)
            return dict(secret), {'etag': 'fresh-etag'}

        with patch.dict(os.environ, env), patch.object(runner, 'raw', side_effect=raw), \
                patch.object(runner, 'cli', return_value={'data': {'invoke-endpoint': 'https://functions.example'}}):
            runner.configure()
        update = next(c for c in calls if c[0] == 'PUT')
        self.assertEqual(update[2], 'fresh-etag')
        self.assertFalse(update[1]['rotationConfig']['isScheduledRotationEnabled'])
        self.assertEqual([c[0] for c in calls], ['GET', 'POST', 'GET', 'PUT', 'GET'])

    def test_concurrent_target_change_blocks_link(self):
        env = {'ROTATION_REGION': 'us-test-1', 'ROTATION_FUNCTION_ID': 'fn', 'ROTATION_SECRET_ID': 'secret',
               'ROTATION_DAYS': '30', 'ROTATION_ENABLED': 'true'}
        results = [({'lifecycleState': 'ACTIVE'}, {'etag': 'first'}), ({'status': 'VALIDATED'}, {}),
                   ({'lifecycleState': 'ACTIVE', 'rotationConfig': {'targetSystemDetails': {'functionId': 'other'}}}, {'etag': 'second'})]
        with patch.dict(os.environ, env), patch.object(runner, 'raw', side_effect=results) as raw, \
                patch.object(runner, 'cli', return_value={'data': {'invoke-endpoint': 'https://functions.example'}}):
            with self.assertRaises(runner.DeploymentError):
                runner.configure()
        self.assertNotIn('PUT', [c.args[0] for c in raw.call_args_list])

    def test_command_failure_does_not_expose_output(self):
        result = runner.subprocess.CompletedProcess(['oci'], 1, 'sensitive-token', 'sensitive-password')
        with patch.object(runner.subprocess, 'run', return_value=result):
            with self.assertRaises(runner.DeploymentError) as error:
                runner.run(['oci', 'raw-request'])
        self.assertNotIn('sensitive', str(error.exception))

    def test_build_keeps_token_out_of_arguments_and_cleans_credentials(self):
        env = {'ROTATION_REGION': 'us-test-1', 'ROTATION_IMAGE': 'iad.ocir.io/test/rotation:1',
               'ROTATION_REGISTRY': 'iad.ocir.io', 'ROTATION_CA': '-----BEGIN CERTIFICATE-----\npublic-ca\n-----END CERTIFICATE-----'}
        calls = []
        docker_config = []
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'scripts').mkdir()
            bundle = root / 'bundle/functions/vault_rotation'
            bundle.mkdir(parents=True)
            (bundle / 'Dockerfile').write_text('FROM python:3.12-slim\nUSER 10001\n')

            def run(args, **kwargs):
                calls.append((args, kwargs.get('stdin')))
                docker_config.append(kwargs['env']['DOCKER_CONFIG'])
                if args[1] == 'build':
                    context = Path(args[-1])
                    self.assertEqual((context / 'certs/postgresql-ca.pem').read_text(), env['ROTATION_CA'])
                    self.assertIn('COPY certs/postgresql-ca.pem', (context / 'Dockerfile').read_text())
                return ''

            with patch.dict(os.environ, env), patch.object(runner, '__file__', str(root / 'scripts/runner.py')), \
                    patch.object(runner, 'raw', return_value=({'token': 'short-lived-test-token'}, {})), \
                    patch.object(runner, 'run', side_effect=run):
                runner.build()
        self.assertNotIn('short-lived-test-token', json.dumps([c[0] for c in calls]))
        self.assertEqual(calls[1][1], 'short-lived-test-token')
        self.assertTrue(all(not Path(p).exists() for p in docker_config))
