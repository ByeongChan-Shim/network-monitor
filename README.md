# Raspberry Pi 네트워크 상태 모니터링

## 목적

Raspberry Pi 3에서 지정한 IP 주소의 연결 상태를 1초마다 검사하고 SQLite에 저장한다.  
LCD에는 최근 24시간 성공률을 5초 간격으로 표시하며, 연결 실패 시 즉시 경고를 표시한다.

## 모니터링 대상

`collector.py`의 대상 목록:

```python
TARGETS = ["8.8.8.8", "192.168.0.1", "203.250.77.254"]
```

- `8.8.8.8`: 외부 인터넷 연결 확인
- `192.168.0.1`: 내부 공유기 또는 게이트웨이 예시
- `203.250.77.254`: 지정 네트워크 대상

## 구성

```text
collector.py
  └─ 1초마다 각 IP에 Ping
  └─ 성공 여부·응답 시간·오류를 network.db에 저장

lcd_display.py
  └─ network.db의 최근 24시간 통계를 읽음
  └─ LCD 화면에 상태 표시
```

## LCD 배선

LCD는 I²C 방식이며, 5 V LCD 보호를 위해 레벨 변환기를 사용한다.

| Raspberry Pi | 레벨 변환기 | LCD |
|---|---|---|
| 물리 핀 1: 3.3 V | `LV` | — |
| 물리 핀 2 또는 4: 5 V | `HV` | `VCC` |
| 물리 핀 6: GND | `GND` | `GND` |
| 물리 핀 3: SDA | `LV1` → `HV1` | `SDA` |
| 물리 핀 5: SCL | `LV2` → `HV2` | `SCL` |

배선은 반드시 Raspberry Pi 전원을 뽑은 상태에서 한다.

## I²C 설정

I²C를 활성화한다.

```bash
sudo raspi-config
```

`Interface Options` → `I2C` → Enable을 선택한 뒤 재부팅한다.

필요한 도구를 설치한다.

```bash
sudo apt update
sudo apt install i2c-tools python3-smbus
```

LCD의 I²C 주소를 확인한다.

```bash
sudo i2cdetect -y 1
```

보통 `27` 또는 `3f`가 표시된다.

## 실행

프로젝트 폴더로 이동한다.

```bash
cd ~/network-monitor
```

터미널 1에서 수집기를 실행한다.

```bash
python3 collector.py
```

터미널 2에서 LCD 표시 프로그램을 실행한다.

```bash
python3 lcd_display.py --address 0x27
```

LCD 주소가 `3f`라면 다음과 같이 실행한다.

```bash
python3 lcd_display.py --address 0x3f
```

프로그램 종료는 각 터미널에서 `Ctrl+C`를 누른다.

## SQLite 확인

SQLite를 연다.

```bash
cd ~/network-monitor
sqlite3 network.db
```

테이블 목록:

```sql
.tables
```

최근 측정 결과:

```sql
SELECT timestamp, target, success, latency_ms, error_type
FROM network_check
ORDER BY id DESC
LIMIT 20;
```

실패 기록만 확인:

```sql
SELECT timestamp, target, error_type, error_message
FROM network_check
WHERE success = 0
ORDER BY id DESC
LIMIT 20;
```

SQLite 종료:

```sql
.quit
```

## LCD 화면 표시

정상 상태에서는 5초마다 다음 화면을 순환한다.

```text
24H ALL  99.8%
Checks: 25920
```

```text
8.8.8.8  99.9%
24H Fail: 3
```

연결이 실패하면 즉시 경고 화면을 표시한다.

```text
ALERT 8.8.8.8
No response
```

실패한 IP가 다음 검사에서 다시 성공하면 경고를 즉시 해제하고, 정상 통계 화면을 다시 5초 주기로 순환한다.
