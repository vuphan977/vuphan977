# Roomly trên điện thoại

Bản hiện tại là **PWA**, cài từ trình duyệt lên màn hình chính, dùng chung backend và dữ liệu với bản web. Khi mở từ biểu tượng, app chạy trong cửa sổ riêng trên các trình duyệt hỗ trợ. Có biểu tượng Android/iPhone, thanh điều hướng dưới, menu điện thoại và màn hình khi mất mạng.

## Android

1. Mở URL HTTPS thật của Roomly trong Chrome.
2. Chọn **Cài Roomly**. Nếu chưa hiện hộp thoại cài, mở menu ⋮ rồi chọn **Cài đặt ứng dụng** hoặc **Thêm vào màn hình chính**.
3. Mở Roomly từ biểu tượng vừa thêm và đăng nhập tài khoản chủ nhà hoặc tài khoản phòng đã cấp.

## iPhone / iPad

1. Mở URL HTTPS thật của Roomly trong Safari.
2. Chọn **Chia sẻ → Thêm vào Màn hình chính → Thêm**. Tên/nút có thể khác theo phiên bản iOS.
3. Mở Roomly từ biểu tượng mới và đăng nhập. Nếu đang xem trong Zalo/Facebook, chuyển sang Safari trước.

Trên máy tính, nút **Cài Roomly** mở hộp thoại cài khi trình duyệt hỗ trợ hoặc hướng dẫn cài. App được cài trên thiết bị vẫn cần backend chạy 24/7; phải triển khai VPS/HTTPS để dùng trên điện thoại thật. `localhost` trên điện thoại là chính điện thoại, không phải máy tính đang chạy server.

## Dữ liệu và kết nối

Cache chỉ lưu các tệp giao diện công khai, biểu tượng và màn hình mất mạng. Không cache API, HTML dashboard cá nhân, tài khoản/người thuê, hóa đơn, công nợ, QR bên ngoài hoặc mật khẩu. Khi đang mở app và mất mạng, hiển thị trạng thái và chặn lưu; không tạo hàng đợi giao dịch offline. Khi mở app lúc mất mạng, hiển thị màn hình kết nối lại. Chọn **Thử lại** sau khi có mạng.

Hóa đơn và nhắc hạn vẫn gửi **trong ứng dụng**, theo phạm vi đã chọn. Chưa có push notification khi app đóng, APK/IPA hoặc bản phát hành Google Play/App Store. Không tự xin quyền thông báo hoặc quyền truy cập điện thoại.

Nếu có phiên bản mới, app hiện nút **Cập nhật** khi service worker mới chờ kích hoạt. Người dùng chủ động cập nhật. Khi thay đổi các tệp precache trong `public/sw.js`, đổi tên phiên bản `roomly-public-v1` để dọn cache cũ đúng phạm vi.

## Kiểm chứng

```sh
APP_DB=/tmp/roomly-mobile-test.db PORT=3010 REMINDER_INTERVAL=1 python server.py
# Terminal khác:
TEST_URL=http://127.0.0.1:3010 node tests/browser-mobile.cjs
```

Bài test dùng Chromium với viewport và user agent điện thoại: manifest/MIME, kích thước PNG, màn hình 320/390/412 px, điều hướng dưới/menu, form chạm, hướng dẫn Android/iPhone, xử lý install prompt giả lập, cache không chứa API, chặn lưu offline, mở offline/kết nối lại và đăng xuất. Các bài kiểm thử nghiệp vụ cũ cũng sử dụng điều hướng điện thoại mới. Chưa kiểm chứng cài trên hệ điều hành thật hoặc Safari/WebKit thật.

Trước khi giao người dùng, thử URL HTTPS vận hành trên ít nhất một máy Android và một iPhone: cài, đăng nhập, nhận hóa đơn, QR, mở từ biểu tượng, đóng/mở lại app, mất mạng và cập nhật. Nếu muốn lên cửa hàng, bước sau cần chốt Android/iOS, làm gói phát hành và có tài khoản nhà phát triển, ký ứng dụng, chính sách riêng tư cùng quy trình xét duyệt của cửa hàng.
