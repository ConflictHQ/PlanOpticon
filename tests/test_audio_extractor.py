"""Tests for the audio extractor module."""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pytest

from video_processor.extractors.audio_extractor import AudioExtractor

class TestAudioExtractor:
    """Test suite for AudioExtractor class."""
    
    def test_init(self):
        """Test initialization of AudioExtractor."""
        # Default parameters
        extractor = AudioExtractor()
        assert extractor.sample_rate == 16000
        assert extractor.mono is True
        
        # Custom parameters
        extractor = AudioExtractor(sample_rate=44100, mono=False)
        assert extractor.sample_rate == 44100
        assert extractor.mono is False
    
    @patch('subprocess.run')
    def test_extract_audio(self, mock_run):
        """Test audio extraction from video."""
        # Mock the subprocess.run call
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a dummy video file
            video_path = Path(temp_dir) / "test_video.mp4"
            with open(video_path, "wb") as f:
                f.write(b"dummy video content")
            
            # Extract audio
            extractor = AudioExtractor()
            
            # Test with default output path
            output_path = extractor.extract_audio(video_path)
            assert output_path == video_path.with_suffix(".wav")
            
            # Test with custom output path
            custom_output = Path(temp_dir) / "custom_audio.wav"
            output_path = extractor.extract_audio(video_path, custom_output)
            assert output_path == custom_output
            
            # Verify subprocess.run was called with correct arguments
            mock_run.assert_called()
            args, kwargs = mock_run.call_args
            assert "ffmpeg" in args[0]
            assert "-i" in args[0]
            assert str(video_path) in args[0]
    
    @patch('soundfile.info')
    def test_get_audio_properties(self, mock_sf_info):
        """Test getting audio properties."""
        # Mock soundfile.info
        mock_info = MagicMock()
        mock_info.duration = 10.5
        mock_info.samplerate = 16000
        mock_info.channels = 1
        mock_info.format = "WAV"
        mock_info.subtype = "PCM_16"
        mock_sf_info.return_value = mock_info
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a dummy audio file
            audio_path = Path(temp_dir) / "test_audio.wav"
            with open(audio_path, "wb") as f:
                f.write(b"dummy audio content")
            
            # Get properties
            extractor = AudioExtractor()
            props = extractor.get_audio_properties(audio_path)
            
            # Verify properties
            assert props["duration"] == 10.5
            assert props["sample_rate"] == 16000
            assert props["channels"] == 1
            assert props["format"] == "WAV"
            assert props["subtype"] == "PCM_16"
            assert props["path"] == str(audio_path)
    
    def test_segment_audio(self):
        """Test audio segmentation."""
        # Create a dummy audio array (1 second at 16kHz)
        audio_data = np.ones(16000)
        sample_rate = 16000
        
        extractor = AudioExtractor()
        
        # Test with 500ms segments, no overlap
        segments = extractor.segment_audio(
            audio_data, 
            sample_rate, 
            segment_length_ms=500, 
            overlap_ms=0
        )
        
        # Should produce 2 segments of 8000 samples each
        assert len(segments) == 2
        assert len(segments[0]) == 8000
        assert len(segments[1]) == 8000
        
        # Test with 600ms segments, 100ms overlap
        segments = extractor.segment_audio(
            audio_data, 
            sample_rate, 
            segment_length_ms=600, 
            overlap_ms=100
        )
        
        # Should produce 2 segments (with overlap)
        assert len(segments) == 2 