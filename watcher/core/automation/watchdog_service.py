import os
import sys
import time
import threading
import subprocess
import signal
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import structlog

logger = structlog.get_logger("watchdog_service")

class ServiceWatchdog:
    """Watchdog service that monitors health and restarts services if needed"""
    
    def __init__(self, 
                 check_interval: int = 30,
                 failure_threshold: int = 3,
                 restart_cooldown: int = 300):  # 5 minutes
        
        self.check_interval = check_interval
        self.failure_threshold = failure_threshold  
        self.restart_cooldown = restart_cooldown
        self._running = False
        self._thread = None
        
        # Track service health
        self.service_failures = {}
        self.last_restart_times = {}
        self.restart_counts = {}
        
        # Services to monitor
        self.monitored_services = {
            "self": {
                "health_check": self._check_self_health,
                "restart_command": self._restart_self_service,
                "critical": True
            },
            "database": {
                "health_check": self._check_database_health,
                "restart_command": None,  # Database issues usually require manual intervention
                "critical": True
            },
            "queue": {
                "health_check": self._check_queue_health,
                "restart_command": self._restart_queue_service,
                "critical": False
            }
        }
    
    def start(self):
        """Start the watchdog service"""
        if self._running:
            logger.warning("Watchdog service is already running")
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self._thread.name = "ServiceWatchdog"
        self._thread.start()
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
        logger.info("Service watchdog started", 
                   check_interval=self.check_interval,
                   failure_threshold=self.failure_threshold)
    
    def stop(self):
        """Stop the watchdog service"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("Service watchdog stopped")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info("Received shutdown signal", signal=signum)
        self.stop()
        sys.exit(0)
    
    def _monitoring_loop(self):
        """Main monitoring loop"""
        logger.info("Watchdog monitoring loop started")
        
        while self._running:
            try:
                current_time = datetime.now()
                
                for service_name, service_config in self.monitored_services.items():
                    self._check_service_health(service_name, service_config, current_time)
                
                time.sleep(self.check_interval)
                
            except Exception as e:
                logger.error("Error in watchdog monitoring loop", error=str(e))
                time.sleep(self.check_interval)
    
    def _check_service_health(self, service_name: str, service_config: Dict, current_time: datetime):
        """Check health of a specific service"""
        try:
            health_check = service_config["health_check"]
            is_healthy = health_check()
            
            if is_healthy:
                # Reset failure count on successful health check
                if service_name in self.service_failures:
                    prev_failures = self.service_failures[service_name]
                    if prev_failures > 0:
                        logger.info("Service recovered", 
                                   service=service_name, 
                                   previous_failures=prev_failures)
                    self.service_failures[service_name] = 0
            else:
                # Increment failure count
                self.service_failures[service_name] = self.service_failures.get(service_name, 0) + 1
                failure_count = self.service_failures[service_name]
                
                logger.warning("Service health check failed",
                              service=service_name,
                              failure_count=failure_count,
                              threshold=self.failure_threshold)
                
                # Check if we should restart the service
                if failure_count >= self.failure_threshold:
                    self._handle_service_failure(service_name, service_config, current_time)
        
        except Exception as e:
            logger.error("Error checking service health", service=service_name, error=str(e))
            # Treat exceptions as health check failures
            self.service_failures[service_name] = self.service_failures.get(service_name, 0) + 1
    
    def _handle_service_failure(self, service_name: str, service_config: Dict, current_time: datetime):
        """Handle service failure - restart if appropriate"""
        
        # Check if we're in restart cooldown period
        last_restart = self.last_restart_times.get(service_name)
        if last_restart:
            time_since_restart = (current_time - last_restart).total_seconds()
            if time_since_restart < self.restart_cooldown:
                logger.warning("Service restart skipped - in cooldown period",
                              service=service_name,
                              cooldown_remaining=self.restart_cooldown - time_since_restart)
                return
        
        # Check restart limits (max 3 restarts per hour)
        restart_count = self.restart_counts.get(service_name, 0)
        if restart_count >= 3:
            # Check if an hour has passed since first restart
            first_restart_time = self.last_restart_times.get(f"{service_name}_first")
            if first_restart_time and (current_time - first_restart_time).total_seconds() < 3600:
                logger.error("Service restart limit reached", 
                           service=service_name,
                           restart_count=restart_count)
                return
            else:
                # Reset counters after an hour
                self.restart_counts[service_name] = 0
        
        # Attempt service restart
        restart_command = service_config.get("restart_command")
        if restart_command:
            logger.warning("Attempting service restart", 
                          service=service_name,
                          failure_count=self.service_failures[service_name])
            
            try:
                success = restart_command()
                
                if success:
                    self.last_restart_times[service_name] = current_time
                    self.restart_counts[service_name] = restart_count + 1
                    self.service_failures[service_name] = 0  # Reset failure count
                    
                    # Track first restart time for rate limiting
                    if restart_count == 0:
                        self.last_restart_times[f"{service_name}_first"] = current_time
                    
                    logger.info("Service restart successful", service=service_name)
                else:
                    logger.error("Service restart failed", service=service_name)
                    
            except Exception as e:
                logger.error("Error during service restart", service=service_name, error=str(e))
        else:
            # No restart command available - log critical error
            if service_config.get("critical", False):
                logger.critical("Critical service failed and cannot be restarted",
                               service=service_name,
                               failure_count=self.service_failures[service_name])
            else:
                logger.error("Service failed and no restart command available",
                           service=service_name)
    
    def _check_self_health(self) -> bool:
        """Check health of the main application"""
        try:
            from core.monitoring.health_check import health_checker
            
            if not hasattr(health_checker, 'get_overall_health'):
                return True  # Assume healthy if no health checker
            
            health = health_checker.get_overall_health()
            return health.get('status') in ['healthy', 'warning']
            
        except Exception as e:
            logger.error("Error checking self health", error=str(e))
            return False
    
    def _check_database_health(self) -> bool:
        """Check database connectivity and basic operations"""
        try:
            from core.database.models import db_manager
            
            # Try a simple database operation
            db_info = db_manager.get_database_size()
            return 'error' not in db_info
            
        except Exception as e:
            logger.error("Database health check failed", error=str(e))
            return False
    
    def _check_queue_health(self) -> bool:
        """Check queue service health"""
        try:
            from core.performance.queue_manager import queue_manager
            
            if not queue_manager or not queue_manager.is_connected():
                return True  # Queue is optional, consider healthy if not used
            
            stats = queue_manager.get_queue_stats()
            return 'error' not in stats
            
        except Exception as e:
            logger.error("Queue health check failed", error=str(e))
            return False
    
    def _restart_self_service(self) -> bool:
        """Restart the main application"""
        try:
            logger.warning("Attempting self-restart...")
            
            # In Docker environment, we exit and let Docker restart the container
            if os.path.exists('/.dockerenv'):
                logger.info("Running in Docker - exiting for container restart")
                # Give some time for logs to flush
                time.sleep(2)
                os._exit(1)  # Force exit that Docker will catch and restart
                return True
            else:
                # In non-Docker environment, try to restart the Python process
                logger.info("Restarting Python process")
                os.execv(sys.executable, ['python'] + sys.argv)
                return True
                
        except Exception as e:
            logger.error("Self-restart failed", error=str(e))
            return False
    
    def _restart_queue_service(self) -> bool:
        """Restart queue service"""
        try:
            from core.performance.queue_manager import queue_manager
            
            if queue_manager:
                logger.info("Restarting queue workers")
                queue_manager.stop_workers()
                time.sleep(5)  # Wait for cleanup
                queue_manager.start_workers()
                return True
            
            return False
            
        except Exception as e:
            logger.error("Queue restart failed", error=str(e))
            return False
    
    def get_watchdog_status(self) -> Dict:
        """Get current watchdog status"""
        return {
            "running": self._running,
            "check_interval": self.check_interval,
            "failure_threshold": self.failure_threshold,
            "restart_cooldown": self.restart_cooldown,
            "monitored_services": list(self.monitored_services.keys()),
            "service_failures": self.service_failures.copy(),
            "restart_counts": self.restart_counts.copy(),
            "last_restart_times": {
                k: v.isoformat() for k, v in self.last_restart_times.items()
                if not k.endswith('_first')
            }
        }
    
    def force_health_check(self) -> Dict:
        """Force immediate health check of all services"""
        logger.info("Forcing health check of all services")
        
        results = {}
        current_time = datetime.now()
        
        for service_name, service_config in self.monitored_services.items():
            try:
                health_check = service_config["health_check"]
                is_healthy = health_check()
                results[service_name] = {
                    "healthy": is_healthy,
                    "timestamp": current_time.isoformat()
                }
                
                if not is_healthy:
                    results[service_name]["current_failures"] = self.service_failures.get(service_name, 0)
                
            except Exception as e:
                results[service_name] = {
                    "healthy": False,
                    "error": str(e),
                    "timestamp": current_time.isoformat()
                }
        
        return results

# Global watchdog service instance
watchdog_service = ServiceWatchdog()