import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from core.file_manager import FileManager, FileValidationError

class TestFileManager:
    """Test file management functionality"""
    
    @pytest.fixture
    def file_manager(self):
        """Create a file manager for testing"""
        return FileManager(max_size_mb=1, cleanup_temp=False)  # 1MB for testing
    
    @pytest.fixture
    def temp_video_file(self):
        """Create a temporary video file for testing"""
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
            # Write some dummy data
            f.write(b'dummy video content' * 1000)  # Small file
            f.flush()
            yield f.name
        
        # Cleanup
        try:
            os.unlink(f.name)
        except FileNotFoundError:
            pass
    
    @pytest.fixture
    def temp_large_file(self):
        """Create a temporary large file for testing"""
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
            # Write data larger than 1MB
            f.write(b'x' * (2 * 1024 * 1024))  # 2MB
            f.flush()
            yield f.name
        
        # Cleanup
        try:
            os.unlink(f.name)
        except FileNotFoundError:
            pass
    
    def test_validate_file_success(self, file_manager, temp_video_file):
        """Test successful file validation"""
        with patch('magic.from_file', return_value='video/mp4'):
            result = file_manager.validate_file(temp_video_file)
            
            assert result['name'] == Path(temp_video_file).name
            assert result['extension'] == '.mp4'
            assert result['is_video'] is True
            assert result['is_audio'] is False
            assert 'hash' in result
            assert 'size_bytes' in result
    
    def test_validate_file_not_exists(self, file_manager):
        """Test validation of non-existent file"""
        with pytest.raises(FileValidationError) as excinfo:
            file_manager.validate_file('/non/existent/file.mp4')
        assert "File does not exist" in str(excinfo.value)
    
    def test_validate_file_too_large(self, file_manager, temp_large_file):
        """Test validation of file that's too large"""
        with pytest.raises(FileValidationError) as excinfo:
            file_manager.validate_file(temp_large_file)
        assert "File too large" in str(excinfo.value)
    
    def test_validate_file_empty(self, file_manager):
        """Test validation of empty file"""
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
            # Don't write anything, file will be empty
            pass
        
        try:
            with pytest.raises(FileValidationError) as excinfo:
                file_manager.validate_file(f.name)
            assert "File is empty" in str(excinfo.value)
        finally:
            os.unlink(f.name)
    
    def test_validate_file_unsupported_extension(self, file_manager):
        """Test validation of file with unsupported extension"""
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as f:
            f.write(b'some text content')
            f.flush()
        
        try:
            with pytest.raises(FileValidationError) as excinfo:
                file_manager.validate_file(f.name)
            assert "Unsupported file extension" in str(excinfo.value)
        finally:
            os.unlink(f.name)
    
    def test_register_and_cleanup_temp_file(self, file_manager, temp_video_file):
        """Test temp file registration and cleanup"""
        # Register temp file
        file_manager.register_temp_file(temp_video_file)
        
        # Verify file exists
        assert Path(temp_video_file).exists()
        
        # Cleanup temp file
        success = file_manager.cleanup_temp_file(temp_video_file)
        assert success is True
        
        # Verify file is deleted
        assert not Path(temp_video_file).exists()
    
    def test_cleanup_nonexistent_temp_file(self, file_manager):
        """Test cleanup of non-existent temp file"""
        success = file_manager.cleanup_temp_file('/non/existent/file.mp4')
        assert success is False
    
    def test_get_file_stats(self, file_manager):
        """Test file statistics gathering"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create some test files
            video_file = Path(temp_dir) / 'test.mp4'
            audio_file = Path(temp_dir) / 'test.mp3'
            text_file = Path(temp_dir) / 'test.txt'
            
            video_file.write_bytes(b'video' * 1000)
            audio_file.write_bytes(b'audio' * 500)
            text_file.write_bytes(b'text' * 100)
            
            stats = file_manager.get_file_stats(temp_dir)
            
            assert stats['total_files'] == 3
            assert stats['video_files'] == 1
            assert stats['audio_files'] == 1
            assert stats['supported_files'] == 2
            assert stats['unsupported_files'] == 1
            assert '.mp4' in stats['file_types']
            assert '.mp3' in stats['file_types']
            assert '.txt' in stats['file_types']
    
    def test_get_file_stats_nonexistent_directory(self, file_manager):
        """Test file stats for non-existent directory"""
        stats = file_manager.get_file_stats('/non/existent/directory')
        assert 'error' in stats
    
    @patch('shutil.disk_usage')
    def test_check_disk_space(self, mock_disk_usage, file_manager):
        """Test disk space checking"""
        # Mock disk usage: (total, used, free) in bytes
        mock_disk_usage.return_value = (10 * 1024**3, 5 * 1024**3, 5 * 1024**3)  # 10GB total, 5GB free
        
        with tempfile.TemporaryDirectory() as temp_dir:
            result = file_manager.check_disk_space(temp_dir, required_mb=1000)
            
            assert result['free_mb'] == 5 * 1024  # 5GB in MB
            assert result['total_mb'] == 10 * 1024  # 10GB in MB
            assert result['sufficient_space'] is True
            assert result['required_mb'] == 1000
    
    @patch('shutil.disk_usage')
    def test_check_disk_space_insufficient(self, mock_disk_usage, file_manager):
        """Test disk space checking with insufficient space"""
        # Mock disk usage: very little free space
        mock_disk_usage.return_value = (10 * 1024**3, 9.9 * 1024**3, 0.1 * 1024**3)  # 100MB free
        
        with tempfile.TemporaryDirectory() as temp_dir:
            result = file_manager.check_disk_space(temp_dir, required_mb=1000)
            
            assert result['sufficient_space'] is False
            assert result['free_mb'] < 1000