import concurrent.futures
import http.cookiejar
import importlib.util
import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

spec=importlib.util.spec_from_file_location('secure_app',Path(__file__).parents[1]/'server.py')
app=importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

class Security(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        app.DB=Path(self.tmp.name)/'app.db'
        app.init()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}'
        self.a=self.client();self.b=self.client()
        self.request(self.a,'/api/register',dict(name='A',email='a@example.com',password='very-secure-123'))
        self.request(self.b,'/api/register',dict(name='B',email='b@example.com',password='very-secure-456'))
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
    def client(self):return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def request(self,client,path,data=None,headers=None):
        req=urllib.request.Request(self.url+path,data=json.dumps(data).encode() if data is not None else None,headers=headers if headers is not None else {'Content-Type':'application/json','X-Requested-With':'Roomly'})
        try:
            with client.open(req) as res:return res.status,json.load(res)
        except urllib.error.HTTPError as err:return err.code,json.load(err)
    def invoice(self):
        data=dict(room_id=1,month='2026-10',electric_old=0,electric_new=50,water_old=0,water_new=5,electric_rate=3500,water_rate=15000,fee=100000)
        self.assertEqual(self.request(self.a,'/api/invoices',data)[0],200)
    def test_authentication_cookie_logout(self):
        self.assertEqual(self.request(self.client(),'/api/state')[0],401)
        self.assertEqual(self.request(self.client(),'/api/login',dict(email='a@example.com',password='incorrect-123'))[0],400)
        self.assertEqual(self.request(self.a,'/api/me')[1]['user']['name'],'A')
        self.assertEqual(self.request(self.a,'/api/logout',{})[0],200)
        self.assertEqual(self.request(self.a,'/api/state')[0],401)
        self.assertEqual(self.request(self.a,'/api/login',dict(email='a@example.com',password='very-secure-123'))[0],200)
    def test_csrf(self):
        self.assertEqual(self.request(self.a,'/api/rooms',dict(name='X',rent=10),headers={'Content-Type':'application/json'})[0],403)
        self.assertEqual(self.request(self.a,'/api/rooms',dict(name='X',rent=10),headers={'X-Requested-With':'Roomly','Origin':'https://evil.example'})[0],403)
    def test_owner_isolation_every_write_and_export(self):
        self.invoice()
        self.request(self.a,'/api/repairs',dict(room_id=1,description='Leak'))
        self.assertEqual(self.request(self.b,'/api/state')[1]['rooms'],[])
        self.assertEqual(self.request(self.b,'/api/export')[1]['data']['invoices'],[])
        for route,data in [('/api/contracts',dict(room_id=1,tenant='Attack',start='2026-01-01',end='2027-01-01')),('/api/invoices',dict(room_id=1)),('/api/payments',dict(id=1,amount=1)),('/api/repairs',dict(room_id=1,description='Attack')),('/api/repair-status',dict(id=1,status='Hoàn tất'))]:
            self.assertEqual(self.request(self.b,route,data)[0],400,route)
        self.assertEqual(self.request(self.b,'/api/rooms',dict(name='P.101',rent=1))[0],200)
        self.assertEqual(len(self.request(self.a,'/api/state')[1]['rooms']),12)
        self.assertEqual(len(self.request(self.b,'/api/state')[1]['rooms']),1)
    def test_concurrent_receipts_do_not_overpay(self):
        self.invoice()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            codes=list(pool.map(lambda _:self.request(self.a,'/api/payments',dict(id=1,amount=2000000))[0],range(2)))
        self.assertEqual(sorted(codes),[200,400])
        state=self.request(self.a,'/api/state')[1]
        self.assertEqual(state['invoices'][0]['paid'],2000000)
        self.assertEqual(len(state['payments']),1)
        self.assertEqual(state['payments'][0]['amount'],2000000)
    def test_backup_restore(self):
        self.invoice()
        backup=Path(self.tmp.name)/'snapshot.db'
        app.backup(backup)
        self.request(self.a,'/api/payments',dict(id=1,amount=100))
        app.restore(backup)
        self.assertEqual(self.request(self.a,'/api/state')[0],401)
        self.request(self.a,'/api/login',dict(email='a@example.com',password='very-secure-123'))
        self.assertEqual(self.request(self.a,'/api/state')[1]['invoices'][0]['paid'],0)
        self.assertTrue(list(Path(self.tmp.name).glob('*.bak')))
    def test_tenant_http_access_and_report_scope(self):
        self.invoice()
        code,invitation=self.request(self.a,'/api/tenant-invite',dict(room_id=1))
        self.assertEqual(code,200)
        tenant=self.client()
        code,_=self.request(tenant,'/api/tenant-register',dict(invite_token=invitation['invite_token'],name='Tenant',email='tenant@example.com',password='tenant-password-123'))
        self.assertEqual(code,200)
        self.assertEqual(self.request(tenant,'/api/me')[1]['user']['role'],'tenant')
        state=self.request(tenant,'/api/state')[1]
        self.assertEqual(len(state['rooms']),1);self.assertEqual(len(state['invoices']),1);self.assertEqual(len(state['notifications']),1)
        for route,data in [('/api/payments',dict(id=1,amount=1)),('/api/room-delete',dict(id=1,confirmation='P.101')),('/api/reset',dict(confirmation='XÓA DỮ LIỆU',password='tenant-password-123')),('/api/rooms',dict(name='Attack',rent=1)),('/api/room-billing',dict(id=1,people=10))]:
            self.assertEqual(self.request(tenant,route,data)[0],403,route)
        self.assertEqual(self.request(tenant,'/api/export')[0],403)
        self.assertEqual(self.request(tenant,'/api/repairs',dict(room_id=2,description='Attack'))[0],400)
        self.assertEqual(self.request(tenant,'/api/repairs',dict(room_id=1,description='Tenant report'))[0],200)
        self.assertEqual(len(self.request(tenant,'/api/state')[1]['repairs']),1)
        self.assertEqual(self.request(tenant,'/api/notification-read',dict(id=state['notifications'][0]['id']))[0],200)
        self.assertEqual(self.request(tenant,'/api/notification-read',dict(id=999))[0],400)
        self.request(self.a,'/api/contracts',dict(room_id=1,tenant='Next person',phone='0901',start='2027-01-01',end='2027-12-31',deposit=0))
        old=self.request(tenant,'/api/state')[1]
        self.assertEqual(len(old['rooms']),0);self.assertEqual(len(old['invoices']),1);self.assertEqual(len(old['repairs']),0)

    def test_password_rotation_revokes_all_sessions(self):
        extra=self.client()
        self.assertEqual(self.request(extra,'/api/login',dict(email='a@example.com',password='very-secure-123'))[0],200)
        self.assertEqual(self.request(self.a,'/api/password-change',dict(current_password='incorrect-123',new_password='replacement-password'))[0],400)
        self.assertEqual(self.request(self.a,'/api/state')[0],200)
        self.assertEqual(self.request(self.a,'/api/password-change',dict(current_password='very-secure-123',new_password='replacement-password'))[0],200)
        self.assertEqual(self.request(self.a,'/api/state')[0],401);self.assertEqual(self.request(extra,'/api/state')[0],401)
        self.assertEqual(self.request(extra,'/api/login',dict(email='a@example.com',password='very-secure-123'))[0],400)
        self.assertEqual(self.request(extra,'/api/login',dict(email='a@example.com',password='replacement-password'))[0],200)
        self.assertEqual(self.request(self.b,'/api/state')[0],200)
    def test_auto_room_login_and_bank_profile_scope(self):
        code,data=self.request(self.a,'/api/contracts',dict(room_id=1,tenant='Room account',phone='090123',start='2026-01-01',end='2026-12-31',deposit=0))
        self.assertEqual(code,200);credentials=data['credentials'];tenant=self.client()
        self.assertEqual(self.request(tenant,'/api/login',dict(email=credentials['login_name'],password=credentials['password']))[0],200)
        self.assertEqual(self.request(tenant,'/api/me')[1]['user']['role'],'tenant')
        self.request(self.a,'/api/payment-profile',dict(bank='970436',account='123456789',holder='OWNER A'))
        self.request(self.b,'/api/payment-profile',dict(bank='970436',account='999999999',holder='OWNER B'))
        self.invoice()
        profiles=self.request(tenant,'/api/state')[1]['payment_profiles']
        self.assertEqual(len(profiles),1);self.assertEqual(profiles[0]['holder'],'OWNER A')
        self.assertEqual(self.request(tenant,'/api/payment-profile',dict(bank='970436',account='888888888',holder='Attack'))[0],403)
        self.assertEqual(self.request(tenant,'/api/tenant-password-reset',dict(room_id=1,confirmation='P.101'))[0],403)
        new=self.request(self.a,'/api/tenant-password-reset',dict(room_id=1,confirmation='P.101'))[1]['credentials']
        self.assertEqual(self.request(tenant,'/api/state')[0],401)
        self.assertEqual(self.request(tenant,'/api/login',dict(email=new['login_name'],password=new['password']))[0],200)
    def test_owner_cannot_reset_personal_tenant_password(self):
        invite=self.request(self.a,'/api/tenant-invite',dict(room_id=1))[1]['invite_token']
        tenant=self.client()
        self.request(tenant,'/api/tenant-register',dict(invite_token=invite,name='Personal',email='personal@example.com',password='personal-password-123'))
        self.assertEqual(self.request(self.a,'/api/tenant-password-reset',dict(room_id=1,confirmation='P.101'))[0],400)
        self.assertEqual(self.request(tenant,'/api/password-change',dict(current_password='personal-password-123',new_password='personal-password-new'))[0],200)
        self.assertEqual(self.request(self.a,'/api/state')[0],200)

    def test_expired_and_forged_sessions(self):
        with app.connect() as db: db.execute('UPDATE sessions SET expires=0 WHERE user_id=1')
        self.assertEqual(self.request(self.a,'/api/state')[0],401)
        self.assertEqual(self.request(self.client(),'/api/state',headers={'Cookie':'roomly_session=forged'})[0],401)
    def test_cookie_flags_and_malformed_requests(self):
        req=urllib.request.Request(self.url+'/api/login',data=json.dumps(dict(email='a@example.com',password='very-secure-123')).encode(),headers={'X-Requested-With':'Roomly'})
        with self.a.open(req) as res:
            cookie=res.headers['Set-Cookie']
            self.assertIn('HttpOnly',cookie);self.assertIn('SameSite=Strict',cookie)
            self.assertEqual(res.headers['Cache-Control'],'no-store')
        self.assertEqual(self.request(self.a,'/api/rooms',dict(name='X',rent=10),headers={'X-Requested-With':'Roomly','Origin':'http://['})[0],403)
        self.assertEqual(self.request(self.a,'/api/rooms',[],headers={'X-Requested-With':'Roomly'})[0],400)
        self.assertEqual(self.request(self.a,'/api/rooms',{'name':'X'*20001,'rent':1})[0],400)
    def test_concurrent_identical_retry(self):
        self.invoice()
        data=dict(id=1,amount=1000000,request_key='concurrent-retry-key')
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            codes=list(pool.map(lambda _:self.request(self.a,'/api/payments',data)[0],range(4)))
        self.assertEqual(codes,[200]*4)
        state=self.request(self.a,'/api/state')[1]
        self.assertEqual(state['invoices'][0]['paid'],1000000)
        self.assertEqual(len(state['payments']),1)

    def test_password_storage_and_throttle(self):
        with app.connect() as db:
            user=dict(db.execute('SELECT * FROM users WHERE id=1').fetchone())
            self.assertNotEqual(user['password_hash'],'very-secure-123')
            self.assertEqual(len(user['salt']),32)
        for _ in range(8):self.request(self.client(),'/api/login',dict(email='a@example.com',password='incorrect-123'))
        code,data=self.request(self.client(),'/api/login',dict(email='a@example.com',password='very-secure-123'))
        self.assertEqual(code,400)
        self.assertIn('15 phút',data['error'])


    def test_fractional_money_rejected(self):
        for value in [1.5, True, -1, '1.5']:
            self.assertEqual(self.request(self.a,'/api/rooms',dict(name='Invalid',rent=value))[0],400)

class Migration(unittest.TestCase):
    def test_legacy_data_preserved_and_claimed_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            app.DB=Path(tmp)/'legacy.db'
            with sqlite3.connect(app.DB) as db:
                db.executescript("""
                CREATE TABLE rooms(id INTEGER PRIMARY KEY,name TEXT UNIQUE NOT NULL,rent INTEGER NOT NULL,tenant TEXT NOT NULL DEFAULT '',phone TEXT NOT NULL DEFAULT '',start TEXT NOT NULL DEFAULT '',end TEXT NOT NULL DEFAULT '',deposit INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE invoices(id INTEGER PRIMARY KEY,room_id INTEGER NOT NULL,month TEXT NOT NULL,electric_old INTEGER NOT NULL,electric_new INTEGER NOT NULL,water_old INTEGER NOT NULL,water_new INTEGER NOT NULL,electric_rate INTEGER NOT NULL,water_rate INTEGER NOT NULL,rent INTEGER NOT NULL,fee INTEGER NOT NULL,total INTEGER NOT NULL,paid INTEGER NOT NULL DEFAULT 0,UNIQUE(room_id,month));
                CREATE TABLE repairs(id INTEGER PRIMARY KEY,room_id INTEGER NOT NULL,description TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'Mới',created TEXT NOT NULL);
                INSERT INTO rooms(id,name,rent,tenant) VALUES(42,'Legacy',3000000,'Existing tenant');
                INSERT INTO invoices VALUES(99,42,'2026-09',0,50,0,5,3500,15000,3000000,0,3250000,1000000);
                INSERT INTO repairs VALUES(51,42,'Existing repair','Mới','2026-09-01');
                """)
            app.init()
            self.assertEqual(len(list(Path(tmp).glob('*.before-auth-*.bak'))),1)
            app.authenticate(dict(email='first@example.com',name='First',password='password-first'),True)
            app.authenticate(dict(email='second@example.com',name='Second',password='password-second'),True)
            app.init()
            with app.connect() as db:
                room=dict(db.execute('SELECT * FROM rooms WHERE id=42').fetchone())
                self.assertEqual(room['tenant'],'Existing tenant')
                self.assertEqual(room['owner_id'],1)
                self.assertEqual(db.execute('SELECT paid FROM invoices WHERE id=99').fetchone()[0],1000000)
                self.assertEqual(db.execute('SELECT sum(amount) FROM payments WHERE owner_id=1').fetchone()[0],1000000)
                self.assertEqual(db.execute('SELECT count(*) FROM rooms WHERE owner_id=2').fetchone()[0],0)
                self.assertEqual(db.execute('SELECT count(*) FROM payments').fetchone()[0],1)

if __name__=='__main__':unittest.main()
