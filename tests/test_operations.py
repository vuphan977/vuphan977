import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('operations',Path(__file__).parents[1]/'server.py')
app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)

class Operations(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();app.DB=Path(self.tmp.name)/'app.db';app.init()
        app.authenticate(dict(name='A',email='a@example.com',password='owner-password-a'),True)
        app.authenticate(dict(name='B',email='b@example.com',password='owner-password-b'),True)
    def tearDown(self):self.tmp.cleanup()
    def activate(self,**extra):
        with app.connect() as db:r=dict(db.execute('SELECT * FROM rooms WHERE id=1').fetchone())
        self.contract=dict(room_id=1,tenant=r['tenant'],phone=r['phone'],start=r['start'],end=r['end'],deposit=r['deposit'])
        return app.mutate('/api/contracts',{**self.contract,**extra},1)
    def invoice(self):app.mutate('/api/invoices',dict(room_id=1,month='2026-10',electric_old=0,electric_new=50,water_old=0,water_new=5),1)
    def test_auto_account_credentials_and_hash(self):
        credentials=self.activate()['credentials']
        self.assertIn('p-101',credentials['login_name']);self.assertGreaterEqual(len(credentials['password']),20)
        app.authenticate(dict(email=credentials['login_name'],password=credentials['password']))
        with app.connect() as db:
            u=dict(db.execute('SELECT * FROM users WHERE login_name=?',(credentials['login_name'],)).fetchone())
            self.assertEqual(u['role'],'tenant');self.assertEqual(u['managed_owner_id'],1);self.assertEqual(u['managed_room_id'],1)
            self.assertNotEqual(u['password_hash'],credentials['password'])
            self.assertEqual(u['password_hash'],app.password_hash(credentials['password'],u['salt']))
        self.assertIsNone(app.mutate('/api/contracts',self.contract,1))
    def test_next_contract_does_not_reuse_account_or_invoices(self):
        first=self.activate()['credentials'];self.invoice()
        second=app.mutate('/api/contracts',{**self.contract,'tenant':'Next person'},1)['credentials']
        self.assertNotEqual(first['login_name'],second['login_name'])
        with app.connect() as db:
            old=db.execute('SELECT id FROM users WHERE login_name=?',(first['login_name'],)).fetchone()[0]
            new=db.execute('SELECT tenant_user_id FROM rooms WHERE id=1').fetchone()[0]
            self.assertNotEqual(old,new);self.assertEqual(db.execute('SELECT tenant_user_id FROM invoices').fetchone()[0],old)
    def test_room_reset_password_owner_scope(self):
        first=self.activate()['credentials'];app.authenticate(dict(email=first['login_name'],password=first['password']))
        with self.assertRaises(ValueError):app.mutate('/api/tenant-password-reset',dict(room_id=1,confirmation='P.101'),2)
        with self.assertRaises(ValueError):app.mutate('/api/tenant-password-reset',dict(room_id=1,confirmation='wrong'),1)
        second=app.mutate('/api/tenant-password-reset',dict(room_id=1,confirmation='P.101'),1)['credentials']
        self.assertEqual(first['login_name'],second['login_name'])
        with self.assertRaises(ValueError):app.authenticate(dict(email=first['login_name'],password=first['password']))
        app.authenticate(dict(email=second['login_name'],password=second['password']))
    def test_reset_recreate_account_does_not_collide(self):
        first=self.activate()['credentials']
        app.mutate('/api/reset',dict(confirmation='XÓA DỮ LIỆU',password='owner-password-a'),1)
        app.mutate('/api/rooms',dict(name='P.101',rent=3000000),1)
        with app.connect() as db:rid=db.execute('SELECT id FROM rooms').fetchone()[0]
        second=app.mutate('/api/contracts',{**self.contract,'room_id':rid},1)['credentials']
        self.assertNotEqual(first['login_name'],second['login_name'])
    def test_void_keeps_journal_restores_debt_and_is_idempotent(self):
        self.activate();self.invoice();app.mutate('/api/payments',dict(id=1,amount=1000000,request_key='receipt-to-void'),1)
        with self.assertRaises(ValueError):app.mutate('/api/payment-void',dict(id=1,reason='Recorded twice'),2)
        with self.assertRaises(ValueError):app.mutate('/api/payment-void',dict(id=1,reason=''),1)
        app.mutate('/api/payment-void',dict(id=1,reason='Recorded twice'),1);app.mutate('/api/payment-void',dict(id=1,reason='Recorded twice'),1)
        with app.connect() as db:
            p=dict(db.execute('SELECT * FROM payments').fetchone());self.assertEqual(p['amount'],1000000);self.assertEqual(p['voided'],1);self.assertEqual(p['void_reason'],'Recorded twice')
            self.assertEqual(db.execute('SELECT paid FROM invoices').fetchone()[0],0)
        with self.assertRaises(ValueError):app.mutate('/api/payments',dict(id=1,amount=1000000,request_key='receipt-to-void'),1)
    def test_end_preserves_history_debt_and_old_tenant(self):
        c=self.activate()['credentials'];self.invoice()
        data=dict(id=1,confirmation='P.101',ended=str(app.business_today()),reason='Moved away')
        with self.assertRaises(ValueError):app.mutate('/api/contract-end',data,1)
        app.mutate('/api/contract-end',{**data,'allow_debt':1},1)
        with app.connect() as db:
            r=dict(db.execute('SELECT * FROM rooms WHERE id=1').fetchone());self.assertEqual(r['tenant'],'');self.assertIsNone(r['tenant_user_id']);self.assertEqual(r['people'],1)
            h=dict(db.execute('SELECT * FROM contract_history').fetchone());self.assertEqual(h['tenant'],'Nguyễn Minh Anh');self.assertEqual(h['deposit'],3000000)
            self.assertEqual(db.execute('SELECT total-paid FROM invoices').fetchone()[0],3150000)
            self.assertIsNotNone(db.execute('SELECT tenant_user_id FROM invoices').fetchone()[0])
        app.authenticate(dict(email=c['login_name'],password=c['password']))
    def test_room_account_cannot_claim_other_room(self):
        c=self.activate()['credentials'];invite=app.mutate('/api/tenant-invite',dict(room_id=2),1)['invite_token']
        with app.connect() as db:
            uid=db.execute('SELECT id FROM users WHERE login_name=?',(c['login_name'],)).fetchone()[0]
            with self.assertRaises(ValueError):app.claim_invitation(db,app.valid_invitation(db,invite),uid)
    def test_reminder_interval_invalid_configuration(self):
        for value in ['nan','0','301','1.5','invalid']:
            with patch.dict(app.os.environ,{'REMINDER_INTERVAL':value}),self.assertRaises(ValueError):app.reminder_interval()
        with patch.dict(app.os.environ,{'REMINDER_INTERVAL':'60'}):self.assertEqual(app.reminder_interval(),60)

if __name__=='__main__':unittest.main()
