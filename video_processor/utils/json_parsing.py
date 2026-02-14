"""Robust JSON extraction from LLM responses."""

import json
import re
from typing import Optional, Union


def parse_json_from_response(text: str) -> Optional[Union[list, dict]]:
    """
    Extract JSON from an LLM response, handling markdown fences,
    explanatory text, and minor formatting issues.

    Strategies tried in order:
    1. Direct parse
    2. Strip markdown fences and parse
    3. Find [...] or {...} substring and parse
    4. Return None
    """
    if not text or not text.strip():
        return None

    cleaned = text.strip()

    # Strategy 1: direct parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Strategy 2: strip markdown fences
    fence_pattern = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)
    match = fence_pattern.search(cleaned)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Strategy 3: find JSON array or object
    # Try array first (often the outermost structure for lists)
    for opener, closer in [("[", "]"), ("{", "}")]:
        start = cleaned.find(opener)
        if start < 0:
            continue
        # Find matching closer (handle nesting)
        depth = 0
        for i in range(start, len(cleaned)):
            if cleaned[i] == opener:
                depth += 1
            elif cleaned[i] == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(cleaned[start : i + 1])
                    except json.JSONDecodeError:
                        break

    return None
