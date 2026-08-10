import pytest
import tempfile
import os
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
from core.config import Config
from core.file_manager import FileManager
from core.database.models import DatabaseManager, TranscriptionJob
from core.performance.queue_manager import QueueManager, Job, JobStatus
from datetime import datetime

class TestIntegration:
    """Integration tests for the complete workflow"""
    
    @pytest.fixture
    def temp_environment(self):
        """Set up temporary environment for integration tests"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create directory structure
            videos_dir = temp_path / "Videos" / "TestProject"
            audio_dir = temp_path / "audio" / "TestProject"
            output_dir = temp_path / "CarpetaTranscripciones" / "TestProject"
            
            videos_dir.mkdir(parents=True)
            audio_dir.mkdir(parents=True)
            output_dir.mkdir(parents=True)
            
            # Create test video file
            test_video = videos_dir / "test_video.mp4"
            test_video.write_bytes(b"fake video content" * 1000)
            
            yield {
                'temp_dir': temp_path,
                'videos_dir': videos_dir,
                'audio_dir': audio_dir,
                'output_dir': output_dir,
                'test_video': test_video
            }
    
    @pytest.fixture
    def integration_config(self):
        """Mock configuration for integration tests"""
        with patch.dict(os.environ, {
            'NOTION_API_KEY': 'test_key',
            'NOTION_DATABASE_ID': 'test_db_id',
            'EMAIL_SENDER': 'test@example.com',
            'EMAIL_PASSWORD': 'test_password',
            'EMAIL_RECEIVER': 'receiver@example.com',
            'MAX_FILE_SIZE_MB': '10',
            'PARALLEL_PROCESSING': 'true',
            'CLEANUP_TEMP_FILES': 'true'
        }):
            yield Config()
    
    def test_file_validation_workflow(self, temp_environment, integration_config):
        """Test complete file validation workflow"""
        file_manager = FileManager(
            max_size_mb=integration_config.max_file_size_mb,
            cleanup_temp=integration_config.cleanup_temp_files
        )
        
        test_video = temp_environment['test_video']
        
        # Mock magic.from_file to return valid MIME type
        with patch('magic.from_file', return_value='video/mp4'):
            # Validate file
            validation_result = file_manager.validate_file(str(test_video))
            
            assert validation_result['is_video'] is True
            assert validation_result['extension'] == '.mp4'
            assert validation_result['size_mb'] > 0
            assert len(validation_result['hash']) > 0
            
            # Register as temp file
            file_manager.register_temp_file(str(test_video))
            
            # Check file stats for directory
            stats = file_manager.get_file_stats(str(temp_environment['videos_dir'].parent))
            assert stats['supported_files'] >= 1
            assert stats['video_files'] >= 1
    
    def test_database_job_lifecycle(self, temp_environment):
        """Test complete database job lifecycle"""
        # Create temporary database
        db_path = temp_environment['temp_dir'] / "test.db"
        db_manager = DatabaseManager(str(db_path))
        
        # Create job
        job = TranscriptionJob(
            id="integration-test-job",
            file_path=str(temp_environment['test_video']),
            project_name="TestProject",
            file_name="test_video.mp4",
            status="queued",
            created_at=datetime.now(),
            file_size_bytes=len(b"fake video content" * 1000),
            file_hash="test-hash"
        )
        
        # Test job creation
        assert db_manager.create_job(job) is True
        
        # Test job retrieval
        retrieved_job = db_manager.get_job(job.id)
        assert retrieved_job is not None
        assert retrieved_job.status == "queued"
        
        # Test job status update
        update_success = db_manager.update_job(job.id, {
            "status": "processing",
            "started_at": datetime.now()
        })
        assert update_success is True
        
        # Test final completion
        completion_time = datetime.now()
        update_success = db_manager.update_job(job.id, {
            "status": "completed",
            "completed_at": completion_time,
            "processing_time_seconds": 45.5,
            "transcription_path": str(temp_environment['output_dir'] / "test_video.txt")
        })
        assert update_success is True
        
        # Verify final state
        final_job = db_manager.get_job(job.id)
        assert final_job.status == "completed"
        assert final_job.processing_time_seconds == 45.5
        assert final_job.transcription_path is not None
        
        # Test statistics
        stats = db_manager.get_processing_statistics(days=1)
        assert stats['total_jobs'] >= 1
        assert stats['completed_jobs'] >= 1
    
    def test_queue_manager_integration(self, temp_environment):
        """Test queue manager integration (without Redis)"""
        # Create queue manager that will fall back to direct processing
        queue_manager = QueueManager(redis_url="redis://nonexistent:6379", max_workers=2)
        
        # Verify it's not connected (will use fallback)
        assert queue_manager.is_connected() is False
        
        # Mock handler
        processed_files = []
        def mock_handler(file_path):
            processed_files.append(file_path)
            time.sleep(0.1)  # Simulate processing time
        
        # Register handler
        queue_manager.register_handler("transcription", mock_handler)
        
        # Create job
        job = Job(
            id="test-queue-job",
            task_type="transcription",
            file_path=str(temp_environment['test_video']),
            project_name="TestProject",
            created_at=datetime.now()
        )
        
        # Enqueue job (should process directly)
        success = queue_manager.enqueue_job(job)
        assert success is True
        
        # Verify file was processed
        assert str(temp_environment['test_video']) in processed_files
    
    @patch('core.transcription.transcription_provider.transcribe')
    @patch('core.summary.summary_provider.generate_summary')
    @patch('core.notifier.email_notifier.send_email')
    def test_end_to_end_workflow_simulation(self, mock_email, mock_summary, mock_transcribe, 
                                          temp_environment, integration_config):
        """Simulate end-to-end workflow without actual transcription"""
        
        # Mock the heavy operations
        mock_transcribe.return_value = "Mocked transcription text"
        mock_summary.return_value = "Mocked summary text"
        mock_email.return_value = True
        
        # Set up components
        file_manager = FileManager(max_size_mb=10)
        db_path = temp_environment['temp_dir'] / "workflow.db"
        db_manager = DatabaseManager(str(db_path))
        
        test_video = temp_environment['test_video']
        output_file = temp_environment['output_dir'] / "test_video.txt"
        
        # Step 1: File validation
        with patch('magic.from_file', return_value='video/mp4'):
            validation_result = file_manager.validate_file(str(test_video))
            assert validation_result['is_video'] is True
        
        # Step 2: Create database job
        job = TranscriptionJob(
            id="e2e-test-job",
            file_path=str(test_video),
            project_name="TestProject",
            file_name="test_video.mp4",
            status="queued",
            created_at=datetime.now(),
            file_size_bytes=validation_result['size_bytes'],
            file_hash=validation_result['hash']
        )
        
        db_manager.create_job(job)
        
        # Step 3: Simulate processing
        db_manager.update_job(job.id, {
            "status": "processing",
            "started_at": datetime.now()
        })
        
        # Create output file to simulate transcription
        output_file.write_text("This is a mocked transcription.")
        
        # Step 4: Complete processing
        processing_time = 30.5
        db_manager.update_job(job.id, {
            "status": "completed",
            "completed_at": datetime.now(),
            "processing_time_seconds": processing_time,
            "transcription_path": str(output_file)
        })
        
        # Step 5: Verify complete workflow
        final_job = db_manager.get_job(job.id)
        assert final_job.status == "completed"
        assert final_job.transcription_path == str(output_file)
        assert output_file.exists()
        
        # Verify statistics
        stats = db_manager.get_processing_statistics(days=1)
        assert stats['total_jobs'] >= 1
        assert stats['completed_jobs'] >= 1
        assert stats['success_rate'] > 0
    
    def test_error_handling_workflow(self, temp_environment):
        """Test error handling in the workflow"""
        db_path = temp_environment['temp_dir'] / "error_test.db"
        db_manager = DatabaseManager(str(db_path))
        
        # Create job that will fail
        job = TranscriptionJob(
            id="error-test-job",
            file_path="/nonexistent/file.mp4",
            project_name="ErrorTest",
            file_name="nonexistent.mp4",
            status="queued",
            created_at=datetime.now()
        )
        
        db_manager.create_job(job)
        
        # Simulate processing start
        db_manager.update_job(job.id, {
            "status": "processing",
            "started_at": datetime.now()
        })
        
        # Simulate failure
        db_manager.update_job(job.id, {
            "status": "failed",
            "completed_at": datetime.now(),
            "error_message": "File not found: /nonexistent/file.mp4"
        })
        
        # Verify error handling
        failed_job = db_manager.get_job(job.id)
        assert failed_job.status == "failed"
        assert "File not found" in failed_job.error_message
        
        # Check statistics include the failure
        stats = db_manager.get_processing_statistics(days=1)
        assert stats['failed_jobs'] >= 1
    
    def test_duplicate_file_handling(self, temp_environment):
        """Test duplicate file detection and handling"""
        db_path = temp_environment['temp_dir'] / "duplicate_test.db"
        db_manager = DatabaseManager(str(db_path))
        file_manager = FileManager()
        
        test_video = temp_environment['test_video']
        
        # Calculate file hash
        with patch('magic.from_file', return_value='video/mp4'):
            validation_result = file_manager.validate_file(str(test_video))
            file_hash = validation_result['hash']
        
        # Create first job (completed)
        job1 = TranscriptionJob(
            id="first-job",
            file_path=str(test_video),
            project_name="TestProject",
            file_name="test_video.mp4",
            status="completed",
            created_at=datetime.now(),
            file_hash=file_hash
        )
        db_manager.create_job(job1)
        
        # Check for duplicate
        duplicate = db_manager.check_duplicate_file(file_hash)
        assert duplicate is not None
        assert duplicate.id == "first-job"
        
        # Simulate handling duplicate (should not create new job)
        if duplicate:
            # Log that file was already processed
            assert duplicate.status == "completed"