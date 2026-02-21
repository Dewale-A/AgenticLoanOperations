"""Tests for the FastAPI endpoints."""

import pytest
from fastapi.testclient import TestClient

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.api.main import app


client = TestClient(app)


class TestHealthEndpoint:
    """Tests for the health check endpoint."""
    
    def test_health_returns_200(self):
        """Health endpoint should return 200."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200
    
    def test_health_returns_status(self):
        """Health response should include status."""
        response = client.get("/api/v1/health")
        data = response.json()
        assert data["status"] == "healthy"
    
    def test_health_returns_version(self):
        """Health response should include version."""
        response = client.get("/api/v1/health")
        data = response.json()
        assert "version" in data


class TestLoansEndpoint:
    """Tests for the loans listing endpoint."""
    
    def test_list_loans_returns_200(self):
        """List loans endpoint should return 200."""
        response = client.get("/api/v1/loans")
        assert response.status_code == 200
    
    def test_list_loans_returns_list(self):
        """List loans should return a list."""
        response = client.get("/api/v1/loans")
        assert isinstance(response.json(), list)
    
    def test_get_nonexistent_loan_returns_404(self):
        """Getting a non-existent loan should return 404."""
        response = client.get("/api/v1/loans/NONEXISTENT_LOAN_XYZ")
        assert response.status_code == 404


class TestProcessEndpoint:
    """Tests for the process endpoint (mocked - no actual LLM calls)."""
    
    def test_process_nonexistent_loan_returns_404(self):
        """Processing a non-existent loan should return 404."""
        response = client.post(
            "/api/v1/process",
            json={"loan_id": "NONEXISTENT_LOAN_XYZ"}
        )
        assert response.status_code == 404


class TestAsyncProcessEndpoint:
    """Tests for the async process endpoint."""
    
    def test_async_process_nonexistent_returns_404(self):
        """Async processing a non-existent loan should return 404."""
        response = client.post(
            "/api/v1/process/async",
            json={"loan_id": "NONEXISTENT_LOAN_XYZ"}
        )
        assert response.status_code == 404
    
    def test_get_nonexistent_job_returns_404(self):
        """Getting a non-existent job should return 404."""
        response = client.get("/api/v1/jobs/nonexistent-job-id")
        assert response.status_code == 404
