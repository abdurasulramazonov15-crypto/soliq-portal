import os
import sys
import subprocess
import time

print("==================================================================")
print("🚀 Soliq Yangiliklari: Telegram Bot va Veb-portal ishga tushmoqda")
print("==================================================================")

# 1. Telegram Botni alohida fon jarayonida ishga tushirish
bot_proc = subprocess.Popen([sys.executable, "bot.py"])
print(f"🤖 Telegram Bot fonda ishga tushdi (PID: {bot_proc.pid})")

# 2. Render belgilagan PORT
port = os.environ.get("PORT", "5000")
print(f"🌐 Veb-portal Gunicorn orqali 0.0.0.0:{port} manzilida faollashmoqda...")

# 3. Gunicorn serverini ishga tushirish (Render aynan shu portni kuzatadi)
cmd = [
    "gunicorn",
    "--workers", "1",
    "--bind", f"0.0.0.0:{port}",
    "--access-logfile", "-",
    "app:app"
]

try:
    subprocess.run(cmd)
finally:
    print("Xizmat to'xtatilmoqda, Telegram bot ham yopilmoqda...")
    bot_proc.terminate()
