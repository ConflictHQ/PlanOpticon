# Document Ingestion

Document ingestion lets you process files -- PDFs, Markdown, and plaintext -- into a knowledge graph. PlanOpticon extracts text from documents, chunks it into manageable pieces, runs LLM-powered entity and relationship extraction, and stores the results in a FalkorDB knowledge graph. This is the same knowledge graph format produced by video analysis, so you can combine video and document insights in a single graph.

## Supported formats

| Extension | Processor | Description |
|-----------|-----------|-------------|
| `.pdf` | `PdfProcessor` | Extracts text page by page using pymupdf or pdfplumber |
| `.md`, `.markdown` | `MarkdownProcessor` | Splits on headings into sections |
| `.txt`, `.text`, `.log`, `.csv` | `PlaintextProcessor` | Splits on paragraph boundaries |

Additional formats can be added by implementing the `DocumentProcessor` base class and registering it (see [Extending with custom processors](#extending-with-custom-processors) below).

## CLI usage

### `planopticon ingest`

```
planopticon ingest INPUT_PATH [OPTIONS]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `INPUT_PATH` | Path to a file or directory to ingest (must exist) |

**Options:**

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--output` | `-o` | Current directory | Output directory for the knowledge graph |
| `--db-path` | | None | Path to an existing `knowledge_graph.db` to merge into |
| `--recursive / --no-recursive` | `-r` | `--recursive` | Recurse into subdirectories (directory ingestion only) |
| `--provider` | `-p` | `auto` | LLM provider for entity extraction (`openai`, `anthropic`, `gemini`, `ollama`, `azure`, `together`, `fireworks`, `cerebras`, `xai`) |
| `--chat-model` | | None | Override the model used for LLM entity extraction |

### Single file ingestion

Process a single document and create a new knowledge graph:

```bash
planopticon ingest spec.md
```

This creates `knowledge_graph.db` and `knowledge_graph.json` in the current directory.

Specify an output directory:

```bash
planopticon ingest report.pdf -o ./results
```

This creates `./results/knowledge_graph.db` and `./results/knowledge_graph.json`.

### Directory ingestion

Process all supported files in a directory:

```bash
planopticon ingest ./docs/
```

By default, this recurses into subdirectories. To process only the top-level directory:

```bash
planopticon ingest ./docs/ --no-recursive
```

PlanOpticon automatically filters for supported file extensions. Unsupported files are silently skipped.

### Merging into an existing knowledge graph

To add document content to an existing knowledge graph (e.g., one created from video analysis), use `--db-path`:

```bash
# First, analyze a video
planopticon analyze meeting.mp4 -o ./results

# Then, ingest supplementary documents into the same graph
planopticon ingest ./meeting-notes/ --db-path ./results/knowledge_graph.db
```

The ingested entities and relationships are merged with the existing graph. Duplicate entities are consolidated automatically by the knowledge graph engine.

### Choosing an LLM provider

Entity and relationship extraction requires an LLM. By default, PlanOpticon auto-detects available providers based on your environment variables. You can override this:

```bash
# Use Anthropic for extraction
planopticon ingest docs/ -p anthropic

# Use a specific model
planopticon ingest docs/ -p openai --chat-model gpt-4o

# Use a local Ollama model
planopticon ingest docs/ -p ollama --chat-model llama3
```

### Output

After ingestion, PlanOpticon prints a summary:

```
Knowledge graph: ./knowledge_graph.db
  spec.md: 12 chunks
  architecture.md: 8 chunks
  requirements.txt: 3 chunks

Ingestion complete:
  Files processed: 3
  Total chunks: 23
  Entities extracted: 47
  Relationships: 31
  Knowledge graph: ./knowledge_graph.db
```

Both `.db` (SQLite/FalkorDB) and `.json` formats are saved automatically.

## How each processor works

### PDF processor

The `PdfProcessor` extracts text from PDF files on a per-page basis. It tries two extraction libraries in order:

1. **pymupdf** (preferred) -- Fast, reliable text extraction. Install with `pip install pymupdf`.
2. **pdfplumber** (fallback) -- Alternative extractor. Install with `pip install pdfplumber`.

If neither library is installed, the processor raises an `ImportError` with installation instructions.

Each page becomes a separate `DocumentChunk` with:

- `text`: The extracted text content of the page
- `page`: The 1-based page number
- `metadata.extraction_method`: Which library was used (`pymupdf` or `pdfplumber`)

To install PDF support:

```bash
pip install 'planopticon[pdf]'
# or
pip install pymupdf
# or
pip install pdfplumber
```

### Markdown processor

The `MarkdownProcessor` splits Markdown files on heading boundaries (lines starting with `#` through `######`). Each heading and its content until the next heading becomes a separate chunk.

**Splitting behavior:**

- If the file contains headings, each heading section becomes a chunk. The `section` field records the heading text.
- Content before the first heading is captured as a `(preamble)` chunk.
- If the file contains no headings, it falls back to paragraph-based chunking (same as plaintext).

For example, a file with this structure:

```markdown
Some intro text.

# Architecture

The system uses a microservices architecture...

## Components

There are three main components...

# Deployment

Deployment is handled via...
```

Produces four chunks: `(preamble)`, `Architecture`, `Components`, and `Deployment`.

### Plaintext processor

The `PlaintextProcessor` handles `.txt`, `.text`, `.log`, and `.csv` files. It splits text on paragraph boundaries (double newlines) and groups paragraphs into chunks with a configurable maximum size.

**Chunking parameters:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_chunk_size` | 2000 characters | Maximum size of each chunk |
| `overlap` | 200 characters | Number of characters from the end of one chunk to repeat at the start of the next |

The overlap ensures that entities or context that spans a paragraph boundary are not lost. Chunks are created by accumulating paragraphs until the next paragraph would exceed `max_chunk_size`, at which point the current chunk is flushed and a new one begins.

## The ingestion pipeline

Document ingestion follows this pipeline:

```
File on disk
    |
    v
Processor selection (by file extension)
    |
    v
Text extraction (PDF pages / Markdown sections / plaintext paragraphs)
    |
    v
DocumentChunk objects (text + metadata)
    |
    v
Source registration (provenance tracking in the KG)
    |
    v
KG content addition (LLM entity/relationship extraction per chunk)
    |
    v
Knowledge graph storage (.db + .json)
```

### Step 1: Processor selection

PlanOpticon maintains a registry of processors keyed by file extension. When you call `ingest_file()`, it looks up the appropriate processor using `get_processor(path)`. If no processor is registered for the file extension, a `ValueError` is raised.

### Step 2: Text extraction

The selected processor reads the file and produces a list of `DocumentChunk` objects. Each chunk contains:

| Field | Type | Description |
|-------|------|-------------|
| `text` | `str` | The extracted text content |
| `source_file` | `str` | Path to the source file |
| `chunk_index` | `int` | Sequential index of this chunk within the file |
| `page` | `Optional[int]` | Page number (PDF only, 1-based) |
| `section` | `Optional[str]` | Section heading (Markdown only) |
| `metadata` | `Dict[str, Any]` | Additional metadata (e.g., extraction method) |

### Step 3: Source registration

Each ingested file is registered as a source in the knowledge graph with provenance metadata:

- `source_id`: A SHA-256 hash of the absolute file path (first 12 characters), unless you provide a custom ID
- `source_type`: Always `"document"`
- `title`: The file stem (filename without extension)
- `path`: The file path
- `mime_type`: Detected MIME type
- `ingested_at`: ISO-8601 timestamp
- `metadata`: Chunk count and file extension

### Step 4: Entity and relationship extraction

Each chunk's text is passed to `knowledge_graph.add_content()`, which uses the configured LLM provider to extract entities and relationships. The content source is tagged with the document name and either the page number or section name:

- `document:report.pdf:page:3`
- `document:spec.md:section:Architecture`
- `document:notes.txt` (no page or section)

### Step 5: Storage

The knowledge graph is saved in both `.db` (SQLite-backed FalkorDB) and `.json` formats.

## Combining with video analysis

A common workflow is to analyze a video recording and then ingest related documents into the same knowledge graph:

```bash
# Step 1: Analyze the meeting recording
planopticon analyze meeting-recording.mp4 -o ./project-kg

# Step 2: Ingest the meeting agenda
planopticon ingest agenda.md --db-path ./project-kg/knowledge_graph.db

# Step 3: Ingest the project spec
planopticon ingest project-spec.pdf --db-path ./project-kg/knowledge_graph.db

# Step 4: Ingest a whole docs folder
planopticon ingest ./reference-docs/ --db-path ./project-kg/knowledge_graph.db

# Step 5: Query the combined graph
planopticon query --db-path ./project-kg/knowledge_graph.db
```

The resulting knowledge graph contains entities and relationships from all sources -- video transcripts, meeting agendas, specs, and reference documents -- with full provenance tracking so you can trace any entity back to its source.

## Python API

### Ingesting a single file

```python
from pathlib import Path
from video_processor.integrators.knowledge_graph import KnowledgeGraph
from video_processor.processors.ingest import ingest_file

kg = KnowledgeGraph(db_path=Path("knowledge_graph.db"))
chunk_count = ingest_file(Path("document.pdf"), kg)
print(f"Processed {chunk_count} chunks")

kg.save(Path("knowledge_graph.db"))
```

### Ingesting a directory

```python
from pathlib import Path
from video_processor.integrators.knowledge_graph import KnowledgeGraph
from video_processor.processors.ingest import ingest_directory

kg = KnowledgeGraph(db_path=Path("knowledge_graph.db"))
results = ingest_directory(
    Path("./docs"),
    kg,
    recursive=True,
    extensions=[".md", ".pdf"],  # Optional: filter by extension
)

for filepath, chunks in results.items():
    print(f"  {filepath}: {chunks} chunks")

kg.save(Path("knowledge_graph.db"))
```

### Listing supported extensions

```python
from video_processor.processors.base import list_supported_extensions

extensions = list_supported_extensions()
print(extensions)
# ['.csv', '.log', '.markdown', '.md', '.pdf', '.text', '.txt']
```

### Working with processors directly

```python
from pathlib import Path
from video_processor.processors.base import get_processor

processor = get_processor(Path("report.pdf"))
if processor:
    chunks = processor.process(Path("report.pdf"))
    for chunk in chunks:
        print(f"Page {chunk.page}: {chunk.text[:100]}...")
```

## Extending with custom processors

To add support for a new file format, implement the `DocumentProcessor` abstract class and register it:

```python
from pathlib import Path
from typing import List
from video_processor.processors.base import (
    DocumentChunk,
    DocumentProcessor,
    register_processor,
)


class HtmlProcessor(DocumentProcessor):
    supported_extensions = [".html", ".htm"]

    def can_process(self, path: Path) -> bool:
        return path.suffix.lower() in self.supported_extensions

    def process(self, path: Path) -> List[DocumentChunk]:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(path.read_text(), "html.parser")
        text = soup.get_text(separator="\n")
        return [
            DocumentChunk(
                text=text,
                source_file=str(path),
                chunk_index=0,
            )
        ]


register_processor(HtmlProcessor.supported_extensions, HtmlProcessor)
```

After registration, `planopticon ingest` will automatically handle `.html` and `.htm` files.

## Companion REPL

Inside the interactive companion REPL, you can ingest files using the `/ingest` command:

```
> /ingest ./meeting-notes.md
Ingested meeting-notes.md: 5 chunks
```

This adds content to the currently loaded knowledge graph.

## Common workflows

### Build a project knowledge base from scratch

```bash
# Ingest all project docs
planopticon ingest ./project-docs/ -o ./knowledge-base

# Query what was captured
planopticon query --db-path ./knowledge-base/knowledge_graph.db

# Export as an Obsidian vault
planopticon export obsidian ./knowledge-base/knowledge_graph.db -o ./vault
```

### Incrementally build a knowledge graph

```bash
# Start with initial docs
planopticon ingest ./sprint-1-docs/ -o ./kg

# Add more docs over time
planopticon ingest ./sprint-2-docs/ --db-path ./kg/knowledge_graph.db
planopticon ingest ./sprint-3-docs/ --db-path ./kg/knowledge_graph.db

# The graph grows with each ingestion
planopticon query --db-path ./kg/knowledge_graph.db stats
```

### Ingest from Google Workspace or Microsoft 365

PlanOpticon provides integrated commands that fetch cloud documents and ingest them in one step:

```bash
# Google Workspace
planopticon gws ingest --folder-id FOLDER_ID -o ./results

# Microsoft 365 / SharePoint
planopticon m365 ingest --web-url https://contoso.sharepoint.com/sites/proj \
    --folder-url /sites/proj/Shared\ Documents
```

These commands handle authentication, document download, text extraction, and knowledge graph creation automatically.
