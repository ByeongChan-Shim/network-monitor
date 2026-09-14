Python 3.13.2 (v3.13.2:4f8bb3947cf, Feb  4 2025, 11:51:10) [Clang 15.0.0 (clang-1500.3.9.4)] on darwin
Type "help", "copyright", "credits" or "license()" for more information.
>>> #!/usr/bin/env python3
... """Display the latest network check stored by collector.py on a 16x2 I2C LCD."""
... 
... import argparse
... import sqlite3
... import time
... from datetime import datetime, timedelta
... from pathlib import Path
... 
... try:
...     from smbus import SMBus
... except ImportError as error:
...     raise SystemExit(
...         "smbus가 없습니다. 'sudo apt install python3-smbus i2c-tools'를 실행하세요."
...     ) from error
... 
... 
... DATABASE_PATH = Path(__file__).with_name("network.db")
... LCD_COLUMNS = 16
... LCD_ROWS = 2
... SUMMARY_PERIOD = timedelta(days=1)
... SCREEN_DURATION_SECONDS = 5.0
... 
... 
... class I2cLcd:
...     """Driver for the common PCF8574 I2C backpack on an HD44780 16x2 LCD."""
... 
...     ENABLE = 0x04
...     REGISTER_SELECT = 0x01
...     BACKLIGHT = 0x08
... 
...     def __init__(self, address, bus_number=1):
...         self.bus = SMBus(bus_number)
...         self.address = address
...         self.backlight = self.BACKLIGHT
...         self._initialize()
... 
    def _write(self, value):
        self.bus.write_byte(self.address, value | self.backlight)

    def _pulse(self, value):
        self._write(value | self.ENABLE)
        time.sleep(0.0005)
        self._write(value & ~self.ENABLE)
        time.sleep(0.0001)

    def _send_nibble(self, nibble, mode=0):
        value = (nibble & 0xF0) | mode
        self._write(value)
        self._pulse(value)

    def _send_byte(self, value, mode=0):
        self._send_nibble(value & 0xF0, mode)
        self._send_nibble((value << 4) & 0xF0, mode)

    def _initialize(self):
        time.sleep(0.05)
        for command in (0x33, 0x32, 0x28, 0x0C, 0x06, 0x01):
            self._send_byte(command)
            time.sleep(0.005)

    def write_line(self, row, text):
        addresses = (0x80, 0xC0)
        self._send_byte(addresses[row])
        for character in text[:LCD_COLUMNS].ljust(LCD_COLUMNS):
            self._send_byte(ord(character), self.REGISTER_SELECT)

    def close(self):
        self.bus.close()


def recent_statistics(database_path):
    since = (datetime.now().astimezone() - SUMMARY_PERIOD).isoformat(timespec="seconds")
    try:
        with sqlite3.connect(database_path) as connection:
            rows = connection.execute(
                """
                SELECT target, COUNT(*), COALESCE(SUM(success), 0)
                FROM network_check
                WHERE timestamp >= ?
                GROUP BY target
                ORDER BY target
                """,
                (since,),
            ).fetchall()
    except sqlite3.Error:
        return []
    return rows


def current_failure(database_path):
    try:
        with sqlite3.connect(database_path) as connection:
            return connection.execute(
                """
                SELECT current.target, current.error_type
                FROM network_check AS current
                INNER JOIN (
                    SELECT target, MAX(id) AS latest_id
                    FROM network_check
                    GROUP BY target
                ) AS latest ON current.id = latest.latest_id
                WHERE current.success = 0
                ORDER BY current.id DESC
                LIMIT 1
                """
            ).fetchone()
    except sqlite3.Error:
        return None


def normal_screens(statistics):
    if not statistics:
        return [("Waiting for data", "Start collector.py")]

    total_checks = sum(total for _, total, _ in statistics)
    successful_checks = sum(successful for _, _, successful in statistics)
    success_rate = successful_checks * 100 / total_checks
    screens = [(f"24H ALL {success_rate:5.1f}%", f"Checks: {total_checks}")]

    for target, total, successful in statistics:
        success_rate = successful * 100 / total
        failed = total - successful
        screens.append((f"{target[:9]} {success_rate:4.1f}%", f"24H Fail: {failed}"))
    return screens


def alert_screen(failure):
    target, error_type = failure
    reason = "No response" if error_type in {"timeout", "unreachable", "ping_failed"} else error_type
    return f"ALERT {target[:10]}", (reason or "Ping failed")[:LCD_COLUMNS]


def main():
    parser = argparse.ArgumentParser(description="Show the latest network check on a 16x2 I2C LCD.")
    parser.add_argument("--address", default="0x27", help="I2C LCD address, for example 0x27 or 0x3f")
    parser.add_argument("--interval", type=float, default=0.5, help="Database check interval in seconds")
    arguments = parser.parse_args()

    address = int(arguments.address, 0)
    lcd = I2cLcd(address)
    print(f"LCD display started at I2C address {arguments.address}. Press Ctrl+C to stop.")
    screen_index = 0
    next_screen_change = time.monotonic() + SCREEN_DURATION_SECONDS
    showing_alert = False
    try:
        while True:
            failure = current_failure(DATABASE_PATH)
            if failure is not None:
                first_line, second_line = alert_screen(failure)
                showing_alert = True
            else:
                if showing_alert:
                    screen_index = 0
                    next_screen_change = time.monotonic() + SCREEN_DURATION_SECONDS
                    showing_alert = False
                screens = normal_screens(recent_statistics(DATABASE_PATH))
                if time.monotonic() >= next_screen_change:
                    screen_index = (screen_index + 1) % len(screens)
                    next_screen_change = time.monotonic() + SCREEN_DURATION_SECONDS
                first_line, second_line = screens[screen_index % len(screens)]
            lcd.write_line(0, first_line)
            lcd.write_line(1, second_line)
            time.sleep(arguments.interval)
    except KeyboardInterrupt:
        print("\nLCD display stopped.")
    finally:
        lcd.close()


if __name__ == "__main__":
    main()
