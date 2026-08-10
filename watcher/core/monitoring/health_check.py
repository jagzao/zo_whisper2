# import psutil
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List
import structlog
from pathlib import Path

# Try to import psutil, but make it optional
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

logger = structlog.get_logger("health_check")

class HealthChecker:
    """Comprehensive health checking for the application"""
    
    def __init__(self, check_interval: int = 60):
        self.check_interval = check_interval
        self._running = False
        self._thread = None
        self._checks: Dict[str, Dict] = {}
        self._last_check = None
    
    def start(self):
        """Start the health check monitoring"""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._health_check_loop, daemon=True)
        self._thread.name = "HealthChecker"
        self._thread.start()
        logger.info("Health checker started", interval=self.check_interval)
    
    def stop(self):
        """Stop the health check monitoring"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Health checker stopped")
    
    def _health_check_loop(self):
        """Main health check loop"""
        while self._running:
            try:
                self._perform_health_checks()
                time.sleep(self.check_interval)
            except Exception as e:
                logger.error("Error in health check loop", error=str(e))
                time.sleep(10)  # Brief pause on error
    
    def _perform_health_checks(self):
        """Perform all health checks"""
        self._last_check = datetime.now()
        
        # System resource checks
        self._checks["system"] = self._check_system_resources()
        
        # Disk space checks
        self._checks["disk_space"] = self._check_disk_space()
        
        # Directory accessibility checks
        self._checks["directories"] = self._check_directories()
        
        # Process health checks
        self._checks["process"] = self._check_process_health()
        
        # Log overall health status
        overall_status = self.get_overall_health()
        logger.info(
            "health_check_completed",
            overall_status=overall_status["status"],
            checks_passed=overall_status["checks_passed"],
            checks_total=overall_status["checks_total"]
        )
    
    def _check_system_resources(self) -> Dict[str, Any]:
        """Check system resource usage"""
        if not PSUTIL_AVAILABLE:
            return {
                "status": "warning",
                "message": "psutil not available - system monitoring disabled",
                "timestamp": datetime.now().isoformat(),
                "cpu_percent": 0.0,
                "memory_percent": 0.0
            }
        
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_available_gb = memory.available / (1024**3)
            
            # Check thresholds
            cpu_healthy = cpu_percent < 90
            memory_healthy = memory_percent < 90 and memory_available_gb > 1
            
            return {
                "status": "healthy" if (cpu_healthy and memory_healthy) else "warning",
                "cpu_percent": round(cpu_percent, 1),
                "memory_percent": round(memory_percent, 1),
                "memory_available_gb": round(memory_available_gb, 2),
                "memory_total_gb": round(memory.total / (1024**3), 2),
                "cpu_healthy": cpu_healthy,
                "memory_healthy": memory_healthy,
                "timestamp": self._last_check.isoformat()
            }
            
        except Exception as e:
            logger.error("Error checking system resources", error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "timestamp": self._last_check.isoformat()
            }
    
    def _check_disk_space(self) -> Dict[str, Any]:
        """Check disk space for important directories"""
        if not PSUTIL_AVAILABLE:
            return {
                "status": "warning",
                "message": "psutil not available - disk monitoring disabled",
                "timestamp": datetime.now().isoformat(),
                "directories": {}
            }
        
        directories_to_check = [
            "/app/Videos",
            "/app/audio", 
            "/app/CarpetaTranscripciones",
            "/app/logs"
        ]
        
        disk_checks = {}
        overall_healthy = True
        
        for directory in directories_to_check:
            try:
                path = Path(directory)
                if not path.exists():
                    continue
                
                # Get disk usage
                usage = psutil.disk_usage(str(path))
                free_gb = usage.free / (1024**3)
                total_gb = usage.total / (1024**3)
                used_percent = (usage.used / usage.total) * 100
                
                # Check if healthy (at least 1GB free and less than 95% used)
                healthy = free_gb > 1 and used_percent < 95
                if not healthy:
                    overall_healthy = False
                
                disk_checks[directory] = {
                    "free_gb": round(free_gb, 2),
                    "total_gb": round(total_gb, 2),
                    "used_percent": round(used_percent, 1),
                    "healthy": healthy
                }
                
            except Exception as e:
                logger.error("Error checking disk space", directory=directory, error=str(e))
                disk_checks[directory] = {"error": str(e), "healthy": False}
                overall_healthy = False
        
        return {
            "status": "healthy" if overall_healthy else "warning",
            "directories": disk_checks,
            "timestamp": self._last_check.isoformat()
        }
    
    def _check_directories(self) -> Dict[str, Any]:
        """Check if important directories are accessible"""
        directories_to_check = [
            "/app/Videos",
            "/app/audio",
            "/app/CarpetaTranscripciones"
        ]
        
        directory_checks = {}
        overall_healthy = True
        
        for directory in directories_to_check:
            try:
                path = Path(directory)
                
                # Check if directory exists and is accessible
                exists = path.exists()
                readable = path.is_dir() and os.access(str(path), os.R_OK) if exists else False
                writable = os.access(str(path), os.W_OK) if exists else False
                
                healthy = exists and readable and writable
                if not healthy:
                    overall_healthy = False
                
                directory_checks[directory] = {
                    "exists": exists,
                    "readable": readable,
                    "writable": writable,
                    "healthy": healthy
                }
                
            except Exception as e:
                logger.error("Error checking directory", directory=directory, error=str(e))
                directory_checks[directory] = {"error": str(e), "healthy": False}
                overall_healthy = False
        
        return {
            "status": "healthy" if overall_healthy else "error",
            "directories": directory_checks,
            "timestamp": self._last_check.isoformat()
        }
    
    def _check_process_health(self) -> Dict[str, Any]:
        """Check process-specific health metrics"""
        if not PSUTIL_AVAILABLE:
            return {
                "status": "warning",
                "message": "psutil not available - process monitoring disabled",
                "timestamp": datetime.now().isoformat(),
                "memory_mb": 0.0,
                "cpu_percent": 0.0
            }
        
        try:
            current_process = psutil.Process()
            
            # Get process info
            memory_info = current_process.memory_info()
            memory_mb = memory_info.rss / (1024**2)
            cpu_percent = current_process.cpu_percent()
            
            # Get thread count
            thread_count = current_process.num_threads()
            
            # Check file descriptors (Unix only)
            fd_count = None
            try:
                fd_count = current_process.num_fds()
            except (AttributeError, Exception):
                pass  # Not available on Windows or access denied
            
            # Check if healthy
            memory_healthy = memory_mb < 2048  # Less than 2GB
            thread_healthy = thread_count < 50  # Less than 50 threads
            
            return {
                "status": "healthy" if (memory_healthy and thread_healthy) else "warning",
                "memory_mb": round(memory_mb, 1),
                "cpu_percent": round(cpu_percent, 1),
                "thread_count": thread_count,
                "fd_count": fd_count,
                "memory_healthy": memory_healthy,
                "thread_healthy": thread_healthy,
                "pid": current_process.pid,
                "timestamp": self._last_check.isoformat()
            }
            
        except Exception as e:
            logger.error("Error checking process health", error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "timestamp": self._last_check.isoformat()
            }
    
    def get_overall_health(self) -> Dict[str, Any]:
        """Get overall health status"""
        if not self._checks:
            return {
                "status": "unknown",
                "reason": "No health checks performed yet",
                "timestamp": datetime.now().isoformat()
            }
        
        # Count check results
        total_checks = 0
        healthy_checks = 0
        warning_checks = 0
        error_checks = 0
        
        for check_name, check_result in self._checks.items():
            total_checks += 1
            status = check_result.get("status", "unknown")
            
            if status == "healthy":
                healthy_checks += 1
            elif status == "warning":
                warning_checks += 1
            elif status == "error":
                error_checks += 1
        
        # Determine overall status
        if error_checks > 0:
            overall_status = "error"
            reason = f"{error_checks} critical issues detected"
        elif warning_checks > 0:
            overall_status = "warning"
            reason = f"{warning_checks} warnings detected"
        else:
            overall_status = "healthy"
            reason = "All checks passed"
        
        return {
            "status": overall_status,
            "reason": reason,
            "checks_total": total_checks,
            "checks_passed": healthy_checks,
            "checks_warning": warning_checks,
            "checks_error": error_checks,
            "last_check": self._last_check.isoformat() if self._last_check else None,
            "timestamp": datetime.now().isoformat()
        }
    
    def get_detailed_health(self) -> Dict[str, Any]:
        """Get detailed health information"""
        return {
            "overall": self.get_overall_health(),
            "checks": self._checks,
            "check_interval": self.check_interval,
            "running": self._running
        }

# Global health checker instance
health_checker = HealthChecker()

import os  # Add missing import