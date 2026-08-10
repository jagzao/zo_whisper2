import pytest
import os
from unittest.mock import patch
from core.config import Config, ConfigurationError

class TestConfig:
    """Test configuration management"""
    
    def test_config_with_all_required_vars(self):
        """Test config initialization with all required variables"""
        with patch.dict(os.environ, {
            'NOTION_API_KEY': 'test_key',
            'NOTION_DATABASE_ID': 'test_db_id',
            'EMAIL_SENDER': 'test@example.com',
            'EMAIL_PASSWORD': 'test_password',
            'EMAIL_RECEIVER': 'receiver@example.com'
        }):
            config = Config()
            assert config.notion_api_key == 'test_key'
            assert config.email_sender == 'test@example.com'
    
    def test_config_missing_required_vars(self):
        """Test config initialization with missing required variables"""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ConfigurationError) as excinfo:
                Config()
            assert "Missing required environment variables" in str(excinfo.value)
    
    def test_config_default_values(self):
        """Test config default values"""
        with patch.dict(os.environ, {
            'NOTION_API_KEY': 'test_key',
            'NOTION_DATABASE_ID': 'test_db_id',
            'EMAIL_SENDER': 'test@example.com',
            'EMAIL_PASSWORD': 'test_password',
            'EMAIL_RECEIVER': 'receiver@example.com'
        }):
            config = Config()
            assert config.language == 'es'
            assert config.max_file_size_mb == 500
            assert config.email_smtp_server == 'smtp.gmail.com'
            assert config.email_smtp_port == 587
    
    def test_config_boolean_parsing(self):
        """Test boolean configuration parsing"""
        with patch.dict(os.environ, {
            'NOTION_API_KEY': 'test_key',
            'NOTION_DATABASE_ID': 'test_db_id',
            'EMAIL_SENDER': 'test@example.com',
            'EMAIL_PASSWORD': 'test_password',
            'EMAIL_RECEIVER': 'receiver@example.com',
            'PARALLEL_PROCESSING': 'false',
            'CLEANUP_TEMP_FILES': 'true'
        }):
            config = Config()
            assert config.parallel_processing is False
            assert config.cleanup_temp_files is True
    
    def test_config_integer_parsing(self):
        """Test integer configuration parsing"""
        with patch.dict(os.environ, {
            'NOTION_API_KEY': 'test_key',
            'NOTION_DATABASE_ID': 'test_db_id',
            'EMAIL_SENDER': 'test@example.com',
            'EMAIL_PASSWORD': 'test_password',
            'EMAIL_RECEIVER': 'receiver@example.com',
            'MAX_FILE_SIZE_MB': '1000',
            'MAX_CONCURRENT_JOBS': '5'
        }):
            config = Config()
            assert config.max_file_size_mb == 1000
            assert config.max_concurrent_jobs == 5
    
    def test_get_summary(self):
        """Test configuration summary"""
        with patch.dict(os.environ, {
            'NOTION_API_KEY': 'test_key',
            'NOTION_DATABASE_ID': 'test_db_id',
            'EMAIL_SENDER': 'test@example.com',
            'EMAIL_PASSWORD': 'test_password',
            'EMAIL_RECEIVER': 'receiver@example.com'
        }):
            config = Config()
            summary = config.get_summary()
            
            assert 'language' in summary
            assert 'max_file_size_mb' in summary
            assert 'parallel_processing' in summary
            # Sensitive data should not be in summary
            assert 'NOTION_API_KEY' not in str(summary)
            assert 'EMAIL_PASSWORD' not in str(summary)