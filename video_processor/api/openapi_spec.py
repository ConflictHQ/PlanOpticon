"""OpenAPI 3.0 specification stub for the PlanOpticon REST API."""


def get_openapi_spec() -> dict:
    """Return an OpenAPI 3.0 spec dict for the planned PlanOpticon API."""
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "PlanOpticon API",
            "version": "0.1.0",
            "description": "Video analysis and knowledge extraction REST API.",
        },
        "paths": {
            "/analyze": {
                "post": {
                    "summary": "Submit a video for analysis",
                    "operationId": "createAnalysis",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["video_url"],
                                    "properties": {
                                        "video_url": {"type": "string", "format": "uri"},
                                        "depth": {
                                            "type": "string",
                                            "enum": ["basic", "standard", "comprehensive"],
                                        },
                                        "focus_areas": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                        "webhook_url": {"type": "string", "format": "uri"},
                                        "speaker_hints": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "202": {
                            "description": "Analysis job accepted",
                            "content": {
                                "application/json": {"schema": {"$ref": "#/components/schemas/Job"}}
                            },
                        }
                    },
                }
            },
            "/jobs/{id}": {
                "get": {
                    "summary": "Get analysis job status",
                    "operationId": "getJob",
                    "parameters": [
                        {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}
                    ],
                    "responses": {
                        "200": {
                            "description": "Job status",
                            "content": {
                                "application/json": {"schema": {"$ref": "#/components/schemas/Job"}}
                            },
                        }
                    },
                }
            },
            "/knowledge-graph/{id}/entities": {
                "get": {
                    "summary": "List entities in a knowledge graph",
                    "operationId": "listEntities",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        },
                        {"name": "type", "in": "query", "schema": {"type": "string"}},
                    ],
                    "responses": {
                        "200": {
                            "description": "Entity list",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "array",
                                        "items": {"$ref": "#/components/schemas/Entity"},
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/knowledge-graph/{id}/relationships": {
                "get": {
                    "summary": "List relationships in a knowledge graph",
                    "operationId": "listRelationships",
                    "parameters": [
                        {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}
                    ],
                    "responses": {
                        "200": {
                            "description": "Relationship list",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "array",
                                        "items": {"$ref": "#/components/schemas/Relationship"},
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/knowledge-graph/{id}/query": {
                "get": {
                    "summary": "Query the knowledge graph with natural language",
                    "operationId": "queryKnowledgeGraph",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        },
                        {
                            "name": "q",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string"},
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "Query results",
                            "content": {"application/json": {"schema": {"type": "object"}}},
                        }
                    },
                }
            },
        },
        "components": {
            "schemas": {
                "Job": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": ["pending", "processing", "completed", "failed"],
                        },
                        "progress": {"type": "number", "format": "float"},
                        "created_at": {"type": "string", "format": "date-time"},
                        "completed_at": {"type": "string", "format": "date-time"},
                        "result_url": {"type": "string", "format": "uri"},
                    },
                },
                "Entity": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "type": {"type": "string"},
                        "descriptions": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "Relationship": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string"},
                        "target": {"type": "string"},
                        "type": {"type": "string"},
                    },
                },
            }
        },
    }
