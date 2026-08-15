from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import FSInputFile, Message

from bot.comfy_client import (
    ComfyClient,
    load_workflow,
    patch_direct_image_prompt,
    patch_direct_video_prompt,
    patch_input_directory,
    select_best_file,
)

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(message)s")
log = logging.getLogger("telegram-bot")

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
if not TOKEN:
    raise SystemExit("TELEGRAM_BOT_TOKEN is required when ENABLE_TELEGRAM_BOT=1")

COMFY_API = os.environ.get("COMFYUI_API_BASE", "http://127.0.0.1:18188")
WORKFLOWS_DIR = Path(os.environ.get("COMFY_WORKFLOWS_DIR", "/workspace/user/default/workflows"))
BOT_DATA_DIR = Path(os.environ.get("TELEGRAM_DATA_DIR", "/workspace/telegram-bot"))
DOWNLOAD_DIR = BOT_DATA_DIR / "downloads"
INPUT_ROOT = Path(os.environ.get("TELEGRAM_INPUT_ROOT", "/workspace/telegram-input"))
TEXT_WORKFLOW = os.environ.get("TELEGRAM_TEXT_WORKFLOW", "GoonMachine_T2I_5090_AUTO_SAFE.json")
PHOTO_WORKFLOW = os.environ.get("TELEGRAM_PHOTO_WORKFLOW", "GoonMachine_I2V_5090_SAFE.json")
BLOCK_NSFW_PHOTO = os.environ.get("TELEGRAM_BLOCK_NSFW_PHOTO", "1").lower() not in {"0", "false", "no"}
ALLOWED = {int(x) for x in os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "").replace(" ", "").split(",") if x}
QUEUE_LOCK = asyncio.Lock()

# Safeguard for photo-to-video with a real-person image.
EXPLICIT_RE = re.compile(r"\b(nsfw|sex|sexual|nude|naked|porn|blowjob|deepthroat|vagina|penis|cum|anal|oral|erotic|xxx)\b", re.I)

bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
client = ComfyClient(COMFY_API)


def is_allowed(message: Message) -> bool:
    if not ALLOWED:
        return True
    return bool(message.from_user and message.from_user.id in ALLOWED)


def contains_explicit(text: str) -> bool:
    return bool(EXPLICIT_RE.search(text or ""))


async def send_result(message: Message, path: Path, is_video: bool) -> None:
    try:
        if is_video:
            await message.answer_video(FSInputFile(path), caption=f"Готово: <code>{path.name}</code>")
        else:
            await message.answer_photo(FSInputFile(path), caption=f"Готово: <code>{path.name}</code>")
    except Exception:
        # If Telegram does not accept the media as photo/video (codec/size/etc.), try as a document.
        await message.answer_document(FSInputFile(path), caption=f"Готово: <code>{path.name}</code>")


@dp.message(CommandStart())
async def start_handler(message: Message) -> None:
    if not is_allowed(message):
        await message.answer("Доступ к боту не разрешён.")
        return
    uid = message.from_user.id if message.from_user else 0
    await message.answer(
        "Готов к работе.\n\n"
        "• <b>Текст</b> → картинка.\n"
        "• <b>Фото + подпись</b> → видео из фотографии по описанию сцены.\n"
        "• /id → показать ваш Telegram user ID.\n\n"
        f"Ваш ID: <code>{uid}</code>"
    )


@dp.message(Command("id"))
async def id_handler(message: Message) -> None:
    uid = message.from_user.id if message.from_user else 0
    await message.answer(f"Ваш Telegram user ID: <code>{uid}</code>")


@dp.message(Command("status"))
async def status_handler(message: Message) -> None:
    if not is_allowed(message):
        await message.answer("Доступ к боту не разрешён.")
        return
    ok = await client.ping()
    await message.answer("ComfyUI: <b>READY</b>" if ok else "ComfyUI пока не отвечает.")


@dp.message(F.photo)
async def photo_handler(message: Message) -> None:
    if not is_allowed(message):
        await message.answer("Доступ к боту не разрешён.")
        return
    prompt = (message.caption or "").strip()
    if not prompt:
        await message.answer("Для видео отправьте фото <b>с подписью</b>, описывающей происходящее в сцене.")
        return
    if BLOCK_NSFW_PHOTO and contains_explicit(prompt):
        await message.answer("Сексуализированную генерацию по фотографии реального человека этот канал не запускает. Используйте нейтральное описание сцены.")
        return

    status = await message.answer("Фото получено. Жду свободный GPU-слот…")
    async with QUEUE_LOCK:
        job_id = f"tg_{message.chat.id}_{message.message_id}"
        job_input = INPUT_ROOT / job_id
        try:
            if job_input.exists():
                shutil.rmtree(job_input)
            job_input.mkdir(parents=True, exist_ok=True)

            tg_file = await bot.get_file(message.photo[-1].file_id)
            local_path = job_input / "input.jpg"
            await bot.download_file(tg_file.file_path, destination=local_path)

            workflow = load_workflow(WORKFLOWS_DIR / PHOTO_WORKFLOW)
            patch_input_directory(workflow, job_input)
            patch_direct_video_prompt(workflow, prompt)

            await status.edit_text("Генерация видео запущена…")
            prompt_id = await client.queue_workflow(workflow)
            history = await client.wait_for_history(prompt_id)
            files = client.extract_generated_files(history)
            chosen = select_best_file(files, want_video=True)
            if not chosen:
                raise RuntimeError("ComfyUI завершил задачу, но видеофайл не найден в history outputs")
            out = await client.download_generated_file(chosen, DOWNLOAD_DIR / prompt_id)
            await status.edit_text("Видео готово. Отправляю…")
            await send_result(message, out, is_video=True)
            await status.delete()
        except Exception as exc:
            log.exception("photo job failed")
            await status.edit_text(f"Ошибка генерации: <code>{str(exc)[:3500]}</code>")
        finally:
            shutil.rmtree(job_input, ignore_errors=True)


@dp.message(F.text)
async def text_handler(message: Message) -> None:
    if not is_allowed(message):
        await message.answer("Доступ к боту не разрешён.")
        return
    prompt = (message.text or "").strip()
    if not prompt or prompt.startswith("/"):
        return

    status = await message.answer("Запрос получен. Жду свободный GPU-слот…")
    async with QUEUE_LOCK:
        try:
            workflow = load_workflow(WORKFLOWS_DIR / TEXT_WORKFLOW)
            patch_direct_image_prompt(workflow, prompt)
            await status.edit_text("Генерация картинки запущена…")
            prompt_id = await client.queue_workflow(workflow)
            history = await client.wait_for_history(prompt_id)
            files = client.extract_generated_files(history)
            chosen = select_best_file(files, want_video=False)
            if not chosen:
                raise RuntimeError("ComfyUI завершил задачу, но изображение не найдено в history outputs")
            out = await client.download_generated_file(chosen, DOWNLOAD_DIR / prompt_id)
            await status.edit_text("Картинка готова. Отправляю…")
            await send_result(message, out, is_video=False)
            await status.delete()
        except Exception as exc:
            log.exception("text job failed")
            await status.edit_text(f"Ошибка генерации: <code>{str(exc)[:3500]}</code>")


async def main() -> None:
    BOT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    INPUT_ROOT.mkdir(parents=True, exist_ok=True)
    log.info("Telegram bot started; ComfyUI=%s; workflows=%s", COMFY_API, WORKFLOWS_DIR)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
