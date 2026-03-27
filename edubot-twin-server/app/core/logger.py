"""
结构化日志工具模块

提供统一的日志记录接口，输出 JSON 格式日志便于分析和告警
"""

import logging
import json
from datetime import datetime
from typing import Optional, Dict, Any

# 配置日志格式
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)

logger = logging.getLogger("edubot-twin")


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
