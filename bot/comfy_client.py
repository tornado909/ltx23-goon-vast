from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiohttp


@dataclass
class GeneratedFile:
    filename: str
    subfolder: str = ""
    type: str = "output"

    @property
    def suffix(self) -> str:
        return Path(self.filename).suffix.lower()


class ComfyClient:
    def __init__(self, api_base: str):
        self.api_base = api_base.rstrip("/")
        self.client_id = str(uuid.uuid4())

    async def ping(self) -> bool:
        timeout = aiohttp.ClientTimeout(total=10)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{self.api_base}/system_stats") as resp:
                    return resp.status < 400
        except Exception:
            return False

    async def convert_workflow(self, workflow: dict[str, Any]) -> dict[str, Any]:
        """Convert normal ComfyUI workflow JSON into /prompt API format."""
        timeout = aiohttp.ClientTimeout(total=120)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(f"{self.api_base}/workflow/convert", json=workflow) as resp:
                text = await resp.text()
                if resp.status >= 400:
                    raise RuntimeError(f"Workflow converter error {resp.status}: {text[:1500]}")
                data = json.loads(text)
                if not isinstance(data, dict) or not data:
                    raise RuntimeError("Workflow converter returned an empty/invalid prompt")
                return data

    async def queue_api_prompt(self, api_prompt: dict[str, Any], workflow: dict[str, Any] | None = None) -> str:
        payload: dict[str, Any] = {"prompt": api_prompt, "client_id": self.client_id}
        if workflow is not None:
            payload["extra_data"] = {"extra_pnginfo": {"workflow": workflow}}
        timeout = aiohttp.ClientTimeout(total=120)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(f"{self.api_base}/prompt", json=payload) as resp:
                text = await resp.text()
                if resp.status >= 400:
                    raise RuntimeError(f"ComfyUI queue error {resp.status}: {text[:2000]}")
                data = json.loads(text)
                if data.get("node_errors"):
                    raise RuntimeError(f"ComfyUI validation errors: {json.dumps(data['node_errors'], ensure_ascii=False)[:2500]}")
                prompt_id = data.get("prompt_id")
                if not prompt_id:
                    raise RuntimeError(f"ComfyUI did not return prompt_id: {data}")
                return prompt_id

    async def queue_workflow(self, workflow: dict[str, Any]) -> str:
        api_prompt = await self.convert_workflow(workflow)
        return await self.queue_api_prompt(api_prompt, workflow=workflow)

    async def wait_for_history(self, prompt_id: str, timeout_seconds: int = 7200, poll_interval: float = 2.5) -> dict[str, Any]:
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            while True:
                if asyncio.get_running_loop().time() > deadline:
                    raise TimeoutError(f"Timed out waiting for prompt {prompt_id}")
                async with session.get(f"{self.api_base}/history/{prompt_id}") as resp:
                    text = await resp.text()
                    if resp.status >= 400:
                        raise RuntimeError(f"ComfyUI history error {resp.status}: {text[:1500]}")
                    data = json.loads(text) if text else {}
                entry = data.get(prompt_id) if isinstance(data, dict) and prompt_id in data else None
                if entry and isinstance(entry, dict):
                    status = ((entry.get("status") or {}).get("status_str") or "").lower()
                    if status == "error":
                        messages = (entry.get("status") or {}).get("messages") or []
                        raise RuntimeError(f"ComfyUI prompt failed: {messages}")
                    if entry.get("outputs"):
                        return entry
                await asyncio.sleep(poll_interval)

    @staticmethod
    def extract_generated_files(history_entry: dict[str, Any]) -> list[GeneratedFile]:
        outputs = history_entry.get("outputs") or {}
        found: list[GeneratedFile] = []
        seen: set[tuple[str, str, str]] = set()
        for node_data in outputs.values():
            if not isinstance(node_data, dict):
                continue
            # Core nodes generally use images; VHS commonly uses gifs even for MP4.
            for bucket in ("images", "gifs", "videos"):
                items = node_data.get(bucket) or []
                if not isinstance(items, list):
                    continue
                for item in items:
                    if not isinstance(item, dict) or not item.get("filename"):
                        continue
                    gf = GeneratedFile(
                        filename=item["filename"],
                        subfolder=item.get("subfolder", ""),
                        type=item.get("type", "output"),
                    )
                    key = (gf.filename, gf.subfolder, gf.type)
                    if key not in seen:
                        seen.add(key)
                        found.append(gf)
        return found

    async def download_generated_file(self, file: GeneratedFile, target_dir: Path) -> Path:
        target_dir.mkdir(parents=True, exist_ok=True)
        params = {"filename": file.filename, "subfolder": file.subfolder, "type": file.type}
        timeout = aiohttp.ClientTimeout(total=3600)
        out = target_dir / Path(file.filename).name
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{self.api_base}/view", params=params) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    raise RuntimeError(f"Download error {resp.status}: {text[:1500]}")
                out.write_bytes(await resp.read())
        return out


def load_workflow(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _node_by_id(workflow: dict[str, Any], node_id: int) -> dict[str, Any]:
    for node in workflow.get("nodes", []):
        if node.get("id") == node_id:
            return node
    raise KeyError(f"Node {node_id} not found")


def disconnect_input(workflow: dict[str, Any], node_id: int, input_name: str) -> None:
    node = _node_by_id(workflow, node_id)
    link_ids: set[int] = set()
    for inp in node.get("inputs") or []:
        if inp.get("name") == input_name and inp.get("link") is not None:
            try:
                link_ids.add(int(inp["link"]))
            except Exception:
                pass
            inp["link"] = None
    if link_ids and isinstance(workflow.get("links"), list):
        workflow["links"] = [link for link in workflow["links"] if not (isinstance(link, list) and link and link[0] in link_ids)]


def set_text_widget(workflow: dict[str, Any], node_id: int, text: str, widget_index: int = 0) -> None:
    node = _node_by_id(workflow, node_id)
    values = node.get("widgets_values")
    if not isinstance(values, list):
        raise RuntimeError(f"Node {node_id} has no list widgets_values")
    while len(values) <= widget_index:
        values.append("")
    values[widget_index] = text


def patch_direct_image_prompt(workflow: dict[str, Any], prompt_text: str) -> dict[str, Any]:
    # Krea2 positive prompt node. Bypass its Ollama-generated upstream text for Telegram jobs.
    disconnect_input(workflow, 71, "text")
    set_text_widget(workflow, 71, prompt_text, 0)
    return workflow


def patch_direct_video_prompt(workflow: dict[str, Any], prompt_text: str) -> dict[str, Any]:
    # LTX Positive Video CLIPTextEncode. Direct user scene prompt, no intermediate Ollama rewrite.
    disconnect_input(workflow, 2924, "text")
    set_text_widget(workflow, 2924, prompt_text, 0)
    return workflow


def patch_input_directory(workflow: dict[str, Any], input_dir: Path, node_id: int = 3103) -> dict[str, Any]:
    node = _node_by_id(workflow, node_id)
    widgets = node.get("widgets_values")
    if isinstance(widgets, dict):
        widgets["directory"] = str(input_dir)
        vp = widgets.get("videopreview")
        if isinstance(vp, dict) and isinstance(vp.get("params"), dict):
            vp["params"]["filename"] = str(input_dir)
    return workflow


def select_best_file(files: list[GeneratedFile], want_video: bool) -> GeneratedFile | None:
    video_exts = {".mp4", ".webm", ".mov", ".mkv", ".gif"}
    image_exts = {".png", ".jpg", ".jpeg", ".webp"}
    preferred = video_exts if want_video else image_exts
    for f in reversed(files):
        if f.suffix in preferred:
            return f
    return files[-1] if files else None
