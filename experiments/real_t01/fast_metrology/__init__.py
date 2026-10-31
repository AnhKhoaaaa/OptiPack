"""Fast 3D Metrology Module: Precomputed SDF & Closed-form Parallax Initializer.

Phase 0 Gate - Stage 0B for OptiPack Computer Vision (Member 1).
Provides sub-150ms CPU cuboid fitting from two calibrated views using:
- Closed-form 1ms geometric parallax height & footprint initializer
- Precomputed Signed Distance Field (SDF) rasterization on ROI crops
- Vectorized Levenberg-Marquardt optimization without in-loop rendering
"""
from experiments.real_t01.fast_metrology.initializer import ClosedFormInitializer
from experiments.real_t01.fast_metrology.fast_sdf_fitter import FastSDFFitter

__all__ = ["ClosedFormInitializer", "FastSDFFitter"]

