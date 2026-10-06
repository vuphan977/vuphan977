import importlib.util
import tempfile
import unittest
from pathlib import Path
import sqlite3

spec = importlib.util.spec_from_file_location('app', Path(__file__).parents[1]/'server.py')
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

class Workflow(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        app.DB=Path(self.tmp.name)/'test.db'
        app.init()
        app.authenticate(dict(email="owner@example.com",password="secure-test-123",name="Owner"),register=True)
    def tearDown(self): self.tmp.cleanup()
    def mutate(self,path,data):
        return app.mutate(path,data,1)
    def invoice(self, **kwargs):
        data=dict(room_id=1,month='2026-10',electric_old=100,electric_new=150,water_old=10,water_new=15,electric_rate=3500,water_rate=15000,fee=100000)
        data.update(kwargs)
        self.mutate('/api/invoices',data)
    def test_billing_and_partial_payment(self):
        self.invoice()
        with app.connect() as db: i=dict(db.execute('SELECT * FROM invoices').fetchone())
        self.assertEqual(i['total'],3150000)
        self.mutate('/api/payments',dict(id=i['id'],amount=1000000))
        with app.connect() as db: self.assertEqual(db.execute('SELECT total-paid FROM invoices').fetchone()[0],2150000)
        self.mutate('/api/payments',dict(id=i['id'],amount=2150000))
        with app.connect() as db: self.assertEqual(db.execute('SELECT total-paid FROM invoices').fetchone()[0],0)
        with self.assertRaises(ValueError): self.mutate('/api/payments',dict(id=i['id'],amount=1))
    def test_invalid_readings_and_duplicate(self):
        with self.assertRaises(ValueError): self.invoice(electric_new=99)
        with self.assertRaises(ValueError): self.invoice(water_new=9)
        self.invoice()
        with self.assertRaises(sqlite3.IntegrityError): self.invoice()
    def test_room_contract_repair(self):
        self.mutate('/api/rooms',dict(name='P.201',rent=4000000))
        with app.connect() as db: rid=db.execute("SELECT id FROM rooms WHERE name='P.201'").fetchone()[0]
        with self.assertRaises(ValueError): self.invoice(room_id=rid)
        self.mutate('/api/contracts',dict(room_id=rid,tenant='Khách mới',phone='0909999999',start='2026-10-01',end='2027-10-01',deposit=4000000))
        self.invoice(room_id=rid)
        self.mutate('/api/repairs',dict(room_id=rid,description='Vòi nước bị rò'))
        self.mutate('/api/repair-status',dict(id=1,status='Hoàn tất'))
        with app.connect() as db: self.assertEqual(db.execute('SELECT status FROM repairs').fetchone()[0],'Hoàn tất')
    def test_restart_preserves_data(self):
        self.invoice()
        app.init()
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM rooms').fetchone()[0],12)
            self.assertEqual(db.execute('SELECT count(*) FROM invoices').fetchone()[0],1)

if __name__=='__main__': unittest.main()
