"""Text extraction module for frames and diagrams."""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class TextExtractor:
    """Extract text from images, frames, and diagrams."""

    def __init__(self, tesseract_path: Optional[str] = None):
        """
        Initialize text extractor.

        Parameters
        ----------
        tesseract_path : str, optional
            Path to tesseract executable for local OCR
        """
        self.tesseract_path = tesseract_path

        # Check if we're using tesseract locally
        self.use_local_ocr = False
        if tesseract_path:
            try:
                import pytesseract

                pytesseract.pytesseract.tesseract_cmd = tesseract_path
                self.use_local_ocr = True
            except ImportError:
                logger.warning("pytesseract not installed, local OCR unavailable")

    def preprocess_image(self, image: np.ndarray) -> np.ndarray:
        """
        Preprocess image for better text extraction.

        Parameters
        ----------
        image : np.ndarray
            Input image

        Returns
        -------
        np.ndarray
            Preprocessed image
        """
        # Convert to grayscale if not already
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # Apply adaptive thresholding
        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2
        )

        # Noise removal
        kernel = np.ones((1, 1), np.uint8)
        opening = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)

        # Invert back
        result = cv2.bitwise_not(opening)

        return result

    def extract_text_local(self, image: np.ndarray) -> str:
        """
        Extract text from image using local OCR (Tesseract).

        Parameters
        ----------
        image : np.ndarray
            Input image

        Returns
        -------
        str
            Extracted text
        """
        if not self.use_local_ocr:
            raise RuntimeError("Local OCR not configured")

        import pytesseract

        # Preprocess image
        processed = self.preprocess_image(image)

        # Extract text
        text = pytesseract.image_to_string(processed)

        return text

    def detect_text_regions(self, image: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """
        Detect potential text regions in image.

        Parameters
        ----------
        image : np.ndarray
            Input image

        Returns
        -------
        list
            List of bounding boxes for text regions (x, y, w, h)
        """
        # Convert to grayscale
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # Apply MSER (Maximally Stable Extremal Regions)
        mser = cv2.MSER_create()
        regions, _ = mser.detectRegions(gray)

        # Convert regions to bounding boxes
        bboxes = []
        for region in regions:
            x, y, w, h = cv2.boundingRect(region.reshape(-1, 1, 2))

            # Apply filtering criteria for text-like regions
            aspect_ratio = w / float(h)
            if 0.1 < aspect_ratio < 10 and h > 5 and w > 5:
                bboxes.append((x, y, w, h))

        # Merge overlapping boxes
        merged_bboxes = self._merge_overlapping_boxes(bboxes)

        logger.debug(f"Detected {len(merged_bboxes)} text regions")
        return merged_bboxes

    def _merge_overlapping_boxes(
        self, boxes: List[Tuple[int, int, int, int]]
    ) -> List[Tuple[int, int, int, int]]:
        """
        Merge overlapping bounding boxes.

        Parameters
        ----------
        boxes : list
            List of bounding boxes (x, y, w, h)

        Returns
        -------
        list
            Merged bounding boxes
        """
        if not boxes:
            return []

        # Sort boxes by x coordinate
        sorted_boxes = sorted(boxes, key=lambda b: b[0])

        merged = []
        current = list(sorted_boxes[0])

        for box in sorted_boxes[1:]:
            # Check if current box overlaps with the next one
            if (
                current[0] <= box[0] + box[2]
                and box[0] <= current[0] + current[2]
                and current[1] <= box[1] + box[3]
                and box[1] <= current[1] + current[3]
            ):
                # Calculate merged box
                x1 = min(current[0], box[0])
                y1 = min(current[1], box[1])
                x2 = max(current[0] + current[2], box[0] + box[2])
                y2 = max(current[1] + current[3], box[1] + box[3])

                # Update current box
                current = [x1, y1, x2 - x1, y2 - y1]
            else:
                # Add current box to merged list and update current
                merged.append(tuple(current))
                current = list(box)

        # Add the last box
        merged.append(tuple(current))

        return merged

    def extract_text_from_regions(
        self, image: np.ndarray, regions: List[Tuple[int, int, int, int]]
    ) -> Dict[Tuple[int, int, int, int], str]:
        """
        Extract text from specified regions in image.

        Parameters
        ----------
        image : np.ndarray
            Input image
        regions : list
            List of regions as (x, y, w, h)

        Returns
        -------
        dict
            Dictionary of {region: text}
        """
        results = {}

        for region in regions:
            x, y, w, h = region

            # Extract region
            roi = image[y : y + h, x : x + w]

            # Skip empty regions
            if roi.size == 0:
                continue

            # Extract text
            if self.use_local_ocr:
                text = self.extract_text_local(roi)
            else:
                text = "API-based text extraction not yet implemented"

            # Store non-empty results
            if text.strip():
                results[region] = text.strip()

        return results

    def extract_text_from_image(self, image: np.ndarray, detect_regions: bool = True) -> str:
        """
        Extract text from entire image.

        Parameters
        ----------
        image : np.ndarray
            Input image
        detect_regions : bool
            Whether to detect and process text regions separately

        Returns
        -------
        str
            Extracted text
        """
        if detect_regions:
            # Detect regions and extract text from each
            regions = self.detect_text_regions(image)
            region_texts = self.extract_text_from_regions(image, regions)

            # Combine text from all regions
            text = "\n".join(region_texts.values())
        else:
            # Extract text from entire image
            if self.use_local_ocr:
                text = self.extract_text_local(image)
            else:
                text = "API-based text extraction not yet implemented"

        return text

    def extract_text_from_file(
        self, image_path: Union[str, Path], detect_regions: bool = True
    ) -> str:
        """
        Extract text from image file.

        Parameters
        ----------
        image_path : str or Path
            Path to image file
        detect_regions : bool
            Whether to detect and process text regions separately

        Returns
        -------
        str
            Extracted text
        """
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")

        # Load image
        image = cv2.imread(str(image_path))
        if image is None:
            raise ValueError(f"Failed to load image: {image_path}")

        # Extract text
        text = self.extract_text_from_image(image, detect_regions)

        return text
