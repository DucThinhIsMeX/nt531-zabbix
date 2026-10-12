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
| common.py | Được import | Cấu hình kết nối, queue, log, mean/stddev và percentile |
| producer.py | A | Gửi message và nhận kết quả bằng kết nối riêng |
| consumer.py | C | Xử lý yêu cầu, gửi kết quả rồi ack |
| metrics_agent.py | C | API chỉ số xử lý và ping C→B |
| collector.py | A | Thu metrics, chẩn đoán, lưu CSV, đẩy đầy đủ metrics tới Zabbix |
| diagnose.py | Được collector import | Bộ luật và giữ nhãn qua hai cửa sổ |
| summarize.py | A | Đối chiếu ID, khử survivorship bias, kiểm chứng Định luật Little |
| calibrate.py | A | Hiệu chỉnh ngưỡng khoa học (mean + k*sigma) từ pilot baseline |
| run_sweep.py | A | Tự động hóa thí nghiệm quét tải (Load Sweep) đa mức |
| summarize_sweep.py | A | Gom nhiều run, tìm knee point bão hòa, xuất bảng sweep |
| plot_sweep.py | A | Vẽ đường cong tải (Throughput, Hockey-stick, Little's Law) |
| run_iperf_baseline.py | A | Đo năng lực thật của liên kết khi chưa bóp (iperf3 TCP/UDP, ping baseline) |
| run_link_sweep.py | A | Bộ thí nghiệm đặc tả liên kết hạ tầng (Độ hữu dụng M/M/1, Mất gói Mathis, Trần TBF) |
| plot_link_sweep.py | A | Vẽ 3 đường cong đặc tả hạ tầng đối chiếu mô hình giải tích lý thuyết |
| cross_layer_join.py | A | Khớp số liệu hai tầng theo timestamp thành bảng nhân quả L3/L4 -> L7 |
| plot_cross_layer.py | A | Vẽ đồ thị ánh xạ xuyên tầng (Throughput collapse, Bufferbloat, Service Drop) |
| zabbix_fidelity.py | A | Đánh giá độ trung thực của Zabbix (chu kỳ 30s/60s vs ground truth 1s, Nyquist limit) |
| plot_fidelity.py | A | Vẽ đồ thị đánh giá độ trễ và hiện tượng bỏ sót micro-burst của Zabbix |
| zabbix/nt531_agent_infra.conf | A/B | Cấu hình Zabbix Agent (UserParameter ping qua liên kết bóp, qdisc backlog, macro {$LINK.CAP}) |
| mark_fault.py | A | Ghi đáp án sự cố (Delay, Loss, Rate, Consumer Slow/Down - Phụ lục) |
| evaluate.py | A | Đối chiếu nhãn dự đoán với sự cố thật (Phụ lục) |
| plot_results.py | A | Vẽ timeline PNG một run (throughput, latency, backlog, RTT) |
| scripts/network_delay.sh | C | Gây trễ AMQP và ICMP tới B (netem delay) |
| scripts/network_loss.sh | C | Gây mất gói AMQP và ICMP tới B (netem loss) |
| scripts/network_rate.sh | C | Giới hạn băng thông egress tới B (tbf rate limit) |
| scripts/network_reset.sh | C | Gỡ toàn bộ rule lab (delay, loss, rate) trên interface |
| compose.rabbitmq.yml | B | Khởi động RabbitMQ |
| compose.zabbix.yml | A | Khởi động Zabbix và PostgreSQL |
| .env.example | A/B/C | Mẫu IP và mật khẩu cần sửa |
| thresholds.json | A | Ngưỡng chẩn đoán (được sinh từ calibrate.py) |

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
sudo apt install -y python3 python3-venv python3-pip curl iproute2 iputils-ping chrony
sudo systemctl enable --now chrony
chronyc tracking
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

> **Bắt buộc đồng bộ thời gian:** Cả ba máy A, B, C phải đồng bộ giờ qua chrony/NTP trước khi đo đạc. Các cờ kiểm tra dữ liệu telemetry (heartbeat, probe freshness) so sánh timestamp giữa các máy với dung sai vài giây. Nếu đồng hồ bị lệch (clock drift), telemetry sẽ bị đánh dấu không hợp lệ (`probe_valid = False`) hoặc làm sai lệch trật tự sự kiện.

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
python metrics_agent.py --broker-ip IP_B --bind IP_C
```

> **Bảo mật mạng Lab:** `metrics_agent.py` không có xác thực, ping 3 gói mỗi chu kỳ để lọc nhiễu RTT. Khuyến nghị chỉ bind vào địa chỉ IP của C (`--bind IP_C`) và thiết lập firewall trên C chỉ cho phép IP của A truy vấn:
> ```bash
> sudo ufw allow from IP_A to any port 9109 proto tcp
> ```

Từ A mở browser hoặc curl `http://IP_C:9109/metrics`. Phải thấy JSON có ts, rtt_ms, workers.

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

A ghi TRANSITION, rồi NORMAL khi baseline ổn định.

### Tạo mất gói mạng (Packet Loss) trên C

Mất gói là hiện tượng mạng nghiêm trọng nhất làm sụp đổ throughput TCP theo mô hình Mathis ($Throughput \le \frac{MSS}{RTT \cdot \sqrt{p}}$). Khi mất gói $p=2\%$, TCP liên tục rơi vào retransmission timeout và co hẹp cửa sổ nghẽn (cwnd), khiến luồng AMQP bị nghẽn nghiêm trọng dù băng thông vật lý còn thừa:

```bash
# Bơm mất gói 2% egress C→B (AMQP port 5672 + ICMP)
sudo bash scripts/network_loss.sh enp3s0 IP_B 2
```

Trên A:

```bash
python mark_fault.py --run-id loss_01 --label NETWORK_LOSS
```

Gỡ rule khi kết thúc kịch bản:

```bash
sudo bash scripts/network_reset.sh enp3s0
```

### Giới hạn băng thông (Bandwidth Throttling / TBF) trên C

Sử dụng Token Bucket Filter (TBF) để giới hạn tốc độ truyền dữ liệu từ C về broker B (ví dụ bóp xuống 500 kbit/s):

```bash
# Giới hạn 500 kbit/s, burst 32KB, latency đệm 50ms
sudo bash scripts/network_rate.sh enp3s0 IP_B 500 32 50
```

Trên A:

```bash
python mark_fault.py --run-id rate_01 --label NETWORK_RATE
```

Gỡ rule:

```bash
sudo bash scripts/network_reset.sh enp3s0
```

## 9. Dừng consumer và thêm worker

Dừng consumer C bằng Ctrl+C khi một run down_01 đang chạy; giữ metrics_agent hoạt động. Trên A ghi CONSUMER_DOWN. Collector phải thấy consumer count về 0, sau hai cửa sổ thường đưa nhãn CONSUMER_DOWN nếu metrics hợp lệ. Chạy lại consumer bằng lệnh Bước 5, ghi TRANSITION rồi NORMAL khi phục hồi.

Thêm worker: mở terminal C khác và chạy `python consumer.py --worker-id C2 --processing-ms 20 --prefetch 1`; worker tiếp theo đặt C3. ID worker phải khác nhau. Mỗi process có kết nối riêng. So sánh 1/2/4 worker với cùng offered load và processing. Nếu processing_ms.txt có tồn tại, giá trị file sẽ ghi đè --processing-ms: nhớ kiểm tra file đó trước run.

## 10. Đưa số liệu vào Zabbix

Cài Agent 2 trên A/B/C và zabbix-sender trên A theo bộ chọn chính thức: https://www.zabbix.com/download . Chọn Zabbix 7.0, Ubuntu version thật và Agent 2. Gán Hostname Lab-A/B/C, ServerActive=IP_A; tạo host đúng tên, gắn Linux by Zabbix agent active. Agent trên Linux thật đo CPU/RAM/NIC của máy vật lý.

Trên Lab-B gắn template RabbitMQ node/cluster by HTTP 7.0 phù hợp; đặt macro endpoint IP_B:15672, credentials và discovery vhost lab. Tạo monitoring account riêng sau lần học, dùng RABBIT_MONITOR_USER/PASSWORD cho collector để không dùng admin lâu dài. RabbitMQ template có thể có item cũ chưa tương thích RabbitMQ 4; kiểm tra Latest data và unsupported items.

Trong Zabbix tạo host Lab-App, nhóm tùy chọn Lab. Tạo từng item dưới đây loại Zabbix trapper, đúng key:

| Key | Type of information | Units | Ý nghĩa trong Observability |
|---|---|---|---|
| app.completed_rate | Numeric float | msg/s | Throughput thực tế hoàn tất |
| app.offered_rate | Numeric float | msg/s | Tốc độ phát tải từ Producer |
| app.latency.p95 | Numeric float | ms | Độ trễ vòng p95 (độ trễ đáp ứng ứng dụng) |
| app.processing.mean | Numeric float | ms | Thời gian xử lý trung bình của worker |
| app.backlog | Numeric unsigned | msgs | Chiều dài hàng đợi RabbitMQ ($L_q$) |
| app.rtt_ms | Numeric float | ms | Độ trễ RTT mạng tầng IP (ping C→B) |
| app.unfinished_count | Numeric unsigned | msgs | Số lượng message tồn đọng / mất mát |
| app.queue.alarm | Numeric unsigned | Boolean | Cảnh báo vượt ngưỡng độ dài queue |
| app.metrics.valid | Numeric unsigned | Boolean | Tính toàn vẹn của dữ liệu telemetry |
| app.diagnosis.code | Numeric unsigned | Mã lỗi | 0: NORMAL, 1: NETWORK, 2: SLOW, 3: DOWN, 4: INCONCLUSIVE, 5: IDLE |

Allowed hosts cho trapper đặt IP_A nếu cần và xác minh sender trước. Test đẩy thử:

```bash
zabbix_sender -z IP_A -s Lab-App -k app.completed_rate -o 5
```

Sau đó chạy collector với cờ `--push-zabbix`:

```bash
python collector.py --run-id zabbix_01 --push-zabbix
```

Collector tự động đóng gói toàn bộ 10 chỉ số trên và gửi hàng loạt (batch mode via stdin) trong 1 kết nối TCP đến Zabbix Server mỗi cửa sổ.

### Vai trò của Zabbix trong Kiến trúc Hệ thống

Nếu hội đồng hỏi *"Toàn bộ chẩn đoán nằm trong Python, vậy Zabbix đóng vai trò gì?"*, nhóm trả lời theo cấu trúc phân tầng chuẩn công nghiệp:
1. **Tầng Thu thập & Tổng hợp Telemetry (Observability Plane):** Zabbix là trung tâm gom dữ liệu đa tầng (Full-Stack Observability):
   - Hạ tầng phần cứng: CPU, RAM, Network Bandwidth của 3 máy A, B, C (qua Zabbix Agent 2).
   - Middleware: RabbitMQ Cluster stats, Socket descriptors, Disk free (qua Template RabbitMQ HTTP).
   - Ứng dụng & Mạng: Throughput, p95 latency, RTT C→B, Backlog, và Mã chẩn đoán (qua Zabbix Trapper).
2. **Tầng Trực quan hóa Thời gian thực (Real-time Dashboards):** Zabbix vẽ tương quan trực quan giữa các đường cong: sụt giảm Throughput có trùng khớp với tăng RTT mạng hay tăng Consumer Processing hay không.
3. **Tầng Cảnh báo Tự động (Alerting & Trigger Engine):** Thiết lập các triggers:
   - Severity HIGH: `app.diagnosis.code = 1` (Network Suspected) hoặc `app.diagnosis.code = 3` (Consumer Down).
   - Severity WARNING: `app.queue.alarm = 1` (Queue tắc nghẽn).
   - Recovery Actions: Tự động gửi thông báo hoặc trigger webhook khắc phục sự cố.

## 11. Hiệu chỉnh ngưỡng chẩn đoán khoa học (Calibration Run)

Không sử dụng các số giả định tùy tiện trong `thresholds.json`. Thay vào đó, chạy một pilot baseline run ở tải bình thường (ví dụ 10 msg/s, không sự cố) trong 2 phút:

```bash
# Trên A: Chạy baseline pilot
python producer.py --run-id pilot_01 --rate 10 --duration 120 --drain-seconds 30
python collector.py --run-id pilot_01
```

Sau khi pilot run hoàn tất, chạy công cụ tự động tính ngưỡng theo nguyên lý 3-sigma ($\mu + 3\sigma$):

```bash
python calibrate.py --baseline-run-id pilot_01 --k 3.0 --output thresholds.json
```

`calibrate.py` sẽ đọc `snapshots.csv`, tính trung bình $\mu$ và độ lệch chuẩn $\sigma$ của:
- RTT mạng LAN thật giữa C và B.
- Thời gian xử lý thực tế của Consumer.
- Độ trễ vòng p95 thực tế của hệ thống.
- Chiều dài hàng đợi Backlog bình thường.

File `thresholds.json` được tạo ra chứa đầy đủ metadata thống kê, có thể giải thích minh bạch trước hội đồng bảo vệ.

## 12. Thí nghiệm Quét tải (Load Sweep Curve) & Khử Survivorship Bias

Đây là thí nghiệm cốt lõi của môn Đánh giá Hiệu năng: cho offered load tăng dần để dựng đường cong bão hòa (Knee Point) và đường trễ gãy khúc (Hockey-Stick Curve).

### Chạy quét tải đa mức tự động

Chạy dãy tải qua các mức [5, 10, 20, 30, 40, 50, 60] msg/s:

```bash
# Xem trước danh sách lệnh
python run_sweep.py --prefix sweep --rates 5 10 20 30 40 50 60

# Hoặc thực thi tuần tự tự động trên A
python run_sweep.py --prefix sweep --rates 5 10 20 30 40 50 60 --duration 60 --execute
```

### Tổng hợp và dựng đường cong tải

Sau khi toàn bộ các run sweep kết thúc:

```bash
python summarize_sweep.py --pattern "sweep_*"
python plot_sweep.py --sweep-json data/sweep_summary.json --output data/load_curves.png
```

Script sẽ xuất ra:
- `data/sweep_summary.json` và `data/sweep_summary.csv`: Bảng tổng hợp số liệu chi tiết.
- `data/load_curves.png`: Đồ thị 4 khung hình ấn tượng:
  1. **Offered Load vs Throughput**: Thể hiện điểm gãy bão hòa (Saturation Knee Point).
  2. **Offered Load vs Latency (Hockey-Stick Curve)**: So sánh p95 chỉ tính message hoàn thành (bị méo mó do Survivorship Bias) với p95 có phạt Timeout (phản ánh trung thực độ trễ bùng nổ khi tắc nghẽn).
  3. **Offered Load vs Unfinished Ratio (%)**: Chỉ ra tỷ lệ message bị drop / timeout vọt lên khi tải vượt ngưỡng phục vụ.
  4. **Kiểm chứng Định luật Little**: Đối chiếu số lượng message trong hệ thống dự đoán ($L = \lambda W$) với số lượng thực tế quan sát ($L_{\text{observed}}$).

### Khử thiên lệch sống sót (Survivorship Bias) trong đo đạc

Trong các hệ thống message queue ở gần điểm bão hòa, những message tệ nhất thường bị quá tải, kẹt trong hàng đợi và timeout sau khi producer dừng phát (nằm trong `confirmed_unfinished_ids`). Nếu chỉ tính percentile trên những message may mắn hoàn thành (`completed`), p95 sẽ trông rất thấp và "đẹp giả tạo" ngay lúc hệ thống đang ngắc ngoải.

`summarize.py` giải quyết triệt để vấn đề này bằng cách:
1. Thống nhất định nghĩa chưa hoàn tất: `unfinished_count = confirmed - completed` (đồng nhất 100% giữa summary báo cáo và Zabbix dashboard).
2. Gán giá trị trần (Timeout Penalty = duration + drain_seconds) cho các unfinished message và tính `p95_ms_with_timeout_penalty`.
3. Trong kiểm chứng Định luật Little, $W$ sử dụng độ trễ có phạt timeout (`w_mean_latency_seconds`) để phản ánh trung thực độ phình trễ khi hệ thống nghẽn.
4. Đồng bộ hóa cửa sổ đo: Tách riêng `steady_state` (cắt bỏ warmup và cooldown) và publish window, loại bỏ nhiễu từ giai đoạn drain.

### Phân biệt Nghẽn Producer (Sync-Confirm Ceiling) và Bão hòa Hệ thống (Knee Point)

Một cạm bẫy thực nghiệm kinh điển trong đo đạc RabbitMQ: `producer.py` bật `ch.confirm_delivery()` trên `BlockingConnection`, nghĩa là mỗi lệnh publish sẽ đồng bộ chờ Broker gửi xác nhận (ack) qua mạng rồi mới publish tiếp.
- Do đó, trần tốc độ phát thực tế của Producer bị giới hạn cơ học bởi: $\text{Rate}_{\max} \approx \frac{1}{\text{RTT}_{\text{confirm}}}$.
- Nếu bạn đặt `--rate 100` trong khi RTT + confirm tốn 20ms, Producer chỉ phát được tối đa 50 msg/s.
- Nếu lấy rate cấu hình làm trục x, đồ thị sẽ tưởng nhầm rằng hệ thống bão hòa ở 50 msg/s ("bão hòa giả" do Producer, không phải do RabbitMQ hay Consumer)!

Hệ thống sweep của chúng ta xử lý vấn đề này rạch ròi:
- [summarize_sweep.py](file:///c:/Users/Duc%20Thinh/Documents/H%E1%BB%8Dc%20t%E1%BA%ADp/NT531-%C4%90%C3%A1nh%20gi%C3%A1%20hi%E1%BB%87u%20n%C4%83ng/%C4%90%E1%BB%93%20%C3%81n/nt531-zabbix/summarize_sweep.py) và [plot_sweep.py](file:///c:/Users/Duc%20Thinh/Documents/H%E1%BB%8Dc%20t%E1%BA%ADp/NT531-%C4%90%C3%A1nh%20gi%C3%A1%20hi%E1%BB%87u%20n%C4%83ng/%C4%90%E1%BB%93%20%C3%81n/nt531-zabbix/plot_sweep.py) **bắt buộc dùng rate đo được thực tế** (`measured_offered_rate`) làm trục $x$, không dùng rate cấu hình.
- Tự động gắn cờ `producer_limited = True` khi tốc độ phát thực tế bị tụt dưới $92\%$ so với rate đặt hoặc có `load_limited_slots > 0`.
- Trên đồ thị, các điểm bị nghẽn do Producer được đánh dấu riêng biệt (tam giác màu cam) và có đường gióng trần Producer confirm limit riêng, tách biệt hoàn toàn với vạch Consumer Saturation Knee Point màu đỏ.

## 13. Cơ sở lý thuyết: Mô hình Hàng đợi M/M/c & Định luật Little cho NT531

Để neo đồ án vững chắc vào trục môn "Đánh giá hiệu năng mạng", nhóm tuyên bố mô hình hóa hệ thống trong báo cáo như sau:

1. **Mô hình Hàng đợi $M/M/c$ (hoặc $M/D/c$):**
   - **Luồng đến (Arrival process):** Producer phát tải theo tiến trình Poisson với cường độ $\lambda$ (offered rate msg/s).
   - **Tầng phục vụ (Service process):** $c$ worker consumers, mỗi worker có cường độ phục vụ $\mu = 1000 / \text{processing\_ms}$ (msg/s). Tổng công suất hệ thống: $C = c \cdot \mu$.
   - **Hệ số sử dụng (Traffic intensity):** $\rho = \frac{\lambda}{c \mu}$.
     - Khi $\rho < 1$: Hệ thống ổn định (steady state), hàng đợi ngắn, latency xấp xỉ thời gian truyền dẫn mạng + thời gian xử lý.
     - Khi $\rho \ge 1$: Hệ thống bão hòa, hàng đợi backlog tăng tuyến tính theo thời gian $L_q(t) \sim (\lambda - c\mu)t$.
2. **Kiểm chứng Định luật Little ($L = \lambda W$):**
   - Định luật phát biểu: Số lượng khách trung bình trong hệ thống $L$ bằng tích của tốc độ đến $\lambda$ và thời gian lưu trú trung bình $W$.
   - Trong `summary.json`, hệ thống tự động trích xuất:
     $$\lambda = \text{throughput (msg/s)}, \quad W = \frac{\overline{\text{latency (ms)}}}{1000} \text{ (giây)}$$
     $$L_{\text{predicted}} = \lambda \cdot W$$
     $$L_{\text{observed}} = \overline{\text{backlog}} + \text{in-flight items}$$
   - Ở vùng tải ổn định ($\rho < 0.8$), sai số giữa $L_{\text{predicted}}$ và $L_{\text{observed}}$ rất nhỏ ($< 15\%$), chứng minh tính đúng đắn của định luật.
   - Ở vùng bão hòa ($\rho \ge 1$), hệ thống vi phạm tính dừng (non-stationary), số liệu thực nghiệm sẽ chỉ ra sự phân kỳ của định luật Little. Đây là điểm phân tích lý thuyết đắt giá nhất để kéo đồ án từ "hệ phân tán" về đúng trọng tâm môn hiệu năng!
3. **Mô hình Mathis cho Packet Loss tầng TCP:**
   - AMQP chạy trên nền TCP (port 5672). Theo công thức Mathis:
     $$\text{Throughput}_{\text{TCP}} \le \frac{\text{MSS}}{\text{RTT} \cdot \sqrt{p}} \times C$$
   - Khi có mất gói $p$, TCP co hẹp Congestion Window và phải truyền lại, khiến tốc độ đẩy ack/result bị bóp nghẹt, làm sập throughput ứng dụng dù độ trễ vật lý không đổi.

## 14. Đánh giá đóng góp riêng & Ma trận chẩn đoán

Sau mỗi run sự cố, chạy:

```bash
python summarize.py --run-id delay_01
python evaluate.py --run-id delay_01
python plot_results.py --run-id delay_01
```

Đọc `evaluation.json`:
- So sánh Queue-only baseline (chỉ nhìn backlog) với Combined Classifier (kết hợp backlog, RTT C→B và processing time).
- Baseline chỉ biết báo động mà không biết nguyên nhân.
- Combined phân biệt chính xác: `NETWORK_SUSPECTED` (khi RTT hoặc loss tăng), `CONSUMER_SLOW_SUSPECTED` (khi service time tăng), và `CONSUMER_DOWN` (khi consumer = 0).

## 15. Kiểm thử đơn vị

```bash
python -m unittest discover -s tests -v
```

Kiểm tra:
- Khử survivorship bias và tính toán timeout penalty.
- Hiệu chỉnh ngưỡng $\mu + 3\sigma$ trong `calibrate.py`.
- Kiểm chứng định luật Little $L = \lambda W$.
- Bộ luật chẩn đoán và cơ chế làm mượt nhãn (StableLabel).

## 16. Khung Đo đạc Hạ tầng Mạng & Khảo sát Ánh xạ Xuyên tầng (Cross-Layer Evaluation)

> [!IMPORTANT]
> **Điều kiện tiên quyết bắt buộc:** Đồng bộ đồng hồ ba máy A, B, C bằng `chrony` hoặc NTP.
> Toàn bộ giá trị nghiên cứu của đồ án nằm ở việc **ghép nối số liệu hai tầng theo mốc thời gian (timestamp)**. Nếu lệch đồng hồ, bảng ánh xạ quan hệ nhân quả giữa L3/L4 và L7 sẽ bị sai lệch hoàn toàn.

Xem hướng dẫn chi tiết dành riêng cho báo cáo đồ án tại: [REPORT_GUIDE.md](file:///c:/Users/Duc%20Thinh/Documents/Học%20tập/NT531-Đánh%20giá%20hiệu%20năng/Đồ%20Án/nt531-zabbix/REPORT_GUIDE.md)

---

### Nhóm 1: Biến Zabbix thành Máy đo Hạ tầng Mạng

1. **Cài đặt Zabbix Agent trên các nút**:
   - Sử dụng file cấu hình [zabbix/nt531_agent_infra.conf](file:///c:/Users/Duc%20Thinh/Documents/Học%20tập/NT531-Đánh%20giá%20hiệu%20năng/Đồ%20Án/nt531-zabbix/zabbix/nt531_agent_infra.conf).
   - Thu thập thông lượng cổng: `net.if.in[eth1]` / `net.if.out[eth1]` (tự động nhận diện qua `net.if.discovery`).
2. **Item Độ hữu dụng Kênh truyền $\rho$**:
   - Công thức: `last(//net.if.out[eth1]) * 8 / {$LINK.CAP}`
   - **Bắt buộc dùng Macro `{$LINK.CAP}`**: Cấu hình macro trên host (ví dụ `10M` hoặc `50M` theo trần tbf). Tuyệt đối **không** lấy tốc độ NIC vật lý 1 Gbps làm mẫu số, nếu không $\rho$ luôn tiệm cận 0 và đường cong mất hoàn toàn ý nghĩa.
3. **UserParameter Ping đi xuyên qua liên kết bị bóp**:
   - Chạy lệnh ping A→B hoặc A→C ngay trên máy phát (Node A) bằng UserParameter (`nt531.ping.rtt[*]`, `nt531.ping.loss[*]`) rồi đẩy số về Zabbix. Tuyệt đối không để Zabbix Server ping thẳng bypass qua liên kết bị bóp.
4. **Đo Baseline iperf3 khi chưa bóp liên kết**:
   ```bash
   python run_iperf_baseline.py --server-ip 192.168.10.30
   ```

---

### Nhóm 2: Bộ Thí nghiệm Đặc tả Liên kết Hạ tầng (Link Characterization Harness)

Chạy song song với sweep tải dịch vụ, đối chiếu trực tiếp với các mô hình giải tích lý thuyết:

```bash
# 1. Quét Độ hữu dụng - Độ trễ (chỉ tbf, iperf3 UDP tăng dần rho=0.1..0.95, đối chiếu M/M/1)
python run_link_sweep.py --scenario utilization_delay --server-ip 192.168.10.30 --link-cap 10 --execute

# 2. Quét Mất gói - Throughput TCP (netem loss 0%..10%, đối chiếu Công thức Mathis)
python run_link_sweep.py --scenario loss_tcp --server-ip 192.168.10.30 --execute

# 3. Quét Trần Băng thông (tbf rate 1..50 Mbps)
python run_link_sweep.py --scenario bandwidth_cap --server-ip 192.168.10.30 --execute

# Vẽ 3 đồ thị đặc tả liên kết hạ tầng:
python plot_link_sweep.py
```

---

### Nhóm 3: Ánh xạ Nhân quả Xuyên Tầng (L3/L4 Hạ tầng $\to$ L7 Dịch vụ)

Đây là **đóng góp nghiên cứu trọng tâm** của đồ án: Chạy cả tầng hạ tầng và tầng dịch vụ dưới cùng kịch bản netem, đồng bộ mốc thời gian, rồi gộp lại thành bảng nhân quả:

```bash
# Ghép metric hai tầng thành bảng nhân quả và lưu JSON/CSV
python cross_layer_join.py

# Vẽ đồ thị ánh xạ xuyên tầng 3 bảng (Throughput collapse, Bufferbloat, Service drop)
python plot_cross_layer.py
```

- **Cơ chế khuếch đại tổn thất**: Mất gói tin L4 kích hoạt TCP retransmission và làm stall 2 vòng xác nhận AMQP (confirm/ack), làm throughput dịch vụ sụt giảm dốc hơn nhiều so với tốc độ mạng thô.
- **Dây chuyền tắc nghẽn**: Khi $\rho \to 1.0$, hàng đợi qdisc Linux phồng lên (Bufferbloat) kéo theo bùng nổ hàng đợi RabbitMQ tại tầng 7.

---

### Nhóm 4: Đánh giá Độ Trung thực của Giám sát Zabbix (Observability Fidelity)

Khảo sát sai số và hiện tượng bỏ sót biến động ngắn do chu kỳ lấy mẫu (Polling Interval):

```bash
# Đánh giá sai số đỉnh, độ trễ phát hiện cảnh báo và hiện tượng mù micro-burst
python zabbix_fidelity.py

# Xuất đồ thị đối chiếu chu kỳ 30s/60s với Ground Truth 1s
python plot_fidelity.py
```

- **Định lý Shannon-Nyquist**: Chu kỳ lấy mẫu $T_{\text{poll}} = 60\text{s}$ hoàn toàn mù trước các micro-burst ngắn hơn $120\text{s}$.
- **Sai số đánh giá đỉnh**: Bỏ lỡ đỉnh RTT thực tế lên tới trên 70-90%.
- **Độ trễ cảnh báo**: Tắc nghẽn kéo dài bị trễ trung bình $\approx 30\text{s}$ trước khi trigger Zabbix chuyển màu đỏ.

---

## 17. Khung Viết Báo cáo Chuẩn cho Môn NT531

1. **Chương 1: Đặt Vấn đề & Mô hình Hàng đợi Mạng**
   - Sự cần thiết của quan sát phân tầng và quan hệ nhân quả L3/L4 $\leftrightarrow$ L7.
   - Lý thuyết hàng đợi $M/M/1$, Định luật Little $L = \lambda W$, Công thức Mathis cho TCP.
2. **Chương 2: Thiết kế Hệ thống Thực nghiệm & Giám sát Zabbix**
   - Sơ đồ Topology 3 máy (Node A Client, Node B Wan Emulator, Node C Target & Server).
   - Bắt buộc đồng bộ thời gian Chrony/NTP ($\Delta t < 1\text{ms}$).
   - Bảng phân tầng Item Zabbix (Macro `{$LINK.CAP}`, UserParameter Ping A→C, qdisc backlog).
3. **Chương 3: Đặc tả Năng lực Liên kết Hạ tầng (L3/L4 Characterization)**
   - Đường cong Độ hữu dụng $\rho$ vs Độ trễ (Đối chiếu mô hình $M/M/1$).
   - Đường cong Suy giảm Throughput TCP vs Mất gói (Đối chiếu công thức Mathis).
   - Quét trần băng thông TBF và hiệu suất liên kết.
4. **Chương 4: Đóng góp Trọng tâm - Ánh xạ Nhân quả Xuyên Tầng (Cross-Layer Mapping)**
   - Ma trận ánh xạ: Mức suy hao mạng $\to$ Biến động RTT $\to$ Sụt giảm Msg/s $\to$ Bùng nổ p95 dịch vụ.
   - Cơ chế khuếch đại tổn thất (Loss Amplification Factor) trong mô hình Publish-Confirm.
   - Hiện tượng Bufferbloat dây chuyền từ qdisc Linux sang hàng đợi ứng dụng.
5. **Chương 5: Nghiên cứu Độ Trung thực của Hệ thống Giám sát Zabbix**
   - Đánh giá đánh đổi giữa chu kỳ polling (30s, 60s) và chi phí mạng/CPU.
   - Hiện tượng mù Micro-burst và sai số đánh giá đỉnh (Peak Underestimation).
   - Giới hạn Nyquist và giải pháp kiến trúc (Push telemetry / High-freq probe).
6. **Phụ lục: Hệ thống Chẩn đoán Sự cố Cũ (Rule-based Diagnostic Suite)**
   - Thuật toán phân loại ma trận nhầm lẫn (`diagnose.py`, `evaluate.py`, `mark_fault.py`).

