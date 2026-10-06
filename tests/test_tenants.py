import importlib.util
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('tenants',Path(__file__).parents[1]/'server.py')
app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)

class Tenants(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();app.DB=Path(self.tmp.name)/'app.db';app.init()
        app.authenticate(dict(name='Owner',email='owner@example.com',password='owner-password-123'),True)
        app.authenticate(dict(name='Other',email='other@example.com',password='other-password-123'),True)
    def tearDown(self):self.tmp.cleanup()
    def invite(self):return app.mutate('/api/tenant-invite',dict(room_id=1),1)['invite_token']
    def tenant(self,token=None):
        return app.authenticate(dict(name='Tenant',email='tenant@example.com',password='tenant-password-123'),True,tenant_invite=token or self.invite())
    def invoice(self,**extra):app.mutate('/api/invoices',dict(room_id=1,month='2026-10',electric_old=100,electric_new=150,water_old=10,water_new=15,**extra),1)
    def test_water_per_person_and_snapshot(self):
        app.mutate('/api/room-billing',dict(id=1,people=3,water_mode='person',water_rate=100000,electric_rate=4000,service_fee=50000),1)
        self.invoice()
        with app.connect() as db:
            i=dict(db.execute('SELECT * FROM invoices').fetchone())
            self.assertEqual(i['water_total'],300000);self.assertEqual(i['total'],3350000)
            self.assertEqual(i['people'],3);self.assertEqual(i['water_mode'],'person')
        app.mutate('/api/room-billing',dict(id=1,people=5,water_rate=200000),1)
        with app.connect() as db:self.assertEqual(db.execute('SELECT water_total FROM invoices').fetchone()[0],300000)
    def test_meter_and_due_day_clamps_to_month(self):
        app.mutate('/api/room-billing',dict(id=1,due_day=31),1)
        self.invoice()
        with app.connect() as db:
            i=dict(db.execute('SELECT * FROM invoices').fetchone());self.assertEqual(i['water_total'],75000);self.assertEqual(i['due_date'],'2026-10-31')
        app.mutate('/api/invoices',dict(room_id=1,month='2026-02',electric_old=0,electric_new=0,water_old=0,water_new=0),1)
        with app.connect() as db:self.assertEqual(db.execute("SELECT due_date FROM invoices WHERE month='2026-02'").fetchone()[0],'2026-02-28')
    def test_settings_validation_and_owner_scope(self):
        for data in [dict(people=0),dict(people=51),dict(due_day=0),dict(remind_days=31),dict(water_mode='unknown'),dict(auto_send=2)]:
            with self.assertRaises(ValueError):app.mutate('/api/room-billing',dict(id=1,**data),1)
        with self.assertRaises(ValueError):app.mutate('/api/room-billing',dict(id=1,people=2),2)
        with self.assertRaises(ValueError):app.mutate('/api/tenant-invite',dict(room_id=1),2)
    def test_invitation_one_use_hashed_and_sets_role(self):
        invite=self.invite()
        with app.connect() as db:self.assertNotEqual(db.execute('SELECT token_hash FROM invitations').fetchone()[0],invite)
        self.tenant(invite)
        with app.connect() as db:
            self.assertEqual(db.execute("SELECT role FROM users WHERE email='tenant@example.com'").fetchone()[0],'tenant')
            self.assertEqual(db.execute('SELECT tenant_user_id FROM rooms WHERE id=1').fetchone()[0],3)
            self.assertEqual(db.execute('SELECT count(*) FROM invitations').fetchone()[0],0)
        with self.assertRaises(ValueError):app.authenticate(dict(name='Attack',email='attack@example.com',password='attack-password-123'),True,tenant_invite=invite)
    def test_expired_and_replaced_invites_rejected(self):
        old=self.invite();new=self.invite()
        with self.assertRaises(ValueError):self.tenant(old)
        with app.connect() as db:db.execute('UPDATE invitations SET expires=0')
        with self.assertRaises(ValueError):self.tenant(new)
        with app.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM users').fetchone()[0],2)
    def test_new_invoice_published_and_reminded_once(self):
        self.tenant();self.invoice()
        app.run_reminders(date(2026,10,1))
        with app.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM notifications').fetchone()[0],1)
        app.run_reminders(date(2026,10,2));app.run_reminders(date(2026,10,5));app.run_reminders(date(2026,10,15))
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM notifications').fetchone()[0],2)
            self.assertEqual(db.execute("SELECT count(*) FROM notifications WHERE kind='reminder'").fetchone()[0],1)
    def test_paid_invoice_has_no_reminder(self):
        self.tenant();self.invoice();app.mutate('/api/payments',dict(id=1,amount=3150000),1);app.run_reminders(date(2026,10,8))
        with app.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM notifications').fetchone()[0],1)
    def test_manual_publish_setting(self):
        app.mutate('/api/room-billing',dict(id=1,auto_send=0),1);self.tenant();self.invoice();app.run_reminders(date(2026,10,8))
        with app.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM notifications').fetchone()[0],0)
        app.mutate('/api/invoice-send',dict(id=1),1);app.mutate('/api/invoice-send',dict(id=1),1);app.run_reminders(date(2026,10,8))
        with app.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM notifications').fetchone()[0],2)
    def test_tenant_change_does_not_expose_new_invoices(self):
        self.tenant();self.invoice()
        app.mutate('/api/contracts',dict(room_id=1,tenant='Next tenant',phone='0900',start='2026-11-01',end='2027-11-01',deposit=0),1)
        app.mutate('/api/invoices',dict(room_id=1,month='2026-11',electric_old=150,electric_new=200,water_old=15,water_new=20),1)
        with app.connect() as db:
            self.assertIsNone(db.execute('SELECT tenant_user_id FROM rooms WHERE id=1').fetchone()[0])
            self.assertEqual(db.execute('SELECT count(*) FROM invoices WHERE tenant_user_id=3').fetchone()[0],1)
    def test_same_name_new_contract_does_not_claim_old_invoice(self):
        self.invoice()
        app.mutate('/api/contracts',dict(room_id=1,tenant='Nguyễn Minh Anh',phone='0909999999',start='2026-11-01',end='2027-11-01',deposit=0),1)
        self.tenant()
        with app.connect() as db:self.assertIsNone(db.execute('SELECT tenant_user_id FROM invoices').fetchone()[0])

    def test_migration_repeat_keeps_settings_and_invoice_breakdown(self):
        app.mutate('/api/room-billing',dict(id=1,water_mode='person',people=3),1);self.invoice();app.init()
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT water_mode FROM rooms WHERE id=1').fetchone()[0],'person')
            self.assertEqual(db.execute('SELECT water_total FROM invoices').fetchone()[0],45000)

if __name__=='__main__':unittest.main()
