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
from http.cookies import SimpleCookie
from urllib.parse import urlsplit
from datetime import date, datetime
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
        if not db.execute('SELECT 1 FROM rooms LIMIT 1').fetchone() and not db.execute('SELECT 1 FROM users LIMIT 1').fetchone():
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

def mutate(path, data, owner_id):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if path == '/api/rooms':
            name = text(data,'name',80)
            db.execute('INSERT INTO rooms(name,rent,owner_id) VALUES(?,?,?)', (name, integer(data,'rent'),owner_id))
        elif path == '/api/contracts':
            room = db.execute('SELECT * FROM rooms WHERE id=? AND owner_id=?',(integer(data,'room_id'),owner_id)).fetchone()
            if not room: raise ValueError('Không tìm thấy phòng')
            tenant = text(data,'tenant',150)
            start, end = iso_date(data.get('start')), iso_date(data.get('end'))
            if end <= start: raise ValueError('Ngày kết thúc phải sau ngày bắt đầu')
            db.execute('UPDATE rooms SET tenant=?,phone=?,start=?,end=?,deposit=? WHERE id=?',(tenant,text(data,'phone',30,False),str(start),str(end),integer(data,'deposit'),room['id']))
        elif path == '/api/invoices':
            room = db.execute('SELECT * FROM rooms WHERE id=? AND owner_id=?',(integer(data,'room_id'),owner_id)).fetchone()
            if not room or not room['tenant']: raise ValueError('Phòng chưa có hợp đồng')
            month = text(data,'month',7)
            if not re.fullmatch(r'\d{4}-\d{2}',month): raise ValueError('Tháng cần định dạng YYYY-MM')
            iso_date(month+'-01')
            if month < room['start'][:7] or month > room['end'][:7]:
                raise ValueError('Tháng hóa đơn nằm ngoài thời hạn hợp đồng')
            keys = ['electric_old','electric_new','water_old','water_new','electric_rate','water_rate','fee']
            eo,en,wo,wn,er,wr,fee = [integer(data,k) for k in keys]
            if en < eo or wn < wo: raise ValueError('Chỉ số mới phải lớn hơn hoặc bằng chỉ số cũ')
            total = room['rent']+(en-eo)*er+(wn-wo)*wr+fee
            if total > 1000000000: raise ValueError('Tổng hóa đơn vượt giới hạn 1 tỷ đồng')
            db.execute('INSERT INTO invoices(room_id,month,electric_old,electric_new,water_old,water_new,electric_rate,water_rate,rent,fee,total,owner_id,tenant_name,tenant_phone,room_name) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(room['id'],month,eo,en,wo,wn,er,wr,room['rent'],fee,total,owner_id,room['tenant'],room['phone'],room['name']))
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

def authenticate(data, register=False, ip='local'):
    email = text(data,'email',254).lower()
    password = data.get('password','')
    if not isinstance(password,str) or not 10 <= len(password) <= 128:
        raise ValueError('Mật khẩu cần 10–128 ký tự')
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email) or len(email)>254:
        raise ValueError('Email không hợp lệ')
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
            salt=secrets.token_hex(16)
            uid=db.execute('INSERT INTO users(email,name,salt,password_hash) VALUES(?,?,?,?)',(email,name,salt,password_hash(password,salt))).lastrowid
            if first:
                for table in ['rooms','invoices','repairs']:
                    db.execute(f'UPDATE {table} SET owner_id=? WHERE owner_id IS NULL',(uid,))
                # Preserve previously recorded prototype receipts as opening entries.
                for inv in db.execute('SELECT * FROM invoices WHERE owner_id=? AND paid>0',(uid,)).fetchall():
                    db.execute('INSERT INTO payments(owner_id,invoice_id,amount,received,note) VALUES(?,?,?,?,?)',(uid,inv['id'],inv['paid'],str(business_today()),'Số dư thu từ bản MVP; ngày thu gốc chưa được ghi nhận'))
        else:
            user=db.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
            salt=user['salt'] if user else '0'*32
            candidate=password_hash(password,salt)
            if not user or not hmac.compare_digest(candidate,user['password_hash']): raise ValueError('Email hoặc mật khẩu không đúng')
            uid=user['id']
        token=secrets.token_urlsafe(32)
        db.execute('DELETE FROM sessions WHERE expires<=?',(now,))
        db.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),uid,now+86400))
        return token

class Handler(SimpleHTTPRequestHandler):
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
            row=db.execute('SELECT users.id,users.email,users.name FROM sessions JOIN users ON users.id=sessions.user_id WHERE token_hash=? AND expires>?',(digest,int(time.time()))).fetchone()
        return dict(row) if row else None
    def do_GET(self):
        if self.path.startswith('/api/'):
            user=self.session()
            if self.path=='/api/me':
                with connect() as db: first=not db.execute('SELECT 1 FROM users LIMIT 1').fetchone()
                self.respond(200,{'user':user,'first_account':first}); return
            if not user: self.respond(401,{'error':'Vui lòng đăng nhập'}); return
            if self.path=='/api/state':
                with connect() as db:
                    self.respond(200,{t:[dict(r) for r in db.execute(f'SELECT * FROM {t} WHERE owner_id=? ORDER BY id DESC',(user['id'],))] for t in ['rooms','invoices','repairs','payments']})
            elif self.path=='/api/export':
                with connect() as db:
                    self.respond(200,{'version':1,'exported':str(business_today()),'data':{t:[dict(r) for r in db.execute(f'SELECT * FROM {t} WHERE owner_id=? ORDER BY id',(user['id'],))] for t in ['rooms','invoices','repairs','payments']}})
            else: self.respond(404,{'error':'Không tìm thấy API'})
        else: super().do_GET()
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
            if not 0 < length <= 20000: raise ValueError('Dữ liệu quá lớn hoặc rỗng')
            data=json.loads(self.rfile.read(length))
            if not isinstance(data,dict): raise ValueError('Dữ liệu không hợp lệ')
            if self.path in ['/api/login','/api/register']:
                token=authenticate(data,self.path=='/api/register',self.client_address[0])
                self.respond(200,{'ok':True},cookie=token); return
            user=self.session()
            if not user: self.respond(401,{'error':'Vui lòng đăng nhập'}); return
            if self.path=='/api/logout':
                cookies=SimpleCookie(self.headers.get('Cookie',''))
                digest=hashlib.sha256(cookies['roomly_session'].value.encode()).hexdigest()
                with connect() as db: db.execute('DELETE FROM sessions WHERE token_hash=?',(digest,))
                self.respond(200,{'ok':True},cookie=''); return
            mutate(self.path,data,user['id']); self.respond(200,{'ok':True})
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

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('command',nargs='?',choices=['serve','backup','restore'],default='serve')
    parser.add_argument('file',nargs='?')
    args=parser.parse_args()
    if args.command=='serve':
        init()
        ThreadingHTTPServer(('0.0.0.0',int(os.environ.get('PORT','3000'))),Handler).serve_forever()
    elif not args.file: parser.error('Cần đường dẫn tệp')
    elif args.command=='backup': backup(args.file)
    else: restore(args.file)
