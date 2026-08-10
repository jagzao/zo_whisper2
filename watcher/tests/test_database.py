import pytest
import tempfile
import os
from datetime import datetime, timedelta
from pathlib import Path
from core.database.models import DatabaseManager, TranscriptionJob, ProcessingStats

class TestDatabaseManager:
    """Test database management functionality"""
    
    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        db_manager = DatabaseManager(db_path)
        yield db_manager
        
        # Cleanup
        try:
            os.unlink(db_path)
        except FileNotFoundError:
            pass
    
    @pytest.fixture
    def sample_job(self):
        """Create a sample transcription job"""
        return TranscriptionJob(
            id="test-job-123",
            file_path="/app/Videos/test.mp4",
            project_name="TestProject",
            file_name="test.mp4",
            status="queued",
            created_at=datetime.now(),
            file_size_bytes=1024*1024,  # 1MB
            file_hash="test-hash-123",
            metadata={"test": "data"}
        )
    
    def test_database_initialization(self, temp_db):
        """Test database initialization"""
        # Database should be initialized without errors
        assert temp_db.db_path.exists()
        
        # Check database size info
        size_info = temp_db.get_database_size()
        assert 'size_bytes' in size_info
        assert 'jobs_count' in size_info
        assert size_info['jobs_count'] == 0
    
    def test_create_and_get_job(self, temp_db, sample_job):
        """Test job creation and retrieval"""
        # Create job
        success = temp_db.create_job(sample_job)
        assert success is True
        
        # Retrieve job
        retrieved_job = temp_db.get_job(sample_job.id)
        assert retrieved_job is not None
        assert retrieved_job.id == sample_job.id
        assert retrieved_job.file_path == sample_job.file_path
        assert retrieved_job.project_name == sample_job.project_name
        assert retrieved_job.status == sample_job.status
        assert retrieved_job.metadata == sample_job.metadata
    
    def test_get_nonexistent_job(self, temp_db):
        """Test retrieval of non-existent job"""
        job = temp_db.get_job("nonexistent-id")
        assert job is None
    
    def test_update_job(self, temp_db, sample_job):
        """Test job updating"""
        # Create job
        temp_db.create_job(sample_job)
        
        # Update job
        updates = {
            "status": "processing",
            "started_at": datetime.now(),
            "processing_time_seconds": 45.5
        }
        success = temp_db.update_job(sample_job.id, updates)
        assert success is True
        
        # Verify updates
        updated_job = temp_db.get_job(sample_job.id)
        assert updated_job.status == "processing"
        assert updated_job.started_at is not None
        assert updated_job.processing_time_seconds == 45.5
    
    def test_update_nonexistent_job(self, temp_db):
        """Test updating non-existent job"""
        success = temp_db.update_job("nonexistent-id", {"status": "completed"})
        assert success is False
    
    def test_get_jobs_by_status(self, temp_db):
        """Test retrieving jobs by status"""
        # Create jobs with different statuses
        job1 = TranscriptionJob(
            id="job1", file_path="/test1.mp4", project_name="Test", 
            file_name="test1.mp4", status="queued", created_at=datetime.now()
        )
        job2 = TranscriptionJob(
            id="job2", file_path="/test2.mp4", project_name="Test",
            file_name="test2.mp4", status="completed", created_at=datetime.now()
        )
        job3 = TranscriptionJob(
            id="job3", file_path="/test3.mp4", project_name="Test",
            file_name="test3.mp4", status="queued", created_at=datetime.now()
        )
        
        temp_db.create_job(job1)
        temp_db.create_job(job2)
        temp_db.create_job(job3)
        
        # Get queued jobs
        queued_jobs = temp_db.get_jobs_by_status("queued")
        assert len(queued_jobs) == 2
        assert all(job.status == "queued" for job in queued_jobs)
        
        # Get completed jobs
        completed_jobs = temp_db.get_jobs_by_status("completed")
        assert len(completed_jobs) == 1
        assert completed_jobs[0].status == "completed"
    
    def test_get_jobs_by_project(self, temp_db):
        """Test retrieving jobs by project"""
        # Create jobs for different projects
        job1 = TranscriptionJob(
            id="job1", file_path="/test1.mp4", project_name="ProjectA",
            file_name="test1.mp4", status="queued", created_at=datetime.now()
        )
        job2 = TranscriptionJob(
            id="job2", file_path="/test2.mp4", project_name="ProjectB",
            file_name="test2.mp4", status="queued", created_at=datetime.now()
        )
        job3 = TranscriptionJob(
            id="job3", file_path="/test3.mp4", project_name="ProjectA",
            file_name="test3.mp4", status="completed", created_at=datetime.now()
        )
        
        temp_db.create_job(job1)
        temp_db.create_job(job2)
        temp_db.create_job(job3)
        
        # Get jobs for ProjectA
        project_a_jobs = temp_db.get_jobs_by_project("ProjectA")
        assert len(project_a_jobs) == 2
        assert all(job.project_name == "ProjectA" for job in project_a_jobs)
        
        # Get jobs for ProjectB
        project_b_jobs = temp_db.get_jobs_by_project("ProjectB")
        assert len(project_b_jobs) == 1
        assert project_b_jobs[0].project_name == "ProjectB"
    
    def test_check_duplicate_file(self, temp_db):
        """Test duplicate file detection"""
        # Create completed job
        job = TranscriptionJob(
            id="job1", file_path="/test.mp4", project_name="Test",
            file_name="test.mp4", status="completed", created_at=datetime.now(),
            file_hash="duplicate-hash"
        )
        temp_db.create_job(job)
        
        # Check for duplicate
        duplicate = temp_db.check_duplicate_file("duplicate-hash")
        assert duplicate is not None
        assert duplicate.id == job.id
        
        # Check for non-existent hash
        no_duplicate = temp_db.check_duplicate_file("unique-hash")
        assert no_duplicate is None
        
        # Create job with same hash but not completed
        job2 = TranscriptionJob(
            id="job2", file_path="/test2.mp4", project_name="Test",
            file_name="test2.mp4", status="failed", created_at=datetime.now(),
            file_hash="duplicate-hash"
        )
        temp_db.create_job(job2)
        
        # Should still only return the completed one
        duplicate = temp_db.check_duplicate_file("duplicate-hash")
        assert duplicate.id == job.id  # Should be the completed job
    
    def test_get_recent_jobs(self, temp_db):
        """Test retrieving recent jobs"""
        # Create jobs at different times
        now = datetime.now()
        job1 = TranscriptionJob(
            id="job1", file_path="/test1.mp4", project_name="Test",
            file_name="test1.mp4", status="completed", created_at=now - timedelta(hours=2)
        )
        job2 = TranscriptionJob(
            id="job2", file_path="/test2.mp4", project_name="Test",
            file_name="test2.mp4", status="completed", created_at=now - timedelta(hours=1)
        )
        job3 = TranscriptionJob(
            id="job3", file_path="/test3.mp4", project_name="Test",
            file_name="test3.mp4", status="completed", created_at=now
        )
        
        temp_db.create_job(job1)
        temp_db.create_job(job2)
        temp_db.create_job(job3)
        
        # Get recent jobs
        recent_jobs = temp_db.get_recent_jobs(limit=10)
        assert len(recent_jobs) == 3
        
        # Should be ordered by created_at DESC (most recent first)
        assert recent_jobs[0].id == "job3"
        assert recent_jobs[1].id == "job2" 
        assert recent_jobs[2].id == "job1"
    
    def test_record_stats(self, temp_db):
        """Test recording processing statistics"""
        stats = ProcessingStats(
            id=1,
            timestamp=datetime.now(),
            files_processed=10,
            files_failed=1,
            average_processing_time=45.5,
            queue_size=3,
            system_memory_mb=1024.0,
            system_cpu_percent=25.5,
            disk_free_gb=500.0
        )
        
        success = temp_db.record_stats(stats)
        assert success is True
    
    def test_get_processing_statistics(self, temp_db):
        """Test getting processing statistics"""
        # Create some test jobs
        now = datetime.now()
        
        # Completed job
        job1 = TranscriptionJob(
            id="job1", file_path="/test1.mp4", project_name="ProjectA",
            file_name="test1.mp4", status="completed", created_at=now,
            processing_time_seconds=30.0, file_size_bytes=1024*1024
        )
        
        # Failed job
        job2 = TranscriptionJob(
            id="job2", file_path="/test2.mp4", project_name="ProjectA",
            file_name="test2.mp4", status="failed", created_at=now,
            processing_time_seconds=15.0, file_size_bytes=512*1024
        )
        
        # Job from different project
        job3 = TranscriptionJob(
            id="job3", file_path="/test3.mp4", project_name="ProjectB",
            file_name="test3.mp4", status="completed", created_at=now,
            processing_time_seconds=60.0, file_size_bytes=2048*1024
        )
        
        temp_db.create_job(job1)
        temp_db.create_job(job2)
        temp_db.create_job(job3)
        
        # Get statistics
        stats = temp_db.get_processing_statistics(days=7)
        
        assert stats['total_jobs'] == 3
        assert stats['completed_jobs'] == 2
        assert stats['failed_jobs'] == 1
        assert stats['success_rate'] == (2/3) * 100
        assert len(stats['projects']) == 2
        
        # Check project breakdown
        project_names = [p['name'] for p in stats['projects']]
        assert 'ProjectA' in project_names
        assert 'ProjectB' in project_names
    
    def test_cleanup_old_jobs(self, temp_db):
        """Test cleaning up old jobs"""
        now = datetime.now()
        old_date = now - timedelta(days=100)  # Very old
        
        # Create old completed job
        old_job = TranscriptionJob(
            id="old-job", file_path="/old.mp4", project_name="Test",
            file_name="old.mp4", status="completed", 
            created_at=old_date, completed_at=old_date
        )
        
        # Create recent completed job
        recent_job = TranscriptionJob(
            id="recent-job", file_path="/recent.mp4", project_name="Test",
            file_name="recent.mp4", status="completed",
            created_at=now, completed_at=now
        )
        
        temp_db.create_job(old_job)
        temp_db.create_job(recent_job)
        
        # Cleanup jobs older than 90 days
        deleted_count = temp_db.cleanup_old_jobs(days_to_keep=90)
        assert deleted_count == 1
        
        # Verify old job is gone, recent job remains
        assert temp_db.get_job("old-job") is None
        assert temp_db.get_job("recent-job") is not None