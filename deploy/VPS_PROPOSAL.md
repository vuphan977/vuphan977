# Phương án VPS để duyệt

Đề xuất dùng **một VPS DigitalOcean tại Singapore**, Ubuntu 24.04 LTS, **2 vCPU / 2 GB RAM / SSD ít nhất 50 GB**. Đây là cấu hình khởi đầu cho MVP quản lý 20–200 phòng; cần đo tải khi có nhiều chủ nhà/người thuê hoạt động đồng thời. Chưa mua dịch vụ hoặc tạo tài nguyên tính phí.

## Ngân sách dự kiến

| Hạng mục | Dự trù |
| --- | --- |
| VPS cấu hình trên | 18–24 USD/tháng |
| Lưu bản sao ngoài VPS, tương thích S3 | Khoảng 5 USD/tháng ở mức cơ bản |
| Tên miền | Dự trù 10–20 USD/năm, tùy tên và đuôi |
| HTTPS qua Caddy/Let's Encrypt | Không có phí chứng chỉ |

**Đề nghị duyệt trần ngân sách 35 USD/tháng**, chưa gồm thuế và các chi phí vượt dung lượng/lưu lượng. Đây là dự trù, không phải báo giá đã xác minh. Giá ngày mua phải đối chiếu tại [DigitalOcean Droplets](https://www.digitalocean.com/pricing/droplets) và [Spaces](https://www.digitalocean.com/pricing/spaces); phiên cloud hiện tại không truy cập được các trang này do giới hạn mạng.

Nếu chưa có nhu cầu chọn DigitalOcean, có thể dùng VPS khác đáp ứng cấu hình tương đương; bộ triển khai không phụ thuộc nhà cung cấp.

## Cách vận hành

- Tên miền trỏ tới IP VPS, Caddy cấp/gia hạn HTTPS. App và database ở mạng riêng.
- Một database SQLite bền vững, một app instance, chưa chạy nhiều VPS cùng database.
- Sao lưu mỗi 6 giờ tại VPS, giữ khoảng 7 ngày; sao chép thêm bản có mã hóa ra kho ngoài VPS, dự kiến giữ 30 ngày. Cần triển khai và kiểm chứng phần sao chép ngoài máy khi có kho lưu/quyền truy cập.
- Mục tiêu mất dữ liệu tối đa 6 giờ nếu lịch sao lưu hoạt động đúng; thời gian khôi phục thực tế phải đo trong buổi nghiệm thu, chưa cam kết SLA.
- Theo dõi HTTPS/healthcheck từ bên ngoài, dung lượng ổ đĩa và tuổi bản sao mới nhất. Cảnh báo gửi cho người vận hành qua kênh được duyệt; chưa thiết lập hay gửi thông báo ra ngoài.
- Tạo chủ nhà qua terminal trước khi mở web. Người thuê nhận tài khoản tự sinh theo phòng. Đăng ký chủ nhà công khai được đóng ban đầu.

## Việc tôi thực hiện sau khi hạ tầng được cấp

1. Cài Docker, mở cổng cần thiết, cấu hình DNS/HTTPS và triển khai bản Git đã kiểm thử.
2. Thiết lập dữ liệu bền vững, sao lưu ngoài VPS và giám sát; bảo vệ thông tin truy cập trên máy chủ.
3. Chạy nghiệm thu qua URL thật cho chủ nhà/người thuê, điện nước, hóa đơn, công nợ, QR và thông báo.
4. Thử khởi động lại và khôi phục từ bản sao ngoài máy; báo kết quả để duyệt cho người dùng thật.

## Nội dung cần duyệt

Nhà cung cấp/cấu hình và trần ngân sách trên; tên miền bạn muốn dùng. Sau khi duyệt cần tài khoản nhà cung cấp và phương thức thanh toán do bạn quản lý, quyền triển khai VPS/DNS và kho sao lưu được cấp qua cơ chế kết nối an toàn. Không gửi mật khẩu, private key hoặc mã thẻ trong chat. Duyệt phương án không đồng nghĩa máy chủ đã được mua hay hệ thống đã được triển khai.
