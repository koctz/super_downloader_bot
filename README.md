sudo apt update && sudo apt upgrade -y
sudo apt install ffmpeg git python3-pip python3-venv -y

# Клонируем репозиторий
git clone https://github.com/koctz/super_downloader_bot.git
cd super_downloader_bot

# Создаем виртуальное окружение
python3 -m venv venv
source venv/bin/activate

# Устанавливаем зависимости
pip install -r requirements.txt

nano .env

[Unit]
Description=Telegram Super Downloader Bot
After=network.target

[Service]
User=root
Group=root
WorkingDirectory=/root/super_downloader_bot
EnvironmentFile=/root/super_downloader_bot/.env
ExecStart=/root/super_downloader_bot/venv/bin/python run.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target


# Перезагружаем менеджер служб
sudo systemctl daemon-reload

# Включаем автозагрузку бота
sudo systemctl enable tgbot

# Запускаем бота
sudo systemctl start tgbot

journalctl -u tgbot -f
