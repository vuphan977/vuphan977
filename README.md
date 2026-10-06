# Roomly — MVP quản lý nhà trọ

Ứng dụng tiếng Việt quản lý phòng, người thuê, hợp đồng, điện nước, hóa đơn, QR chuyển khoản, công nợ, báo hỏng, lịch sử thu tiền và xuất dữ liệu.

## Chạy ứng dụng

Yêu cầu Python 3.12+. Server không có dependency bên ngoài.

```sh
python server.py
```

Cổng mặc định 3000; `PORT` đổi cổng, `APP_DB` đổi đường dẫn SQLite (mặc định `data/app.db`). Dữ liệu lưu bền vững. Đăng ký tài khoản để bắt đầu; mật khẩu tối thiểu 10 ký tự. Cookie phiên HttpOnly/SameSite=Strict, hết hạn sau 24 giờ. Có giới hạn thử đăng nhập/đăng ký: 10 lần mỗi IP trong 15 phút.

**Tài khoản đầu tiên tiếp nhận dữ liệu mẫu hoặc dữ liệu từ bản MVP cũ.** Tạo tài khoản chủ nhà của bạn trong môi trường riêng trước khi chia sẻ. Tài khoản sau bắt đầu với không gian trống. Không tạo sẵn mật khẩu quản trị.

Nâng cấp từ bản cũ tự sao lưu SQLite thành `data/app.db.before-auth-*.bak` trước khi chuyển đổi; phòng, hóa đơn và báo hỏng được giữ lại. Khoản tiền đã thu từ bản cũ được ghi là số dư đầu kỳ, ngày ghi nhận là ngày chuyển đổi vì bản cũ không có ngày thu thực tế.

## Luồng sử dụng

1. Thêm phòng và giá thuê.
2. Tạo hợp đồng với người thuê, thời hạn và tiền cọc.
3. Lập hóa đơn từ chỉ số điện nước, đơn giá và phí dịch vụ. Không cho tạo trùng tháng, chỉ số giảm hoặc hóa đơn ngoài thời hạn hợp đồng. Hóa đơn giữ tên phòng/người thuê tại thời điểm lập, không đổi theo hợp đồng sau đó.
4. Chọn QR, nhập BIN ngân hàng, tài khoản và chủ tài khoản. QR qua `img.vietqr.io`, cần Internet. Kiểm tra người nhận trước khi chuyển; chưa có tự động đối soát ngân hàng.
5. Ghi nhận thu tiền toàn bộ/một phần cùng ngày nhận và ghi chú. Dashboard tính dòng tiền theo **ngày thu**. Các khoản thu được ghi thành nhật ký; gửi lại cùng mã yêu cầu không ghi thu lần hai; không cho thu vượt công nợ, kể cả khi hai yêu cầu chạy đồng thời.
6. Báo hỏng, tiếp nhận và hoàn tất.
7. Mục Dữ liệu tải JSON của riêng tài khoản; không bao gồm mật khẩu/phiên đăng nhập. Tệp JSON này dùng lưu trữ/đối chiếu, chưa hỗ trợ nhập lại qua giao diện.

Mỗi chủ nhà chỉ đọc/sửa dữ liệu của mình; tên phòng có thể trùng giữa hai chủ nhà. Thông tin tài khoản ngân hàng lưu cục bộ trong trình duyệt theo tài khoản, không lưu vào database.

## Sao lưu và khôi phục cho người vận hành

Bản sao toàn bộ SQLite chứa dữ liệu của tất cả chủ nhà, mật khẩu đã băm và phiên đăng nhập. Bảo vệ tệp như dữ liệu riêng tư. Bản sao được đặt quyền 0600. Không đưa vào Git hoặc gửi cho khách hàng.

```sh
python server.py backup data/backups/roomly-2026-10-06.db
```

Lệnh dùng SQLite backup API, kiểm tra integrity và từ chối ghi đè tệp đã có. Dùng tên mới mỗi lần. Để khôi phục, **dừng tất cả server sử dụng DB này trước**, rồi chạy:

```sh
python server.py restore data/backups/roomly-2026-10-06.db
python server.py
```

Khôi phục kiểm tra tính toàn vẹn và các cột bắt buộc trước khi thay dữ liệu, tạo bản sao trạng thái hiện tại `*.before-restore-*.bak`, sau đó khôi phục và thu hồi toàn bộ phiên. Người dùng phải đăng nhập lại. Chưa có lịch sao lưu tự động hoặc lưu trữ ngoài máy.

## Kiểm thử

```sh
python -m unittest discover -s tests -v
node --check public/app.js
```

Bao gồm 21 kiểm thử: nghiệp vụ hóa đơn, thanh toán một phần, dữ liệu qua khởi động lại, đăng nhập/đăng xuất, CSRF, tách dữ liệu, yêu cầu thu tiền đồng thời, giới hạn đăng nhập, phiên hết hạn/giả mạo, yêu cầu thu tiền gửi lại đồng thời, dữ liệu sai kiểu, lịch sử người thuê và vòng sao lưu/khôi phục.

Kiểm thử trình duyệt cần Playwright và Chromium. Trong cloud hiện tại chúng có sẵn. Chạy với database riêng, không dùng dữ liệu vận hành:

```sh
APP_DB=/tmp/roomly-browser-test.db PORT=3001 python server.py
# Terminal khác:
TEST_URL=http://127.0.0.1:3001 node tests/browser.cjs
```

Bài test tạo tài khoản và dữ liệu thử, qua 11 màn hình, dữ liệu 200 phòng, tách tài khoản, chống chèn HTML, thu tiền trên điện thoại, xử lý báo hỏng, lịch sử người thuê và các thao tác chính; QR được kiểm tra tham số bằng dịch vụ giả lập, không phải chuyển khoản ngân hàng thực. Ngày mặc định theo múi giờ Việt Nam. Ảnh desktop/mobile lưu ở `artifacts/` (không đưa vào Git).

## Trước khi bán SaaS công khai

Đây là bản phát triển, chưa triển khai production. Cần reverse proxy HTTPS và `COOKIE_SECURE=1` (chỉ bật khi truy cập HTTPS), server triển khai phù hợp, xác minh email/khôi phục mật khẩu, theo dõi lỗi, sao lưu định kỳ ngoài máy, quản lý thuê bao và đối soát ngân hàng. Bộ giới hạn IP đang dùng IP kết nối trực tiếp; khi qua proxy cần cấu hình chính xác IP khách hàng. Hợp đồng là bản ghi thời hạn, chưa có văn bản pháp lý hoặc lịch sử thay đổi người thuê. Nhật ký hiện theo dõi các khoản thu, chưa phải audit log mọi thay đổi hệ thống. Chưa có thông báo tự động, AI hoặc tính phí thuê bao.
