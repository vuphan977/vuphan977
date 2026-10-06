import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location('regression_app',Path(__file__).parents[1]/'server.py')
app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)

class Regressions(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();app.DB=Path(self.tmp.name)/'app.db';app.init()
        app.authenticate(dict(email='regression@example.com',password='regression-password',name='Owner'),True)
    def tearDown(self):self.tmp.cleanup()
    def invoice(self,**kwargs):
        data=dict(room_id=1,month='2026-10',electric_old=0,electric_new=50,water_old=0,water_new=5,electric_rate=3500,water_rate=15000,fee=100000)
        data.update(kwargs);app.mutate('/api/invoices',data,1)
    def test_required_text_rejects_non_string(self):
        for value in [None,{},[],123]:
            with self.subTest(value=value),self.assertRaises(ValueError):
                app.mutate('/api/rooms',dict(name=value,rent=1),1)
    def test_invoice_snapshot_survives_tenant_change(self):
        self.invoice()
        app.mutate('/api/contracts',dict(room_id=1,tenant='Next tenant',phone='0123',start='2027-01-01',end='2027-12-31',deposit=0),1)
        with app.connect() as db:
            invoice=dict(db.execute('SELECT * FROM invoices').fetchone())
            self.assertEqual(invoice['tenant_name'],'Nguyễn Minh Anh')
            self.assertEqual(invoice['room_name'],'P.101')
    def test_payment_retry_is_idempotent(self):
        self.invoice()
        data=dict(id=1,amount=1000000,request_key='test-payment-unique-key')
        app.mutate('/api/payments',data,1);app.mutate('/api/payments',data,1)
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT paid FROM invoices').fetchone()[0],1000000)
            self.assertEqual(db.execute('SELECT count(*) FROM payments').fetchone()[0],1)
        with self.assertRaises(ValueError):app.mutate('/api/payments',{**data,'amount':2000000},1)
    def test_invoice_outside_contract_rejected(self):
        with self.assertRaises(ValueError):self.invoice(month='2027-01')
    def test_invoice_total_is_payable(self):
        with self.assertRaises(ValueError):self.invoice(electric_new=1000000000,electric_rate=1000000000)
    def test_fake_backup_does_not_overwrite_database(self):
        fake=Path(self.tmp.name)/'fake.db'
        with sqlite3.connect(fake) as db:
            for table in ['rooms','invoices','repairs','users','sessions','payments']:
                db.execute(f'CREATE TABLE {table}(junk TEXT)')
        with self.assertRaises(ValueError):app.restore(fake)
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM rooms').fetchone()[0],12)
            self.assertEqual(db.execute('SELECT count(*) FROM users').fetchone()[0],1)

if __name__=='__main__':unittest.main()
