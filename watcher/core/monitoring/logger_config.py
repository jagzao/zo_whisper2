import logging
import structlog
import sys
from pathlib import Path
from typing import Dict, Any
import json
from datetime import datetime

class StructuredLogger:
    """Centralized logging configuration with structured output"""
    
    def __init__(self, log_level: str = "INFO", log_format: str = "standard", log_file: str = None):
        self.log_level = getattr(logging, log_level.upper())
        self.log_format = log_format
        self.log_file = log_file
        self._setup_logging()
    
    def _setup_logging(self):
        """Configure structured logging"""
        
        # Configure structlog
        if self.log_format == "json":
            processors = [
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.JSONRenderer()
            ]
        else:
            processors = [
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.dev.ConsoleRenderer(colors=True)
            ]
        
        structlog.configure(
            processors=processors,
            wrapper_class=structlog.make_filtering_bound_logger(self.log_level),
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )
        
        # Configure standard logging
        logging.basicConfig(
            level=self.log_level,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            handlers=self._get_handlers()
        )
    
    def _get_handlers(self):
        """Get logging handlers"""
        handlers = []
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(self.log_level)
        handlers.append(console_handler)
        
        # File handler if specified
        if self.log_file:
            log_path = Path(self.log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            file_handler = logging.FileHandler(log_path)
            file_handler.setLevel(self.log_level)
            
            if self.log_format == "json":
                file_handler.setFormatter(JSONFormatter())
            else:
                file_handler.setFormatter(
                    logging.Formatter(
                        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
                    )
                )
            handlers.append(file_handler)
        
        return handlers
    
    def get_logger(self, name: str):
        """Get a structured logger instance"""
        return structlog.get_logger(name)

class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for log records"""
    
    def format(self, record):
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # Add extra fields if present
        if hasattr(record, 'extra_fields'):
            log_entry.update(record.extra_fields)
        
        return json.dumps(log_entry)

class ApplicationMetrics:
    """Track application metrics and performance"""
    
    def __init__(self):
        self.metrics = {
            "files_processed": 0,
            "files_failed": 0,
            "processing_times": [],
            "queue_sizes": [],
            "errors": [],
            "start_time": datetime.now(),
            "last_activity": datetime.now()
        }
        self._logger = structlog.get_logger("metrics")
    
    def record_file_processed(self, file_path: str, processing_time: float, success: bool = True):
        """Record a file processing event"""
        self.metrics["last_activity"] = datetime.now()
        
        if success:
            self.metrics["files_processed"] += 1
            self.metrics["processing_times"].append(processing_time)
            
            # Keep only last 100 processing times for memory efficiency
            if len(self.metrics["processing_times"]) > 100:
                self.metrics["processing_times"] = self.metrics["processing_times"][-100:]
            
            self._logger.info(
                "file_processed",
                file_path=file_path,
                processing_time=processing_time,
                total_processed=self.metrics["files_processed"]
            )
        else:
            self.metrics["files_failed"] += 1
            self._logger.error(
                "file_processing_failed",
                file_path=file_path,
                processing_time=processing_time,
                total_failed=self.metrics["files_failed"]
            )
    
    def record_error(self, error_type: str, error_message: str, context: Dict[str, Any] = None):
        """Record an error event"""
        error_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": error_type,
            "message": error_message,
            "context": context or {}
        }
        
        self.metrics["errors"].append(error_entry)
        
        # Keep only last 50 errors
        if len(self.metrics["errors"]) > 50:
            self.metrics["errors"] = self.metrics["errors"][-50:]
        
        self._logger.error(
            "application_error",
            error_type=error_type,
            error_message=error_message,
            context=context
        )
    
    def record_queue_size(self, queue_name: str, size: int):
        """Record queue size for monitoring"""
        queue_entry = {
            "timestamp": datetime.now().isoformat(),
            "queue_name": queue_name,
            "size": size
        }
        
        self.metrics["queue_sizes"].append(queue_entry)
        
        # Keep only last 100 queue size records
        if len(self.metrics["queue_sizes"]) > 100:
            self.metrics["queue_sizes"] = self.metrics["queue_sizes"][-100:]
    
    def get_summary(self) -> Dict[str, Any]:
        """Get metrics summary"""
        now = datetime.now()
        uptime = (now - self.metrics["start_time"]).total_seconds()
        
        processing_times = self.metrics["processing_times"]
        avg_processing_time = sum(processing_times) / len(processing_times) if processing_times else 0
        
        return {
            "uptime_seconds": uptime,
            "uptime_formatted": str(now - self.metrics["start_time"]),
            "files_processed": self.metrics["files_processed"],
            "files_failed": self.metrics["files_failed"],
            "success_rate": (
                self.metrics["files_processed"] / 
                (self.metrics["files_processed"] + self.metrics["files_failed"])
                if (self.metrics["files_processed"] + self.metrics["files_failed"]) > 0 
                else 0
            ),
            "average_processing_time": round(avg_processing_time, 2),
            "recent_errors": len([
                e for e in self.metrics["errors"] 
                if datetime.fromisoformat(e["timestamp"]) > now - datetime.timedelta(hours=1)
            ]),
            "last_activity": self.metrics["last_activity"].isoformat(),
            "processing_rate_per_hour": (
                self.metrics["files_processed"] / (uptime / 3600) 
                if uptime > 0 else 0
            )
        }
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get application health status"""
        now = datetime.now()
        last_activity_age = (now - self.metrics["last_activity"]).total_seconds()
        
        # Determine health status
        if last_activity_age > 3600:  # No activity for 1 hour
            status = "unhealthy"
            reason = "No recent activity"
        elif self.metrics["files_failed"] > self.metrics["files_processed"] * 0.5:  # >50% failure rate
            status = "degraded"
            reason = "High failure rate"
        elif len([e for e in self.metrics["errors"] if datetime.fromisoformat(e["timestamp"]) > now - datetime.timedelta(minutes=15)]) > 5:
            status = "degraded"
            reason = "High error rate"
        else:
            status = "healthy"
            reason = "All systems operational"
        
        return {
            "status": status,
            "reason": reason,
            "timestamp": now.isoformat(),
            "last_activity_seconds_ago": round(last_activity_age),
            "recent_errors": len([
                e for e in self.metrics["errors"] 
                if datetime.fromisoformat(e["timestamp"]) > now - datetime.timedelta(minutes=15)
            ])
        }

# Global instances
logger_config = None
app_metrics = ApplicationMetrics()