# Vast.ai Template — LTX 2.3 / 10Eros / Goon Machine + Telegram (RTX 5090)

Полная пошаговая инструкция: **`vast/START_GUIDE_RU.md`**.

После того как GitHub Actions соберёт image:

```text
ghcr.io/<USER>/ltx23-goon-vast:5090
```

создайте один Private Template в Vast.ai.

## Поля New Template

| Поле | Значение |
|---|---|
| Image visibility | Public, если GHCR package public; Private, если настроили credentials |
| Registry | GitHub Container Registry / ghcr.io |
| Docker Image | `ghcr.io/<USER>/ltx23-goon-vast` |
| Tag | `5090` |
| Template Name | `LTX2.3 10Eros + Goon + Telegram - RTX 5090` |
| Launch Mode | **docker ENTRYPOINT / Entrypoint** |
| Disk Space | **200 GB** |
| Add local volume | выключено |
| Port 1 | `1111` TCP |
| Port 2 | `8188` TCP |
| Private template | включено |

## Несекретные Environment Variables

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

Если Telegram нужен:

```text
ENABLE_TELEGRAM_BOT=1
```

Секреты лучше хранить в **Vast Account → Environment Variables**, а не в Template:

```text
TELEGRAM_BOT_TOKEN=...
CIVITAI_TOKEN=...
HF_TOKEN=...
```

Опционально:

```text
TELEGRAM_ALLOWED_USER_IDS=123456789
```

## После Rent

1. Vast запускает Docker image.
2. `Open` ведёт в Instance Portal.
3. Автоматически проверяются RTX/VRAM/RAM/disk, запускается Ollama, скачиваются модели и готовятся workflow.
4. Запускается ComfyUI и workflow converter.
5. Если Telegram включён — запускается polling worker.
6. В логах появляется `[comfyui] READY`.
7. Instance Portal → **ComfyUI** открывает веб-интерфейс.

## Рекомендуемый хост

**RTX 5090, 32 GB VRAM, 64+ GB RAM, 200+ GB disk, CUDA 12.8+, reliability желательно 99%+**.

Проект рассчитан на `Rent → работа → скачать output → Destroy`. Persistent volume не требуется.
