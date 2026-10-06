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

Mỗi chủ nhà chỉ đọc/sửa dữ liệu của mình; tên phòng có thể trùng giữa hai chủ nhà. Thông tin ngân hàng lưu trong database theo chủ nhà; người thuê chỉ nhận thông tin của chủ nhà có hóa đơn đã gửi cho mình.

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

Bao gồm 56 kiểm thử: nghiệp vụ hóa đơn, thanh toán một phần, dữ liệu qua khởi động lại, đăng nhập/đăng xuất, CSRF, tách dữ liệu, yêu cầu thu tiền đồng thời, giới hạn đăng nhập, phiên hết hạn/giả mạo, yêu cầu thu tiền gửi lại đồng thời, dữ liệu sai kiểu, lịch sử người thuê và vòng sao lưu/khôi phục.

Kiểm thử trình duyệt cần Playwright và Chromium. Trong cloud hiện tại chúng có sẵn. Chạy với database riêng, không dùng dữ liệu vận hành:

```sh
APP_DB=/tmp/roomly-browser-test.db PORT=3001 python server.py
# Terminal khác:
TEST_URL=http://127.0.0.1:3001 node tests/browser.cjs
```

Bài test tạo tài khoản và dữ liệu thử, qua các màn hình chủ nhà và người thuê, dữ liệu 200 phòng, tách tài khoản, chống chèn HTML, thu tiền trên điện thoại, xử lý báo hỏng, lịch sử người thuê và các thao tác chính; QR được kiểm tra tham số bằng dịch vụ giả lập, không phải chuyển khoản ngân hàng thực. Ngày mặc định theo múi giờ Việt Nam. Ảnh desktop/mobile lưu ở `artifacts/` (không đưa vào Git).

## Trước khi bán SaaS công khai

Đây là bản phát triển, chưa triển khai production. Cần reverse proxy HTTPS và `COOKIE_SECURE=1` (chỉ bật khi truy cập HTTPS), server triển khai phù hợp, xác minh email/khôi phục mật khẩu, theo dõi lỗi, sao lưu định kỳ ngoài máy, quản lý thuê bao và đối soát ngân hàng. Bộ giới hạn IP đang dùng IP kết nối trực tiếp; khi qua proxy cần cấu hình chính xác IP khách hàng. Hợp đồng là bản ghi thời hạn, chưa có văn bản pháp lý hoặc lịch sử thay đổi người thuê. Nhật ký hiện theo dõi các khoản thu, chưa phải audit log mọi thay đổi hệ thống. Có thông báo hóa đơn và nhắc hạn trong ứng dụng khi server đang chạy; chưa có email/Zalo, AI hoặc tính phí thuê bao.

## Xóa phòng, reset và chốt tháng (bản mới)

- **Phòng → Xóa phòng**: nhập chính xác tên phòng để xác nhận. Xóa cả hợp đồng, hóa đơn, khoản thu, công nợ và báo hỏng liên quan. Không thể hoàn tác trong ứng dụng; nên xuất dữ liệu trước.
- **Dữ liệu → Reset về tài khoản trống**: nhập `XÓA DỮ LIỆU` và mật khẩu hiện tại. Chỉ xóa dữ liệu quản lý của tài khoản đang đăng nhập; giữ tài khoản, không tác động chủ nhà khác. Sau khởi động lại cũng không tự sinh phòng mẫu. Reset xóa thông tin QR đã lưu trên trình duyệt hiện tại; các trình duyệt khác có thể còn thông tin QR cục bộ.
- **Phòng → Sửa phòng**: đổi tên và giá thuê. Hóa đơn đã lập giữ tên/giá gốc. Có tìm theo phòng/người thuê và lọc tình trạng thuê.
- **Điện nước → Chốt điện nước nhiều phòng**: chọn tháng, đơn giá, phí dịch vụ; chọn các phòng, nhập chỉ số mới. Lấy chỉ số cũ từ hóa đơn gần nhất trước tháng chọn, cho phép sửa khi cần. Phòng ngoài thời hạn hợp đồng hoặc đã có hóa đơn tháng đó sẽ không xuất hiện trong danh sách. Lập tối đa 200 hóa đơn trong một giao dịch; một phòng sai sẽ hủy toàn bộ lần lập, không tạo dữ liệu một phần. Đây là thao tác chủ nhà xác nhận, chưa tự phát hành theo lịch.

Kiểm thử quản lý trong trình duyệt (server/database thử riêng như ở trên):

```sh
TEST_URL=http://127.0.0.1:3001 node tests/browser-management.cjs
```

Bài test này thực sự xóa/reset dữ liệu của tài khoản thử do chính nó tạo. Không chạy trên cơ sở dữ liệu vận hành.

## Điện, nước theo người và tài khoản người thuê

**Phòng → Điện nước / Nhắc thu** cho phép lưu riêng từng phòng:

- Đơn giá một số điện (kWh). Tiền điện = (chỉ số chốt − chỉ số đầu) × đơn giá.
- Số người (1–50) và cách tính nước: **Theo đồng hồ** = (chốt − đầu) × giá/m³; **Theo người** = số người × giá/người/tháng. Khi theo người, không cần nhập chỉ số nước.
- Phí dịch vụ cố định theo tháng, ngày thu tiền (1–31), nhắc trước 0–30 ngày.
- Bật/tắt tự gửi hóa đơn và nhắc hạn trong ứng dụng. Ngày thu 31 được điều chỉnh về ngày cuối tháng ngắn hơn.

Hóa đơn một phòng tự lấy đơn giá/phí đã lưu và có bảng tạm tính. Lập hàng loạt mặc định dùng cài đặt của từng phòng; các ô đơn giá chung để trống. Nếu cần, nhập đơn giá chung để ghi đè cho lượt lập đó. Hóa đơn lưu số người, cách tính nước, đơn giá, tiền phòng, điện, nước, dịch vụ và hạn thu tại thời điểm lập; các thay đổi cài đặt sau không sửa hóa đơn cũ. Nút **Chi tiết** hiển thị bảng tiền từng khoản và **In / Lưu PDF** qua trình duyệt.

### Liên kết tài khoản người thuê

1. Nếu muốn dùng tài khoản cá nhân/email, chọn **Tắt: dùng liên kết mời** khi tạo hợp đồng; mặc định hệ thống tự cấp tài khoản phòng (xem bên dưới). Chủ nhà cài đặt tính tiền.
2. Chọn **Mời người thuê** ở phòng, sao chép liên kết và gửi cho đúng người thuê qua kênh bạn sử dụng.
3. Người thuê mở liên kết và tự tạo tài khoản; hoặc đăng nhập tài khoản người thuê đã có để nhận lời mời. Liên kết dùng một lần, hết hạn sau 7 ngày. Tạo lời mời mới thu hồi lời mời cũ. Tài khoản chủ nhà không thể dùng lời mời để nhận quyền người thuê.
4. Người thuê có bốn mục: **Hóa đơn của tôi**, **Thông báo**, **Báo hỏng**, **Tài khoản**. Chỉ xem hóa đơn được gửi cho mình và báo hỏng do mình tạo; không được ghi nhận thu tiền, sửa phòng/giá hoặc reset.

Mỗi phòng hiện liên kết **một tài khoản đại diện người thuê**; số người tính tiền nước có thể lớn hơn một. Chưa hỗ trợ nhiều tài khoản đồng cư trú cùng phòng. Người thuê có thể liên kết nhiều phòng. Khi đổi tên người thuê, điện thoại hoặc ngày bắt đầu hợp đồng, liên kết cũ bị gỡ; cần mời lại. Hóa đơn cũ vẫn thuộc tài khoản cũ. Có mã phiên hợp đồng để tránh gửi hóa đơn của hợp đồng trước cho người thuê mới trùng tên.

### Gửi hóa đơn và nhắc hạn

- Nếu bật tự gửi và đã liên kết tài khoản, hóa đơn mới được gửi vào tài khoản người thuê ngay khi tạo, trong cùng giao dịch lưu hóa đơn. Nếu liên kết sau, gửi các hóa đơn phù hợp của hợp đồng hiện tại.
- Nếu tắt tự gửi, hóa đơn chưa hiển thị cho người thuê. Chủ nhà bấm **Gửi hóa đơn** để gửi thủ công. Gửi lại không tạo thông báo trùng.
- Tác vụ nền chạy mỗi 60 giây khi `python server.py` hoạt động, gửi một thông báo nhắc cho hóa đơn đã gửi, còn nợ và đến mốc nhắc. Nếu server vừa khởi động lại sau mốc này, tác vụ sẽ kiểm tra và gửi bù. Không lặp lại hằng ngày, không nhắc hóa đơn đã thu đủ. Cài đặt bật/tắt và số ngày nhắc hiện tại của phòng được áp dụng cho tác vụ; ngày hạn trên hóa đơn giữ nguyên.
- Đây là **thông báo bên trong ứng dụng**, được lưu để người thuê đọc khi đăng nhập; giao diện người thuê cập nhật mỗi 15 giây khi tab đang mở, không có cửa sổ nhập liệu; chưa có push trên điện thoại, email hoặc Zalo. Máy/server phải hoạt động để tác vụ chạy. Chủ nhà vẫn ghi nhận thu tiền thủ công, chưa có đối soát ngân hàng.
- Link mời dùng địa chỉ mà chủ nhà đang mở. Nếu là localhost trên máy chủ nhà, người thuê trên máy khác không mở được; cần triển khai lên địa chỉ truy cập chung. Khi thử trên một máy, mở link bằng cửa sổ ẩn danh/trình duyệt khác.

Kiểm thử cổng người thuê trên database riêng, rút ngắn chu kỳ nhắc để kiểm chứng worker thực tế:

```sh
APP_DB=/tmp/roomly-portal-test.db PORT=3001 REMINDER_INTERVAL=1 python server.py
# Terminal khác
TEST_URL=http://127.0.0.1:3001 node tests/browser-tenants.cjs
```

Bài test cấu hình 3 người, nước theo người, điện theo chỉ số, nhận lời mời, tự gửi hóa đơn, chạy worker nhắc hạn thực, xem từng khoản, đánh dấu đã đọc, báo hỏng và chặn thao tác quản trị từ tài khoản người thuê. Không có gửi ra dịch vụ bên ngoài.

## Tự cấp tài khoản theo phòng (mặc định)

Khi chủ nhà tạo hoặc cập nhật hợp đồng cho phòng chưa có tài khoản người thuê, hệ thống tự tạo tài khoản đại diện phòng và liên kết ngay. **Tên đăng nhập** dựa trên mã chủ nhà, tên phòng, phiên hợp đồng và mã tài khoản để không trùng giữa các nhà/phòng. **Mật khẩu ngẫu nhiên chỉ xuất hiện một lần** trong cửa sổ sau khi lưu; chủ nhà sao chép và giao riêng cho người thuê. Đóng cửa sổ sẽ xóa mật khẩu khỏi nội dung giao diện. Database chỉ lưu băm PBKDF2 có salt, không lưu mật khẩu gốc.

Người thuê mở địa chỉ ứng dụng, nhập tên phòng đã được cấp vào ô **Email hoặc tên đăng nhập phòng** cùng mật khẩu. Không cần tự đăng ký. Các địa chỉ `@roomly.local` trong DB chỉ là mã nội bộ, không phải email gửi thư.

- Khi đổi tên người thuê, số điện thoại hoặc ngày bắt đầu hợp đồng, cấp tài khoản mới nếu bật tự tạo. Tài khoản cũ giữ các hóa đơn của hợp đồng cũ; người thuê mới không thấy lịch sử đó.
- Lưu lại cùng thông tin khi phòng đã liên kết không tạo tài khoản hoặc hiện lại mật khẩu.
- **Phòng → Cấp lại mật khẩu phòng** yêu cầu nhập tên phòng, sinh mật khẩu mới và thu hồi các phiên của tài khoản phòng. Chỉ áp dụng tài khoản tự cấp do chính chủ nhà quản lý; không cho chủ nhà đổi mật khẩu tài khoản email cá nhân của người thuê.
- Tài khoản tự cấp chỉ nhận quyền cho phòng đã cấp, không được dùng lời mời để nhận thêm phòng/chủ nhà khác. Tài khoản email cá nhân vẫn có thể nhận các lời mời hợp lệ.
- **Tài khoản → Đổi mật khẩu** có ở cả chủ nhà và người thuê. Yêu cầu mật khẩu hiện tại, tối thiểu 10 ký tự và đăng nhập lại; thu hồi tất cả phiên của tài khoản đó. Chưa có khôi phục mật khẩu qua email khi người dùng quên mật khẩu.

## Chốt hợp đồng, hủy thu nhầm và QR người thuê

**Hợp đồng → Trả phòng**: nhập tên phòng, ngày trả, lý do. Nếu còn nợ, mặc định chặn; chủ nhà có thể chọn **Cho kết thúc và giữ công nợ**. Phòng về trống, số người về 1, ngắt tài khoản hiện tại và giữ lịch sử hợp đồng, tiền cọc đã ghi, hóa đơn, công nợ và các khoản thu. Đây không phải thao tác hoàn cọc tự động. Khi thay người thuê trực tiếp, hợp đồng trước cũng được ghi lịch sử.

**Lịch sử thu tiền → Hủy khoản thu**: nhập lý do, đánh dấu khoản thu đã hủy và khôi phục công nợ tương ứng. Bản ghi gốc còn trong nhật ký, có thời điểm/lý do hủy; dashboard bỏ các khoản đã hủy. Hủy lặp lại không trừ tiền hai lần. Mã yêu cầu của khoản thu đã hủy không thể dùng để ghi lại; muốn thu lại phải tạo khoản thu mới. Thao tác không thực hiện hoàn tiền ngân hàng.

**Dữ liệu → Cài đặt nhận thanh toán**: lưu BIN ngân hàng, số tài khoản và tên người nhận ở chủ nhà. Người thuê chỉ được xem thông tin nhận tiền của chủ nhà có hóa đơn đã gửi cho mình và có thể mở QR từ hóa đơn còn nợ. QR dùng tài khoản nhận tiền hiện tại của chủ nhà, không phải bản chụp lịch sử ngân hàng; kiểm tra người nhận trước khi chuyển. QR đã kiểm tra tham số qua dịch vụ giả lập; chưa có giao dịch/đối soát ngân hàng thực.

Kiểm thử thao tác vận hành bổ sung, dùng database riêng và cổng riêng để không chia sẻ giới hạn đăng nhập với các suite khác:

```sh
APP_DB=/tmp/roomly-account-browser.db PORT=3002 REMINDER_INTERVAL=1 python server.py
# Terminal khác
TEST_URL=http://127.0.0.1:3002 node tests/browser-operations.cjs
```

Không chạy các bài test trình duyệt trên DB vận hành. Chúng thực sự tạo tài khoản, đổi mật khẩu, kết thúc hợp đồng, hủy khoản thu và reset fixture.

## Triển khai vận hành

Xem [hướng dẫn Docker + HTTPS + sao lưu](deploy/README.md). Bộ triển khai đóng đăng ký chủ nhà công khai, tắt dữ liệu mẫu và lưu database trong volume riêng. Cần nghiệm thu trên máy chủ/tên miền thật, sao lưu ngoài máy và giám sát trước khi dùng thương mại.

## App điện thoại

Roomly có bản PWA cài từ trình duyệt lên màn hình chính Android/iPhone, điều hướng dưới và màn hình mất mạng. Xem [hướng dẫn cài và phạm vi kiểm chứng](deploy/MOBILE.md). Cần URL HTTPS vận hành để dùng trên điện thoại thật; hiện chưa phát hành APK/IPA hoặc lên cửa hàng. Chạy bài kiểm thử bổ sung `TEST_URL=http://127.0.0.1:3010 node tests/browser-mobile.cjs` với server/database thử riêng như hướng dẫn.
