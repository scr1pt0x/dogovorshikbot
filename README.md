# dogovorshikbot — Telegram бот для заполнения договоров

Telegram-бот на Python, который пошагово собирает данные у пользователя и генерирует DOCX-документы:
1) Для `Мурабаха` — 2 файла (договор + график платежей)
2) Для `Истисна` — 1 файл (единый договор на 3 страницах)

⚠️ PDF-генерация отключена (по текущей конфигурации проекта).

---

## Возможности

- Пошаговый диалог (кнопки/ввод) без перегруза
- Генерация документов **по DOCX-шаблонам** с плейсхолдерами `{{...}}`
- Отдельные сценарии для `Мурабаха` и `Истисна`
- Атомарная нумерация договоров в `data/counter.json` (с файловой блокировкой)
- Стабильная вставка текста в DOCX без разрушения форматирования шаблона  
  (генератор делает **только замену плейсхолдеров**, не “нормализует” стили)

---

## Стек

- Python 3.9+ (рекомендуется 3.11+)
- `python-telegram-bot` (async)
- `python-docx`
- `python-dateutil`
- `python-dotenv`
- `portalocker` (блокировка counter.json)
- (опционально) LibreOffice — **не требуется**, если PDF отключён

---

## Структура проекта
- dogovorshikbot/
- bot.py
- handlers.py
- docx_generator.py
- utils.py
- contract_number.py
- paths.py
- requirements.txt
- .env               (не коммитится)
- templates/
- murabaha_template.docx
- murabaha_schedule.docx
- istisna_template.docx
- data/
- counter.json     (не коммитится)
- output/
- ready_contracts/ (временные файлы, не коммитятся)
- ---

## Быстрый старт (локально)

### 1) Установка зависимостей
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
BOT_TOKEN=PASTE_YOUR_TELEGRAM_BOT_TOKEN_HERE
# TG_PROXY=socks5://user:pass@host:port   (опционально, если Telegram API режется сетью)