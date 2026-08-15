# Пошаговый запуск LTX 2.3 / 10Eros / Goon Machine + Telegram на Vast.ai

Эта инструкция рассчитана на итоговую схему:

**один раз собрать Docker image и создать свой Vast Template → затем каждый раз выбрать RTX 5090 → Rent → дождаться READY → открыть ComfyUI или писать Telegram-боту → скачать результаты → Destroy.**

Проект специально сделан для временных (ephemeral) инстансов. После Destroy модели, исходники и результаты на этом инстансе исчезнут.

---

## 1. Что понадобится один раз

1. Аккаунт Vast.ai с балансом.
2. Аккаунт GitHub.
3. Этот проект.
4. Рекомендуемый GPU для аренды: **RTX 5090 32 GB VRAM**.
5. Рекомендуемая RAM хоста: **64 GB или больше**.
6. Диск инстанса: **200 GB**.
7. Опционально:
   - Hugging Face token (`HF_TOKEN`);
   - Civitai API token (`CIVITAI_TOKEN`);
   - Telegram bot token (`TELEGRAM_BOT_TOKEN`).

Токены не нужно записывать в GitHub-репозиторий или внутрь Docker image.

---

## 2. Один раз собрать Docker image через GitHub

### 2.1. Создать репозиторий

Создайте новый репозиторий GitHub, например:

```text
ltx23-goon-vast
```

Распакуйте архив проекта. В корне GitHub-репозитория должны лежать непосредственно:

```text
Dockerfile
README.md
.env.example
config/
docker/
bot/
scripts/
workflows/
vast/
.github/
```

То есть `Dockerfile` должен быть в корне репозитория, а не на дополнительный уровень ниже.

### 2.2. Загрузить проект в `main`

Можно загрузить файлы через веб-интерфейс GitHub или обычным Git:

```bash
git init
git add .
git commit -m "Initial Vast 5090 image"
git branch -M main
git remote add origin https://github.com/<USER>/ltx23-goon-vast.git
git push -u origin main
```

### 2.3. Дождаться GitHub Actions

В проекте уже есть:

```text
.github/workflows/publish-ghcr.yml
```

После push в `main` GitHub Actions должен собрать image:

```text
ghcr.io/<USER>/ltx23-goon-vast:5090
```

Откройте GitHub → **Actions** → `Build and publish Vast image` и дождитесь зелёного статуса.

### 2.4. Видимость GHCR package

Самый простой вариант — сделать GHCR package **Public**. Секретов внутри image нет: модели и токены в image не запекаются.

Если хотите оставить package Private, Vast должен иметь credentials для чтения GHCR package. Для первого запуска Public проще и исключает большую часть ошибок `pull access denied`.

---

## 3. Создать Telegram-бота (опционально)

Если Telegram не нужен, пропустите этот раздел и оставьте:

```text
ENABLE_TELEGRAM_BOT=0
```

Если нужен:

1. В Telegram откройте `@BotFather`.
2. Выполните `/newbot`.
3. Задайте имя и username.
4. Получите token вида:

```text
1234567890:AA....
```

Этот token далее задаётся как `TELEGRAM_BOT_TOKEN` в Vast.

### Как работает бот

- сообщение **только с текстом** → генерируется **картинка**;
- **фото + подпись** → генерируется **видео из фото**, где подпись используется как описание сцены;
- `/status` → проверка доступности ComfyUI;
- `/id` → показывает числовой Telegram user ID.

По умолчанию photo-to-video канал не запускает сексуализированные запросы по фотографии реального человека (`TELEGRAM_BLOCK_NSFW_PHOTO=1`).

---

## 4. Добавить секреты в Vast.ai

Для секретов лучше использовать глобальные Environment Variables аккаунта Vast, а не сохранять их в Template.

Добавьте по необходимости:

```text
HF_TOKEN=<ваш Hugging Face token>
CIVITAI_TOKEN=<ваш Civitai token>
TELEGRAM_BOT_TOKEN=<token от BotFather>
```

Если Telegram нужен, также:

```text
ENABLE_TELEGRAM_BOT=1
```

Если пока не знаете свой Telegram numeric ID, сначала оставьте:

```text
TELEGRAM_ALLOWED_USER_IDS=
```

После первого запуска отправьте боту `/id`, получите ID, а затем можете добавить его в Vast:

```text
TELEGRAM_ALLOWED_USER_IDS=123456789
```

Для нескольких пользователей:

```text
TELEGRAM_ALLOWED_USER_IDS=123456789,987654321
```

**Важно:** не запускайте одновременно два Vast-инстанса с одним и тем же Telegram bot token, если оба используют polling. Иначе они будут конкурировать за Telegram updates.

---

## 5. Создать свой Vast Template

Откройте Vast.ai → **Templates** → **New Template**.

### 5.1. Docker image

Если GHCR package публичный:

```text
Image visibility: Public
Registry: GitHub Container Registry / ghcr.io (если есть в списке)
Docker Image: ghcr.io/<USER>/ltx23-goon-vast
Tag: 5090
```

Если интерфейс Vast сам подставляет выбранный registry и не принимает `ghcr.io/` в поле Docker Image, используйте:

```text
<USER>/ltx23-goon-vast
```

Ключевой итог — Vast должен получать именно:

```text
ghcr.io/<USER>/ltx23-goon-vast:5090
```

### 5.2. Название

Например:

```text
LTX2.3 10Eros + Goon + Telegram - RTX 5090
```

### 5.3. Launch Mode

Выберите:

```text
docker ENTRYPOINT
```

или вариант с названием **Entrypoint**, если UI Vast показывает его именно так.

Это важно: SSH/Jupyter launch modes заменяют обычный entrypoint контейнера, а наш проект должен стартовать автоматически через Docker CMD/ENTRYPOINT.

### 5.4. Disk Space

Выберите:

```text
200 GB
```

32 GB недостаточно. На инстанс загружаются ComfyUI, 10Eros, Krea/LTX assets, Ollama model, кеши и результаты.

### 5.5. Local volume

Для выбранного сценария:

```text
Add local volume: OFF
```

Это соответствует схеме «арендовал → поработал → скачал результат → Destroy».

### 5.6. Ports

Добавьте TCP:

```text
1111 TCP
8188 TCP
```

`1111` используется Instance Portal, `8188` — логический ComfyUI service port в шаблоне. Внутри контейнера Portal проксирует ComfyUI на его локальный runtime port.

### 5.7. Несекретные Environment Variables шаблона

Добавьте:

```text
OPEN_BUTTON_PORT=1111
OPEN_BUTTON_TOKEN=1
PORTAL_CONFIG=localhost:1111:11111:/:Instance Portal|localhost:8188:18188:/:ComfyUI
DATA_DIRECTORY=/workspace
COMFY_RESERVE_VRAM=2
DOWNLOAD_LUSTIFY_V10=1
DOWNLOAD_OPTIONAL_POST=0
OLLAMA_MODEL=satgeze/gemma4-12b-uncensored-1m:latest
COMFYUI_API_BASE=http://127.0.0.1:18188
COMFY_WORKFLOWS_DIR=/workspace/user/default/workflows
TELEGRAM_DATA_DIR=/workspace/telegram-bot
TELEGRAM_INPUT_ROOT=/workspace/telegram-input
TELEGRAM_TEXT_WORKFLOW=GoonMachine_T2I_5090_AUTO_SAFE.json
TELEGRAM_PHOTO_WORKFLOW=GoonMachine_I2V_5090_SAFE.json
TELEGRAM_BLOCK_NSFW_PHOTO=1
```

Если Telegram включаете через Account Environment Variables, здесь `ENABLE_TELEGRAM_BOT` и token можно не дублировать.

Если хотите хранить флаг прямо в Private Template:

```text
ENABLE_TELEGRAM_BOT=1
```

но сам `TELEGRAM_BOT_TOKEN` лучше оставить в Account Environment Variables.

### 5.8. Private template

Включите:

```text
Private template: ON
```

Это скрывает ваш шаблон из публичного каталога. Видимость Template и видимость Docker image — разные вещи.

Нажмите **Create**.

---

## 6. Каждый раз, когда нужна генерация

Теперь повторная работа выглядит очень коротко.

### 6.1. Выбрать шаблон

Vast.ai → Templates → **My Templates** → ваш:

```text
LTX2.3 10Eros + Goon + Telegram - RTX 5090
```

Нажмите запуск/Play, чтобы перейти к предложениям GPU.

### 6.2. Фильтр хоста

Ищите примерно такие параметры:

```text
GPU: RTX 5090
VRAM: 32 GB
System RAM: >= 64 GB
Disk available: >= 200 GB
CUDA: 12.8+
Reliability: желательно >= 99%
Цена: ваш целевой предел <= $0.50/hour
```

Также полезны:

- PCIe 4.0/5.0 x16;
- быстрый SSD/NVMe;
- хорошая download speed, потому что при каждом новом ephemeral Rent модели скачиваются заново.

### 6.3. Rent

Нажмите **Rent**.

После старта происходит два этапа:

1. Vast скачивает ваш Docker image.
2. Контейнер автоматически скачивает модели и готовит runtime.

На первом старте конкретного инстанса это не мгновенно: загружаются десятки гигабайт.

---

## 7. Что контейнер делает автоматически

После запуска никаких команд вводить не нужно.

`docker/start.sh` автоматически:

1. создаёт `/workspace/models`, `/workspace/input`, `/workspace/output`, кеши и workflow-папки;
2. запускает bootstrap/status page;
3. проверяет GPU, VRAM, RAM, диск и CUDA/PyTorch;
4. запускает Ollama;
5. скачивает модель Ollama;
6. скачивает 10Eros и остальные требуемые модели;
7. создаёт AUTO-варианты workflow;
8. запускает ComfyUI;
9. проверяет `/workflow/convert` для Telegram API automation;
10. если `ENABLE_TELEGRAM_BOT=1`, запускает Telegram polling worker.

Когда всё готово, в логах появляется:

```text
[comfyui] READY
```

---

## 8. Открыть веб-интерфейс

В разделе Vast → Instances дождитесь, когда кнопка станет **Open**.

Нажмите **Open**.

Откроется Instance Portal. В нём должна быть ссылка:

```text
ComfyUI
```

Нажмите её.

Пока модели ещё скачиваются, может отображаться bootstrap/status page или сервис может быть временно недоступен. Это нормально до окончания подготовки.

После READY откроется полноценный ComfyUI.

---

## 9. Какие workflow будут доступны

Runtime автоматически кладёт workflow в:

```text
/workspace/user/default/workflows
```

Основные:

```text
GoonMachine_T2I_5090_AUTO_SAFE.json
GoonMachine_T2I2V_5090_AUTO_SAFE.json
GoonMachine_T2I2V_5090_AUTO_FULL.json
GoonMachine_I2V_5090_SAFE.json
10Eros_I2V_DMD_V5_5090.json
GoonMachine_original_v08.json
```

### Для первого теста

Используйте SAFE варианты.

```text
GoonMachine_T2I_5090_AUTO_SAFE
GoonMachine_T2I2V_5090_AUTO_SAFE
GoonMachine_I2V_5090_SAFE
```

FULL имеет смысл включать после того, как базовый запуск подтверждён стабильным на конкретном драйвере/хосте.

---

## 10. Использование Telegram

После `[comfyui] READY` Telegram worker тоже запускается.

### Текст → картинка

Отправьте боту обычное текстовое сообщение, например описание нужной сцены.

Бот:

1. берёт `GoonMachine_T2I_5090_AUTO_SAFE.json`;
2. напрямую подставляет ваш текст в positive Krea prompt;
3. конвертирует обычный ComfyUI workflow в API prompt;
4. ставит задачу в очередь ComfyUI;
5. ждёт completion;
6. отправляет готовое изображение в Telegram.

### Фото + подпись → видео

Отправьте одну фотографию и добавьте caption/подпись с описанием происходящего в сцене.

Бот:

1. сохраняет фото во временную папку конкретной задачи;
2. берёт `GoonMachine_I2V_5090_SAFE.json`;
3. указывает workflow на эту папку;
4. напрямую подставляет caption в LTX positive video prompt;
5. запускает ComfyUI;
6. ждёт готовое видео;
7. отправляет MP4 в ответ.

Задачи Telegram выполняются последовательно одной очередью, чтобы параллельные запросы не конфликтовали за VRAM и input/output.

### Если бот молчит

Проверьте:

```text
ENABLE_TELEGRAM_BOT=1
TELEGRAM_BOT_TOKEN=...
```

Отправьте:

```text
/status
```

Если два Vast-инстанса одновременно используют один bot token — оставьте только один.

---

## 11. Где лежат результаты

На инстансе:

```text
/workspace/output
```

Telegram дополнительно временно сохраняет скачанные из ComfyUI результаты в:

```text
/workspace/telegram-bot/downloads
```

Перед Destroy обязательно скачайте нужные материалы.

---

## 12. Завершение работы

Когда закончили:

1. скачайте нужные изображения и видео;
2. убедитесь, что ничего ценного не осталось только в `/workspace`;
3. Vast.ai → Instances → **Destroy**.

После Destroy текущий ephemeral storage исчезнет.

В следующий раз:

```text
My Template → выбрать новый RTX 5090 → Rent → дождаться READY → работать
```

Ничего заново настраивать не требуется, кроме естественного повторного скачивания моделей на новый хост.

---

## 13. Частые проблемы

### `pull access denied` / Docker image не скачивается

Причина обычно в приватном GHCR package.

Решение для первого запуска: сделайте package Public или настройте в Vast credentials для private registry.

### Кнопка Open есть, но ComfyUI не открывается

Подождите завершения bootstrap и посмотрите Instance Logs. Большие модели ещё могут скачиваться.

Проверьте, что Template содержит:

```text
1111 TCP
8188 TCP
OPEN_BUTTON_PORT=1111
PORTAL_CONFIG=localhost:1111:11111:/:Instance Portal|localhost:8188:18188:/:ComfyUI
```

### Недостаточно диска

Используйте 200 GB. Если включите дополнительные тяжёлые post-processing модели, может понадобиться больше.

### Civitai/Hugging Face возвращают 401/403/429

Добавьте/проверьте:

```text
CIVITAI_TOKEN
HF_TOKEN
```

### Telegram: ошибка `/workflow/convert`

Проект устанавливает `comfyui-workflow-to-api-converter-endpoint` внутрь Docker image. Если endpoint отсутствует, убедитесь, что запущен image, собранный из последней версии проекта, и пересоберите GitHub Action.

### OOM на RTX 5090

Начните с SAFE workflow, уменьшите resolution/duration и не включайте тяжёлый optional post-processing сразу.

`COMFY_RESERVE_VRAM=2` оставляет резерв VRAM для стабильности.

### Telegram не может прислать большой MP4

Бот сначала пытается отправить как video, затем как document. Если Telegram всё равно отклоняет файл, он остаётся в `/workspace/output` и доступен через веб-интерфейс ComfyUI до Destroy.

---

## 14. Важные официальные страницы Vast.ai

- Templates / Introduction: https://docs.vast.ai/guides/templates/introduction
- Creating Templates: https://docs.vast.ai/guides/templates/creating-templates
- Template Settings: https://docs.vast.ai/guides/templates/template-settings
- Advanced Setup / custom images / PORTAL_CONFIG: https://docs.vast.ai/guides/templates/advanced-setup
- Docker Execution Environment: https://docs.vast.ai/guides/instances/docker-environment
- Networking & Ports: https://docs.vast.ai/guides/instances/connect/networking

---

## 15. Быстрый чек-лист первого запуска

- [ ] GitHub Actions собрал `ghcr.io/<USER>/ltx23-goon-vast:5090`
- [ ] GHCR package доступен Vast
- [ ] Создан Private Vast Template
- [ ] Launch Mode = docker ENTRYPOINT / Entrypoint
- [ ] Disk = 200 GB
- [ ] Ports = 1111 TCP + 8188 TCP
- [ ] `PORTAL_CONFIG` задан
- [ ] При необходимости добавлены `HF_TOKEN` и `CIVITAI_TOKEN`
- [ ] При необходимости `ENABLE_TELEGRAM_BOT=1`
- [ ] `TELEGRAM_BOT_TOKEN` задан в Account Environment Variables
- [ ] Арендован RTX 5090 32 GB + >=64 GB RAM
- [ ] В логах появился `[comfyui] READY`
- [ ] Open → Instance Portal → ComfyUI работает
- [ ] `/status` у Telegram-бота отвечает `READY`
- [ ] Перед Destroy результаты скачаны
