# tg-saver

Асинхронный Telegram-бот на Python (aiogram 3) для пересылки сообщений и медиафайлов между каналами, группами и чатами с поддержкой дедупликации, контролем лимитов API и встроенной стилометрической аналитикой.

## Возможности

- **Маршрутизация сообщений:** гибкая настройка правил пересылки (`forward` или чистая копия `copy`) между каналами и чатами.
- **Сборка альбомов:** автоматическая группировка медиафайлов с одинаковым `media_group_id` и их нативная отправка.
- **Идемпотентность и защита от циклов:** двухфазная регистрация статусов сообщений исключает дублирование, а алгоритм DFS на этапе настройки блокирует зацикливание маршрутов (A → B → A).
- **Rate Limiting:** регулируемая асинхронная очередь отправки с соблюдением ограничений Telegram API и автоматическим backoff при `Retry-After`.
- **Стилометрический анализ:** подсчет базовых метрик стиля общения (длина сообщений, пунктуация, TTR, распределение частей речи) без сохранения исходного текста (Zero-Raw-Text).
- **Безопасность:** разграничение доступа по ролям (Owner, Admin, User), опциональная защита входа паролем.

---

## Требования

- Python 3.12+
- SQLite 3
- Telegram Bot Token ([@BotFather](https://t.me/BotFather))

---

## Быстрый старт

### 1. Клонирование и установка зависимостей

```bash
git clone https://github.com/your-username/tg-saver.git
cd tg-saver

python -m venv venv

# Windows
.\venv\Scripts\activate

# Linux / macOS
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Настройка переменных окружения

Скопируйте пример конфигурационного файла:

```bash
cp .env.example .env
```

Заполните параметры в `.env`:

```ini
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
OWNER_ID=123456789
DATABASE_PATH=data/forwarder.db
LOG_LEVEL=INFO
```

### 3. Запуск

```bash
python main.py
```

---

## Настройка Telegram-бота

1. Создайте бота через [@BotFather](https://t.me/BotFather) (`/newbot`).
2. Для работы в группах отключите приватность:
   - `/setprivacy` → выберите бота → **Disable**.
3. Разрешите добавление в группы:
   - `/setjoingroups` → выберите бота → **Enable**.
4. Добавьте бота в каналы/группы:
   - **В источнике:** как администратора с правом чтения сообщений.
   - **В назначении:** как администратора с правом публикации сообщений.
5. После отправки любого тестового сообщения в чат бот зарегистрирует его в своей базе данных. Далее создайте маршрут через команду `/routes`.

---

## Конфигурация (.env)

| Параметр | По умолчанию | Описание |
|---|---|---|
| `BOT_TOKEN` | *обязательный* | Токен бота от BotFather |
| `OWNER_ID` | `0` | Числовой ID владельца бота в Telegram |
| `ADMIN_IDS` | `""` | Дополнительные ID администраторов через запятую |
| `DATABASE_PATH` | `data/forwarder.db` | Путь к файлу базы данных SQLite |
| `LOG_LEVEL` | `INFO` | Уровень логирования (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `FORWARD_RATE_LIMIT_PER_MINUTE` | `20` | Максимум сообщений в минуту на один чат |
| `QUEUE_MAX_SIZE` | `500` | Максимальный размер очереди сообщений |
| `ALBUM_DEBOUNCE_SECONDS` | `0.8` | Время ожидания компонентов медиагруппы (сек) |
| `ACCESS_PASSWORD` | `changeme` | Пароль доступа для новых пользователей |
| `PASSWORD_REQUIRED` | `true` | Требовать ли пароль при первом входе |
| `ANALYTICS_ENABLED` | `true` | Включение модуля стилометрии |
| `DATA_RETENTION_DAYS` | `30` | Срок хранения агрегированной статистики (дни) |

---

## Основные команды бота

- `/start` — главное меню и статус авторизации.
- `/routes` — управление маршрутами пересылки.
- `/sources` — список подключенных чатов-источников.
- `/destinations` — список целевых каналов и групп.
- `/profile` — просмотр рассчитанного профиля стиля.
- `/compare` — сравнение текста с эталонным стилем.
- `/admin` — панель управления (для владельца и администраторов).
- `/status` — состояние очередей и общая статистика.

---

## Тестирование

Запуск тестов через pytest:

```bash
pytest
```

---

## Развертывание (Systemd)

Пример службы для Linux (`/etc/systemd/system/tg-forwarder.service`):

```ini
[Unit]
Description=Telegram Media Forwarder
After=network.target

[Service]
Type=simple
User=botuser
WorkingDirectory=/opt/tg-saver
ExecStart=/opt/tg-saver/venv/bin/python main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now tg-forwarder
```

---

## Лицензия

Проект распространяется под лицензией [MIT](LICENSE).
