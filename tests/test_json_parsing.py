"""Tests for robust JSON parsing from LLM responses."""

from video_processor.utils.json_parsing import parse_json_from_response


class TestParseJsonFromResponse:
    def test_direct_dict(self):
        assert parse_json_from_response('{"key": "value"}') == {"key": "value"}

    def test_direct_array(self):
        assert parse_json_from_response("[1, 2, 3]") == [1, 2, 3]

    def test_markdown_fenced_json(self):
        text = '```json\n{"key": "value"}\n```'
        assert parse_json_from_response(text) == {"key": "value"}

    def test_markdown_fenced_no_lang(self):
        text = "```\n[1, 2]\n```"
        assert parse_json_from_response(text) == [1, 2]

    def test_json_embedded_in_text(self):
        text = 'Here is the result:\n{"name": "test", "value": 42}\nEnd of result.'
        result = parse_json_from_response(text)
        assert result == {"name": "test", "value": 42}

    def test_array_embedded_in_text(self):
        text = 'The entities are:\n[{"name": "Alice"}, {"name": "Bob"}]\nThat is all.'
        result = parse_json_from_response(text)
        assert len(result) == 2
        assert result[0]["name"] == "Alice"

    def test_nested_json(self):
        text = '{"outer": {"inner": [1, 2, 3]}}'
        result = parse_json_from_response(text)
        assert result["outer"]["inner"] == [1, 2, 3]

    def test_empty_string(self):
        assert parse_json_from_response("") is None

    def test_none_input(self):
        assert parse_json_from_response(None) is None

    def test_whitespace_only(self):
        assert parse_json_from_response("   \n  ") is None

    def test_no_json(self):
        assert parse_json_from_response("This is just plain text.") is None

    def test_invalid_json(self):
        assert parse_json_from_response("{invalid json}") is None

    def test_multiple_json_objects_picks_first(self):
        text = '{"a": 1} and {"b": 2}'
        result = parse_json_from_response(text)
        assert result == {"a": 1}

    def test_complex_fenced(self):
        text = """Here is the analysis:

```json
[
  {"point": "Architecture uses microservices", "topic": "Architecture"},
  {"point": "Deployment is automated", "topic": "DevOps"}
]
```

I hope this helps!"""
        result = parse_json_from_response(text)
        assert len(result) == 2
        assert result[0]["topic"] == "Architecture"
