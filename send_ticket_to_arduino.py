import time
import requests
import serial

# ======== 這裡依照你的環境修改  ========
API_URL = "http://127.0.0.1:8000/queues/api/current_number/"
DOCTOR_ID = 1          # 要顯示哪一個醫師的叫號，就填那個 Doctor.id  
SERIAL_PORT = "COM3"   # 你的 Arduino 接在哪一個 COM Port，就改掉 
BAUDRATE = 9600
POLL_INTERVAL = 3.0    # 幾秒抓一次資料
# ====================================

def fetch_numbers():
    """呼叫 Django API，拿到 current / next 號碼 """
    try:
        resp = requests.get(
            API_URL,
            params={"doctor_id": DOCTOR_ID},
            timeout=3,
        )
        resp.raise_for_status()
        data = resp.json()

        cur = data.get("current") or {}
        nxt = data.get("next") or {}

        current_num = cur.get("number")
        next_num = nxt.get("number")

        return current_num, next_num
    except Exception as e:
        print("[ERROR] fetch_numbers:", e)
        return None, None

def main():
    print(f"[INFO] Connect serial: {SERIAL_PORT} @ {BAUDRATE}")
    ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=1)
    time.sleep(2)  # 給 Arduino 一點時間重啟 

    last_sent = None

    while True:
        current_num, next_num = fetch_numbers()

        # 如果沒有號碼，就用 0 代表「無」 
        if current_num is None:
            current_num = 0
        if next_num is None:
            next_num = 0

        # 傳給 Arduino 的格式：例如 "15,16\n"
        msg = f"{current_num},{next_num}\n"

        # 避免一直重複傳同樣的資料
        if msg != last_sent:
            ser.write(msg.encode("ascii"))
            ser.flush()
            print("[SEND]", msg.strip())
            last_sent = msg
        else:
            print("[SKIP] same data:", msg.strip())

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
