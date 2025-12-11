import os
import sys
import time

import serial  # pip install pyserial

# === 讓這個腳本可以使用 Django 專案 ===
BASE_DIR = r"C:\project\hospitalsys"
sys.path.append(BASE_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hospitalsys.settings")

import django
django.setup()

from django.utils import timezone
from queues.models import VisitTicket
from doctors.models import Doctor

# === 串口設定，請把 COM3 改成你實際的 Port 喵 ===
SERIAL_PORT = "COM3"  # 例如 COM4 / COM5，去裝置管理員看喵
BAUDRATE = 9600

DOCTOR_ID = 1  # 想顯示哪一位醫師的號碼就改這裡喵
INTERVAL_SEC = 3  # 每幾秒更新一次

def get_current_number_for_doctor(doctor_id):
    """回傳指定醫師今天目前 CALLING/IN_PROGRESS 的號碼，沒有的話回 0 喵"""
    today = timezone.localdate()
    doctor = Doctor.objects.filter(id=doctor_id, is_active=True).first()
    if not doctor:
        print(f"[WARN] Doctor {doctor_id} not found or inactive")
        return 0

    ticket = (
        VisitTicket.objects
        .filter(
            date=today,
            doctor=doctor,
            status__in=["CALLING", "IN_PROGRESS"],
        )
        .order_by("number")
        .first()
    )
    if ticket:
        return ticket.number
    return 0

def main():
    print(f"[INFO] Opening serial port {SERIAL_PORT} ...")
    ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=1)
    time.sleep(2)  # 等 Arduino reset 完喵

    try:
        last_sent = None
        while True:
            number = get_current_number_for_doctor(DOCTOR_ID)
            # 只在號碼有變動的時候才送，避免沒完沒了刷喵
            if number != last_sent:
                last_sent = number
                payload = f"{number:04d}\n"
                ser.write(payload.encode("utf-8"))
                print(f"[SEND] {payload.strip()}")

            time.sleep(INTERVAL_SEC)
    except KeyboardInterrupt:
        print("\n[INFO] Stopped by user.")
    finally:
        ser.close()
        print("[INFO] Serial closed.")

if __name__ == "__main__":
    main()
