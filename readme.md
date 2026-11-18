# Competitor Diff Monitor (AI + Telegram/LINE)

ระบบส่องราคาและฟีเจอร์คู่แข่งอัตโนมัติ (Clean Markdown + Diff Check + AI วิเคราะห์ความต่าง + บันทึก CSV + แจ้งเตือน Telegram / LINE) ออกแบบตามแนวทาง **AI Coding Workflow (Refactored Single-File + Automated Test Suite)** เพื่อให้รันทดสอบได้ทั้งบน **Google Antigravity (Pure Cloud / Remote Control)** และบนเครื่องคอมพิวเตอร์ (VS Code)

---

## โครงสร้างไฟล์ใน Repository

| ไฟล์ | หน้าที่ |
| :--- | :--- |
| `competitor_diff_monitor.py` | โค้ดหลักฉบับสมบูรณ์ (ตั้งค่า, Diff Engine, Crawl4AI, AI Analyzer, Telegram/LINE, CSV Logger) |
| `test_monitor.py` | ชุดทดสอบอัตโนมัติ (Unit Tests + Mocked Integration Tests 15 กรณี) |
| `requirements.txt` | รายการแพ็กเกจ Python ที่ต้องใช้ |
| `.env.example` | ตัวอย่างการตั้งค่า Token และโมเดล AI (ห้าม Commit ไฟล์ `.env` จริงขึ้น GitHub) |
| `.gitignore` | ป้องกันไม่ให้ไฟล์ความลับ (`.env`), `snapshots/`, `*.csv` และ `*.log` หลุดขึ้น Git |

---

## วิธีรันใน Google Antigravity (Pure Cloud & Remote Control)

### 1. รัน Automated Tests บน Pure Cloud / GitHub Actions
ตัว `test_monitor.py` ใช้ Standard Library (`unittest`) ร่วมกับ `pydantic` และ Mock การเชื่อมต่อภายนอกทั้งหมด จึงสามารถสั่งรันทดสอบบน **Google Antigravity Pure Cloud** ได้ทันทีโดยไม่ต้องมี Browser หรือ Ollama:

```bash
pip install pydantic
python -m unittest -v test_monitor.py
```

### 2. รันส่องเว็บจริงผ่าน Antigravity Remote Control (เชื่อมกับคอมที่บ้าน)
เนื่องจาก `Crawl4AI` ต้องเปิด Headless Browser และ `Ollama` รันอยู่ที่ `http://localhost:11434/v1` ให้ใช้โหมด **Remote Control** บน Antigravity หรือรันในเครื่อง PC ตามขั้นตอนด้านล่าง:

1. ติดตั้งแพ็กเกจและ Browser สำหรับ Crawl4AI:
   ```bash
   pip install -r requirements.txt
   crawl4ai-setup
   ```
2. คัดลอกไฟล์ตั้งค่าและใส่ Token ของคุณ:
   ```bash
   cp .env.example .env
   ```
   *(หรือตั้งค่า Environment Variables สำหรับ `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `LINE_CHANNEL_ACCESS_TOKEN`, `LINE_USER_ID`)*
3. รันสคริปต์ส่องเว็บจริง:
   ```bash
   python competitor_diff_monitor.py
   ```

---

## ขั้นตอนสร้าง GitHub Repo และ Commit โค้ดขึ้น GitHub

นำไฟล์ทั้งหมดไปวางในโฟลเดอร์โปรเจกต์บนเครื่องของคุณ แล้วรันคำสั่งด้านล่างใน Terminal (VS Code):

```bash
# 1. สร้าง Git repo ใหม่ในโฟลเดอร์โปรเจกต์
git init
git branch -M main

# 2. รัน Test ยืนยันความถูกต้องก่อน Commit เสมอ
python -m unittest -v test_monitor.py

# 3. Stage และ Commit ไฟล์ทั้งหมด
git add competitor_diff_monitor.py test_monitor.py requirements.txt .env.example .gitignore README.md
git commit -m "feat: initial competitor diff monitor with automated test suite"

# 4. เชื่อมต่อกับ GitHub Repo ที่สร้างไว้ แล้ว Push ขึ้น Cloud
git remote add origin https://github.com/<USERNAME>/<REPO_NAME>.git
git push -u origin main
```

*(คำแนะนำสำหรับ Google Antigravity: หลังจาก Push ขึ้น GitHub แล้ว สามารถเปิดโปรเจกต์นี้จาก GitHub ใน Antigravity เพื่อสั่ง Agent แก้ไขโค้ดเป็น Micro-Task และรัน `python -m unittest -v test_monitor.py` ตรวจงานได้ทุกครั้ง)*
