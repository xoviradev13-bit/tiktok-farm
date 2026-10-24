import os
import sys
import logging
from logging.handlers import RotatingFileHandler
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional

from backend.config import BASE_DIR, DATA_DIR

LOGS_DIR = DATA_DIR / "logs"
LOG_FILE_PATH = LOGS_DIR / "app.log"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Formatters
FILE_LOG_FORMAT = "%(asctime)s [%(levelname)-7s] [%(name)s:%(lineno)d] [%(threadName)s] - %(message)s"
CONSOLE_LOG_FORMAT = "%(asctime)s [%(levelname)-7s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Configure root app logger
_logger = logging.getLogger("tiktok_farm")
_logger.setLevel(logging.DEBUG)

# Ensure no duplicate handlers if re-imported
if not _logger.handlers:
    # 1. Rotating File Handler (10MB per file, keep 5 backups, UTF-8 encoded)
    try:
        file_handler = RotatingFileHandler(
            filename=str(LOG_FILE_PATH),
            mode="a",
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
            delay=False
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(FILE_LOG_FORMAT, datefmt=DATE_FORMAT))
        _logger.addHandler(file_handler)
    except Exception as e:
        print(f"[LOGGER INIT ERROR] Cannot create file handler: {e}", file=sys.stderr)

    # 2. Console Stream Handler
    try:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter(CONSOLE_LOG_FORMAT, datefmt=DATE_FORMAT))
        _logger.addHandler(console_handler)
    except Exception as e:
        print(f"[LOGGER INIT ERROR] Cannot create console handler: {e}", file=sys.stderr)

def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Trả về logger chuẩn cho module tương ứng"""
    if not name:
        return _logger
    return _logger.getChild(name)

# Shorthand logging helpers
def log_debug(msg: str, *args, **kwargs):
    _logger.debug(msg, *args, **kwargs)

def log_info(msg: str, *args, **kwargs):
    _logger.info(msg, *args, **kwargs)

def log_warning(msg: str, *args, **kwargs):
    _logger.warning(msg, *args, **kwargs)

def log_error(msg: str, *args, **kwargs):
    _logger.error(msg, *args, **kwargs)

def log_exception(msg: str, *args, **kwargs):
    """Ghi lại lỗi kèm toàn bộ stack trace vào file log"""
    _logger.exception(msg, *args, **kwargs)

# Hook uncaught exceptions to log file
def _handle_uncaught_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    _logger.critical(
        f"UNCAUGHT EXCEPTION in Main Thread: {exc_type.__name__}: {exc_value}",
        exc_info=(exc_type, exc_value, exc_traceback)
    )

sys.excepthook = _handle_uncaught_exception

if hasattr(threading, "excepthook"):
    def _handle_thread_exception(args):
        if issubclass(args.exc_type, KeyboardInterrupt):
            return
        thread_name = args.thread.name if args.thread else "UnknownThread"
        _logger.critical(
            f"UNCAUGHT EXCEPTION in Thread [{thread_name}]: {args.exc_type.__name__}: {args.exc_value}",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback)
        )
    threading.excepthook = _handle_thread_exception

def get_log_file_info() -> Dict[str, Any]:
    """Lấy thông tin file log thực tế trên đĩa"""
    if not LOG_FILE_PATH.exists():
        return {
            "exists": False,
            "path": str(LOG_FILE_PATH),
            "size_bytes": 0,
            "size_formatted": "0 KB",
            "modified_time": None
        }

    size = LOG_FILE_PATH.stat().st_size
    mtime = LOG_FILE_PATH.stat().st_mtime
    import datetime
    mtime_str = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")

    size_formatted = f"{size / 1024:.1f} KB" if size < 1024 * 1024 else f"{size / (1024 * 1024):.2f} MB"

    return {
        "exists": True,
        "path": str(LOG_FILE_PATH),
        "size_bytes": size,
        "size_formatted": size_formatted,
        "modified_time": mtime_str
    }

def get_recent_log_lines(
    limit: int = 400,
    level_filter: str = "ALL",
    search_query: str = ""
) -> List[Dict[str, Any]]:
    """
    Đọc các dòng log gần nhất từ file app.log để hiển thị lên UI với bộ lọc linh hoạt.
    """
    if not LOG_FILE_PATH.exists():
        return []

    lines: List[str] = []
    try:
        # Đọc ngược từ cuối file hoặc đọc toàn bộ nếu file vừa phải
        with open(LOG_FILE_PATH, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
            lines = all_lines[-max(limit * 3, 1000):]
    except Exception as e:
        return [{"raw": f"[ERROR READING LOG FILE: {e}]", "level": "ERROR", "time": "", "message": str(e)}]

    parsed_records = []
    level_filter = level_filter.upper().strip()
    search_query = search_query.lower().strip()

    # Regex nhận dạng dòng log chuẩn: 2026-10-25 04:50:00 [INFO   ] [name:123] [thread] - message
    import re
    log_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+\[([A-Z]+)\s*\]\s+\[([^\]]+)\]\s+\[([^\]]+)\]\s+-\s+(.*)$")

    current_entry = None

    for line in lines:
        match = log_pattern.match(line)
        if match:
            if current_entry:
                parsed_records.append(current_entry)
            timestamp, lvl, source, thread_name, msg = match.groups()
            current_entry = {
                "time": timestamp,
                "level": lvl.strip(),
                "source": source.strip(),
                "thread": thread_name.strip(),
                "message": msg.strip(),
                "raw": line.strip()
            }
        else:
            # Continuation line (ví dụ Traceback line)
            if current_entry:
                current_entry["message"] += "\n" + line.rstrip()
                current_entry["raw"] += "\n" + line.rstrip()
            else:
                current_entry = {
                    "time": "",
                    "level": "INFO",
                    "source": "sys",
                    "thread": "main",
                    "message": line.strip(),
                    "raw": line.strip()
                }

    if current_entry:
        parsed_records.append(current_entry)

    # Áp dụng bộ lọc
    filtered = []
    for r in parsed_records:
        r_level = r["level"].upper()
        if level_filter != "ALL":
            if level_filter == "ERROR" and r_level not in ("ERROR", "CRITICAL"):
                continue
            elif level_filter == "WARNING" and r_level not in ("WARNING", "ERROR", "CRITICAL"):
                continue
            elif level_filter == "INFO" and r_level not in ("INFO", "WARNING", "ERROR", "CRITICAL"):
                continue
            elif level_filter == "DEBUG" and r_level != "DEBUG":
                continue

        if search_query:
            if (search_query not in r["message"].lower() and
                search_query not in r["source"].lower() and
                search_query not in r["raw"].lower()):
                continue

        filtered.append(r)

    return filtered[-limit:]

def clear_log_file() -> bool:
    """Xóa trắng nội dung file log"""
    try:
        with open(LOG_FILE_PATH, "w", encoding="utf-8") as f:
            f.truncate(0)
        _logger.info("Đã làm sạch file nhật ký hệ thống app.log.")
        return True
    except Exception as e:
        print(f"[CLEAR LOG ERROR] {e}", file=sys.stderr)
        return False

# Initial boot record
_logger.info("=== HỆ THỐNG LOGGING ĐÃ KHỞI TẠO THÀNH CÔNG ===")
