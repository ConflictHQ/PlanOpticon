"""Source revisions and validated multimodal extraction context."""

import hashlib
import json
from pathlib import Path

from video_processor.models import EvidenceObservation


def file_revision(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_source_id(path: Path, revision: str) -> str:
    return hashlib.sha256(f"{Path(path).resolve()}\0{revision}".encode()).hexdigest()


def observation(source: dict, modality: str, locator: dict, detector_confidence=None) -> dict:
    return normalized_observation(
        {
            "source_record": source,
            "source_revision": source.get("metadata", {}).get("sha256"),
            "modality": modality,
            "locator": {key: value for key, value in locator.items() if value is not None},
            "detector_confidence": detector_confidence,
        }
    )


def normalized_observation(value: dict | None) -> dict | None:
    if value is None:
        return None
    # Metadata is open JSON on SourceRecord; reject non-finite/non-JSON values
    # there too and copy mutable caller data before retaining it.
    data = json.loads(json.dumps(value, allow_nan=False))
    return EvidenceObservation.model_validate(data).model_dump(mode="json", exclude_none=True)


def check_source_revision(existing: dict | None, incoming: dict) -> None:
    if existing is None:
        return
    old = existing.get("metadata", {}).get("sha256")
    new = incoming.get("metadata", {}).get("sha256")
    if old != new and (old is not None or new is not None):
        raise ValueError("source identity already belongs to a different or unqualified revision")
