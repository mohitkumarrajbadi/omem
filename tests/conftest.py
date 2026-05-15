import os
import tempfile
import pytest
import shutil

@pytest.fixture(autouse=True)
def isolated_omem_db(monkeypatch):
    """Ensure every test gets a fresh, isolated database if it uses default SQLite."""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "brain.db")
    
    original_expanduser = os.path.expanduser
    def mock_expanduser(path):
        if path == "~/.omem/brain.db":
            return db_path
        return original_expanduser(path)
        
    monkeypatch.setattr(os.path, "expanduser", mock_expanduser)
    
    yield
    
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)
