# LTX 2.3 / 10Eros / Goon Machine — one-click Vast.ai template for RTX 5090

Готовый исходный проект для сценария:

**выбрать Vast Template → арендовать RTX 5090 → дождаться READY → Open → ComfyUI → генерация → скачать результат → Destroy.**

Ручной SSH, `git clone`, установка ComfyUI и моделей на каждом новом хосте не нужны.

## Что входит

- ComfyUI, pinned на `v0.24.0` для воспроизводимой сборки.
- LTX 2.3 / **10Eros v1.4 FP8 mixed**.
- DMD LoRA и официальный `10Eros_10SNodes_I2V_Basic_DMD_V5` workflow.
- Пользовательский **Goon Machine v0.8** workflow — оригинал сохранён без изменений.
- Готовые Linux/Vast/RTX 5090 варианты Goon Machine.
- Krea2 T2I stage + public fallback checkpoint.
- LTX audio/video VAE, text encoders, spatial upscaler, Krea/LTX LoRA pack, VHS/FFmpeg.
- Локальный Ollama и модель, которую ожидает Goon workflow.
- Vast Instance Portal: bootstrap page и затем ComfyUI на том же app-link.
- Hardware preflight для ~32 GB VRAM / ~64 GB RAM / диска.
- Автоматическое скачивание весов только при старте арендованного инстанса — веса не запекаются в Docker image.
- Опциональный Telegram-бот: текст → изображение, фото + подпись → видео.
- Автоматический workflow→API converter для запуска сложного ComfyUI workflow через Telegram.

## Goon Machine: какие версии лежат в проекте

`workflows/GoonMachine_original_v08.json` — точная копия переданного JSON.

`GoonMachine_T2I_5090_LUSTIFY_SAFE.json` — только Krea T2I-картинка, без запуска LTX-video стадии; используется Telegram text→image.

`GoonMachine_T2I2V_5090_LUSTIFY_SAFE.json` — T2I через Lustify V10 + LTX, SageAttention/RTX VSR обходятся для более предсказуемого первого запуска на Blackwell.

`GoonMachine_T2I2V_5090_FALLBACK_SAFE.json` — полностью публичный Krea fallback, если Lustify V10 недоступен.

`GoonMachine_I2V_5090_SAFE.json` — пропускает Krea T2I, берёт изображение из `/workspace/input` и запускает LTX video stage.

`GoonMachine_T2I2V_5090_LUSTIFY_FULL.json` — максимально близкий к исходному workflow вариант с активными SageAttention и RTX VSR.

Во время старта создаются также **AUTO**-варианты: если exact Lustify V10 скачался, используется он; если нет — автоматически выбирается public Krea fallback. Если exact 10Eros LoRA недоступен, эта LoRA отключается, а сам 10Eros checkpoint остаётся рабочим. Exact `ltx23-ultimatedt-NSFW-sulphured_audio_final_k3nk.safetensors` также включается только если этот конкретный LoRA-файл присутствует; похожий merge/checkpoint намеренно не подменяется вместо LoRA. Если у вас появится прямой URL exact-файла, его можно один раз добавить как секрет `ULTIMATE_DT_URL`; без него эта конкретная LoRA автоматически отключается.

## Важный момент по Lustify V10

На момент сборки проекта (08.08.2026) автор указывает open release для Lustify V10 (Krea 2) на 10.08.2026. Поэтому downloader сначала пытается получить exact V10 через Civitai API/`CIVITAI_TOKEN`, а при недоступности сохраняет полностью рабочий fallback workflow на `krea2TurboUncensored_v1.safetensors`. После открытого релиза exact workflow должен подхватываться автоматически при новом Rent без изменения Docker image.

## Одноразовая подготовка шаблона

### 1. Создать GitHub repo

Распакуйте этот проект в новый репозиторий, например `ltx23-goon-vast`, и push в `main`.

GitHub Actions из `.github/workflows/publish-ghcr.yml` автоматически соберёт:

`ghcr.io/<ВАШ_GITHUB>/ltx23-goon-vast:5090`

Если package оставите private, добавьте GHCR credentials в Vast Registry. Если сделаете package public — credentials не нужны, но содержимое image будет общедоступно.

### 2. Создать Vast Template

Все значения уже выписаны в `vast/TEMPLATE.md`.

Основные параметры: `docker ENTRYPOINT`, 200 GB disk, TCP 1111 и 8188, `OPEN_BUTTON_PORT=1111`, `OPEN_BUTTON_TOKEN=1`, `PORTAL_CONFIG=localhost:1111:11111:/:Instance Portal|localhost:8188:18188:/:ComfyUI`.

### 3. Секреты

В Account Environment Variables Vast можно добавить:

```text
CIVITAI_TOKEN=...
HF_TOKEN=...
```

Токены не надо коммитить в GitHub и не надо вписывать в публичный template.

## Что происходит на каждом новом Vast-хосте

Контейнер запускается штатным Vast ENTRYPOINT, поэтому остаётся Instance Portal. Затем `docker/start.sh`:

1. создаёт `/workspace/models`, `/workspace/input`, `/workspace/output`, `/workspace/user`;
2. показывает status page в Portal;
3. проверяет GPU/VRAM/RAM/disk и CUDA/PyTorch;
4. запускает Ollama и скачивает требуемую LLM;
5. скачивает веса Hugging Face/Civitai;
6. создаёт symlink aliases без дублирования 29 GB 10Eros checkpoint;
7. готовит AUTO workflows;
8. заменяет bootstrap page на ComfyUI.

В `/workspace/download-report.json` сохраняется, какие exact/fallback assets были использованы.

## Модели

Основные модели скачиваются из исходных репозиториев TenStrip, Lightricks, Kijai, Comfy-Org, Kutches, Sentinel7 и других источников, указанных в `config/models.json`. Никаких больших весов в этом ZIP и Docker image нет.

Особенность 10Eros: один файл v1.4 FP8 используется через symlink и как standalone checkpoint, и как LTX diffusion model для Goon Machine — на диске он не хранится дважды.

Опциональные тяжёлые post-processing модели SeedVR2/DepthAnything не скачиваются по умолчанию, потому что соответствующие ветки исходного workflow отключены. Их node packs установлены, поэтому их можно включить позднее и добавить загрузку при необходимости.


## Telegram-бот

Telegram запускается вместе с ComfyUI, если задать:

```text
ENABLE_TELEGRAM_BOT=1
TELEGRAM_BOT_TOKEN=<token>
```

Опционально ограничьте доступ:

```text
TELEGRAM_ALLOWED_USER_IDS=123456789
```

Команды: `/start`, `/id`, `/status`. Текстовое сообщение запускает image-only Krea workflow; фото с подписью запускает I2V workflow. Для API automation проект устанавливает `comfyui-workflow-to-api-converter-endpoint`, потому что обычный UI workflow JSON и формат `/prompt` ComfyUI различаются.

Подробная инструкция: `vast/START_GUIDE_RU.md`.

## Папки во время работы

```text
/workspace/input                 исходники для I2V
/workspace/output                изображения и MP4
/workspace/models                модели
/workspace/user/default/workflows готовые workflow
/workspace/.cache                HF/Ollama cache
/var/log/portal/ltx-suite.log    bootstrap + runtime log
/workspace/download-report.json  отчёт exact/fallback downloads
```

## Первый запуск

У первого запуска конкретного ephemeral-инстанса есть естественная задержка: нужно скачать десятки гигабайт весов. Никаких команд выполнять не нужно — прогресс виден через ComfyUI app-link в Instance Portal. После Destroy данные удаляются, как и требуется для схемы «пару часов поработал и забыл».

## Проверка проекта

Локально без GPU можно выполнить:

```bash
python scripts/validate_project.py
```

Она проверяет JSON, Python syntax, Bash syntax и ключевые патчи workflow. Полный inference-test требует реального NVIDIA GPU и запуска собранного Docker image; в текущей среде сборки этот этап физически не выполняется.

## Обновление

Для обновления custom nodes или ComfyUI измените Dockerfile/config и запустите GitHub Action заново. Tag `5090` будет указывать на новую сборку, а следующий Vast Rent получит её автоматически.
