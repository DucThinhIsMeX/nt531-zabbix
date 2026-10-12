# Bộ code đồ án NT531.R11 trên ba máy Linux thật

Bản 1.0 - 08/10/2026. Trong thư mục này đã có code, không cần tự tạo lại các file Python theo bản kế hoạch trước.

## Đọc trước khi chạy

A chạy Zabbix, producer và collector. B chạy RabbitMQ. C chạy consumer và metrics_agent. Ba máy dùng Linux trực tiếp và cùng LAN. Lệnh cài package dưới đây theo Ubuntu 24.04; nếu khác Ubuntu 24.04 cần đổi bộ lệnh cài phù hợp. Không cài lại Linux đã có.

Code dùng request/result queues durable classic, persistent messages, confirm và manual ack. Kết quả có thể lặp khi có lỗi: producer deduplicate theo ID, không hứa exactly-once. Độ trễ là toàn vòng ứng dụng đo tại A; không gọi là độ trễ mạng một chiều.

Đã kiểm tra cú pháp và test phép tính/phân loại. Máy soạn code không có Docker daemon hoặc ba máy LAN của nhóm, nên chưa xác nhận tích hợp RabbitMQ/Zabbix/netem trên phần cứng thật. Làm bài thử nhỏ ở Bước 5 trước khi đo chính thức.

## 1. Giải nén trên cả ba máy

Tải ZIP, chép sang A/B/C rồi giải nén bằng trình quản lý file. Mở thư mục nt531-zabbix bằng VS Code trên mỗi máy. Terminal trong VS Code phải đang ở thư mục này. Chạy pwd để kiểm tra.

Các tên file trong thư mục đã được cấp sẵn:

| File | Chạy trên | Công việc |
|---|---|---|
| common.py | Được import | Cấu hình kết nối, queue, log và percentile |
| producer.py | A | Gửi message và nhận kết quả bằng kết nối riêng |
| consumer.py | C | Xử lý yêu cầu, gửi kết quả rồi ack |
| metrics_agent.py | C | API chỉ số xử lý và ping C→B |
| collector.py | A | Thu metrics, chẩn đoán, lưu CSV, gửi Zabbix tùy chọn |
| diagnose.py | Được collector import | Bộ luật và giữ nhãn qua hai cửa sổ |
| summarize.py | A | Đối chiếu ID, thống kê throughput và latency |
| mark_fault.py | A | Ghi đáp án sự cố do người làm thí nghiệm biết |
| evaluate.py | A | Đối chiếu nhãn dự đoán với sự cố thật |
| plot_results.py | A | Vẽ timeline PNG |
| scripts/network_delay.sh | C | Gây trễ AMQP và ICMP tới B |
| scripts/network_reset.sh | C | Gỡ rule lab |
| compose.rabbitmq.yml | B | Khởi động RabbitMQ |
| compose.zabbix.yml | A | Khởi động Zabbix và PostgreSQL |
| .env.example | A/B/C | Mẫu IP và mật khẩu cần sửa |
| thresholds.json | A | Ngưỡng chẩn đoán mẫu, cần hiệu chỉnh bằng pilot |

## 2. Ghi IP thật

Trên từng máy:

```bash
cat /etc/os-release
ip -br addr
ip route
```

Ví dụ A=192.168.1.101, B=.102, C=.103. Đây là ví dụ, thay bằng IP LAN thật. Từ A và C ping B bằng IP thật. Không dùng localhost thay địa chỉ của máy khác.

## 3. Cài Python và sửa cấu hình trên cả ba máy

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip curl iproute2 iputils-ping
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Chỉ cp lần đầu; nếu .env đã có thì sửa file đó, không ghi đè mật khẩu cũ. VS Code có thể ẩn .env? Dùng Ctrl+P rồi nhập .env để mở.

Trong .env trên A/B/C sửa:

- RABBIT_HOST = IP thật B.
- CONSUMER_HOST = IP thật C.
- ZABBIX_SERVER = IP thật A.
- RABBIT_PASSWORD = cùng một mật khẩu riêng của nhóm trên cả ba máy.
- ZABBIX_DB_PASSWORD = mật khẩu DB, dùng trên A.

Đặt mật khẩu chữ/số dài để dễ nhập .env; không dùng mẫu ChangeThis. Không commit .env. Mọi terminal mới đều chạy `source .venv/bin/activate` trước khi dùng Python.

## 4. Cài Docker Engine trên A và B, chạy dịch vụ

Docker cài trên Linux A/B; C không cần Docker. Làm theo phần apt repository của tài liệu https://docs.docker.com/engine/install/ubuntu/ . Có thể dùng đoạn cho Ubuntu 24.04 sau nếu chưa có Docker:

```bash
sudo apt update
sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources > /dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo docker run --rm hello-world
```

Nếu Ubuntu version khác, không giữ nguyên Suites: noble. Nếu đã có Docker, kiểm tra bản cài và làm theo tài liệu để tránh xung đột package.

Trên B:

```bash
sudo docker compose -f compose.rabbitmq.yml config --quiet
sudo docker compose -f compose.rabbitmq.yml up -d
sudo docker compose -f compose.rabbitmq.yml ps
```

Mở browser A tại http://IP_B:15672, đăng nhập lab_user và RABBIT_PASSWORD. Các IP_* trong URL cần thay bằng số IP, không nhập nguyên chữ IP_B.

Trên A:

```bash
sudo docker compose -f compose.zabbix.yml config --quiet
sudo docker compose -f compose.zabbix.yml up -d
sudo docker compose -f compose.zabbix.yml ps
```

Mở http://IP_A:8080. Đăng nhập Admin/zabbix nếu hệ thống mới tạo; đổi mật khẩu. Nếu chưa mở được, đọc logs bằng `sudo docker compose -f compose.zabbix.yml logs --tail=80`. Khởi tạo DB có thể cần vài phút. Không đổi password .env rồi nghĩ password trong volume đã lưu sẽ tự đổi.

Image tags trong Compose theo nhánh để học. Sau khi chạy ổn, ghi version và RepoDigests, pin trước run chính. Kiểm tra tương thích template Zabbix với RabbitMQ thực tế, không mặc định mọi health item cũ hỗ trợ RabbitMQ 4.

## 5. Lần chạy đầu tiên chỉ 30 giây

Mở Terminal C số 1:

```bash
source .venv/bin/activate
python consumer.py --worker-id C1 --processing-ms 20 --prefetch 1
```

C phải in Consumer C1 running. Nếu lỗi, xem IP/mật khẩu/vhost lab và RabbitMQ trên B.

Mở Terminal C số 2, kích hoạt venv, thay IP_B bằng IP thật:

```bash
python metrics_agent.py --broker-ip IP_B
```

Từ A mở browser http://IP_C:9109/metrics. Phải thấy JSON có ts, rtt_ms, workers; workers ban đầu có thể rỗng. API không có xác thực, chỉ dùng mạng lab tin cậy; bind IP_C cụ thể bằng --bind và chỉ cho IP_A truy cập 9109 nếu cấu hình firewall. Không mở public Internet.

Mở Terminal A số 1:

```bash
source .venv/bin/activate
python producer.py --run-id first_01 --rate 5 --duration 30 --payload-bytes 1024 --drain-seconds 30
```

Khoảng 150 yêu cầu được phát nếu A duy trì được lịch. C in ID từng yêu cầu. Kết thúc A in confirmed, completed_unique và confirmed_unfinished_ids. Trong lần đầu không sự cố, danh sách chưa hoàn tất nên rỗng; nếu không, cần đọc log và sửa trước khi đo.

Producer đang chạy, mở Terminal A số 2:

```bash
source .venv/bin/activate
python collector.py --run-id first_01
```

Collector cần manifest do producer tạo nên mở sau khi producer bắt đầu. Khi producer đã kết thúc, collector vẫn ghi trạng thái IDLE; bấm Ctrl+C để dừng collector.

Trên A:

```bash
python summarize.py --run-id first_01
python plot_results.py --run-id first_01
```

Mở `data/runs/first_01/summary.json`, `snapshots.csv` và `timeline.png` bằng VS Code. p95 nhỏ hơn hoặc lớn hơn một mức nào đó chưa tự chứng minh đúng/sai; đối chiếu payload, processing và LAN thật.

Mỗi lần chạy đổi run-id, ví dụ first_02. Code từ chối ghi đè run cũ. Chỉ chạy một producer/run tại một thời điểm. Không xóa/purge queue có yêu cầu cũ chưa drain. Kết quả thuộc run khác được log foreign_result rồi ack; đây là bộ lab một run, không phải môi trường nhiều client.

## 6. Nhìn hiểu những con số

- confirmed: broker đã xác nhận publish, chưa đảm bảo consumer xử lý xong.
- completed_unique: số ID có kết quả duy nhất A nhận được.
- confirmed_unfinished_ids: broker xác nhận nhưng A chưa nhận kết quả trong thời gian chờ.
- completed_without_confirm_ids: kết quả có thể tới dù confirm bị lỗi hoặc trạng thái publish chưa biết; được báo riêng.
- p95_ms_completed_cohort: 95% các kết quả đã hoàn tất có độ trễ không vượt xấp xỉ con số này. Tính percentile trực tiếp từ message, không lấy trung bình các p95 cửa sổ.
- completed_rate_in_publish_window: số hoàn tất trong cửa sổ phát tải chia duration. Kết quả drain được thống kê riêng trong tổng hoàn tất.
- offered_rate_in_publish_window: tốc độ thử phát thật. Nếu thấp hơn rate đặt, A/publisher có thể là nút thắt.
- Duplicate được ghi nhưng không cộng lại vào throughput.

Bản này dùng publisher confirm đồng bộ để dễ đọc. Tải cao có thể bị giới hạn bởi tốc độ confirm; không gọi mức tải đặt trước là mức đã đạt. Console log, JSONL và polling cũng có overhead cần giữ giống nhau giữa các run.

## 7. Tạo consumer chậm mà không sửa code

Cả các worker cùng đọc processing_ms.txt trước mỗi message. File này ghi thời gian xử lý mô phỏng bằng ms.

Trên C:

```bash
printf '20\n' > processing_ms.txt
```

Trên A số 1 chạy run mới với tải 20 msg/s, 5 phút:

```bash
python producer.py --run-id slow_01 --rate 20 --duration 300 --drain-seconds 120
```

A số 2:

```bash
python collector.py --run-id slow_01
```

A số 3, ghi trạng thái bình thường:

```bash
python mark_fault.py --run-id slow_01 --label NORMAL
```

Sau khoảng 60 giây trên C đổi:

```bash
printf '200\n' > processing_ms.txt
```

Ngay khi file C đã đổi, A số 3 ghi:

```bash
python mark_fault.py --run-id slow_01 --label CONSUMER_SLOW
```

Sau khoảng 60 giây, C trả về 20 ms. Vì backlog cũ còn tồn tại, A ghi TRANSITION trong thời gian phục hồi, chỉ ghi NORMAL khi hệ thống đã ổn định lại.

```bash
python mark_fault.py --run-id slow_01 --label TRANSITION
```

Khi queue và latency đã về baseline:

```bash
python mark_fault.py --run-id slow_01 --label NORMAL
```

Ghi nhãn trên A bằng tay có sai số thao tác; ghi nhận sai số và dùng lịch sự cố rõ trong báo cáo. Bộ luật không đọc faults.jsonl hoặc tên run-id.

## 8. Tạo mạng chậm trên C

Dùng run mới delay_01 và processing_ms.txt=20. Chạy producer, collector, mark NORMAL như bước trước. Tìm NIC LAN trên C:

```bash
ip route get IP_B
```

Dòng kết quả có dev enp3s0 hoặc một tên khác; lấy đúng tên. Ví dụ bên dưới phải thay cả enp3s0 và IP_B theo máy thật:

```bash
sudo bash scripts/network_delay.sh enp3s0 IP_B 100
```

Script tăng trễ 100 ms trên egress C→B cho AMQP TCP port 5672 và ICMP. Metrics_agent ping C→B nằm trong cùng lớp chịu trễ; HTTP 9109 và telemetry về A nằm ngoài rule. Đây là trễ thêm một chiều, không phải 100 ms cả hai chiều. Xác minh tc counters và RTT; không chỉ tin thông báo script.

Trên A:

```bash
python mark_fault.py --run-id delay_01 --label NETWORK_DELAY
```

Sau đoạn thử, C gỡ:

```bash
sudo bash scripts/network_reset.sh enp3s0
```

A ghi TRANSITION, rồi NORMAL khi baseline ổn định. Script chỉ chấp nhận qdisc mặc định và từ chối cấu hình tùy chỉnh có sẵn; khi reset Linux phục hồi default, không hứa tái tạo chính xác các thông số default được chỉnh trước đó. Không dùng script trên interface đang có cấu hình ngoài đồ án. Kiểm tra RTT trước/sau, không chạy iperf3 đồng thời trong run message.

Bản 1.0 đã cấp script delay/reset. Script bandwidth và loss là phần mở rộng, chưa có trong ZIP này; không cần chúng để demo ba loại nguyên nhân đầu tiên.

## 9. Dừng consumer và thêm worker

Dừng consumer C bằng Ctrl+C khi một run down_01 đang chạy; giữ metrics_agent hoạt động. Trên A ghi CONSUMER_DOWN. Collector phải thấy consumer count về 0, sau hai cửa sổ thường đưa nhãn CONSUMER_DOWN nếu metrics hợp lệ. Chạy lại consumer bằng lệnh Bước 5, ghi TRANSITION rồi NORMAL khi phục hồi.

Thêm worker: mở terminal C khác và chạy `python consumer.py --worker-id C2 --processing-ms 20 --prefetch 1`; worker tiếp theo đặt C3. ID worker phải khác nhau. Mỗi process có kết nối riêng. So sánh 1/2/4 worker với cùng offered load và processing. Nếu processing_ms.txt có tồn tại, giá trị file sẽ ghi đè --processing-ms: nhớ kiểm tra file đó trước run.

## 10. Đưa số liệu vào Zabbix

Cài Agent 2 trên A/B/C và zabbix-sender trên A theo bộ chọn chính thức: https://www.zabbix.com/download . Chọn Zabbix 7.0, Ubuntu version thật và Agent 2. Gán Hostname Lab-A/B/C, ServerActive=IP_A; tạo host đúng tên, gắn Linux by Zabbix agent active. Agent trên Linux thật đo CPU/RAM/NIC của máy vật lý.

Trên Lab-B gắn template RabbitMQ node/cluster by HTTP 7.0 phù hợp; đặt macro endpoint IP_B:15672, credentials và discovery vhost lab. Tạo monitoring account riêng sau lần học, dùng RABBIT_MONITOR_USER/PASSWORD cho collector để không dùng admin lâu dài. RabbitMQ template có thể có item cũ chưa tương thích RabbitMQ 4; kiểm tra Latest data và unsupported items.

Trong Zabbix tạo host Lab-App, nhóm tùy chọn Lab. Tạo từng item dưới đây loại Zabbix trapper, đúng key:

| Key | Type of information | Units |
|---|---|---|
| app.completed_rate | Numeric float | msg/s |
| app.latency.p95 | Numeric float | ms |
| app.processing.mean | Numeric float | ms |
| app.metrics.valid | Numeric unsigned | Không cần |
| app.diagnosis.code | Numeric unsigned | Không cần |

Allowed hosts cho trapper đặt IP_A nếu cần và xác minh sender trước. Test:

```bash
zabbix_sender -z IP_A -s Lab-App -k app.completed_rate -o 5
```

Kết quả phải processed:1 failed:0 và Latest data có số 5. Sau đó chạy collector trong run mới với tùy chọn:

```bash
python collector.py --run-id zabbix_01 --push-zabbix
```

Producer zabbix_01 phải đang chạy trước collector. Bản này gửi số liệu scalar mỗi cửa sổ, không gửi từng message. Sender errors được in để kiểm tra. Diagnosis code: 0 NORMAL, 1 NETWORK_SUSPECTED, 2 CONSUMER_SLOW_SUSPECTED, 3 CONSUMER_DOWN, 4 INCONCLUSIVE, 5 IDLE. Có thể tạo value mapping trên item để hiện chữ.

Tạo dashboard gồm CPU/RAM, queue ready/unacknowledged, completion rate, p95, processing mean và diagnosis code. Tạo trigger CONSUMER_DOWN hoặc NETWORK_SUSPECTED trên diagnosis.code; thêm điều kiện run hoạt động nếu mở rộng. Gắn kiểm tra nodata/telemetry hợp lệ để tránh stale label. Bộ code ghi nhãn và CSV; cấu hình trigger/dashboard là thao tác trên giao diện, không tự tạo qua API trong bản này.

## 11. Đánh giá đóng góp riêng

Sau mỗi run producer xong, dừng collector rồi:

```bash
python summarize.py --run-id slow_01
python evaluate.py --run-id slow_01
python plot_results.py --run-id slow_01
```

Đọc evaluation.json. Queue-only baseline dùng backlog threshold và cùng hai cửa sổ giữ nhãn; chỉ biết cảnh báo, không có khả năng đoán nguyên nhân. Combined thêm network RTT và processing để phân loại. So sánh false alarms, phát hiện sự cố và độ trễ; nguyên nhân đúng của Combined được đo riêng. Null detection delay nghĩa là không phát hiện trong đoạn, không phải 0 giây.

Thresholds.json là ngưỡng DEMO, chưa phải chuẩn hoặc kết quả nghiên cứu. Chạy pilot để lấy baseline, chọn ngưỡng trên calibration runs rồi cố định ngưỡng trước test runs mới. Bộ luật chỉ thử phân biệt những tình huống kiểm soát đã nêu; không giải quyết mọi lỗi mạng hoặc CPU. MIXED và thiếu telemetry trả INCONCLUSIVE. Latency cửa sổ rỗng không thay bằng 0.

Lặp tối thiểu ba run độc lập mỗi cấu hình. Cửa sổ liền nhau trong run có tương quan; không trình bày chúng như hàng trăm thí nghiệm độc lập. Mỗi run giữ versions/digests, phần cứng, NIC, payload, worker, prefetch và interval; code manifest có thông số app nhưng nhóm phải bổ sung inventory phần cứng/versions và commit.

Evaluation v1.0 thống kê ma trận dạng counts trong JSON, tỷ lệ nhãn đúng theo cửa sổ, inconclusive và detection từng đoạn. Với MIXED, expected INCONCLUSIVE là nhãn từ chối kết luận có chủ đích, cần báo riêng khi viết accuracy phân loại các nguyên nhân đơn. Ground truth thời gian do thao tác tay có sai số. Bản này chưa tự tính khoảng tin cậy hoặc tạo heatmap confusion matrix.

## 12. Test và lỗi thường gặp

```bash
python -m unittest discover -s tests -v
```

- ModuleNotFoundError: kích hoạt venv và pip install requirements.
- Connection refused: RabbitMQ chưa chạy, IP_B sai, firewall hoặc LAN chưa thông.
- ACCESS_REFUSED: user/password/vhost lab sai; không dùng guest từ xa.
- PRECONDITION_FAILED: queue cũ khai báo khác loại/durable; kiểm tra queue thật. Đừng xóa/purge khi có dữ liệu cần giữ; dùng vhost lab riêng cho lần triển khai sạch.
- Metrics_agent không mở trên A: CONSUMER_HOST/IP_C, port 9109, firewall.
- INCONCLUSIVE lúc đầu: chưa có dữ liệu processing của run hoặc ping/API chưa cập nhật.
- Luôn INCONCLUSIVE: xem broker_valid/probe_valid trong snapshots, ngưỡng, rtt và processing; không sửa để ép nhãn mong muốn.
- Queue không tăng: offered load vẫn thấp hơn capacity hoặc A không đạt rate.
- Sender failed: tên host/key, loại trapper, allowed hosts và port10051.
- Không có faults.jsonl: đã quên chạy mark_fault; không tự bịa thời điểm sau khi nhìn dự đoán.
- Không reset được network: kiểm tra qdisc và marker; script không xóa rule lạ.

## 13. Phần nhóm cần tự hiểu

Đọc consumer.py từ trên xuống: nhận → xử lý → gửi kết quả được confirm → log → ack. Đọc producer.py: luồng nhận riêng → tạo ID → ghi start → publish → ghép kết quả → đo latency → drain. Đọc diagnose.py với snapshots.csv của run thật và thử giải thích từng nhãn.

Bộ code để học và tái lập thí nghiệm, không thay việc đọc tài liệu và giải thích khi bảo vệ. Báo cáo trung thực các phép thử không đạt, chẩn đoán sai và giới hạn publisher/telemetry. Không cam kết điểm mới toàn cầu hoặc hiệu quả trước khi đo.

Tài liệu: https://www.rabbitmq.com/docs/confirms ; https://www.rabbitmq.com/docs/http-api-reference ; https://pika.readthedocs.io/en/stable/modules/adapters/blocking.html ; https://www.zabbix.com/integrations/rabbitmq .

Đồng bộ giờ trên ba Linux trước khi ghép timeline. Collector dùng producer heartbeat để phát hiện ứng dụng chết; độ lệch đồng hồ C/A vượt khoảng cho phép làm probe không hợp lệ. Đo latency message tại A bằng perf_counter không phụ thuộc đồng hồ C. processing.mean trong bản này là trung bình các giá trị xử lý mới nhất của từng worker, không phải trung bình mọi message trong cửa sổ; dữ liệu gốc consumer vẫn được giữ để tính lại chính xác khi phân tích.
