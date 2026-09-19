# استقرار ۲۴/۷ روی سرور لینوکسی

سه روش (از توصیه‌شده‌ترین):

---

## روش ۱: systemd service (توصیه‌شده)

پروژه را روی سرور بگذارید (مثلاً `/opt/tapsi-garage`):

```bash
sudo apt update && sudo apt install -y python3 python3-pip   # اوبونتو/دبیان
sudo git clone <آدرس-پروژه> /opt/tapsi-garage  # یا scp کنید
cd /opt/tapsi-garage
sudo pip3 install -r requirements.txt

# تست یک‌باره
python3 main.py daemon --city 1 --once --csv data/products.csv
```

فایل سرویس را کپی کنید:

```bash
sudo cp deploy/tapsi-garage.service /etc/systemd/system/
sudo nano /etc/systemd/system/tapsi-garage.service   # مسیرها/گزینه‌ها را تنظیم کنید
sudo systemctl daemon-reload
sudo systemctl enable --now tapsi-garage

# مشاهدهٔ لاگ زنده:
journalctl -u tapsi-garage -f
# یا فایل لاگ خود پروژه:
tail -f /opt/tapsi-garage/data/daemon.log
```

توقف/ری‌استارت:

```bash
sudo systemctl stop tapsi-garage
sudo systemctl restart tapsi-garage
```

---

## روش ۲: systemd timer (اگر نمی‌خواهید پروسه همیشه روشن بماند)

```bash
sudo cp deploy/tapsi-garage.timer.service /etc/systemd/system/
sudo cp deploy/tapsi-garage.timer.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tapsi-garage.timer.timer
systemctl list-timers   # ببینید کی اجرا می‌شود
```

---

## روش ۳: cron (ساده‌ترین)

```bash
crontab -e
# هر ساعت (دورهٔ یک‌بارِ اجرا با --once):
0 * * * * cd /opt/tapsi-garage && /usr/bin/python3 main.py daemon --city 1 --once --csv data/products.csv --json data/products.json >> data/cron.log 2>&1
```

---

## نکات مهم

- **فاصلهٔ دوره‌ها**: پیش‌فرض `--interval 3600` (هر ساعت). برای هر ۶ ساعت: `--interval 21600`.
  قیمت‌ها معمولاً روزانه عوض می‌شوند؛ هر ۱–۶ ساعت منطقی است. خیلی فشرده نکنید.
- **تغییر قیمت‌ها**: هر دوره با دورهٔ قبل مقایسه می‌شود و تفاوت‌ها در جدول
  `price_history` ذخیره می‌شوند؛ با `python3 main.py changes` ببینید.
- **لاگ‌ها**: `data/daemon.log` (چرخش ندارد — اگر طولانی شد حذفش کنید یا
  logrotate بگذارید).
- **سبد خرید روی سرور**: سشن مهمان در `data/session.json` است؛ اگر پاکش کنید
  سبد جدیدی شروع می‌شود. برای بررسی وضعیت سبد: `python3 main.py cart report`.
- **Docker** (اختیاری):

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "main.py", "daemon", "--city", "1", "--interval", "3600", \
     "--csv", "data/products.csv", "--json", "data/products.json"]
```

```bash
docker build -t tapsi-garage .
docker run -d --name tapsi-garage -v $(pwd)/data:/app/data tapsi-garage
docker logs -f tapsi-garage
```
