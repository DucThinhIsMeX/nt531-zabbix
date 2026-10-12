# Kiểm tra bản 1.0

Ngày 08/10/2026.

Đã thực hiện:

- Compile toàn bộ file Python.
- Parse hai cấu hình Docker Compose bằng YAML parser.
- bash -n cho hai script delay/reset.
- 4 test cases, gồm percentile rỗng/nội suy; bình thường, mạng chậm, xử lý chậm, consumer dừng, thiếu dữ liệu và nhiều nguyên nhân; giữ nhãn qua hai cửa sổ; duplicate và request chưa hoàn tất.
- Chạy CLI summarize.py, evaluate.py và plot_results.py trên một fixture tổng hợp, kiểm tra JSON đầu ra, delay và PNG được tạo.

Chưa thực hiện:

- Kết nối live RabbitMQ, chạy Zabbix hoặc áp dụng tc lên NIC thật. Môi trường soạn không có Docker daemon hoặc ba máy LAN của nhóm.
- Kiểm chứng threshold demo trên phần cứng thật.
- Đo tính mới hoặc mức cải thiện của phương pháp trước khi có experiment.

Dependency Pika/python-dotenv/Requests cần được cài theo requirements.txt trên máy nhóm. Kiểm tra cú pháp không thay thế kiểm thử tích hợp. README Bước 5 là bài thử tích hợp nhỏ đầu tiên.

Phạm vi: code cho request/result, consumer runtime delay, ICMP/network metrics, collector, rule diagnosis, optional sender, delay/reset, summary/evaluation/timeline. Bandwidth/loss script và tự tạo Zabbix hosts/items/dashboard qua API chưa có trong bản này.
