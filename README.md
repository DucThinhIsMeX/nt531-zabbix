# NT531 - Bộ code đồ án: Đánh giá hiệu năng mạng bằng Zabbix

## Vai trò ba máy
- Máy A : Zabbix Server, điều khiển, phân tích.
- Máy B : iperf3 server (đích đo). Chạy: `iperf3 -s`
- Máy C : chạy run_link_sweep.py (tạo nhiễu bằng tc + đo bằng iperf3/ping),
  cài Zabbix agent + file zabbix/nt531_agent_infra.conf.

Liên kết đo: cáp Ethernet C<->B, dải 10.10.0.x (B=10.10.0.1, C=10.10.0.2).

## File
| File | Công dụng |
|---|---|
| run_link_sweep.py | Script chính, chạy 3 kịch bản (loss_tcp / utilization_delay / bandwidth_cap) |
| common.py | Hàm tiện ích (atomic_json, mean, utc...) - run_link_sweep.py import |
| zabbix/nt531_agent_infra.conf | UserParameter cho Zabbix agent đo RTT/loss/backlog (bản đã sửa cú pháp) |
| scripts/network_*.sh | Script tc/netem/tbf thủ công (dự phòng; run_link_sweep.py đã tự áp tc) |
| requirements.txt | Thư viện Python |

## Cài trên máy C
```
sudo apt install -y python3 python3-venv python3-pip iperf3 iputils-ping
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Lệnh chạy ba kịch bản (trên máy C, iperf3 server đã chạy trên B)
KB1 - throughput theo mất gói (đối chiếu Mathis):
```
python run_link_sweep.py --scenario loss_tcp --server-ip 10.10.0.1 --duration 90 --loss-cap 50 --base-delay 5
```
KB2 - độ trễ theo độ hữu dụng (đối chiếu M/M/1, lặp 3 lần):
```
python run_link_sweep.py --scenario utilization_delay --server-ip 10.10.0.1 --link-cap 2 --duration 12 --repeats 3
```
KB3 - hiệu suất theo trần băng thông:
```
python run_link_sweep.py --scenario bandwidth_cap --server-ip 10.10.0.1 --duration 15
```

Kết quả lưu trong data/link_sweeps/ (CSV + JSON) và in bảng ra màn hình.

## Zabbix (trên máy C)
```
sudo cp zabbix/nt531_agent_infra.conf /etc/zabbix/zabbix_agent2.d/
# sửa Timeout=10 trong /etc/zabbix/zabbix_agent2.conf
sudo systemctl restart zabbix-agent2
zabbix_agent2 -t 'nt531.ping.rtt[10.10.0.1]'   # kiểm thử, phải ra số
```
