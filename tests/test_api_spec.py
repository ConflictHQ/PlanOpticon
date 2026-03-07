"""Tests for video_processor.api.openapi_spec."""

from video_processor.api.openapi_spec import get_openapi_spec


def test_returns_dict():
    spec = get_openapi_spec()
    assert isinstance(spec, dict)


def test_has_top_level_keys():
    spec = get_openapi_spec()
    for key in ("openapi", "info", "paths", "components"):
        assert key in spec, f"Missing top-level key: {key}"


def test_openapi_version():
    spec = get_openapi_spec()
    assert spec["openapi"].startswith("3.0")


def test_info_section():
    spec = get_openapi_spec()
    info = spec["info"]
    assert "title" in info
    assert "version" in info
    assert "PlanOpticon" in info["title"]


def test_expected_paths():
    spec = get_openapi_spec()
    expected_paths = [
        "/analyze",
        "/jobs/{id}",
        "/knowledge-graph/{id}/entities",
        "/knowledge-graph/{id}/relationships",
        "/knowledge-graph/{id}/query",
    ]
    for path in expected_paths:
        assert path in spec["paths"], f"Missing path: {path}"


def test_analyze_endpoint():
    spec = get_openapi_spec()
    analyze = spec["paths"]["/analyze"]
    assert "post" in analyze
    post = analyze["post"]
    assert "summary" in post
    assert "requestBody" in post
    assert "responses" in post
    assert "202" in post["responses"]


def test_jobs_endpoint():
    spec = get_openapi_spec()
    jobs = spec["paths"]["/jobs/{id}"]
    assert "get" in jobs
    get = jobs["get"]
    assert "parameters" in get
    assert get["parameters"][0]["name"] == "id"


def test_entities_endpoint():
    spec = get_openapi_spec()
    entities = spec["paths"]["/knowledge-graph/{id}/entities"]
    assert "get" in entities


def test_relationships_endpoint():
    spec = get_openapi_spec()
    rels = spec["paths"]["/knowledge-graph/{id}/relationships"]
    assert "get" in rels


def test_query_endpoint():
    spec = get_openapi_spec()
    query = spec["paths"]["/knowledge-graph/{id}/query"]
    assert "get" in query
    params = query["get"]["parameters"]
    param_names = [p["name"] for p in params]
    assert "q" in param_names


def test_component_schemas():
    spec = get_openapi_spec()
    schemas = spec["components"]["schemas"]
    for schema_name in ("Job", "Entity", "Relationship"):
        assert schema_name in schemas, f"Missing schema: {schema_name}"


def test_job_schema_properties():
    spec = get_openapi_spec()
    job = spec["components"]["schemas"]["Job"]
    props = job["properties"]
    assert "id" in props
    assert "status" in props
    assert "progress" in props


def test_job_status_enum():
    spec = get_openapi_spec()
    status = spec["components"]["schemas"]["Job"]["properties"]["status"]
    assert "enum" in status
    assert "pending" in status["enum"]
    assert "completed" in status["enum"]


def test_analyze_request_body_schema():
    spec = get_openapi_spec()
    schema = spec["paths"]["/analyze"]["post"]["requestBody"]["content"]["application/json"][
        "schema"
    ]
    assert "video_url" in schema["properties"]
    assert "video_url" in schema["required"]
