"""Tests for the frame extractor module."""

import os
import tempfile

import numpy as np
import pytest

from video_processor.extractors.frame_extractor import (
    calculate_frame_difference,
    is_gpu_available,
    save_frames,
)


# Create dummy test frames
@pytest.fixture
def dummy_frames():
    # Create a list of dummy frames with different content
    frames = []
    for i in range(3):
        # Create frame with different intensity for each
        frame = np.ones((100, 100, 3), dtype=np.uint8) * (i * 50)
        frames.append(frame)
    return frames


def test_calculate_frame_difference():
    """Test frame difference calculation."""
    # Create two frames with some difference
    frame1 = np.zeros((100, 100, 3), dtype=np.uint8)
    frame2 = np.ones((100, 100, 3), dtype=np.uint8) * 128  # 50% intensity

    # Calculate difference
    diff = calculate_frame_difference(frame1, frame2)

    # Expected difference is around 128/255 = 0.5
    assert 0.45 <= diff <= 0.55

    # Test identical frames
    diff_identical = calculate_frame_difference(frame1, frame1.copy())
    assert diff_identical < 0.001  # Should be very close to 0


def test_is_gpu_available():
    """Test GPU availability check."""
    # This just tests that the function runs without error
    # We don't assert the result because it depends on the system
    result = is_gpu_available()
    assert isinstance(result, bool)


def test_save_frames(dummy_frames):
    """Test saving frames to disk."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Save frames
        paths = save_frames(dummy_frames, temp_dir, "test_frame")

        # Check that we got the correct number of paths
        assert len(paths) == len(dummy_frames)

        # Check that files were created
        for path in paths:
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0  # Files should have content
