import os
import re
import glob

# Знаходимо останній лог-файл
log_files = glob.glob('/root/data/server_metrics_*.log')
if not log_files:
    print('Лог-файлів не знайдено.')
    exit(0)

latest_log = max(log_files, key=os.path.getctime)

with open(latest_log, 'r') as f:
    lines = f.readlines()
    if not lines:
        print('Лог-файл порожній.')
        exit(0)
    
    # Беремо останній запис
    last_line = lines[-1].strip()

# Витягуємо метрики з останнього запису
pattern = r'\[(.*?)\] CPU: (\d+\.?\d*), RAM: (\d+)/(\d+), Disk: (\d+)%?, Processes: (\d+)'
match = re.search(pattern, last_line)

if not match:
    print('Не вдалося розпізнати формат запису.')
    exit(0)

timestamp, cpu_usage, ram_used, ram_total, disk_usage, process_count = match.groups()

# Конвертуємо у числа
cpu_usage = float(cpu_usage)
ram_used = int(ram_used)
ram_total = int(ram_total)
ram_usage = (ram_used / ram_total) * 100

disk_usage = int(disk_usage.strip('%'))

# Перевірка на попередження
warnings = []

if cpu_usage > 80:
    warnings.append(f'Високе використання CPU: {cpu_usage:.1f}%')

if ram_usage > 90:
    warnings.append(f'Високе використання RAM: {ram_usage:.1f}%')

if disk_usage > 90:
    warnings.append(f'Високе використання диску: {disk_usage}%')

# Якщо є попередження — надсилаємо через message tool
if warnings:
    warning_text = ', '.join(warnings)
    print(f"🔴 Попередження про продуктивність: {warning_text}")
    # Виводимо спеціальний тег для message tool
    print("__SEND_MESSAGE__: 🔴 Попередження про продуктивність: " + warning_text)
else:
    print("Аналіз завершено: попереджень немає.")
