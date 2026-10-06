# Triển khai Roomly trên một máy chủ

Bộ triển khai dành cho một máy Linux có Docker Engine và Docker Compose v2, 2 GB RAM trở lên, ổ đĩa bền vững, một tên miền trỏ tới IP máy chủ và cổng 80/443 mở. Dữ liệu SQLite nằm trong Docker volume; chưa hỗ trợ nhiều máy chủ dùng chung database. Không dùng môi trường Codex làm máy chủ vận hành 24/7.

## Cài lần đầu

```sh
git clone https://github.com/vuphan977/vuphan977.git
cd vuphan977
```

Tạo `.env` với đúng tên miền của bạn, ví dụ `DOMAIN=tro.example.com`. Không đặt URL có `https://` vào biến này. `.env` không được đưa vào Git.

```sh
docker compose build app
docker compose run --rm -it app python server.py create-owner owner@example.com --name "Chủ nhà"
docker compose up -d
docker compose ps
```

Thay email trước khi chạy. Lệnh tạo chủ nhà hỏi mật khẩu hai lần trong terminal và không in mật khẩu. Tạo chủ nhà **trước** khi bật web. Cấu hình vận hành không tạo dữ liệu mẫu và đóng đăng ký chủ nhà công khai; tài khoản người thuê theo phòng và nhận lời mời vẫn hoạt động. Chỉ mở đăng ký chủ nhà khi bạn đã quyết định cho khách hàng tự đăng ký.

Caddy tự cấp/gia hạn HTTPS khi DNS và cổng đúng. App không xuất cổng trực tiếp ra Internet. Giữ app trong mạng riêng vì app chỉ tin `X-Forwarded-For` từ mạng này để giới hạn đăng nhập theo IP thực. Nếu subnet `172.30.8.0/24` trùng mạng máy chủ, đổi đồng thời subnet và `TRUSTED_PROXY_CIDRS`.

## Nghiệm thu trước khi giao người dùng

Trên URL HTTPS thực, đăng nhập chủ nhà và kiểm tra: tạo phòng → hợp đồng → nhận tài khoản tự sinh → cấu hình điện/nước theo người → hóa đơn → người thuê đăng nhập nhận hóa đơn → QR đúng ngân hàng/số tiền → ghi thu một phần → công nợ → nhắc hạn → báo hỏng. Kiểm tra người thuê khác không xem được hóa đơn này. QR chưa tự xác nhận tiền vào ngân hàng.

Kiểm tra cookie `roomly_session` có Secure/HttpOnly/SameSite=Strict. Khởi động lại app rồi xác nhận dữ liệu còn nguyên. `https://<tên-miền>/healthz` phải trả `{"ok":true}`. Healthcheck chỉ xác minh HTTP và database, không thay thế kiểm tra nghiệp vụ hoặc giám sát từ bên ngoài.

## Sao lưu

Service `backup` sao lưu ngay khi khởi động và mỗi 6 giờ, giữ 28 bản gần nhất, tương đương khoảng 7 ngày. Chỉ xóa bản tự động sau khi bản mới đã kiểm tra integrity. Bản sao nằm trong cùng volume tại `/data/backups`; **mất máy chủ vẫn có thể mất cả dữ liệu và bản sao**. Trước khi vận hành thực, thiết lập thêm việc sao chép có mã hóa sang nơi lưu ngoài máy chủ và cảnh báo khi sao lưu lỗi.

```sh
docker compose logs --tail=30 backup
docker compose exec app python server.py backup /data/backups/manual-before-upgrade.db
docker compose cp app:/data/backups ./private-backups
```

Dùng tên bản sao mới mỗi lần. `private-backups` chứa thông tin riêng tư; không đưa vào Git, không gửi cho người thuê. Kiểm chứng khôi phục trên máy thử trước khi vận hành.

## Khôi phục

```sh
docker compose stop app backup
docker compose run --rm app python server.py restore /data/backups/<tên-bản-sao>.db
docker compose up -d app backup web
```

Thay tên bản sao thật. Khôi phục tạo bản sao trạng thái cũ và thu hồi toàn bộ phiên đăng nhập. Không chạy khôi phục khi app/backup vẫn đang dùng DB.

## Cập nhật

Tạo bản sao với tên mới, sau đó:

```sh
git pull --ff-only
docker compose build app
docker compose stop app backup
docker compose up -d
docker compose ps
docker compose logs --tail=30 app backup
```

Không chạy `docker compose down -v`: tùy chọn `-v` xóa các volume dữ liệu. Khi cần quay lại phiên bản cũ sau migration, dừng dịch vụ và khôi phục bản sao trước cập nhật; không chỉ đổi source code.

## Phạm vi đã chuẩn bị

HTTPS, restart tự động, healthcheck, database bền vững, sao lưu trong máy và hướng dẫn khôi phục. Việc nghiệm thu trên tên miền thật, sao lưu ngoài máy, cảnh báo vận hành vẫn cần hoàn tất trước khi bán. Chưa có thanh toán gói SaaS, tự động đối soát ngân hàng hay gửi email/Zalo.

## Quên mật khẩu chủ nhà

Người vận hành có quyền vào máy chủ xác minh danh tính chủ nhà trước, rồi chạy `docker compose exec -it app python server.py reset-owner-password owner@example.com`. Lệnh hỏi mật khẩu mới hai lần và thu hồi mọi phiên của chủ nhà đó. Chỉ dùng sau khi xác minh đúng người; chưa có khôi phục qua email.
