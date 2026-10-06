# Bản để duyệt — 06/10/2026

## Nghiệp vụ đã có

- Phòng, người thuê, hợp đồng; xóa phòng hoặc reset dữ liệu có xác nhận.
- Tự cấp tên đăng nhập theo phòng và mật khẩu ngẫu nhiên khi tạo người thuê; cấp lại mật khẩu, thu hồi phiên cũ.
- Điện theo chỉ số đầu/cuối; nước theo đồng hồ hoặc số người; đơn giá, phí dịch vụ riêng cho từng phòng.
- Hóa đơn chi tiết, lập hàng loạt đến 200 phòng, gửi hóa đơn và nhắc hạn trong ứng dụng.
- Người thuê xem hóa đơn/công nợ riêng, nhận thông báo, QR theo ngân hàng chủ nhà, báo hỏng.
- Thu một phần/toàn bộ, hủy khoản ghi thu sai có lưu lý do, trả phòng và giữ lịch sử/công nợ.
- Dashboard, xuất dữ liệu, đổi mật khẩu, tách dữ liệu các chủ nhà.

## Đã kiểm chứng trong môi trường thử

56 kiểm thử Python; 4 bài kiểm thử trình duyệt: nghiệp vụ, quản lý phòng/reset, tài khoản người thuê/thông báo và tài khoản theo phòng/trả phòng. Bao gồm 200 phòng, giao diện điện thoại, thanh toán đồng thời, chống lặp khoản thu, phân quyền và phản hồi mạng đến sai thứ tự.

Docker build và bộ app/Caddy/backup đã chạy. HTTPS nội bộ được kiểm tra với chứng chỉ gốc tin cậy; cookie Secure/HttpOnly/SameSite=Strict, đóng đăng ký chủ nhà, tạo chủ nhà qua terminal, sao lưu/khôi phục và thu hồi phiên. QR được kiểm tra với dịch vụ giả lập, chưa xác minh giao dịch ngân hàng thực.

GitHub Actions được cấu hình chạy backend, kiểm tra cú pháp JavaScript và build image khi push/PR. Kết quả CI trên GitHub phải xem tại tab Actions; kết quả tại máy thử không thay thế kết quả CI.

## Còn phải hoàn tất để vận hành thật

1. Cấp máy chủ và tên miền, triển khai bằng [hướng dẫn vận hành](deploy/README.md).
2. Nghiệm thu toàn bộ luồng trên URL HTTPS thật, gồm ngân hàng nhận tiền đúng.
3. Thiết lập sao lưu có mã hóa ngoài máy chủ và cảnh báo lỗi/gián đoạn; kiểm chứng khôi phục từ bản sao ngoài máy.
4. Duyệt cho người dùng thật sử dụng sau khi các bước trên đạt.

Hiện chưa có máy chủ/tên miền hoặc quyền hạ tầng được kết nối trong phiên này. Chưa thể gọi bản này là hệ thống đã vận hành 24/7. Phạm vi MVP chưa gồm AI, gửi email/Zalo, thu phí gói SaaS hoặc tự đối soát ngân hàng.
