"""Frame extraction module for video processing."""

import functools
import logging
from pathlib import Path
from typing import List, Optional, Tuple, Union

import cv2
import numpy as np
from tqdm import tqdm

logger = logging.getLogger(__name__)

# Haar cascade for face detection — ships with OpenCV
_FACE_CASCADE_PATH = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
_FACE_CASCADE = None


def _get_face_cascade() -> cv2.CascadeClassifier:
    """Lazy-load the face cascade classifier."""
    global _FACE_CASCADE
    if _FACE_CASCADE is None:
        _FACE_CASCADE = cv2.CascadeClassifier(_FACE_CASCADE_PATH)
    return _FACE_CASCADE


def detect_faces(frame: np.ndarray) -> List[Tuple[int, int, int, int]]:
    """Detect faces in a frame using Haar cascade. Returns list of (x, y, w, h)."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
    cascade = _get_face_cascade()
    faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))
    return list(faces) if len(faces) > 0 else []


def is_people_frame(
    frame: np.ndarray,
    face_area_threshold: float = 0.03,
    min_face_size: int = 90,
) -> bool:
    """
    Determine if a frame is primarily showing people (webcam/video conference).

    Heuristics:
      1. Face detection — if significant faces occupy enough frame area
      2. Black bar detection — video conferences often have thick black bars
      3. Small faces with black bars — profile pictures in conference UI

    Faces smaller than min_face_size are ignored (sidebar thumbnails in screen shares).

    Parameters
    ----------
    frame : np.ndarray
        BGR image frame
    face_area_threshold : float
        Minimum ratio of total face area to frame area to classify as people frame
    min_face_size : int
        Minimum face width/height in pixels to count as a significant face

    Returns
    -------
    bool
        True if frame is primarily people/webcam content
    """
    h, w = frame.shape[:2]
    frame_area = h * w

    # Detect all faces
    all_faces = detect_faces(frame)

    # Separate significant faces (webcam-sized) from tiny ones (sidebar thumbnails)
    significant_faces = [(x, y, fw, fh) for (x, y, fw, fh) in all_faces if fw >= min_face_size]

    if significant_faces:
        total_face_area = sum(fw * fh for (_, _, fw, fh) in significant_faces)
        face_ratio = total_face_area / frame_area

        # Multiple significant faces or large face area → people frame
        if len(significant_faces) >= 2 or face_ratio >= face_area_threshold:
            logger.debug(
                f"People frame: {len(significant_faces)} significant faces, "
                f"face_ratio={face_ratio:.3f}"
            )
            return True

    # Check for video conference layout: large black border areas
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
    black_pixels = np.sum(gray < 15)
    black_ratio = black_pixels / frame_area

    if black_ratio > 0.25 and all_faces:
        # Significant black bars + any face = video conference UI (e.g., profile pic on black)
        logger.debug(f"People frame: black_ratio={black_ratio:.2f} with {len(all_faces)} faces")
        return True

    return False


def filter_people_frames(
    frames: List[np.ndarray],
    face_area_threshold: float = 0.03,
) -> Tuple[List[np.ndarray], int]:
    """
    Filter out frames that primarily show people/webcam views.

    Returns (filtered_frames, num_removed).
    """
    filtered = []
    removed = 0
    for frame in tqdm(frames, desc="Filtering people frames", unit="frame"):
        if is_people_frame(frame, face_area_threshold):
            removed += 1
        else:
            filtered.append(frame)

    if removed:
        logger.info(f"Filtered out {removed}/{len(frames)} people/webcam frames")
    return filtered, removed


def is_gpu_available() -> bool:
    """Check if GPU acceleration is available for OpenCV."""
    try:
        # Check if CUDA is available
        count = cv2.cuda.getCudaEnabledDeviceCount()
        return count > 0
    except Exception:
        return False


def gpu_accelerated(func):
    """Decorator to use GPU implementation when available."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if is_gpu_available() and not kwargs.get("disable_gpu"):
            # Remove the disable_gpu kwarg if it exists
            kwargs.pop("disable_gpu", None)
            return func_gpu(*args, **kwargs)
        # Remove the disable_gpu kwarg if it exists
        kwargs.pop("disable_gpu", None)
        return func(*args, **kwargs)

    return wrapper


def calculate_frame_difference(prev_frame: np.ndarray, curr_frame: np.ndarray) -> float:
    """
    Calculate the difference between two frames.

    Parameters
    ----------
    prev_frame : np.ndarray
        Previous frame
    curr_frame : np.ndarray
        Current frame

    Returns
    -------
    float
        Difference score between 0 and 1
    """
    # Convert to grayscale
    if len(prev_frame.shape) == 3:
        prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
    else:
        prev_gray = prev_frame

    if len(curr_frame.shape) == 3:
        curr_gray = cv2.cvtColor(curr_frame, cv2.COLOR_BGR2GRAY)
    else:
        curr_gray = curr_frame

    # Calculate absolute difference
    diff = cv2.absdiff(prev_gray, curr_gray)

    # Normalize and return mean difference
    return np.mean(diff) / 255.0


@gpu_accelerated
def extract_frames(
    video_path: Union[str, Path],
    sampling_rate: float = 1.0,
    change_threshold: float = 0.15,
    periodic_capture_seconds: float = 30.0,
    max_frames: Optional[int] = None,
    resize_to: Optional[Tuple[int, int]] = None,
) -> List[np.ndarray]:
    """
    Extract frames from video based on visual change detection + periodic capture.

    Two capture strategies work together:
      1. Change detection: capture when visual difference exceeds threshold
         (catches transitions like webcam ↔ screen share)
      2. Periodic capture: capture every N seconds regardless of change
         (catches slow-evolving content like document scrolling)

    The downstream people filter removes any webcam frames captured periodically.

    Parameters
    ----------
    video_path : str or Path
        Path to video file
    sampling_rate : float
        Frame sampling rate (1.0 = every frame)
    change_threshold : float
        Threshold for detecting significant visual changes
    periodic_capture_seconds : float
        Capture a frame every N seconds regardless of change (0 to disable)
    max_frames : int, optional
        Maximum number of frames to extract
    resize_to : tuple of (width, height), optional
        Resize frames to this dimension

    Returns
    -------
    list
        List of extracted frames as numpy arrays
    """
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Could not open video file: {video_path}")

    # Get video properties
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # Calculate frame interval based on sampling rate
    if sampling_rate <= 0:
        raise ValueError("Sampling rate must be positive")

    frame_interval = max(1, int(1 / sampling_rate))

    # Periodic capture interval in frames (0 = disabled)
    periodic_interval = int(periodic_capture_seconds * fps) if periodic_capture_seconds > 0 else 0

    logger.info(
        f"Video: {video_path.name}, FPS: {fps:.0f}, Frames: {frame_count}, "
        f"Sample interval: {frame_interval}, "
        f"Periodic capture: every {periodic_capture_seconds:.0f}s"
    )

    extracted_frames = []
    prev_frame = None
    frame_idx = 0
    last_capture_frame = -periodic_interval  # allow first periodic capture immediately

    pbar = tqdm(
        total=frame_count,
        desc="Extracting frames",
        unit="frame",
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
    )

    while cap.isOpened():
        # Process frame only if it's a sampling point
        if frame_idx % frame_interval == 0:
            success, frame = cap.read()
            if not success:
                break

            # Resize if specified
            if resize_to is not None:
                frame = cv2.resize(frame, resize_to)

            should_capture = False
            reason = ""

            # First frame always gets extracted
            if prev_frame is None:
                should_capture = True
                reason = "first"
            else:
                # Change detection
                diff = calculate_frame_difference(prev_frame, frame)
                if diff > change_threshold:
                    should_capture = True
                    reason = f"change={diff:.3f}"

                # Periodic capture — even if change is small
                elif (
                    periodic_interval > 0 and (frame_idx - last_capture_frame) >= periodic_interval
                ):
                    should_capture = True
                    reason = "periodic"

            if should_capture:
                extracted_frames.append(frame)
                prev_frame = frame
                last_capture_frame = frame_idx
                logger.debug(f"Frame {frame_idx} extracted ({reason})")

            pbar.set_postfix(extracted=len(extracted_frames))

            # Check if we've reached the maximum
            if max_frames is not None and len(extracted_frames) >= max_frames:
                break
        else:
            # Skip frame but advance counter
            cap.grab()

        frame_idx += 1
        pbar.update(frame_interval)

    pbar.close()
    cap.release()
    logger.info(f"Extracted {len(extracted_frames)} frames from {frame_count} total frames")
    return extracted_frames


def func_gpu(*args, **kwargs):
    """GPU-accelerated version of extract_frames."""
    # This would be implemented with CUDA acceleration
    # For now, fall back to the unwrapped CPU version
    logger.info("GPU acceleration not yet implemented, falling back to CPU")
    return extract_frames.__wrapped__(*args, **kwargs)


def save_frames(
    frames: List[np.ndarray], output_dir: Union[str, Path], base_filename: str = "frame"
) -> List[Path]:
    """
    Save extracted frames to disk.

    Parameters
    ----------
    frames : list
        List of frames to save
    output_dir : str or Path
        Directory to save frames in
    base_filename : str
        Base name for frame files

    Returns
    -------
    list
        List of paths to saved frame files
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    saved_paths = []
    for i, frame in enumerate(frames):
        output_path = output_dir / f"{base_filename}_{i:04d}.jpg"
        cv2.imwrite(str(output_path), frame)
        saved_paths.append(output_path)

    return saved_paths
