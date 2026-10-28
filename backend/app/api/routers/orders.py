"""Orders and Cartonization Analysis API Router."""

import json
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, File, Form, UploadFile
from backend.app.schemas.contracts import OrderAnalysisResponse, PackingRequest, PackingSolutionResponse
from backend.app.solver.cpsat_solver import solve_packing


router = APIRouter(prefix="/orders", tags=["Orders & Packing"])

# Paths to golden mock fixtures for instantaneous unblocking
FIXTURES_DIR = Path(__file__).resolve().parents[4] / "tests" / "fixtures"


def _load_fixture(filename: str) -> dict:
    with open(FIXTURES_DIR / filename, "r", encoding="utf-8") as f:
        return json.load(f)


@router.post("/analyze", response_model=OrderAnalysisResponse)
async def analyze_order(
    top_image: UploadFile = File(..., description="Top-down RGB image of packing station with ArUco sheet"),
    oblique_image: Optional[UploadFile] = File(None, description="Oblique 35-45 degree angle image"),
    capture_mode: str = Form("dual_photo"),
    enable_cloud_sam: bool = Form(False),
    enable_muse_semantics: bool = Form(True),
) -> OrderAnalysisResponse:
    """Analyze tabletop order capture: detect ArUco, segment items, measure 3D boxes, and extract AI semantics.

    In Milestone M0, this returns the golden fixture so Member 4 can immediately build against live API responses.
    Member 1 & Member 2 will wire live CV and Meta API pipelines here in Milestone M2.
    """
    sample_data = _load_fixture("order_analysis_sample.json")
    return OrderAnalysisResponse(**sample_data)


@router.post("/pack", response_model=PackingSolutionResponse)
async def pack_order(request: PackingRequest) -> PackingSolutionResponse:
    """Run 3D cartonization and packing solver on user-verified items, returning optimal box and step placements.

    Directly executes the deterministic Extreme-Point / CP-SAT solver and validates geometry.
    """
    return solve_packing(request)
