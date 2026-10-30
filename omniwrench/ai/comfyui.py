"""ComfyUI als kostenloser, lokaler Anbieter für Bilder, Musik und Video. Qt-frei.

ComfyUI läuft als eigenes Programm (Windows: ComfyUI Desktop, Port 8000; manuell/portable: Port 8188). OmniWrench
schickt fertige Workflows im API-Format an POST /prompt, wartet über /history/<id> und holt die Dateien über /view.
Welche Modelle es gibt, steht in PRESETS; die Dateien lädt download() direkt in den Modellordner von ComfyUI
(ermittelt über /internal/folder_paths, sonst vom Benutzer gewählt). Jede andere Checkpoint-Datei lässt sich in
Pixelizer als „ckpt:<datei>“ eintragen.
"""

from __future__ import annotations

import os
import random
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Callable

from . import http as aihttp
from .http import AIError, Cancelled

DEFAULT_URL = "http://127.0.0.1:8188"
DESKTOP_URL = "http://127.0.0.1:8000"
WINGET_ID = "Comfy.ComfyUI-Desktop"
DOWNLOAD_PAGE = "https://www.comfy.org/download"
LINUX_COMMAND = ("git clone https://github.com/comfyanonymous/ComfyUI ~/ComfyUI && cd ~/ComfyUI && "
                 "python3 -m venv venv && venv/bin/pip install torch torchvision torchaudio && "
                 "venv/bin/pip install -r requirements.txt && venv/bin/python main.py")
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
HF = "https://huggingface.co/"

# Modell -> Art, Dateien (Unterordner, Datei, Adresse, GB), Grafikspeicher in GB (Empfehlung)
PRESETS: dict[str, dict] = {
    "sdxl-turbo": {"kind": "image", "vram": 6, "files": [
        ("checkpoints", "sd_xl_turbo_1.0_fp16.safetensors",
         HF + "stabilityai/sdxl-turbo/resolve/main/sd_xl_turbo_1.0_fp16.safetensors", 6.9)]},
    "flux-schnell": {"kind": "image", "vram": 12, "files": [
        ("checkpoints", "flux1-schnell-fp8.safetensors",
         HF + "Comfy-Org/flux1-schnell/resolve/main/flux1-schnell-fp8.safetensors", 17.2)]},
    "ltx-video": {"kind": "video", "vram": 8, "files": [
        ("checkpoints", "ltx-video-2b-v0.9.5.safetensors",
         HF + "Lightricks/LTX-Video/resolve/main/ltx-video-2b-v0.9.5.safetensors", 6.3),
        ("text_encoders", "t5xxl_fp8_e4m3fn.safetensors",
         HF + "comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors", 4.9)]},
    "ace-step": {"kind": "music", "vram": 8, "files": [
        ("checkpoints", "ace_step_v1_3.5b.safetensors",
         HF + "Comfy-Org/ACE-Step_ComfyUI_repackaged/resolve/main/all_in_one/ace_step_v1_3.5b.safetensors", 7.7)]},
}
NEEDED_NODES = {"image": ("CheckpointLoaderSimple", "KSampler", "SaveImage"),
                "video": ("LTXVConditioning", "EmptyLTXVLatentVideo", "LTXVScheduler", "CreateVideo", "SaveVideo"),
                "music": ("TextEncodeAceStepAudio", "EmptyAceStepLatentAudio", "VAEDecodeAudio", "SaveAudioMP3")}
VIDEO_NEGATIVE = ("low quality, worst quality, deformed, distorted, disfigured, motion smear, motion artifacts, "
                  "fused fingers, bad anatomy, weird hand, ugly")
_SDXL_TURBO_SIZE = {"1:1": (512, 512), "16:9": (768, 432), "9:16": (432, 768), "4:3": (640, 480), "3:4": (480, 640)}
_FLUX_SIZE = {"1:1": (1024, 1024), "16:9": (1344, 768), "9:16": (768, 1344), "4:3": (1152, 896), "3:4": (896, 1152)}
_VIDEO_SIZE = {"16:9": (832, 480), "9:16": (480, 832), "1:1": (640, 640)}
FPS = 24


def models_for(kind: str) -> list[str]:
    return [name for name, p in PRESETS.items() if p["kind"] == kind]


def size_gb(name: str) -> float:
    return round(sum(f[3] for f in PRESETS[name]["files"]), 1)


# ------------------------------------------------------------------ Dienst
def root_url(base_url: str = "") -> str:
    return (base_url or DEFAULT_URL).rstrip("/")


def is_local(base_url: str = "") -> bool:
    host = urllib.parse.urlparse(root_url(base_url)).hostname or ""
    return host in ("localhost", "127.0.0.1", "::1")


def _json(base_url: str, path: str, body: dict | None = None, timeout: float = 30):
    return aihttp.json_request("POST" if body is not None else "GET", root_url(base_url) + path, {}, body,
                               timeout=timeout)


def version(base_url: str = "") -> str:
    """ComfyUI-Version oder "" (läuft nicht)."""
    try:
        stats = _json(base_url, "/system_stats", timeout=3)
    except (AIError, OSError, ValueError):
        return ""
    return str((stats.get("system") or {}).get("comfyui_version") or "?")


def find_server(base_url: str = "") -> str:
    """Adresse eines laufenden ComfyUI (gewünschte, dann 8188, dann Desktop 8000) oder ""."""
    for url in dict.fromkeys([root_url(base_url), DEFAULT_URL, DESKTOP_URL]):
        if version(url):
            return url
    return ""


def folders(base_url: str = "") -> dict[str, list[str]]:
    """Modellordner je Art laut ComfyUI (nur neuere Versionen)."""
    try:
        data = _json(base_url, "/internal/folder_paths", timeout=5)
    except (AIError, OSError, ValueError):
        return {}
    out = {}
    for key, value in (data or {}).items():
        paths = value[0] if isinstance(value, list) and value and isinstance(value[0], list) else value
        out[key] = [str(p) for p in paths] if isinstance(paths, list) else []
    return out


def guess_models_dir(base_url: str = "") -> str:
    """Modellordner (…/models): von ComfyUI gemeldet, sonst üblicher Ort von Desktop / git-Installation."""
    for path in (folders(base_url).get("checkpoints") or []):
        p = Path(path)
        if p.name == "checkpoints" and p.parent.is_dir():
            return str(p.parent)
    home = Path.home()
    for cand in (home / "Documents" / "ComfyUI" / "models", home / "ComfyUI" / "models",
                 home / "ComfyUI_windows_portable" / "ComfyUI" / "models"):
        if cand.is_dir():
            return str(cand)
    return ""


def available(base_url: str, folder: str) -> list[str]:
    """Dateinamen, die ComfyUI in einem Modellordner sieht."""
    try:
        data = _json(base_url, "/models/" + folder, timeout=10)
    except AIError as err:
        if err.status == 404:
            return []
        raise
    return [str(x) for x in data] if isinstance(data, list) else []


def missing_files(name: str, base_url: str = "", models_dir: str = "") -> list[tuple[str, str, str, float]]:
    """Fehlende Dateien eines Modells (über ComfyUI, sonst im Modellordner geprüft)."""
    out, seen = [], {}
    for folder, file, url, gb in PRESETS[name]["files"]:
        if base_url:
            if folder not in seen:
                try:
                    seen[folder] = set(available(base_url, folder))
                    if folder == "text_encoders":
                        seen[folder] |= set(available(base_url, "clip"))
                except (AIError, OSError):
                    seen[folder] = None
            if seen[folder] is not None:
                if file not in seen[folder]:
                    out.append((folder, file, url, gb))
                continue
        if not (models_dir and (Path(models_dir) / folder / file).is_file()):
            out.append((folder, file, url, gb))
    return out


# ------------------------------------------------------------------ Installation
def executable() -> str:
    """ComfyUI Desktop (Windows) bzw. main.py einer git-Installation, sonst ""."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", ""))
        for cand in (base / "Programs" / "@comfyorgcomfyui-electron" / "ComfyUI.exe",
                     base / "Programs" / "ComfyUI" / "ComfyUI.exe"):
            if cand.is_file():
                return str(cand)
    main = Path.home() / "ComfyUI" / "main.py"
    return str(main) if main.is_file() else ""


def install_windows(progress: Callable[[str], None] | None = None) -> bool:
    """ComfyUI Desktop über winget (für den Benutzer). False = kein winget, Download-Seite öffnen."""
    if not shutil.which("winget"):
        return False
    proc = subprocess.Popen(["winget", "install", "-e", "--id", WINGET_ID, "--silent", "--accept-package-agreements",
                             "--accept-source-agreements", "--disable-interactivity"], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, errors="replace", creationflags=NO_WINDOW)
    for line in proc.stdout or []:
        line = line.strip().strip("\r")
        if line and progress:
            progress(line[-160:])
    code = proc.wait()
    if code != 0 and not executable():
        raise RuntimeError(f"winget exit code {code}")
    return True


def start(base_url: str = "", wait: float = 60.0) -> str:
    """ComfyUI starten (Desktop-App bzw. python main.py). Gibt die erreichbare Adresse zurück oder ""."""
    found = find_server(base_url)
    if found:
        return found
    exe = executable()
    if not exe:
        return ""
    if exe.endswith(".py"):
        py = Path(exe).parent / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        cmd = [str(py) if py.is_file() else (shutil.which("python3") or "python3"), exe, "--listen", "127.0.0.1",
               "--port", "8188"]
        cwd = str(Path(exe).parent)
    else:
        cmd, cwd = [exe], None
    subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                     creationflags=NO_WINDOW if exe.endswith(".py") else 0,
                     start_new_session=sys.platform != "win32")
    end = time.time() + wait
    while time.time() < end:
        found = find_server(base_url)
        if found:
            return found
        time.sleep(1)
    return ""


def download(name: str, models_dir: str, base_url: str = "", progress: Callable[[str], None] | None = None,
             stop: threading.Event | None = None) -> None:
    """Fehlende Dateien eines Modells in den Modellordner laden; abgebrochene Downloads (.part) setzen fort."""
    from omniwrench.core.net import _SSL, USER_AGENT
    for folder, file, url, gb in missing_files(name, "", models_dir):
        target = Path(models_dir) / folder / file
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_name(file + ".part")
        have = part.stat().st_size if part.exists() else 0
        headers = {"User-Agent": USER_AGENT}
        if have:
            headers["Range"] = f"bytes={have}-"
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60, context=_SSL) as resp:
            if have and resp.status != 206:          # Server kann nicht fortsetzen
                have = 0
            total = have + int(resp.headers.get("Content-Length") or 0)
            done = have
            with open(part, "ab" if have else "wb") as f:
                while chunk := resp.read(1 << 20):
                    if stop is not None and stop.is_set():
                        raise Cancelled()
                    f.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(f"{file}: {done * 100 // total if total else 0} % "
                                 f"({done / 1e9:.1f} / {total / 1e9:.1f} GB)")
        part.replace(target)


# ------------------------------------------------------------------ Workflows (API-Format)
def _seed() -> int:
    return random.randint(1, 2**48)


def image_workflow(model: str, prompt: str, negative: str = "", aspect: str = "1:1", count: int = 1) -> dict:
    if model.startswith("ckpt:"):
        ckpt = model[5:]
        xl = "xl" in ckpt.lower() or "flux" in ckpt.lower()
        w, h = _FLUX_SIZE.get(aspect, (1024, 1024)) if xl else (_SDXL_TURBO_SIZE.get(aspect, (512, 512)))
        steps, cfg, sampler, sched, latent = 25, 7.0, "dpmpp_2m", "karras", "EmptyLatentImage"
    elif model == "flux-schnell":
        ckpt = PRESETS[model]["files"][0][1]
        w, h = _FLUX_SIZE.get(aspect, (1024, 1024))
        steps, cfg, sampler, sched, latent = 4, 1.0, "euler", "simple", "EmptySD3LatentImage"
    else:
        ckpt = PRESETS["sdxl-turbo"]["files"][0][1]
        w, h = _SDXL_TURBO_SIZE.get(aspect, (512, 512))
        steps, cfg, sampler, sched, latent = 4, 1.0, "euler_ancestral", "sgm_uniform", "EmptyLatentImage"
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["1", 1]}},
        "4": {"class_type": latent, "inputs": {"width": w, "height": h, "batch_size": max(1, min(4, count))}},
        "5": {"class_type": "KSampler", "inputs": {"seed": _seed(), "steps": steps, "cfg": cfg, "sampler_name": sampler,
                                                   "scheduler": sched, "denoise": 1.0, "model": ["1", 0],
                                                   "positive": ["2", 0], "negative": ["3", 0],
                                                   "latent_image": ["4", 0]}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"filename_prefix": "OmniWrench/image", "images": ["6", 0]}},
    }


def video_frames(seconds: int) -> int:
    """LTX-Video braucht 8·n+1 Bilder."""
    secs = max(2, min(10, int(seconds or 5)))
    return round(secs * FPS / 8) * 8 + 1


def video_workflow(prompt: str, negative: str = "", aspect: str = "16:9", seconds: int = 5) -> dict:
    w, h = _VIDEO_SIZE.get(aspect, (832, 480))
    files = PRESETS["ltx-video"]["files"]
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": files[0][1]}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": files[1][1], "type": "ltxv", "device": "default"}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": negative or VIDEO_NEGATIVE, "clip": ["2", 0]}},
        "5": {"class_type": "LTXVConditioning", "inputs": {"positive": ["3", 0], "negative": ["4", 0],
                                                           "frame_rate": FPS}},
        "6": {"class_type": "EmptyLTXVLatentVideo", "inputs": {"width": w, "height": h,
                                                               "length": video_frames(seconds), "batch_size": 1}},
        "7": {"class_type": "LTXVScheduler", "inputs": {"steps": 30, "max_shift": 2.05, "base_shift": 0.95,
                                                        "stretch": True, "terminal": 0.1, "latent": ["6", 0]}},
        "8": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "9": {"class_type": "SamplerCustom", "inputs": {"add_noise": True, "noise_seed": _seed(), "cfg": 3.0,
                                                        "model": ["1", 0], "positive": ["5", 0],
                                                        "negative": ["5", 1], "sampler": ["8", 0],
                                                        "sigmas": ["7", 0], "latent_image": ["6", 0]}},
        "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["1", 2]}},
        "11": {"class_type": "CreateVideo", "inputs": {"images": ["10", 0], "fps": FPS}},
        "12": {"class_type": "SaveVideo", "inputs": {"video": ["11", 0], "filename_prefix": "OmniWrench/video",
                                                     "format": "auto", "codec": "auto"}},
    }


def music_workflow(tags: str, lyrics: str = "", seconds: int = 60, instrumental: bool = False) -> dict:
    text = "[inst]" if instrumental or not lyrics.strip() else lyrics.strip()
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": PRESETS["ace-step"]["files"][0][1]}},
        "2": {"class_type": "ModelSamplingSD3", "inputs": {"shift": 5.0, "model": ["1", 0]}},
        "3": {"class_type": "LatentOperationTonemapReinhard", "inputs": {"multiplier": 1.0}},
        "4": {"class_type": "LatentApplyOperationCFG", "inputs": {"model": ["2", 0], "operation": ["3", 0]}},
        "5": {"class_type": "TextEncodeAceStepAudio", "inputs": {"tags": tags, "lyrics": text,
                                                                  "lyrics_strength": 0.99, "clip": ["1", 1]}},
        "6": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["5", 0]}},
        "7": {"class_type": "EmptyAceStepLatentAudio", "inputs": {"seconds": max(5, min(240, int(seconds or 60))),
                                                                   "batch_size": 1}},
        "8": {"class_type": "KSampler", "inputs": {"seed": _seed(), "steps": 50, "cfg": 5.0, "sampler_name": "euler",
                                                   "scheduler": "simple", "denoise": 1.0, "model": ["4", 0],
                                                   "positive": ["5", 0], "negative": ["6", 0],
                                                   "latent_image": ["7", 0]}},
        "9": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["8", 0], "vae": ["1", 2]}},
        "10": {"class_type": "SaveAudioMP3", "inputs": {"audio": ["9", 0], "filename_prefix": "OmniWrench/music",
                                                        "quality": "V0"}},
    }


# ------------------------------------------------------------------ Erzeugen
def check_ready(base_url: str, kind: str, model: str) -> None:
    """Läuft ComfyUI, kennt es die Knoten, sind die Modelldateien da? Sonst AIError mit code comfy_*."""
    if not version(base_url):
        raise AIError(root_url(base_url), "network", code="comfy_offline")
    for node in NEEDED_NODES.get(kind, ()):
        try:
            info = _json(base_url, "/object_info/" + node, timeout=10)
        except AIError:
            info = {}
        if not info:
            raise AIError(node, "request", code="comfy_old")
    if model.startswith("ckpt:"):
        if model[5:] not in available(base_url, "checkpoints"):
            raise AIError(model[5:], "request", code="comfy_missing")
        return
    missing = missing_files(model, base_url)
    if missing:
        raise AIError(", ".join(f[1] for f in missing), "request", code="comfy_missing")


def run(base_url: str, workflow: dict, stop: threading.Event | None = None,
        progress: Callable[[str], None] | None = None, timeout: float = 1800) -> list[tuple[bytes, str]]:
    """Workflow ausführen, auf das Ergebnis warten und die Dateien holen: [(daten, dateiname)]."""
    answer = _json(base_url, "/prompt", {"prompt": workflow, "client_id": uuid.uuid4().hex}, timeout=60)
    pid = answer.get("prompt_id")
    if not pid:
        raise AIError(str(answer.get("error") or answer)[:300], "server", code="comfy_failed")
    t0 = time.time()
    while True:
        if stop is not None and stop.is_set():
            try:
                _json(base_url, "/queue", {"delete": [pid]})
                _json(base_url, "/interrupt", {})
            except (AIError, OSError):
                pass
            raise Cancelled()
        hist = (_json(base_url, "/history/" + pid, timeout=30) or {}).get(pid)
        if hist:
            status = hist.get("status") or {}
            if status.get("status_str") == "error":
                detail = ""
                for msg in status.get("messages") or []:
                    if isinstance(msg, list) and len(msg) > 1 and msg[0] == "execution_error":
                        detail = str((msg[1] or {}).get("exception_message") or "").strip()
                raise AIError(detail[:300] or "error", "server", code="comfy_failed")
            if status.get("completed", True) and hist.get("outputs") is not None:
                return [_fetch(base_url, item) for item in _files(hist["outputs"])]
        if time.time() - t0 > timeout:
            raise AIError("timeout", "server", code="comfy_failed")
        if progress:
            progress(f"ComfyUI … {int(time.time() - t0)} s")
        if stop is not None:
            if stop.wait(1.0):
                continue
        else:
            time.sleep(1.0)


def _files(outputs: dict) -> list[dict]:
    out = []
    for node in outputs.values():
        for value in (node or {}).values():
            if isinstance(value, list):
                out += [v for v in value if isinstance(v, dict) and v.get("filename") and v.get("type") != "temp"]
    return out


def _fetch(base_url: str, item: dict) -> tuple[bytes, str]:
    query = urllib.parse.urlencode({"filename": item["filename"], "subfolder": item.get("subfolder", ""),
                                    "type": item.get("type", "output")})
    with aihttp.request("GET", root_url(base_url) + "/view?" + query, {}, timeout=300) as resp:
        return resp.read(), item["filename"]
