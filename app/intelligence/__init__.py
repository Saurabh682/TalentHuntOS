"""Intelligence package for Candidate DNA, AutoPilot continuous sourcing, Signal Detection, and Smart JD Writing."""

from app.intelligence.candidate_dna import (
    CandidateDNA,
    generate_candidate_dna,
    calculate_dna_similarity,
    find_similar_candidates,
)
from app.intelligence.auto_pilot import (
    AutoPilotScheduler,
    autopilot_scheduler,
    run_autopilot_hunt_job,
    start_global_autopilot,
)
from app.intelligence.signal_detector import (
    HiringSignal,
    detect_candidate_signals,
    simulate_signal_feed,
    rank_candidates_by_signal_readiness,
)
from app.intelligence.jd_writer import (
    JDBiasAnalysis,
    analyze_jd_bias,
    debias_jd,
    generate_optimized_jd,
    enhance_jd,
)

__all__ = [
    "CandidateDNA",
    "generate_candidate_dna",
    "calculate_dna_similarity",
    "find_similar_candidates",
    "AutoPilotScheduler",
    "autopilot_scheduler",
    "run_autopilot_hunt_job",
    "start_global_autopilot",
    "HiringSignal",
    "detect_candidate_signals",
    "simulate_signal_feed",
    "rank_candidates_by_signal_readiness",
    "JDBiasAnalysis",
    "analyze_jd_bias",
    "debias_jd",
    "generate_optimized_jd",
    "enhance_jd",
]
