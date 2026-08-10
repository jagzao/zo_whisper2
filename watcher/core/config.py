import os
import logging
from typing import Optional, Dict, Any
from pathlib import Path

class ConfigurationError(Exception):
    """Raised when configuration is invalid or missing"""
    pass

class Config:
    """Centralized configuration management with validation"""
    
    def __init__(self):
        self._load_and_validate()
    
    def _load_and_validate(self):
        """Load and validate all configuration values"""
        
        # All vars are optional — warn but don't fail
        optional_vars = {
            'NOTION_API_KEY': 'Notion integration disabled',
            'NOTION_DATABASE_ID': 'Notion integration disabled',
            'EMAIL_SENDER': 'Email notifications disabled',
            'EMAIL_PASSWORD': 'Email notifications disabled',
            'EMAIL_RECEIVER': 'Email notifications disabled',
        }
        for var, note in optional_vars.items():
            if not os.getenv(var):
                logging.warning(f"[CONFIG] {var} not set — {note}")
    
    # Notion Configuration
    @property
    def notion_api_key(self) -> str:
        return os.getenv('NOTION_API_KEY')
    
    @property
    def notion_database_id(self) -> str:
        return os.getenv('NOTION_DATABASE_ID')
    
    # Email Configuration
    @property
    def email_sender(self) -> str:
        return os.getenv('EMAIL_SENDER')
    
    @property
    def email_password(self) -> str:
        return os.getenv('EMAIL_PASSWORD')
    
    @property
    def email_receiver(self) -> str:
        return os.getenv('EMAIL_RECEIVER')
    
    @property
    def email_smtp_server(self) -> str:
        return os.getenv('EMAIL_SMTP_SERVER', 'smtp.gmail.com')
    
    @property
    def email_smtp_port(self) -> int:
        return int(os.getenv('EMAIL_SMTP_PORT', '587'))
    
    # Processing Configuration
    @property
    def language(self) -> str:
        return os.getenv('LANGUAGE', 'es')
    
    @property
    def max_file_size_mb(self) -> int:
        return int(os.getenv('MAX_FILE_SIZE_MB', '500'))
    
    @property
    def cleanup_temp_files(self) -> bool:
        return os.getenv('CLEANUP_TEMP_FILES', 'true').lower() == 'true'
    
    @property
    def parallel_processing(self) -> bool:
        return os.getenv('PARALLEL_PROCESSING', 'true').lower() == 'true'
    
    @property
    def max_concurrent_jobs(self) -> int:
        return int(os.getenv('MAX_CONCURRENT_JOBS', '3'))
    
    # Path Configuration
    @property
    def rag_base_path(self) -> Optional[str]:
        path = os.getenv('RAG_BASE_PATH')
        return path if path and Path(path).exists() else None
    
    @property
    def sync_base_path(self) -> Optional[str]:
        path = os.getenv('SYNC_BASE_PATH')
        return path if path and Path(path).exists() else None
    
    # Performance Settings
    @property
    def enable_redis_queue(self) -> bool:
        return os.getenv('ENABLE_REDIS_QUEUE', 'false').lower() == 'true'
    
    @property
    def redis_url(self) -> str:
        return os.getenv('REDIS_URL', 'redis://localhost:6379')
    
    @property
    def enable_file_monitoring(self) -> bool:
        return os.getenv('ENABLE_FILE_MONITORING', 'true').lower() == 'true'
    
    # Logging Configuration
    @property
    def log_level(self) -> str:
        return os.getenv('LOG_LEVEL', 'INFO')
    
    @property
    def log_format(self) -> str:
        return os.getenv('LOG_FORMAT', 'standard')
    
    @property
    def log_file_path(self) -> str:
        default = str(Path(__file__).parents[2] / "logs" / "watcher.log")
        return os.getenv('LOG_FILE_PATH', default)
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of current configuration (without sensitive data)"""
        return {
            'language': self.language,
            'max_file_size_mb': self.max_file_size_mb,
            'parallel_processing': self.parallel_processing,
            'max_concurrent_jobs': self.max_concurrent_jobs,
            'cleanup_temp_files': self.cleanup_temp_files,
            'enable_redis_queue': self.enable_redis_queue,
            'enable_file_monitoring': self.enable_file_monitoring,
            'log_level': self.log_level,
            'log_format': self.log_format,
            'rag_integration_available': self.rag_base_path is not None,
            'sync_integration_available': self.sync_base_path is not None
        }

# Global configuration instance
config = Config()