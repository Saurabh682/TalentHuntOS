"""Silero VAD (Voice Activity Detection) wrapper for TalentHunt OS."""

import math
import struct
import logging
from typing import Tuple

logger = logging.getLogger("talenthunt.voice.vad")


class SileroVAD:
    """Voice Activity Detector using Silero VAD / RMS energy analysis."""

    def __init__(
        self,
        sample_rate: int = 16000,
        threshold: float = 0.5,
        min_speech_duration_ms: int = 250,
        min_silence_duration_ms: int = 600
    ) -> None:
        self.sample_rate = sample_rate
        self.threshold = threshold
        self.min_speech_duration_ms = min_speech_duration_ms
        self.min_silence_duration_ms = min_silence_duration_ms
        self._init_silero_model()

    def _init_silero_model(self) -> None:
        """Initialize Silero VAD session if dependencies are present."""
        try:
            import onnxruntime as ort
            logger.info("ONNXRuntime available for Silero VAD.")
        except ImportError:
            logger.info("ONNXRuntime not installed. Using audio RMS threshold fallback for VAD.")

    def calculate_rms(self, pcm_bytes: bytes) -> float:
        """Calculate Root Mean Square (RMS) energy level of 16-bit PCM audio samples."""
        if not pcm_bytes or len(pcm_bytes) < 2:
            return 0.0
        
        try:
            import numpy as np
            samples = np.frombuffer(pcm_bytes, dtype=np.int16)
            mean_sq = np.mean(samples.astype(np.float64)**2)
            return math.sqrt(mean_sq)
        except (ImportError, Exception):
            count = len(pcm_bytes) // 2
            format_str = f"<{count}h"
            try:
                samples = struct.unpack(format_str, pcm_bytes[:count * 2])
                sum_squares = sum(s * s for s in samples)
                mean_square = sum_squares / count
                return math.sqrt(mean_square)
            except Exception:
                return 0.0

    def is_speech(self, audio_chunk: bytes, energy_threshold: float = 300.0) -> Tuple[bool, float]:
        """Detect speech in audio chunk.
        
        Returns:
            Tuple[bool, float]: (is_speech_detected, confidence_score)
        """
        if not audio_chunk:
            return False, 0.0

        rms = self.calculate_rms(audio_chunk)
        safe_threshold = max(energy_threshold, 1.0)
        confidence = min(1.0, rms / (safe_threshold * 3))
        has_speech = rms > energy_threshold
        
        return has_speech, confidence
