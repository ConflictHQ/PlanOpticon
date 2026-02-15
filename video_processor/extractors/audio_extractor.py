"""Audio extraction and processing module for video analysis."""
import logging
import os
import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

import librosa
import numpy as np
import soundfile as sf

logger = logging.getLogger(__name__)

class AudioExtractor:
    """Extract and process audio from video files."""
    
    def __init__(self, sample_rate: int = 16000, mono: bool = True):
        """
        Initialize the audio extractor.
        
        Parameters
        ----------
        sample_rate : int
            Target sample rate for extracted audio
        mono : bool
            Whether to convert audio to mono
        """
        self.sample_rate = sample_rate
        self.mono = mono
        
    def extract_audio(
        self, 
        video_path: Union[str, Path], 
        output_path: Optional[Union[str, Path]] = None, 
        format: str = "wav"
    ) -> Path:
        """
        Extract audio from video file.
        
        Parameters
        ----------
        video_path : str or Path
            Path to video file
        output_path : str or Path, optional
            Path to save extracted audio (if None, saves alongside video)
        format : str
            Audio format to save (wav, mp3, etc.)
            
        Returns
        -------
        Path
            Path to extracted audio file
        """
        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")
            
        # Generate output path if not provided
        if output_path is None:
            output_path = video_path.with_suffix(f".{format}")
        else:
            output_path = Path(output_path)
            
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Extract audio using ffmpeg
        try:
            cmd = [
                "ffmpeg", 
                "-i", str(video_path), 
                "-vn",  # No video
                "-acodec", "pcm_s16le",  # PCM 16-bit little-endian
                "-ar", str(self.sample_rate),  # Sample rate
                "-ac", "1" if self.mono else "2",  # Channels (mono or stereo)
                "-y",  # Overwrite output
                str(output_path)
            ]
            
            # Run ffmpeg command
            result = subprocess.run(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                check=True
            )
            
            logger.info(f"Extracted audio from {video_path} to {output_path}")
            return output_path
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to extract audio: {e.stderr.decode()}")
            raise RuntimeError(f"Failed to extract audio: {e.stderr.decode()}")
        except Exception as e:
            logger.error(f"Error extracting audio: {str(e)}")
            raise
            
    def load_audio(self, audio_path: Union[str, Path]) -> Tuple[np.ndarray, int]:
        """
        Load audio file into memory.
        
        Parameters
        ----------
        audio_path : str or Path
            Path to audio file
            
        Returns
        -------
        tuple
            (audio_data, sample_rate)
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
            
        # Load audio data
        audio_data, sr = librosa.load(
            audio_path, 
            sr=self.sample_rate if self.sample_rate else None,
            mono=self.mono
        )
        
        logger.info(f"Loaded audio from {audio_path}: shape={audio_data.shape}, sr={sr}")
        return audio_data, sr
        
    def get_audio_properties(self, audio_path: Union[str, Path]) -> Dict:
        """
        Get properties of audio file.
        
        Parameters
        ----------
        audio_path : str or Path
            Path to audio file
            
        Returns
        -------
        dict
            Audio properties (duration, sample_rate, channels, etc.)
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
            
        # Get audio info
        info = sf.info(audio_path)
        
        properties = {
            "duration": info.duration,
            "sample_rate": info.samplerate,
            "channels": info.channels,
            "format": info.format,
            "subtype": info.subtype,
            "path": str(audio_path)
        }
        
        return properties
        
    def segment_audio(
        self,
        audio_data: np.ndarray,
        sample_rate: int,
        segment_length_ms: int = 30000,
        overlap_ms: int = 0
    ) -> list:
        """
        Segment audio into chunks.
        
        Parameters
        ----------
        audio_data : np.ndarray
            Audio data
        sample_rate : int
            Sample rate of audio
        segment_length_ms : int
            Length of segments in milliseconds
        overlap_ms : int
            Overlap between segments in milliseconds
            
        Returns
        -------
        list
            List of audio segments as numpy arrays
        """
        # Convert ms to samples
        segment_length_samples = int(segment_length_ms * sample_rate / 1000)
        overlap_samples = int(overlap_ms * sample_rate / 1000)
        
        # Calculate hop length
        hop_length = segment_length_samples - overlap_samples
        
        # Initialize segments list
        segments = []
        
        # Generate segments
        for i in range(0, len(audio_data), hop_length):
            end_idx = min(i + segment_length_samples, len(audio_data))
            segment = audio_data[i:end_idx]
            
            # Only add if segment is long enough (at least 50% of target length)
            if len(segment) >= segment_length_samples * 0.5:
                segments.append(segment)
                
            # Break if we've reached the end
            if end_idx == len(audio_data):
                break
                
        logger.info(f"Segmented audio into {len(segments)} chunks")
        return segments
        
    def save_segment(
        self, 
        segment: np.ndarray, 
        output_path: Union[str, Path], 
        sample_rate: int
    ) -> Path:
        """
        Save audio segment to file.
        
        Parameters
        ----------
        segment : np.ndarray
            Audio segment data
        output_path : str or Path
            Path to save segment
        sample_rate : int
            Sample rate of segment
            
        Returns
        -------
        Path
            Path to saved segment
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        sf.write(output_path, segment, sample_rate)
        return output_path
