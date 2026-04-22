"""
结构化日志工具模块

提供统一的日志记录接口，输出 JSON 格式日志便于分析和告警
"""

import logging
import json
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, Dict, Any

# 获取日志目录（项目根目录下的 logs/）
# 当前文件路径：edubot-twin-server/app/core/logger.py
# 目标路径：edubot-twin/logs/
LOG_DIR = Path(__file__).resolve().parents[3] / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "edubot.log"

# 配置日志记录器
logger = logging.getLogger("edubot-twin")
logger.setLevel(logging.INFO)

# 避免重复配置 Handler
if not logger.handlers:
    # 1. 终端处理器（标准输出）
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(console_handler)

    # 2. 文件处理器（轮转存储，单文件最大 10MB，保留 5 个备份）
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(file_handler)


def log_container_event(
    event_type: str,
    container_id: Optional[int] = None,
    student_id: Optional[int] = None,
    status: Optional[str] = None,
    message: str = "",
    level: str = "INFO",
    extra: Optional[Dict[str, Any]] = None
):
    """
    记录容器相关事件的结构化日志
    
    Args:
        event_type: 事件类型 (create/start/stop/delete/metrics_collect)
        container_id: 容器 ID
        student_id: 学生 ID
        status: 容器状态
        message: 日志消息
        level: 日志级别 (ERROR/WARNING/INFO)
        extra: 额外的上下文信息
    """
    log_data = {
        "timestamp": datetime.utcnow().isoformat(),
        "event_type": event_type,
        "container_id": container_id,
        "student_id": student_id,
        "status": status,
        "message": message,
    }
    
    if extra:
        log_data["extra"] = extra
    
    log_message = json.dumps(log_data, ensure_ascii=False)
    
    if level == "ERROR":
        logger.error(log_message)
    elif level == "WARNING":
        logger.warning(log_message)
    else:
        logger.info(log_message)
