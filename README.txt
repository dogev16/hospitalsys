========================================
Hospitalsys Django 專案安裝與執行說明
========================================

【專案用途】
- 本專案為 Django 作業專案（診所/醫院管理系統），包含：
  - 病人管理（patients）
  - 掛號/預約（appointments）
  - 排隊（queues）
  - 處方（prescriptions）
  - 庫存（inventory）
  - 前台/公開頁面（public）
  - 內部首頁（/internal/）

【系統環境需求】
- 作業系統：Windows / macOS / Linux 皆可
- Python：3.11+（建議 3.12 / 3.13）
- pip：已安裝
- （可選）Git：若用 git clone

【專案結構假設】
- manage.py 位於專案根目錄
- requirements.txt 位於專案根目錄
- 資料庫預設使用 sqlite（db.sqlite3）

----------------------------------------
一、第一次安裝（本機 Local）
----------------------------------------

1) 取得專案
- 若你是用壓縮檔：解壓縮到任意資料夾
- 若你是用 git：
  git clone 【可替換：你的 repo 連結】
  cd hospitalsys

2) 建立虛擬環境（建議）
Windows（PowerShell）：
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1

Windows（CMD）：
  python -m venv .venv
  .\.venv\Scripts\activate

macOS / Linux：
  python3 -m venv .venv
  source .venv/bin/activate

3) 安裝套件
  pip install -r requirements.txt

4) 設定環境變數（建議使用 .env）
在專案根目錄建立 .env（可參考 .env.example）
最低需求（最少）：
  SECRET_KEY=你自己的key
  DEBUG=True
  ALLOWED_HOSTS=127.0.0.1,localhost

※ 若你沒用 .env，也可以直接在 settings.py 設定 SECRET_KEY / DEBUG / ALLOWED_HOSTS。

5) 初始化資料庫（migration）
  python manage.py migrate

6) 建立管理員帳號（可選）
  python manage.py createsuperuser

7) 啟動專案
  python manage.py runserver

8) 開啟瀏覽器測試
- 前台（public）：http://127.0.0.1:8000/
- 內部首頁：      http://127.0.0.1:8000/internal/
- 管理後台：      http://127.0.0.1:8000/admin/

----------------------------------------
二、常見問題排查
----------------------------------------

1) NoReverseMatch（模板 url 名稱找不到）
- 檢查 templates 內 {% url 'xxx' %} 的名字是否存在於 urls.py
- 若有 namespace，必須寫成：
  {% url 'public:home' %}
  {% url 'patients:patient_list' %}

2) TemplateSyntaxError：'block' tag appears more than once
- 同一個 template 檔案內 block title / block content 不能重複宣告
- 並且 {% extends "base.html" %} 必須放在檔案最上方（第一行附近）

3) 靜態檔案沒跑版（CSS 不生效）
- 檢查 base.html 是否有：
  {% load static %}
  <link rel="stylesheet" href="{% static 'css/hospital_theme.css' %}">
- DEBUG=True 通常會自動處理 static；DEBUG=False 需要 collectstatic（見部署章節）

----------------------------------------
三、部署到 Render（可選）
----------------------------------------

【重要概念】
- Render 上通常會使用 DEBUG=False
- DEBUG=False 必須設定 ALLOWED_HOSTS，否則會 DisallowedHost

建議環境變數（Render Dashboard 設定）：
- SECRET_KEY：請填一串隨機字
- DEBUG：False
- ALLOWED_HOSTS：.onrender.com

（如果你用 sqlite：通常不建議雲端；若作業允許可用，但資料可能會因重部署而重置）
（若改 PostgreSQL：需要 DATABASE_URL）

部署常用指令（Render Start Command）
- 先 migrate：
  python manage.py migrate
- 收集靜態檔案（若有 STATIC_ROOT）：
  python manage.py collectstatic --noinput
- 啟動（常見用 gunicorn；需 requirements.txt 內有 gunicorn）
  gunicorn hospitalsys.wsgi:application

----------------------------------------
四、附註
----------------------------------------
- 本 README 為作業展示用途，安全設定採最小可用原則。
- 若需完整資安（HTTPS、CSRF、CSP、資料庫權限、密碼政策等）可再加強。
