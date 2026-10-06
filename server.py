import json
import os
import sqlite3
import hashlib
import hmac
import secrets
import time
import re
from contextlib import contextmanager, closing
import argparse
import calendar
import threading
import sys
import unicodedata
import ipaddress
import getpass
from http.cookies import SimpleCookie
from urllib.parse import urlsplit
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent
DB = Path(os.environ.get('APP_DB', str(ROOT / 'data' / 'app.db')))

def business_today():
    return datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date()

@contextmanager
def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB)
    DB.chmod(0o600)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=10000")
    try:
        with db:
            yield db
    finally:
        db.close()

def init():
    if DB.exists():
        with closing(sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True)) as old:
            columns={r[1] for r in old.execute('PRAGMA table_info(rooms)')}
        if columns and 'owner_id' not in columns:
            backup(str(DB)+f'.before-auth-{time.time_ns()}.bak')
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS rooms(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, rent INTEGER NOT NULL, tenant TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '', start TEXT NOT NULL DEFAULT '', end TEXT NOT NULL DEFAULT '', deposit INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS invoices(id INTEGER PRIMARY KEY, room_id INTEGER NOT NULL, month TEXT NOT NULL, electric_old INTEGER NOT NULL, electric_new INTEGER NOT NULL, water_old INTEGER NOT NULL, water_new INTEGER NOT NULL, electric_rate INTEGER NOT NULL, water_rate INTEGER NOT NULL, rent INTEGER NOT NULL, fee INTEGER NOT NULL, total INTEGER NOT NULL, paid INTEGER NOT NULL DEFAULT 0, UNIQUE(room_id, month));
        CREATE TABLE IF NOT EXISTS repairs(id INTEGER PRIMARY KEY, room_id INTEGER NOT NULL, description TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Mới', created TEXT NOT NULL);
        ''')
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL, salt TEXT NOT NULL, password_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS login_attempts(ip TEXT NOT NULL, created INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL, invoice_id INTEGER NOT NULL, amount INTEGER NOT NULL, received TEXT NOT NULL, note TEXT NOT NULL DEFAULT '');
        """)
        for table in ['rooms','invoices','repairs']:
            columns = {r['name'] for r in db.execute(f'PRAGMA table_info({table})')}
            if 'owner_id' not in columns:
                db.execute(f'ALTER TABLE {table} ADD COLUMN owner_id INTEGER')
        invoice_columns={r['name'] for r in db.execute('PRAGMA table_info(invoices)')}
        for column, source in [('tenant_name','tenant'),('tenant_phone','phone'),('room_name','name')]:
            if column not in invoice_columns:
                db.execute(f"ALTER TABLE invoices ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
                db.execute(f"UPDATE invoices SET {column}=COALESCE((SELECT {source} FROM rooms WHERE rooms.id=invoices.room_id),'')")
        if 'request_key' not in {r['name'] for r in db.execute('PRAGMA table_info(payments)')}:
            db.execute('ALTER TABLE payments ADD COLUMN request_key TEXT')
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS payment_request_key ON payments(owner_id,request_key) WHERE request_key IS NOT NULL')
        # Replace the prototype's global room-name constraint without losing rows.
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name='rooms_owner_name'").fetchone():
            db.execute("CREATE TABLE rooms_v2(id INTEGER PRIMARY KEY, name TEXT NOT NULL, rent INTEGER NOT NULL, tenant TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '', start TEXT NOT NULL DEFAULT '', end TEXT NOT NULL DEFAULT '', deposit INTEGER NOT NULL DEFAULT 0, owner_id INTEGER)")
            db.execute('INSERT INTO rooms_v2 SELECT id,name,rent,tenant,phone,start,end,deposit,owner_id FROM rooms')
            db.execute('DROP TABLE rooms')
            db.execute('ALTER TABLE rooms_v2 RENAME TO rooms')
            db.execute('CREATE UNIQUE INDEX rooms_owner_name ON rooms(owner_id,name)')
        for table, columns in {
            'payments': {'voided':'INTEGER NOT NULL DEFAULT 0','void_reason':"TEXT NOT NULL DEFAULT ''",'voided_at':"TEXT NOT NULL DEFAULT ''"},
            'users': {'role': "TEXT NOT NULL DEFAULT 'owner'",'login_name':'TEXT','managed_owner_id':'INTEGER','managed_room_id':'INTEGER'},
            'repairs': {'reporter_user_id':'INTEGER'},
            'rooms': {'contract_version':'INTEGER NOT NULL DEFAULT 1','people': 'INTEGER NOT NULL DEFAULT 1','water_mode': "TEXT NOT NULL DEFAULT 'meter'",'electric_rate': 'INTEGER NOT NULL DEFAULT 3500','water_rate': 'INTEGER NOT NULL DEFAULT 15000','service_fee': 'INTEGER NOT NULL DEFAULT 100000','due_day': 'INTEGER NOT NULL DEFAULT 5','remind_days': 'INTEGER NOT NULL DEFAULT 3','auto_send': 'INTEGER NOT NULL DEFAULT 1','auto_remind': 'INTEGER NOT NULL DEFAULT 1','tenant_user_id': 'INTEGER'},
            'invoices': {'contract_version':'INTEGER NOT NULL DEFAULT 1','people': 'INTEGER NOT NULL DEFAULT 1','water_mode': "TEXT NOT NULL DEFAULT 'meter'",'water_total': 'INTEGER NOT NULL DEFAULT 0','due_date': "TEXT NOT NULL DEFAULT ''",'tenant_user_id': 'INTEGER'},
        }.items():
            existing={r['name'] for r in db.execute(f'PRAGMA table_info({table})')}
            for column, definition in columns.items():
                if column not in existing:
                    db.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')
                    if table=='invoices' and column=='water_total':
                        db.execute('UPDATE invoices SET water_total=(water_new-water_old)*water_rate')
        db.executescript("""
        CREATE TABLE IF NOT EXISTS payment_profiles(owner_id INTEGER PRIMARY KEY,bank TEXT NOT NULL,account TEXT NOT NULL,holder TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS contract_history(id INTEGER PRIMARY KEY,owner_id INTEGER NOT NULL,room_id INTEGER NOT NULL,room_name TEXT NOT NULL,tenant TEXT NOT NULL,phone TEXT NOT NULL,start TEXT NOT NULL,planned_end TEXT NOT NULL,ended TEXT NOT NULL,deposit INTEGER NOT NULL,contract_version INTEGER NOT NULL,reason TEXT NOT NULL,UNIQUE(owner_id,room_id,contract_version));
        CREATE TABLE IF NOT EXISTS invitations(token_hash TEXT PRIMARY KEY,owner_id INTEGER NOT NULL,room_id INTEGER NOT NULL,tenant_name TEXT NOT NULL,expires INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY,owner_id INTEGER NOT NULL,user_id INTEGER NOT NULL,invoice_id INTEGER NOT NULL,kind TEXT NOT NULL,title TEXT NOT NULL,created TEXT NOT NULL,is_read INTEGER NOT NULL DEFAULT 0,UNIQUE(user_id,invoice_id,kind));
        """)
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS user_login_name ON users(login_name) WHERE login_name IS NOT NULL')
        if 'contract_version' not in {r['name'] for r in db.execute('PRAGMA table_info(invitations)')}:
            db.execute('ALTER TABLE invitations ADD COLUMN contract_version INTEGER NOT NULL DEFAULT 1')
        if os.environ.get('SEED_DEMO','1')=='1' and not db.execute('SELECT 1 FROM rooms LIMIT 1').fetchone() and not db.execute('SELECT 1 FROM users LIMIT 1').fetchone():
            for i in range(1, 13):
                db.execute('INSERT INTO rooms(name,rent,tenant,phone,start,end,deposit) VALUES(?,?,?,?,?,?,?)', (f'P.{100+i}', 2800000 if i < 7 else 3200000, ['Nguyễn Minh Anh','Trần Quốc Bảo','Lê Thu Hà','Phạm Hoàng Nam','Võ Ngọc Linh','Đặng Đức Huy','Bùi Thanh Mai','Đỗ Hải Long'][i-1] if i <= 8 else '', '0901234567' if i<=8 else '', '2026-01-01' if i<=8 else '', '2026-12-31' if i<=8 else '', 3000000 if i<=8 else 0))

def integer(data, key, default=0):
    value = data.get(key, default)
    if isinstance(value, bool) or not re.fullmatch(r'[0-9]+',str(value)):
        raise ValueError('Số liệu không hợp lệ')
    n = int(value)
    if n < 0 or n > 1000000000:
        raise ValueError('Số liệu phải từ 0 đến 1 tỷ')
    return n

def text(data, key, limit, required=True):
    value=data.get(key,'')
    if not isinstance(value,str): raise ValueError(f'{key}: dữ liệu phải là văn bản')
    value=value.strip()
    if (required and not value) or len(value)>limit:
        raise ValueError(f'{key}: cần {"1" if required else "0"}–{limit} ký tự')
    return value

def iso_date(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):
        raise ValueError('Ngày cần định dạng YYYY-MM-DD')
    return date.fromisoformat(value)

def create_invoice(db, data, owner_id):
    room = db.execute('SELECT * FROM rooms WHERE id=? AND owner_id=?',(integer(data,'room_id'),owner_id)).fetchone()
    if not room or not room['tenant']: raise ValueError('Phòng chưa có hợp đồng')
    month = text(data,'month',7)
    if not re.fullmatch(r'\d{4}-\d{2}',month): raise ValueError('Tháng cần định dạng YYYY-MM')
    iso_date(month+'-01')
    if month < room['start'][:7] or month > room['end'][:7]:
        raise ValueError('Tháng hóa đơn nằm ngoài thời hạn hợp đồng')
    eo,en = [integer(data,k) for k in ['electric_old','electric_new']]
    mode=room['water_mode']
    wo,wn = [integer(data,k) for k in ['water_old','water_new']] if mode=='meter' else (0,0)
    er=integer(data,'electric_rate',room['electric_rate'])
    wr=integer(data,'water_rate',room['water_rate'])
    fee=integer(data,'fee',room['service_fee'])
    water_total=(wn-wo)*wr if mode=='meter' else room['people']*wr
    if en < eo or wn < wo: raise ValueError('Chỉ số mới phải lớn hơn hoặc bằng chỉ số cũ')
    total = room['rent']+(en-eo)*er+water_total+fee
    due_date=f"{month}-{min(room['due_day'],calendar.monthrange(int(month[:4]),int(month[5:]))[1]):02d}"
    if total > 1000000000: raise ValueError('Tổng hóa đơn vượt giới hạn 1 tỷ đồng')
    invoice_id=db.execute('INSERT INTO invoices(room_id,month,electric_old,electric_new,water_old,water_new,electric_rate,water_rate,rent,fee,total,owner_id,tenant_name,tenant_phone,room_name,people,water_mode,water_total,due_date,tenant_user_id,contract_version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(room['id'],month,eo,en,wo,wn,er,wr,room['rent'],fee,total,owner_id,room['tenant'],room['phone'],room['name'],room['people'],mode,water_total,due_date,room['tenant_user_id'],room['contract_version'])).lastrowid
    if room['auto_send'] and room['tenant_user_id']:
        publish_invoice(db,invoice_id,owner_id,room['tenant_user_id'],'invoice',f'Hóa đơn {month} · {room["name"]}')

def mutate(path, data, owner_id):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if path == '/api/rooms':
            name = text(data,'name',80)
            db.execute('INSERT INTO rooms(name,rent,owner_id) VALUES(?,?,?)', (name, integer(data,'rent'),owner_id))
        elif path == '/api/tenant-password-reset':
            room=db.execute('SELECT * FROM rooms WHERE id=? AND owner_id=?',(integer(data,'room_id'),owner_id)).fetchone()
            if not room or not room['tenant_user_id']: raise ValueError('Phòng chưa có tài khoản người thuê')
            if data.get('confirmation')!=room['name']: raise ValueError('Nhập đúng tên phòng để cấp lại mật khẩu')
            user=db.execute('SELECT * FROM users WHERE id=? AND managed_owner_id=? AND managed_room_id=?',(room['tenant_user_id'],owner_id,room['id'])).fetchone()
            if not user or not user['login_name']: raise ValueError('Đây là tài khoản cá nhân; người thuê tự đổi mật khẩu trong mục Tài khoản')
            password=secrets.token_urlsafe(16);salt=secrets.token_hex(16)
            db.execute('UPDATE users SET salt=?,password_hash=? WHERE id=?',(salt,password_hash(password,salt),user['id']))
            db.execute('DELETE FROM sessions WHERE user_id=?',(user['id'],))
            return {'credentials':{'login_name':user['login_name'],'password':password,'room_name':room['name']}}
        elif path == '/api/payment-profile':
            bank=text(data,'bank',6);account=text(data,'account',20);holder=text(data,'holder',150)
            if not re.fullmatch(r'[0-9]{6}',bank) or not re.fullmatch(r'[0-9]{4,20}',account): raise ValueError('Kiểm tra BIN ngân hàng 6 số và số tài khoản 4–20 số')
            db.execute('INSERT INTO payment_profiles(owner_id,bank,account,holder) VALUES(?,?,?,?) ON CONFLICT(owner_id) DO UPDATE SET bank=excluded.bank,account=excluded.account,holder=excluded.holder',(owner_id,bank,account,holder))
        elif path == '/api/contract-end':
            room=db.execute('SELECT * FROM rooms WHERE id=? AND owner_id=?',(integer(data,'id'),owner_id)).fetchone()
            if not room or not room['tenant']: raise ValueError('Không tìm thấy hợp đồng đang thuê')
            if data.get('confirmation')!=room['name']: raise ValueError('Nhập đúng tên phòng để xác nhận')
            ended=iso_date(data.get('ended'))
            if ended>business_today() or ended<iso_date(room['start']): raise ValueError('Ngày trả phòng phải trong khoảng từ ngày bắt đầu đến hôm nay')
            allow_debt=integer(data,'allow_debt',0)
            if allow_debt not in [0,1]: raise ValueError('Thiết lập công nợ không hợp lệ')
            debt=db.execute('SELECT COALESCE(sum(total-paid),0) FROM invoices WHERE room_id=? AND owner_id=? AND contract_version=?',(room['id'],owner_id,room['contract_version'])).fetchone()[0]
            if debt and not allow_debt: raise ValueError('Hợp đồng còn công nợ; chọn giữ công nợ nếu vẫn kết thúc')
            archive_contract(db,room,str(ended),text(data,'reason',500))
            db.execute("UPDATE rooms SET tenant='',phone='',start='',end='',deposit=0,people=1,tenant_user_id=NULL,contract_version=contract_version+1 WHERE id=? AND owner_id=?",(room['id'],owner_id))
            db.execute('DELETE FROM invitations WHERE room_id=? AND owner_id=?',(room['id'],owner_id))
        elif path == '/api/payment-void':
            payment=db.execute('SELECT * FROM payments WHERE id=? AND owner_id=?',(integer(data,'id'),owner_id)).fetchone()
            if not payment: raise ValueError('Không tìm thấy khoản thu')
            reason=text(data,'reason',500)
            if len(reason)<3: raise ValueError('Lý do hủy cần ít nhất 3 ký tự')
            if payment['voided']: return
            invoice=db.execute('SELECT * FROM invoices WHERE id=? AND owner_id=?',(payment['invoice_id'],owner_id)).fetchone()
            if not invoice or invoice['paid']<payment['amount']: raise ValueError('Dữ liệu thu tiền không khớp; cần kiểm tra trước khi hủy')
            db.execute('UPDATE invoices SET paid=paid-? WHERE id=?',(payment['amount'],invoice['id']))
            db.execute('UPDATE payments SET voided=1,void_reason=?,voided_at=? WHERE id=?',(reason,datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).isoformat(),payment['id']))
        elif path == '/api/room-billing':
            room=db.execute('SELECT * FROM rooms WHERE id=? AND owner_id=?',(integer(data,'id'),owner_id)).fetchone()
            if not room: raise ValueError('Không tìm thấy phòng')
            people=integer(data,'people',room['people'])
            due=integer(data,'due_day',room['due_day']);remind=integer(data,'remind_days',room['remind_days'])
            mode=data.get('water_mode',room['water_mode'])
            if not 1<=people<=50 or not 1<=due<=31 or not 0<=remind<=30 or mode not in ['meter','person']:
                raise ValueError('Kiểm tra số người (1–50), ngày thu (1–31), ngày nhắc (0–30) và cách tính nước')
            auto_send=integer(data,'auto_send',room['auto_send']);auto_remind=integer(data,'auto_remind',room['auto_remind'])
            if auto_send not in [0,1] or auto_remind not in [0,1]: raise ValueError('Thiết lập tự động không hợp lệ')
            db.execute('UPDATE rooms SET people=?,water_mode=?,electric_rate=?,water_rate=?,service_fee=?,due_day=?,remind_days=?,auto_send=?,auto_remind=? WHERE id=? AND owner_id=?',(people,mode,integer(data,'electric_rate',room['electric_rate']),integer(data,'water_rate',room['water_rate']),integer(data,'service_fee',room['service_fee']),due,remind,auto_send,auto_remind,room['id'],owner_id))
        elif path == '/api/tenant-invite':
            room=db.execute('SELECT * FROM rooms WHERE id=? AND owner_id=?',(integer(data,'room_id'),owner_id)).fetchone()
            if not room or not room['tenant']: raise ValueError('Phòng chưa có người thuê')
            if room['tenant_user_id']: raise ValueError('Phòng đã liên kết tài khoản người thuê')
            token=secrets.token_urlsafe(32)
            db.execute('DELETE FROM invitations WHERE room_id=? AND owner_id=?',(room['id'],owner_id))
            db.execute('INSERT INTO invitations(token_hash,owner_id,room_id,tenant_name,expires,contract_version) VALUES(?,?,?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),owner_id,room['id'],room['tenant'],int(time.time())+7*86400,room['contract_version']))
            return {'invite_token':token}
        elif path == '/api/invoice-send':
            inv=db.execute('SELECT * FROM invoices WHERE id=? AND owner_id=?',(integer(data,'id'),owner_id)).fetchone()
            if not inv or not inv['tenant_user_id']: raise ValueError('Hóa đơn chưa liên kết tài khoản người thuê')
            publish_invoice(db,inv['id'],owner_id,inv['tenant_user_id'],'invoice',f'Hóa đơn {inv["month"]} · {inv["room_name"]}')
        elif path == '/api/room-update':
            rid=integer(data,'id')
            cur=db.execute('UPDATE rooms SET name=?,rent=? WHERE id=? AND owner_id=?',(text(data,'name',80),integer(data,'rent'),rid,owner_id))
            if not cur.rowcount: raise ValueError('Không tìm thấy phòng')
        elif path == '/api/room-delete':
            rid=integer(data,'id')
            room=db.execute('SELECT * FROM rooms WHERE id=? AND owner_id=?',(rid,owner_id)).fetchone()
            if not room: raise ValueError('Không tìm thấy phòng')
            if data.get('confirmation')!=room['name']: raise ValueError('Nhập đúng tên phòng để xác nhận xóa')
            db.execute('DELETE FROM payments WHERE owner_id=? AND invoice_id IN (SELECT id FROM invoices WHERE room_id=? AND owner_id=?)',(owner_id,rid,owner_id))
            db.execute('DELETE FROM invoices WHERE room_id=? AND owner_id=?',(rid,owner_id))
            db.execute('DELETE FROM repairs WHERE room_id=? AND owner_id=?',(rid,owner_id))
            db.execute('DELETE FROM contract_history WHERE room_id=? AND owner_id=?',(rid,owner_id))
            db.execute('DELETE FROM notifications WHERE owner_id=? AND invoice_id NOT IN (SELECT id FROM invoices)',(owner_id,))
            db.execute('DELETE FROM invitations WHERE room_id=? AND owner_id=?',(rid,owner_id))
            db.execute('DELETE FROM rooms WHERE id=? AND owner_id=?',(rid,owner_id))
        elif path == '/api/reset':
            if data.get('confirmation')!='XÓA DỮ LIỆU': raise ValueError('Nhập XÓA DỮ LIỆU để xác nhận')
            user=db.execute('SELECT * FROM users WHERE id=?',(owner_id,)).fetchone()
            password=data.get('password')
            if not user or not isinstance(password,str) or not 10<=len(password)<=128 or not hmac.compare_digest(password_hash(password,user['salt']),user['password_hash']):
                raise ValueError('Mật khẩu không đúng')
            for table in ['payment_profiles','contract_history','notifications','invitations','payments','invoices','repairs','rooms']:
                db.execute(f'DELETE FROM {table} WHERE owner_id=?',(owner_id,))
        elif path == '/api/invoices-batch':
            items=data.get('items')
            if not isinstance(items,list) or not 1<=len(items)<=200: raise ValueError('Chọn từ 1 đến 200 phòng')
            for item in items:
                if not isinstance(item,dict): raise ValueError('Chỉ số phòng không hợp lệ')
                readings={k:item.get(k) for k in ['room_id','electric_old','electric_new','water_old','water_new']}
                create_invoice(db,{**data,**readings},owner_id)
        elif path == '/api/contracts':
            room = db.execute('SELECT * FROM rooms WHERE id=? AND owner_id=?',(integer(data,'room_id'),owner_id)).fetchone()
            if not room: raise ValueError('Không tìm thấy phòng')
            tenant = text(data,'tenant',150)
            start, end = iso_date(data.get('start')), iso_date(data.get('end'))
            if end <= start: raise ValueError('Ngày kết thúc phải sau ngày bắt đầu')
            if room['tenant'] and tenant!=room['tenant']:
                archive_contract(db,room,str(business_today()),'Cập nhật người thuê')
            if tenant != room['tenant'] or text(data,'phone',30,False)!=room['phone'] or str(start)!=room['start']:
                db.execute('UPDATE rooms SET tenant_user_id=NULL,contract_version=contract_version+1 WHERE id=?',(room['id'],))
                db.execute('DELETE FROM invitations WHERE room_id=?',(room['id'],))
            db.execute('UPDATE rooms SET tenant=?,phone=?,start=?,end=?,deposit=? WHERE id=?',(tenant,text(data,'phone',30,False),str(start),str(end),integer(data,'deposit'),room['id']))
            auto=integer(data,'auto_account',1)
            if auto not in [0,1]: raise ValueError('Thiết lập tự tạo tài khoản không hợp lệ')
            updated=db.execute('SELECT * FROM rooms WHERE id=?',(room['id'],)).fetchone()
            if auto and not updated['tenant_user_id']:
                return {'credentials':provision_tenant(db,updated)}
        elif path == '/api/invoices':
            create_invoice(db,data,owner_id)
        elif path == '/api/payments':
            inv = db.execute('SELECT * FROM invoices WHERE id=? AND owner_id=?',(integer(data,'id'),owner_id)).fetchone()
            if not inv: raise ValueError('Không tìm thấy hóa đơn')
            amount = integer(data,'amount')
            received = str(iso_date(data.get('received', str(business_today()))))
            if received > str(business_today()): raise ValueError('Ngày thu không thể ở tương lai')
            note = text(data,'note',500,False)
            request_key=data.get('request_key')
            if request_key is not None:
                if not isinstance(request_key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,80}',request_key):
                    raise ValueError('Mã yêu cầu thanh toán không hợp lệ')
                previous=db.execute('SELECT * FROM payments WHERE owner_id=? AND request_key=?',(owner_id,request_key)).fetchone()
                if previous:
                    if previous['voided']: raise ValueError('Khoản thu trước đã hủy; tạo yêu cầu thu mới')
                    if (previous['invoice_id'],previous['amount'],previous['received'],previous['note'])!=(inv['id'],amount,received,note):
                        raise ValueError('Yêu cầu đã ghi nhận với dữ liệu khác; kiểm tra lịch sử thu tiền')
                    return
            if amount <= 0 or amount > inv['total']-inv['paid']: raise ValueError('Số tiền vượt công nợ hoặc bằng 0')
            db.execute('INSERT INTO payments(owner_id,invoice_id,amount,received,note,request_key) VALUES(?,?,?,?,?,?)',(owner_id,inv['id'],amount,received,note,request_key))
            db.execute('UPDATE invoices SET paid=paid+? WHERE id=?',(amount,inv['id']))
        elif path == '/api/repairs':
            rid = integer(data,'room_id')
            if not db.execute('SELECT 1 FROM rooms WHERE id=? AND owner_id=?',(rid,owner_id)).fetchone(): raise ValueError('Không tìm thấy phòng')
            description = text(data,'description',2000)
            db.execute('INSERT INTO repairs(room_id,description,created,owner_id) VALUES(?,?,?,?)',(rid,description,str(business_today()),owner_id))
        elif path == '/api/repair-status':
            if data.get('status') not in ['Mới','Đang xử lý','Hoàn tất']: raise ValueError('Trạng thái không hợp lệ')
            cur=db.execute('UPDATE repairs SET status=? WHERE id=? AND owner_id=?',(data['status'],integer(data,'id'),owner_id))
            if not cur.rowcount: raise ValueError('Không tìm thấy báo hỏng')
        else: raise ValueError('Thao tác không tồn tại')

def password_hash(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 310000).hex()

def authenticate(data, register=False, ip='local', tenant_invite=None):
    email = text(data,'email',254).lower()
    password = data.get('password','')
    if not isinstance(password,str) or not 10 <= len(password) <= 128:
        raise ValueError('Mật khẩu cần 10–128 ký tự')
    if register and (not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email) or len(email)>254):
        raise ValueError('Email không hợp lệ')
    if register and email.endswith('@roomly.local'): raise ValueError('Tên miền dành riêng cho tài khoản phòng')
    now=int(time.time())
    # Persist throttling before validation: failed attempts must also count.
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('DELETE FROM login_attempts WHERE created<?',(now-900,))
        if db.execute('SELECT count(*) FROM login_attempts WHERE ip=?',(ip,)).fetchone()[0]>=10:
            raise ValueError('Quá nhiều lần thử. Vui lòng thử lại sau 15 phút.')
        db.execute('INSERT INTO login_attempts VALUES(?,?)',(ip,now))
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if register:
            name=text(data,'name',100)
            first = not db.execute('SELECT 1 FROM users LIMIT 1').fetchone()
            invitation=valid_invitation(db,tenant_invite) if tenant_invite is not None else None
            role='tenant' if invitation else 'owner'
            salt=secrets.token_hex(16)
            uid=db.execute('INSERT INTO users(email,name,salt,password_hash,role) VALUES(?,?,?,?,?)',(email,name,salt,password_hash(password,salt),role)).lastrowid
            if invitation:
                claim_invitation(db,invitation,uid)
            if first and role=='owner':
                for table in ['rooms','invoices','repairs']:
                    db.execute(f'UPDATE {table} SET owner_id=? WHERE owner_id IS NULL',(uid,))
                # Preserve previously recorded prototype receipts as opening entries.
                for inv in db.execute('SELECT * FROM invoices WHERE owner_id=? AND paid>0',(uid,)).fetchall():
                    db.execute('INSERT INTO payments(owner_id,invoice_id,amount,received,note) VALUES(?,?,?,?,?)',(uid,inv['id'],inv['paid'],str(business_today()),'Số dư thu từ bản MVP; ngày thu gốc chưa được ghi nhận'))
        else:
            user=db.execute('SELECT * FROM users WHERE email=? OR login_name=?',(email,email)).fetchone()
            salt=user['salt'] if user else '0'*32
            candidate=password_hash(password,salt)
            if not user or not hmac.compare_digest(candidate,user['password_hash']): raise ValueError('Email hoặc mật khẩu không đúng')
            uid=user['id']
        token=secrets.token_urlsafe(32)
        db.execute('DELETE FROM sessions WHERE expires<=?',(now,))
        db.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),uid,now+86400))
        return token

def provision_tenant(db,room):
    slug=unicodedata.normalize('NFKD',room['name']).encode('ascii','ignore').decode().lower()
    slug=re.sub(r'[^a-z0-9]+','-',slug).strip('-')[:40] or f'phong-{room["id"]}'
    sequence=db.execute('SELECT COALESCE(max(id),0)+1 FROM users').fetchone()[0]
    login=f'nha{room["owner_id"]}-{slug}-hd{room["contract_version"]}-u{sequence}'
    password=secrets.token_urlsafe(16);salt=secrets.token_hex(16)
    uid=db.execute('INSERT INTO users(email,name,salt,password_hash,role,login_name,managed_owner_id,managed_room_id) VALUES(?,?,?,?,?,?,?,?)',(f'{login}@roomly.local',room['tenant'],salt,password_hash(password,salt),'tenant',login,room['owner_id'],room['id'])).lastrowid
    db.execute('UPDATE rooms SET tenant_user_id=? WHERE id=?',(uid,room['id']))
    invitation={'room_id':room['id'],'owner_id':room['owner_id'],'tenant_name':room['tenant'],'contract_version':room['contract_version'],'token_hash':''}
    claim_invitation(db,invitation,uid)
    db.execute('DELETE FROM invitations WHERE room_id=? AND owner_id=?',(room['id'],room['owner_id']))
    return {'login_name':login,'password':password,'room_name':room['name']}

def archive_contract(db,room,ended,reason):
    db.execute('INSERT OR IGNORE INTO contract_history(owner_id,room_id,room_name,tenant,phone,start,planned_end,ended,deposit,contract_version,reason) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(room['owner_id'],room['id'],room['name'],room['tenant'],room['phone'],room['start'],room['end'],ended,room['deposit'],room['contract_version'],reason))

def change_password(uid,data):
    current=data.get('current_password');new=data.get('new_password')
    if not isinstance(current,str) or not 10<=len(current)<=128 or not isinstance(new,str) or not 10<=len(new)<=128:
        raise ValueError('Mật khẩu cần 10–128 ký tự')
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        user=db.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
        if not user or not hmac.compare_digest(password_hash(current,user['salt']),user['password_hash']):
            raise ValueError('Mật khẩu hiện tại không đúng')
        salt=secrets.token_hex(16)
        db.execute('UPDATE users SET salt=?,password_hash=? WHERE id=?',(salt,password_hash(new,salt),uid))
        db.execute('DELETE FROM sessions WHERE user_id=?',(uid,))

def reminder_interval():
    try: interval=int(os.environ.get('REMINDER_INTERVAL','60'))
    except ValueError: raise ValueError('REMINDER_INTERVAL cần là số nguyên từ 1 đến 300 giây')
    if not 1<=interval<=300: raise ValueError('REMINDER_INTERVAL cần từ 1 đến 300 giây')
    return interval

def publish_invoice(db,invoice_id,owner_id,user_id,kind,title):
    db.execute('INSERT OR IGNORE INTO notifications(owner_id,user_id,invoice_id,kind,title,created) VALUES(?,?,?,?,?,?)',(owner_id,user_id,invoice_id,kind,title,datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).isoformat()))

def valid_invitation(db,token):
    if not isinstance(token,str) or not 20<=len(token)<=100: raise ValueError('Liên kết mời không hợp lệ')
    invitation=db.execute('SELECT i.* FROM invitations i JOIN rooms r ON r.id=i.room_id AND r.owner_id=i.owner_id WHERE i.token_hash=? AND i.expires>? AND r.tenant=i.tenant_name AND r.contract_version=i.contract_version AND r.tenant_user_id IS NULL',(hashlib.sha256(token.encode()).hexdigest(),int(time.time()))).fetchone()
    if not invitation: raise ValueError('Liên kết mời đã hết hạn, đã dùng hoặc hợp đồng đã đổi')
    return invitation

def claim_invitation(db,invitation,uid):
    user=db.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
    if user['managed_room_id'] and (user['managed_room_id']!=invitation['room_id'] or user['managed_owner_id']!=invitation['owner_id']):
        raise ValueError('Tài khoản phòng chỉ được dùng cho phòng đã cấp')
    db.execute('UPDATE rooms SET tenant_user_id=? WHERE id=? AND owner_id=?',(uid,invitation['room_id'],invitation['owner_id']))
    # Only invoices with the matching snapshot tenant are attached to this account.
    db.execute('UPDATE invoices SET tenant_user_id=? WHERE room_id=? AND owner_id=? AND tenant_name=? AND contract_version=? AND tenant_user_id IS NULL',(uid,invitation['room_id'],invitation['owner_id'],invitation['tenant_name'],invitation['contract_version']))
    room=db.execute('SELECT auto_send FROM rooms WHERE id=?',(invitation['room_id'],)).fetchone()
    if room['auto_send']:
        for invoice in db.execute('SELECT * FROM invoices WHERE room_id=? AND tenant_user_id=?',(invitation['room_id'],uid)).fetchall():
            publish_invoice(db,invoice['id'],invitation['owner_id'],uid,'invoice',f'Hóa đơn {invoice["month"]} · {invoice["room_name"]}')
    db.execute('DELETE FROM invitations WHERE token_hash=?',(invitation['token_hash'],))

def run_reminders(now=None):
    today=now or business_today()
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        invoices=db.execute("SELECT i.*,r.remind_days FROM invoices i JOIN rooms r ON r.id=i.room_id AND r.owner_id=i.owner_id WHERE i.tenant_user_id IS NOT NULL AND i.paid<i.total AND r.auto_remind=1 AND i.due_date<>'' AND EXISTS(SELECT 1 FROM notifications n WHERE n.invoice_id=i.id AND n.user_id=i.tenant_user_id AND n.kind='invoice')").fetchall()
        for invoice in invoices:
            due=iso_date(invoice['due_date'])
            if today>=due-timedelta(days=invoice['remind_days']):
                publish_invoice(db,invoice['id'],invoice['owner_id'],invoice['tenant_user_id'],'reminder',f'Nhắc thanh toán {invoice["room_name"]} · hạn {invoice["due_date"]}')

def reminder_worker(stop,interval=60):
    while not stop.is_set():
        try: run_reminders()
        except sqlite3.Error: print('Reminder worker: database unavailable; retrying next tick',file=sys.stderr)
        stop.wait(interval)

class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, '.webmanifest': 'application/manifest+json'}
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(ROOT/'public'),**kwargs)
    def end_headers(self):
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','same-origin')
        self.send_header('Cache-Control','no-store')
        super().end_headers()
    def respond(self,code,data,cookie=None):
        payload=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(code)
        if cookie is not None:
            secure='; Secure' if os.environ.get('COOKIE_SECURE')=='1' else ''
            self.send_header('Set-Cookie',f'roomly_session={cookie}; HttpOnly; SameSite=Strict; Path=/; Max-Age={86400 if cookie else 0}{secure}')
        self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(payload))); self.end_headers(); self.wfile.write(payload)
    def session(self):
        cookies=SimpleCookie()
        try: cookies.load(self.headers.get('Cookie',''))
        except Exception: return None
        token=cookies.get('roomly_session')
        if not token: return None
        digest=hashlib.sha256(token.value.encode()).hexdigest()
        with connect() as db:
            row=db.execute('SELECT users.id,users.email,users.name,users.role,users.login_name FROM sessions JOIN users ON users.id=sessions.user_id WHERE token_hash=? AND expires>?',(digest,int(time.time()))).fetchone()
        return dict(row) if row else None
    def do_GET(self):
        if self.path=='/healthz':
            try:
                with connect() as db: db.execute('SELECT 1 FROM users LIMIT 1').fetchone()
                self.respond(200,{'ok':True})
            except sqlite3.Error: self.respond(503,{'ok':False})
            return
        if self.path.startswith('/api/'):
            user=self.session()
            if self.path=='/api/me':
                with connect() as db: first=not db.execute('SELECT 1 FROM users LIMIT 1').fetchone()
                self.respond(200,{'user':user,'first_account':first}); return
            if not user: self.respond(401,{'error':'Vui lòng đăng nhập'}); return
            if user['role']=='tenant':
                self.tenant_get(user); return
            if self.path=='/api/state':
                with connect() as db:
                    self.respond(200,{t:[dict(r) for r in db.execute(f'SELECT * FROM {t} WHERE owner_id=? ORDER BY {'owner_id' if t=='payment_profiles' else 'id'} DESC',(user['id'],))] for t in ['rooms','invoices','repairs','payments','contract_history','payment_profiles']})
            elif self.path=='/api/export':
                with connect() as db:
                    self.respond(200,{'version':1,'exported':str(business_today()),'data':{t:[dict(r) for r in db.execute(f'SELECT * FROM {t} WHERE owner_id=? ORDER BY {"owner_id" if t=="payment_profiles" else "id"}',(user['id'],))] for t in ['rooms','invoices','repairs','payments','contract_history','payment_profiles']}})
            else: self.respond(404,{'error':'Không tìm thấy API'})
        else: super().do_GET()
    def tenant_get(self,user):
        if self.path!='/api/state': self.respond(403,{'error':'Tài khoản người thuê không có quyền quản lý'});return
        with connect() as db:
            data={
                'rooms':[dict(r) for r in db.execute('SELECT id,name,tenant,phone,start,end,people,owner_id FROM rooms WHERE tenant_user_id=?',(user['id'],))],
                'invoices':[dict(r) for r in db.execute("SELECT i.* FROM invoices i WHERE tenant_user_id=? AND EXISTS(SELECT 1 FROM notifications n WHERE n.invoice_id=i.id AND n.user_id=i.tenant_user_id AND n.kind='invoice') ORDER BY id DESC",(user['id'],))],
                'notifications':[dict(r) for r in db.execute('SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC',(user['id'],))],
                'repairs':[dict(r) for r in db.execute('SELECT p.* FROM repairs p JOIN rooms r ON r.id=p.room_id AND r.owner_id=p.owner_id WHERE r.tenant_user_id=? AND p.reporter_user_id=? ORDER BY p.id DESC',(user['id'],user['id']))],
                'payments':[],
                'payment_profiles':[dict(r) for r in db.execute("SELECT DISTINCT p.* FROM payment_profiles p JOIN invoices i ON i.owner_id=p.owner_id WHERE i.tenant_user_id=? AND EXISTS(SELECT 1 FROM notifications n WHERE n.invoice_id=i.id AND n.user_id=i.tenant_user_id AND n.kind='invoice')",(user['id'],))],
            }
            self.respond(200,data)
    def tenant_post(self,user,data):
        with connect() as db:
            if self.path=='/api/notification-read':
                cur=db.execute('UPDATE notifications SET is_read=1 WHERE id=? AND user_id=?',(integer(data,'id'),user['id']))
                if not cur.rowcount: raise ValueError('Không tìm thấy thông báo')
            elif self.path=='/api/tenant-join':
                db.execute('BEGIN IMMEDIATE');invitation=valid_invitation(db,data.get('invite_token'));claim_invitation(db,invitation,user['id'])
            elif self.path=='/api/repairs':
                room=db.execute('SELECT * FROM rooms WHERE id=? AND tenant_user_id=?',(integer(data,'room_id'),user['id'])).fetchone()
                if not room: raise ValueError('Không tìm thấy phòng')
                db.execute('INSERT INTO repairs(room_id,description,created,owner_id,reporter_user_id) VALUES(?,?,?,?,?)',(room['id'],text(data,'description',2000),str(business_today()),room['owner_id'],user['id']))
            else: self.respond(403,{'error':'Tài khoản người thuê không có quyền thực hiện thao tác này'});return
        self.respond(200,{'ok':True})
    def do_POST(self):
        # Custom header cannot be submitted by cross-origin HTML forms; no CORS is enabled.
        origin=self.headers.get('Origin')
        try:
            parsed=urlsplit(origin) if origin else None
            invalid_origin=parsed and (parsed.scheme not in ['http','https'] or parsed.netloc!=self.headers.get('Host') or parsed.path or parsed.query or parsed.fragment)
        except ValueError:
            invalid_origin=True
        if self.headers.get('X-Requested-With')!='Roomly' or invalid_origin:
            self.respond(403,{'error':'Yêu cầu không hợp lệ'}); return
        try:
            length=int(self.headers.get('Content-Length',0))
            if not 0 < length <= (100000 if self.path=='/api/invoices-batch' else 20000): raise ValueError('Dữ liệu quá lớn hoặc rỗng')
            data=json.loads(self.rfile.read(length))
            if not isinstance(data,dict): raise ValueError('Dữ liệu không hợp lệ')
            if self.path in ['/api/login','/api/register','/api/tenant-register']:
                if self.path=='/api/register' and os.environ.get('ALLOW_OWNER_SIGNUP','1')!='1':
                    self.respond(403,{'error':'Đăng ký chủ nhà hiện chưa mở'});return
                token=authenticate(data,self.path!='/api/login',client_ip(self.client_address[0],self.headers.get('X-Forwarded-For','')),text(data,'invite_token',100) if self.path=='/api/tenant-register' else None)
                self.respond(200,{'ok':True},cookie=token); return
            user=self.session()
            if not user: self.respond(401,{'error':'Vui lòng đăng nhập'}); return
            if self.path=='/api/password-change':
                change_password(user['id'],data);self.respond(200,{'ok':True},cookie='');return
            if self.path=='/api/logout':
                cookies=SimpleCookie(self.headers.get('Cookie',''))
                digest=hashlib.sha256(cookies['roomly_session'].value.encode()).hexdigest()
                with connect() as db: db.execute('DELETE FROM sessions WHERE token_hash=?',(digest,))
                self.respond(200,{'ok':True},cookie=''); return
            if user['role']=='tenant':
                self.tenant_post(user,data);return
            result=mutate(self.path,data,user['id']); self.respond(200,{'ok':True,**(result or {})})
        except sqlite3.OperationalError: self.respond(503,{'error':'Hệ thống đang bận, vui lòng thử lại'})
        except sqlite3.IntegrityError: self.respond(400,{'error':'Email, phòng hoặc hóa đơn tháng này đã tồn tại'})
        except (ValueError,KeyError,TypeError,OverflowError) as exc: self.respond(400,{'error':str(exc) or 'Dữ liệu không hợp lệ'})

def backup(destination):
    if not DB.is_file(): raise ValueError('Chưa có cơ sở dữ liệu để sao lưu')
    target=Path(destination)
    if target.exists(): raise ValueError('Tệp đích đã tồn tại; chọn tên mới')
    target.parent.mkdir(parents=True,exist_ok=True)
    # Exclusive creation prevents accidental overwrite and restricts credential-data access.
    with target.open('xb'): pass
    target.chmod(0o600)
    with connect() as source, closing(sqlite3.connect(target)) as dest:
        source.backup(dest)
        if dest.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise ValueError('Bản sao lưu không hợp lệ')
    print(f'Đã sao lưu: {target}')

def restore(source):
    source=Path(source).resolve()
    if not source.is_file() or source==DB.resolve(): raise ValueError('Chọn tệp sao lưu hợp lệ khác DB hiện tại')
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as candidate:
        if candidate.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise ValueError('Bản sao lưu bị lỗi')
        tables={r[0] for r in candidate.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'rooms','invoices','repairs','users','sessions','payments'}.issubset(tables): raise ValueError('Không phải bản sao lưu Roomly')
        required={
            'rooms': {'id','name','rent','tenant','phone','start','end','deposit','owner_id'},
            'invoices': {'id','room_id','month','electric_old','electric_new','water_old','water_new','electric_rate','water_rate','rent','fee','total','paid','owner_id'},
            'repairs': {'id','room_id','description','status','created','owner_id'},
            'users': {'id','email','name','salt','password_hash'},
            'sessions': {'token_hash','user_id','expires'},
            'payments': {'id','owner_id','invoice_id','amount','received','note'},
        }
        for table, columns in required.items():
            if not columns.issubset({r[1] for r in candidate.execute(f'PRAGMA table_info({table})')}):
                raise ValueError('Cấu trúc bản sao lưu không hợp lệ; dữ liệu hiện tại được giữ nguyên')
        if DB.exists(): backup(str(DB)+f'.before-restore-{time.time_ns()}.bak')
        with connect() as target:
            candidate.backup(target)
            target.execute('DELETE FROM sessions')
    print('Đã khôi phục; phiên đăng nhập đã được thu hồi')

def client_ip(peer, forwarded):
    # Only a configured, isolated reverse proxy may supply the client address.
    trusted=[ipaddress.ip_network(value.strip()) for value in os.environ.get('TRUSTED_PROXY_CIDRS','').split(',') if value.strip()]
    if any(ipaddress.ip_address(peer) in network for network in trusted):
        try: return str(ipaddress.ip_address(forwarded.split(',')[-1].strip()))
        except ValueError: pass
    return peer

def reset_owner_password(email,password):
    password=text({'password':password},'password',128)
    if len(password)<10: raise ValueError('Mật khẩu cần ít nhất 10 ký tự')
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        user=db.execute("SELECT id FROM users WHERE email=? AND role='owner'",(email.strip().lower(),)).fetchone()
        if not user: raise ValueError('Không tìm thấy chủ nhà')
        salt=secrets.token_hex(16)
        db.execute('UPDATE users SET salt=?,password_hash=? WHERE id=?',(salt,password_hash(password,salt),user['id']))
        db.execute('DELETE FROM sessions WHERE user_id=?',(user['id'],))

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('command',nargs='?',choices=['serve','backup','restore','create-owner','reset-owner-password'],default='serve')
    parser.add_argument('file',nargs='?')
    parser.add_argument('--name',default='Chủ nhà')
    args=parser.parse_args()
    if args.command=='serve':
        interval=reminder_interval()
        init()
        stop=threading.Event()
        threading.Thread(target=reminder_worker,args=(stop,interval),daemon=True).start()
        try:
            ThreadingHTTPServer(('0.0.0.0',int(os.environ.get('PORT','3000'))),Handler).serve_forever()
        finally: stop.set()
    elif args.command in ['create-owner','reset-owner-password']:
        if not args.file: parser.error('Cần email chủ nhà')
        password=getpass.getpass('Mật khẩu chủ nhà: ')
        if password!=getpass.getpass('Nhập lại mật khẩu: '): parser.error('Mật khẩu không khớp')
        if args.command=='create-owner':
            init()
            token=authenticate({'name':args.name,'email':args.file,'password':password},True)
            with connect() as db:
                db.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),))
            print('Đã tạo chủ nhà; mật khẩu không được lưu dạng văn bản')
        else:
            reset_owner_password(args.file,password)
            print('Đã đổi mật khẩu chủ nhà và thu hồi các phiên đăng nhập')
    elif not args.file: parser.error('Cần đường dẫn tệp')
    elif args.command=='backup': backup(args.file)
    else: restore(args.file)
