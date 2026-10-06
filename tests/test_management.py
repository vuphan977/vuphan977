import importlib.util
import tempfile
import unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location('management',Path(__file__).parents[1]/'server.py')
app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)

class Management(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();app.DB=Path(self.tmp.name)/'app.db';app.init()
        app.authenticate(dict(name='A',email='a@example.com',password='owner-password-a'),True)
        app.authenticate(dict(name='B',email='b@example.com',password='owner-password-b'),True)
        self.base=dict(month='2026-10',electric_rate=3500,water_rate=15000,fee=100000)
        self.readings=dict(electric_old=0,electric_new=50,water_old=0,water_new=5)
    def tearDown(self):self.tmp.cleanup()
    def invoice(self,rid=1):app.mutate('/api/invoices',{**self.base,**self.readings,'room_id':rid},1)
    def test_delete_cascades_and_requires_confirmation(self):
        self.invoice();app.mutate('/api/payments',dict(id=1,amount=1000),1);app.mutate('/api/repairs',dict(room_id=1,description='Leak'),1)
        with self.assertRaises(ValueError):app.mutate('/api/room-delete',dict(id=1,confirmation='wrong'),1)
        with self.assertRaises(ValueError):app.mutate('/api/room-delete',dict(id=1,confirmation='P.101'),2)
        app.mutate('/api/room-delete',dict(id=1,confirmation='P.101'),1)
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM rooms').fetchone()[0],11)
            for table in ['invoices','payments','repairs']:self.assertEqual(db.execute(f'SELECT count(*) FROM {table}').fetchone()[0],0)
    def test_reset_isolated_authenticated_and_not_reseeded(self):
        self.invoice();app.mutate('/api/rooms',dict(name='B room',rent=100),2)
        for data in [dict(confirmation='wrong',password='owner-password-a'),dict(confirmation='XÓA DỮ LIỆU',password='wrong-password')]:
            with self.assertRaises(ValueError):app.mutate('/api/reset',data,1)
        with app.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM rooms WHERE owner_id=1').fetchone()[0],12)
        app.mutate('/api/reset',dict(confirmation='XÓA DỮ LIỆU',password='owner-password-a'),1)
        app.init()
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM rooms WHERE owner_id=1').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM rooms WHERE owner_id=2').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM users').fetchone()[0],2)
            self.assertEqual(db.execute('SELECT count(*) FROM invoices').fetchone()[0],0)
    def test_room_edit_preserves_old_invoice_price_and_name(self):
        self.invoice()
        app.mutate('/api/room-update',dict(id=1,name='New name',rent=5000000),1)
        with app.connect() as db:
            inv=dict(db.execute('SELECT * FROM invoices').fetchone())
            self.assertEqual(inv['rent'],2800000);self.assertEqual(inv['room_name'],'P.101')
        with self.assertRaises(ValueError):app.mutate('/api/room-update',dict(id=1,name='Attack',rent=0),2)
    def test_batch_works_and_rejects_cross_owner(self):
        app.mutate('/api/invoices-batch',{**self.base,'items':[{**self.readings,'room_id':1},{**self.readings,'room_id':2}]},1)
        with app.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM invoices').fetchone()[0],2)
        with self.assertRaises(ValueError):app.mutate('/api/invoices-batch',{**self.base,'items':[{**self.readings,'room_id':3}]},2)
    def test_batch_rolls_back_entire_month_on_invalid_room(self):
        with self.assertRaises(ValueError):app.mutate('/api/invoices-batch',{**self.base,'items':[{**self.readings,'room_id':1},{**self.readings,'room_id':12}]},1)
        with app.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM invoices').fetchone()[0],0)
    def test_batch_duplicate_rolls_back_only_new_records(self):
        self.invoice()
        with self.assertRaises(Exception) as caught:
            app.mutate('/api/invoices-batch',{**self.base,'items':[{**self.readings,'room_id':2},{**self.readings,'room_id':1}]},1)
        import sqlite3
        self.assertIsInstance(caught.exception,sqlite3.IntegrityError)
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM invoices').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT room_id FROM invoices').fetchone()[0],1)
    def test_batch_200_rooms(self):
        items=[]
        with app.connect() as db:
            for n in range(200):
                rid=db.execute("INSERT INTO rooms(name,rent,tenant,start,end,owner_id) VALUES(?,3000000,'Tenant','2026-01-01','2027-01-01',1)",(f'Bulk.{n}',)).lastrowid
                items.append({**self.readings,'room_id':rid})
        app.mutate('/api/invoices-batch',{**self.base,'items':items},1)
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM invoices').fetchone()[0],200)
            self.assertEqual(db.execute('SELECT sum(total) FROM invoices').fetchone()[0],200*3350000)

    def test_batch_size_and_types(self):
        for items in [[],None,[None],[{**self.readings,'room_id':1}]*201]:
            with self.assertRaises(ValueError):app.mutate('/api/invoices-batch',{**self.base,'items':items},1)

if __name__=='__main__':unittest.main()
