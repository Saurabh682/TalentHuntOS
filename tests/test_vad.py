import pytest
import struct
import math
import sys
from unittest.mock import patch
from app.voice.vad import SileroVAD

def test_silero_vad_init_default():
    vad = SileroVAD()
    assert vad.sample_rate == 16000
    assert vad.threshold == 0.5
    assert vad.min_speech_duration_ms == 250
    assert vad.min_silence_duration_ms == 600

def test_silero_vad_init_custom():
    vad = SileroVAD(sample_rate=8000, threshold=0.8, min_speech_duration_ms=100, min_silence_duration_ms=200)
    assert vad.sample_rate == 8000
    assert vad.threshold == 0.8
    assert vad.min_speech_duration_ms == 100
    assert vad.min_silence_duration_ms == 200

def test_init_silero_model_onnxruntime_available(caplog):
    import logging
    # Need to set log level to INFO to capture the log
    caplog.set_level(logging.INFO, logger="talenthunt.voice.vad")
    
    with patch.dict('sys.modules', {'onnxruntime': type('MockOnnx', (object,), {})()}):
        vad = SileroVAD()
        assert "ONNXRuntime available for Silero VAD." in caplog.text

def test_init_silero_model_onnxruntime_missing(caplog):
    import logging
    caplog.set_level(logging.INFO, logger="talenthunt.voice.vad")
    
    with patch.dict('sys.modules', {'onnxruntime': None}):
        vad = SileroVAD()
        assert "ONNXRuntime not installed. Using audio RMS threshold fallback for VAD." in caplog.text

def test_calculate_rms_empty():
    vad = SileroVAD()
    assert vad.calculate_rms(b'') == 0.0
    assert vad.calculate_rms(b'1') == 0.0

def test_calculate_rms_valid():
    vad = SileroVAD()
    pcm_bytes = struct.pack("<2h", 1000, -1000)
    rms = vad.calculate_rms(pcm_bytes)
    assert math.isclose(rms, 1000.0)

def test_calculate_rms_odd_length():
    vad = SileroVAD()
    pcm_bytes = struct.pack("<1h", 1000) + b'\x00'
    rms = vad.calculate_rms(pcm_bytes)
    assert math.isclose(rms, 1000.0)

def test_calculate_rms_exception():
    vad = SileroVAD()
    with patch('struct.unpack', side_effect=Exception("Test Exception")):
        assert vad.calculate_rms(b'\x00\x00') == 0.0

def test_is_speech_empty():
    vad = SileroVAD()
    assert vad.is_speech(b'') == (False, 0.0)
    assert vad.is_speech(None) == (False, 0.0)

def test_is_speech_no_speech():
    vad = SileroVAD()
    pcm_bytes = struct.pack("<1h", 100)
    has_speech, confidence = vad.is_speech(pcm_bytes, energy_threshold=300.0)
    assert has_speech is False
    assert math.isclose(confidence, 100.0 / 900.0)

def test_is_speech_has_speech():
    vad = SileroVAD()
    pcm_bytes = struct.pack("<1h", 1000)
    has_speech, confidence = vad.is_speech(pcm_bytes, energy_threshold=300.0)
    assert has_speech is True
    assert math.isclose(confidence, 1.0)

def test_is_speech_safe_threshold():
    vad = SileroVAD()
    pcm_bytes = struct.pack("<1h", 2)
    has_speech, confidence = vad.is_speech(pcm_bytes, energy_threshold=0.0)
    assert has_speech is True
    assert math.isclose(confidence, 2.0 / 3.0)
