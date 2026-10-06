import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('deployment_server', ROOT / 'server.py')
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)
worker_spec = importlib.util.spec_from_file_location('backup_worker', ROOT / 'deploy/backup_worker.py')
worker = importlib.util.module_from_spec(worker_spec)
worker_spec.loader.exec_module(worker)


class Deployment(unittest.TestCase):
    def test_operator_password_recovery_revokes_sessions(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(app,'DB',Path(tmp)/'app.db'):
            app.init()
            app.authenticate({'name':'Owner','email':'owner@example.com','password':'old-owner-password'},True)
            app.reset_owner_password('owner@example.com','new-owner-password')
            with app.connect() as db:
                self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0],0)
            with self.assertRaises(ValueError):
                app.authenticate({'email':'owner@example.com','password':'old-owner-password'})
            app.authenticate({'email':'owner@example.com','password':'new-owner-password'})
            with self.assertRaises(ValueError):
                app.reset_owner_password('missing@example.com','new-owner-password')

    def test_proxy_headers_cannot_bypass_direct_login_limit(self):
        with patch.dict(app.os.environ, {'TRUSTED_PROXY_CIDRS': ''}):
            self.assertEqual(app.client_ip('192.0.2.1', '198.51.100.1'), '192.0.2.1')

    def test_only_internal_proxy_supplies_actual_client(self):
        with patch.dict(app.os.environ, {'TRUSTED_PROXY_CIDRS': '172.30.8.0/24'}):
            self.assertEqual(app.client_ip('172.30.8.3', 'spoofed, 198.51.100.1'), '198.51.100.1')
            self.assertEqual(app.client_ip('172.30.8.3', 'invalid'), '172.30.8.3')
            self.assertEqual(app.client_ip('192.0.2.1', '198.51.100.1'), '192.0.2.1')

    def test_production_initialization_and_rotating_restore(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(app.os.environ, {'SEED_DEMO': '0'}):
            with patch.object(app, 'DB', Path(tmp) / 'app.db'), patch.object(worker, 'server', app):
                app.init()
                with app.connect() as db:
                    self.assertEqual(db.execute('SELECT count(*) FROM rooms').fetchone()[0], 0)
                app.authenticate({'name': 'Owner', 'email': 'owner@example.com', 'password': 'test-owner-password'}, True)
                app.mutate('/api/rooms', {'name': 'Room 1', 'rent': 3000000}, 1)
                unrelated = Path(tmp) / 'backups' / 'roomly-manual.db'
                app.backup(unrelated)
                worker.snapshot(2)
                worker.snapshot(2)
                latest = worker.snapshot(2)
                self.assertEqual(len(list(latest.parent.glob('roomly-*.db'))), 3)
                self.assertTrue(unrelated.is_file())
                self.assertEqual(latest.stat().st_mode & 0o777, 0o600)
                with app.connect() as db:
                    db.execute('DELETE FROM rooms')
                app.restore(latest)
                with app.connect() as db:
                    self.assertEqual(db.execute('SELECT name FROM rooms').fetchone()[0], 'Room 1')
                    self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0], 0)
