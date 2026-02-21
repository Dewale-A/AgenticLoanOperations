"""
FastAPI Application for AgenticLoanOperations.

Provides REST endpoints for loan operations processing.

Endpoints:
    POST /api/v1/process           - Process a loan file (full workflow)
    POST /api/v1/process/async     - Async processing with job tracking
    GET  /api/v1/jobs/{job_id}     - Check job status
    GET  /api/v1/health            - Health check
    GET  /api/v1/loans             - List available loan files
    GET  /api/v1/loans/{loan_id}   - Get loan file details
"""

import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config.settings import SAMPLE_LOANS_DIR, OUTPUT_DIR
from src.crew import LoanOperationsCrew
from src.models.loan_file import LoanFile, FundingStatus


# ============================================================================
# Pydantic Models (Request/Response)
# ============================================================================

class ProcessRequest(BaseModel):
    """Request to process a loan file."""
    loan_id: str = Field(..., description="Loan file ID (e.g., 'LOAN001')")
    verbose: bool = Field(default=False, description="Enable verbose output")


class ProcessResponse(BaseModel):
    """Response from loan processing."""
    loan_id: str
    status: str
    duration_seconds: float
    output_file: Optional[str] = None
    result_summary: str
    processed_at: str


class AsyncProcessResponse(BaseModel):
    """Response from async loan processing request."""
    job_id: str
    loan_id: str
    status: str
    message: str


class JobStatus(BaseModel):
    """Status of an async processing job."""
    job_id: str
    loan_id: str
    status: str  # pending, processing, completed, failed
    result: Optional[ProcessResponse] = None
    error: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None


class LoanSummary(BaseModel):
    """Summary of a loan file."""
    loan_id: str
    borrower_name: str
    loan_type: str
    loan_amount: float
    funding_status: str
    approval_date: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    timestamp: str
    version: str
    sample_loans_available: int


# ============================================================================
# In-memory job tracking (would use Redis/DB in production)
# ============================================================================

jobs: dict[str, JobStatus] = {}
executor = ThreadPoolExecutor(max_workers=3)


# ============================================================================
# Lifespan Management
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    # Startup
    output_dir = Path(OUTPUT_DIR)
    output_dir.mkdir(exist_ok=True)
    yield
    # Shutdown
    executor.shutdown(wait=True)


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="AgenticLoanOperations API",
    description="Multi-agent AI system for post-approval loan operations",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Helper Functions
# ============================================================================

def get_loan_file_path(loan_id: str) -> Path:
    """Get the path to a loan file."""
    # Try with .json extension
    path = Path(SAMPLE_LOANS_DIR) / f"{loan_id}.json"
    if path.exists():
        return path
    
    # Try without extension (maybe already has it)
    path = Path(SAMPLE_LOANS_DIR) / loan_id
    if path.exists():
        return path
    
    raise HTTPException(status_code=404, detail=f"Loan file not found: {loan_id}")


def process_loan_sync(loan_id: str, verbose: bool = False) -> ProcessResponse:
    """Process a loan file synchronously."""
    loan_path = get_loan_file_path(loan_id)
    start_time = datetime.now()
    
    loan_file = LoanFile.from_json(str(loan_path))
    crew = LoanOperationsCrew(loan_file, verbose=verbose)
    result = crew.run()
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    # Save output
    output_dir = Path(OUTPUT_DIR)
    output_file = output_dir / f"{loan_file.loan_id}_operations_report.md"
    
    with open(output_file, 'w') as f:
        f.write(f"# Loan Operations Report: {loan_file.loan_id}\n\n")
        f.write(f"**Generated:** {end_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**Processing Time:** {duration:.1f} seconds\n\n")
        f.write("---\n\n")
        f.write(str(result))
    
    return ProcessResponse(
        loan_id=loan_file.loan_id,
        status="completed",
        duration_seconds=round(duration, 2),
        output_file=str(output_file),
        result_summary=str(result)[:500] + "..." if len(str(result)) > 500 else str(result),
        processed_at=end_time.isoformat(),
    )


def process_loan_background(job_id: str, loan_id: str, verbose: bool):
    """Background task to process a loan."""
    jobs[job_id].status = "processing"
    
    try:
        result = process_loan_sync(loan_id, verbose)
        jobs[job_id].status = "completed"
        jobs[job_id].result = result
        jobs[job_id].completed_at = datetime.now().isoformat()
    except Exception as e:
        jobs[job_id].status = "failed"
        jobs[job_id].error = str(e)
        jobs[job_id].completed_at = datetime.now().isoformat()


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/api/v1/health", response_model=HealthResponse)
async def health_check():
    """Check API health and availability."""
    sample_dir = Path(SAMPLE_LOANS_DIR)
    loan_count = len(list(sample_dir.glob("*.json"))) if sample_dir.exists() else 0
    
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now().isoformat(),
        version="1.0.0",
        sample_loans_available=loan_count,
    )


@app.get("/api/v1/loans", response_model=list[LoanSummary])
async def list_loans():
    """List all available loan files."""
    sample_dir = Path(SAMPLE_LOANS_DIR)
    if not sample_dir.exists():
        return []
    
    loans = []
    for loan_path in sample_dir.glob("*.json"):
        try:
            loan_file = LoanFile.from_json(str(loan_path))
            loans.append(LoanSummary(
                loan_id=loan_file.loan_id,
                borrower_name=loan_file.borrower_name,
                loan_type=loan_file.loan_type,
                loan_amount=loan_file.loan_amount,
                funding_status=loan_file.funding_status.value,
                approval_date=loan_file.approval_date,
            ))
        except Exception:
            continue
    
    return loans


@app.get("/api/v1/loans/{loan_id}", response_model=LoanSummary)
async def get_loan(loan_id: str):
    """Get details of a specific loan file."""
    loan_path = get_loan_file_path(loan_id)
    loan_file = LoanFile.from_json(str(loan_path))
    
    return LoanSummary(
        loan_id=loan_file.loan_id,
        borrower_name=loan_file.borrower_name,
        loan_type=loan_file.loan_type,
        loan_amount=loan_file.loan_amount,
        funding_status=loan_file.funding_status.value,
        approval_date=loan_file.approval_date,
    )


@app.post("/api/v1/process", response_model=ProcessResponse)
async def process_loan(request: ProcessRequest):
    """
    Process a loan file through the full operations workflow (synchronous).
    
    This runs the complete multi-agent pipeline and returns when done.
    For long-running jobs, use /api/v1/process/async instead.
    """
    return process_loan_sync(request.loan_id, request.verbose)


@app.post("/api/v1/process/async", response_model=AsyncProcessResponse)
async def process_loan_async(request: ProcessRequest, background_tasks: BackgroundTasks):
    """
    Submit a loan for async processing.
    
    Returns a job ID immediately. Poll /api/v1/jobs/{job_id} for status.
    """
    # Verify loan exists
    get_loan_file_path(request.loan_id)
    
    job_id = str(uuid.uuid4())
    jobs[job_id] = JobStatus(
        job_id=job_id,
        loan_id=request.loan_id,
        status="pending",
        created_at=datetime.now().isoformat(),
    )
    
    # Submit to background thread
    executor.submit(process_loan_background, job_id, request.loan_id, request.verbose)
    
    return AsyncProcessResponse(
        job_id=job_id,
        loan_id=request.loan_id,
        status="pending",
        message="Job submitted. Poll /api/v1/jobs/{job_id} for status.",
    )


@app.get("/api/v1/jobs/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str):
    """Get the status of an async processing job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    
    return jobs[job_id]


# ============================================================================
# Run (for development)
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
