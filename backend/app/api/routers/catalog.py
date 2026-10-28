"""Carton Catalog API Router."""

from typing import List
from fastapi import APIRouter
from backend.app.schemas.contracts import CartonSpec
from backend.app.solver.carton_catalog import STANDARD_CARTONS


router = APIRouter(prefix="/catalog", tags=["Carton Catalog"])


@router.get("/cartons", response_model=List[CartonSpec])
async def list_cartons() -> List[CartonSpec]:
    """Retrieve the standard finite corrugated carton catalog."""
    return STANDARD_CARTONS
