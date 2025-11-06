# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
请求日志模块 - 记录用户请求、prompt和最终结果
日志文件不会被删除，用于定期审查
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from threading import Lock

logger = logging.getLogger(__name__)


class RequestLogger:
    """用于记录API请求详情的日志器"""
    
    def __init__(self, log_dir: str = "logs/requests"):
        """
        初始化请求日志器
        
        Args:
            log_dir: 日志目录路径
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        
        # 创建当前月份的日志文件
        self.current_log_file = self._get_current_log_file()
        
        logger.info(f"RequestLogger initialized. Log directory: {self.log_dir}")
        logger.info(f"Current log file: {self.current_log_file}")
    
    def _get_current_log_file(self) -> Path:
        """
        获取当前月份的日志文件路径
        格式: requests_YYYY_MM.jsonl
        """
        now = datetime.now()
        filename = f"requests_{now.year}_{now.month:02d}.jsonl"
        return self.log_dir / filename
    
    def _ensure_log_file_exists(self):
        """确保日志文件存在，如果月份变化则创建新文件"""
        current_file = self._get_current_log_file()
        if current_file != self.current_log_file:
            self.current_log_file = current_file
            logger.info(f"Rotating to new log file: {self.current_log_file}")
        
        # 创建空文件（如果不存在）
        if not self.current_log_file.exists():
            self.current_log_file.touch()
            logger.info(f"Created new log file: {self.current_log_file}")
    
    def log_request(
        self,
        thread_id: str,
        user_query: str,
        messages: List[Dict[str, Any]],
        request_metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        记录请求开始
        
        Args:
            thread_id: 线程ID
            user_query: 用户问题
            messages: 消息列表
            request_metadata: 请求元数据（如配置参数等）
        
        Returns:
            request_id: 请求ID，用于后续记录响应
        """
        timestamp = datetime.now().isoformat()
        request_id = f"{thread_id}_{timestamp}"
        
        log_entry = {
            "request_id": request_id,
            "thread_id": thread_id,
            "timestamp": timestamp,
            "type": "request",
            "user_query": user_query,
            "messages": messages,
            "metadata": request_metadata or {},
        }
        
        self._write_log_entry(log_entry)
        logger.info(f"Logged request: {request_id}")
        
        return request_id
    
    def log_prompt(
        self,
        request_id: str,
        agent_name: str,
        prompt: str,
        prompt_metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        记录生成的prompt
        
        Args:
            request_id: 请求ID
            agent_name: Agent名称
            prompt: Prompt内容
            prompt_metadata: Prompt元数据
        """
        timestamp = datetime.now().isoformat()
        
        log_entry = {
            "request_id": request_id,
            "timestamp": timestamp,
            "type": "prompt",
            "agent_name": agent_name,
            "prompt": prompt,
            "metadata": prompt_metadata or {},
        }
        
        self._write_log_entry(log_entry)
        logger.debug(f"Logged prompt for request: {request_id}, agent: {agent_name}")
    
    def log_response(
        self,
        request_id: str,
        final_result: str,
        intermediate_results: Optional[List[Dict[str, Any]]] = None,
        response_metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        记录最终响应
        
        Args:
            request_id: 请求ID
            final_result: 最终结果
            intermediate_results: 中间结果列表
            response_metadata: 响应元数据
        """
        timestamp = datetime.now().isoformat()
        
        log_entry = {
            "request_id": request_id,
            "timestamp": timestamp,
            "type": "response",
            "final_result": final_result,
            "intermediate_results": intermediate_results or [],
            "metadata": response_metadata or {},
        }
        
        self._write_log_entry(log_entry)
        logger.info(f"Logged response for request: {request_id}")
    
    def log_error(
        self,
        request_id: str,
        error_message: str,
        error_details: Optional[Dict[str, Any]] = None,
    ):
        """
        记录错误
        
        Args:
            request_id: 请求ID
            error_message: 错误消息
            error_details: 错误详情
        """
        timestamp = datetime.now().isoformat()
        
        log_entry = {
            "request_id": request_id,
            "timestamp": timestamp,
            "type": "error",
            "error_message": error_message,
            "error_details": error_details or {},
        }
        
        self._write_log_entry(log_entry)
        logger.error(f"Logged error for request: {request_id}: {error_message}")
    
    def log_feedback(
        self,
        request_id: str,
        user_feedback: str,
        feedback_type: str,
        message_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        feedback_metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        记录用户反馈
        
        Args:
            request_id: 请求ID
            user_feedback: 用户反馈内容 (like/dislike)
            feedback_type: 反馈类型 (rating, comment等)
            message_id: 消息ID
            agent_name: Agent名称
            feedback_metadata: 反馈元数据
        """
        timestamp = datetime.now().isoformat()
        
        log_entry = {
            "request_id": request_id,
            "timestamp": timestamp,
            "type": "user_feedback",
            "user_feedback": user_feedback,
            "feedback_type": feedback_type,
            "message_id": message_id,
            "agent_name": agent_name,
            "metadata": feedback_metadata or {},
        }
        
        self._write_log_entry(log_entry)
        logger.info(f"Logged user feedback for request: {request_id}, feedback: {user_feedback}, type: {feedback_type}")
    
    def _write_log_entry(self, entry: Dict[str, Any]):
        """
        写入日志条目到文件（JSONL格式）
        使用锁确保线程安全
        """
        with self._lock:
            try:
                self._ensure_log_file_exists()
                
                # 追加模式写入，确保不会删除现有日志
                with open(self.current_log_file, "a", encoding="utf-8") as f:
                    json_line = json.dumps(entry, ensure_ascii=False)
                    f.write(json_line + "\n")
                
            except Exception as e:
                logger.error(f"Failed to write log entry: {e}")
                logger.error(f"Entry: {entry}")
    
    def get_log_files(self) -> List[Path]:
        """
        获取所有日志文件列表
        
        Returns:
            日志文件路径列表，按时间排序（最新的在前）
        """
        log_files = sorted(
            self.log_dir.glob("requests_*.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        return log_files
    
    def read_logs(
        self,
        limit: Optional[int] = None,
        log_file: Optional[Path] = None,
    ) -> List[Dict[str, Any]]:
        """
        读取日志条目
        
        Args:
            limit: 限制返回条目数量
            log_file: 指定日志文件，默认读取当前文件
        
        Returns:
            日志条目列表
        """
        target_file = log_file or self.current_log_file
        
        if not target_file.exists():
            logger.warning(f"Log file does not exist: {target_file}")
            return []
        
        entries = []
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            entry = json.loads(line)
                            entries.append(entry)
                            
                            if limit and len(entries) >= limit:
                                break
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to parse log line: {e}")
                            continue
        except Exception as e:
            logger.error(f"Failed to read log file: {e}")
        
        return entries


# 全局单例实例
_request_logger: Optional[RequestLogger] = None


def get_request_logger() -> RequestLogger:
    """
    获取全局RequestLogger实例（单例模式）
    
    Returns:
        RequestLogger实例
    """
    global _request_logger
    
    if _request_logger is None:
        # 从环境变量读取日志目录，默认为 logs/requests
        log_dir = os.getenv("REQUEST_LOG_DIR", "logs/requests")
        _request_logger = RequestLogger(log_dir=log_dir)
    
    return _request_logger

