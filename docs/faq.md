# FAQ & Troubleshooting

## Frequently Asked Questions

### Do I need an API key?

You need at least one of:

- **Cloud API key**: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `GEMINI_API_KEY`
- **Local Ollama**: Install [Ollama](https://ollama.com), pull a model, and run `ollama serve`

Some features work without any AI provider:

- `planopticon query stats` — direct knowledge graph queries
- `planopticon query "entities --type person"` — structured entity lookups
- `planopticon export markdown` — document generation from existing KG (7 document types, no LLM)
- `planopticon kg inspect` — knowledge graph statistics
- `planopticon kg convert` — format conversion

### How much does it cost?

PlanOpticon defaults to cheap models to minimize costs:

| Task | Default model | Approximate cost |
|------|--------------|-----------------|
| Chat/analysis | Claude Haiku / GPT-4o-mini | ~$0.25-0.50 per 1M tokens |
| Vision (diagrams) | Gemini Flash / GPT-4o-mini | ~$0.10-0.50 per 1M tokens |
| Transcription | Local Whisper (free) / Whisper-1 | $0.006/minute |

A typical 1-hour meeting costs roughly $0.05-0.15 to process with default models. Use `--provider ollama` for zero cost.

### Can I run fully offline?

Yes. Install Ollama and local Whisper:

```bash
ollama pull llama3.2
ollama pull llava
pip install planopticon[gpu]
planopticon analyze -i video.mp4 -o ./output --provider ollama
```

No data leaves your machine.

### What video formats are supported?

Any format FFmpeg can decode:

- MP4, MKV, AVI, MOV, WebM, FLV, WMV, M4V
- Container formats with common codecs (H.264, H.265, VP8, VP9, AV1)

### What document formats can I ingest?

- **PDF** — text extraction via pymupdf or pdfplumber
- **Markdown** — parsed with heading-based chunking
- **Plain text** — paragraph-based chunking with overlap

### How does the knowledge graph work?

PlanOpticon extracts entities (people, technologies, concepts, decisions) and relationships from your content. These are stored in a SQLite database (`knowledge_graph.db`) with zero external dependencies. Entities are automatically classified using a planning taxonomy (goals, requirements, risks, tasks, milestones).

When you process multiple sources, entities are merged using fuzzy name matching (0.85 threshold) with type conflict resolution and provenance tracking.

### Can I use PlanOpticon with my existing Obsidian vault?

Yes, in both directions:

```bash
# Ingest an Obsidian vault into PlanOpticon
planopticon ingest ~/Obsidian/MyVault --output ./kb --recursive

# Export PlanOpticon knowledge to an Obsidian vault
planopticon export obsidian --input ./kb --output ~/Obsidian/PlanOpticon
```

The Obsidian export produces proper YAML frontmatter, wiki-links (`[[Entity Name]]`), and tag pages.

### How do I add my own AI provider?

Create a provider module, extend `BaseProvider`, and register it:

```python
from video_processor.providers.base import BaseProvider, ProviderRegistry

class MyProvider(BaseProvider):
    provider_name = "myprovider"

    def chat(self, messages, max_tokens=4096, temperature=0.7, model=None):
        # Your implementation
        ...

ProviderRegistry.register(
    name="myprovider",
    provider_class=MyProvider,
    env_var="MY_PROVIDER_API_KEY",
    model_prefixes=["my-"],
    default_models={"chat": "my-model-v1", "vision": "", "audio": ""},
)
```

See the [Contributing guide](contributing.md) for details.

---

## Troubleshooting

### Authentication errors

#### "No auth method available for zoom"

You need to set credentials before authenticating:

```bash
export ZOOM_CLIENT_ID="your-client-id"
export ZOOM_CLIENT_SECRET="your-client-secret"
planopticon auth zoom
```

The error message tells you which environment variables to set. Each service requires different credentials — see the [Authentication guide](guide/authentication.md).

#### "Token expired" or "401 Unauthorized"

Your saved token has expired and auto-refresh failed. Re-authenticate:

```bash
planopticon auth google   # or whatever service
```

To clear a stale token:

```bash
planopticon auth google --logout
planopticon auth google
```

Tokens are stored in `~/.planopticon/{service}_token.json`.

#### OAuth redirect errors

If the browser-based OAuth flow fails, check:

1. Your client ID and secret are correct
2. The redirect URI in your OAuth app matches PlanOpticon's default (`urn:ietf:wg:oauth:2.0:oob`)
3. The OAuth app has the required scopes enabled

### Provider errors

#### "ANTHROPIC_API_KEY not set"

Set at least one provider's API key:

```bash
export OPENAI_API_KEY="sk-..."
# or
export ANTHROPIC_API_KEY="sk-ant-..."
# or
export GEMINI_API_KEY="AI..."
```

Or use a `.env` file in your project directory.

#### "Unexpected role system" (Anthropic)

This was a bug in older versions where system messages were passed in the messages array instead of as a top-level parameter. Update to v0.4.0 or later.

#### "Model not found" or "Invalid model"

Check available models:

```bash
planopticon list-models
```

Common model name issues:
- Anthropic: use `claude-haiku-4-5-20251001`, not `claude-haiku`
- OpenAI: use `gpt-4o-mini`, not `gpt4o-mini`

#### Rate limiting / 429 errors

PlanOpticon doesn't currently implement automatic retry. If you hit rate limits:

1. Use a different provider: `--provider gemini`
2. Use cheaper/faster models: `--chat-model gpt-4o-mini`
3. Reduce processing depth: `--depth basic`
4. Use Ollama for zero rate limits: `--provider ollama`

### Processing errors

#### "FFmpeg not found"

Install FFmpeg:

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt-get install ffmpeg libsndfile1

# Windows
# Download from https://ffmpeg.org/download.html and add to PATH
```

#### "Audio extraction failed: no audio track found"

The video file has no audio track. PlanOpticon will skip transcription and continue with frame analysis only.

#### "Frame extraction memory error"

For very long videos, frame extraction can use significant memory. Use the `--max-memory-mb` safety valve:

```bash
planopticon analyze -i long-video.mp4 -o ./output --max-memory-mb 2048
```

Or reduce the sampling rate:

```bash
planopticon analyze -i long-video.mp4 -o ./output --sampling-rate 0.25
```

#### Batch processing — one video fails

Individual video failures don't stop the batch. Failed videos are logged in the batch manifest with error details. Check the batch root `manifest.json` for the specific error.

### Knowledge graph issues

#### "No knowledge graph loaded" in companion

The companion auto-discovers knowledge graphs by looking for `knowledge_graph.db` or `knowledge_graph.json` in the current directory and parent directories. Either:

1. `cd` to the directory containing your knowledge graph
2. Specify the path explicitly: `planopticon companion --kb ./path/to/kb`

#### Empty or sparse knowledge graph

Common causes:

1. **Too few entities extracted**: Try `--depth comprehensive` for deeper analysis
2. **Short or low-quality transcript**: Check `transcript/transcript.txt` — poor audio produces poor transcription
3. **Wrong provider**: Some models extract entities better than others. Try `--provider openai --chat-model gpt-4o` for higher quality

#### Duplicate entities after merge

The fuzzy matching threshold is 0.85 (SequenceMatcher ratio). If you're getting duplicates, the names are too different for automatic matching. You can manually inspect and merge:

```bash
planopticon kg inspect ./knowledge_graph.db
planopticon query "entities --name python"
```

### Companion / REPL issues

#### Chat gives generic advice instead of project-specific answers

The companion needs both a knowledge graph and an LLM provider. Check:

```
planopticon> /status
```

If it says "KG: not loaded" or "Provider: none", fix those first:

```
planopticon> /provider openai
planopticon> /model gpt-4o-mini
```

#### Companion is slow

The companion makes LLM API calls for chat messages. To speed things up:

1. Use a faster model: `/model gpt-4o-mini` or `/model claude-haiku-4-5-20251001`
2. Use direct queries instead of chat: `/entities`, `/search`, `/neighbors` don't need an LLM
3. Use Ollama locally for lower latency: `/provider ollama`

### Export issues

#### Obsidian export has broken links

Make sure your Obsidian vault has wiki-links enabled (Settings > Files & Links > Use [[Wikilinks]]). PlanOpticon exports use wiki-link syntax by default.

#### PDF export fails

PDF export requires the `pdf` extra:

```bash
pip install planopticon[pdf]
```

This installs WeasyPrint, which has system dependencies. On macOS:

```bash
brew install pango
```

On Ubuntu:

```bash
sudo apt-get install libpango1.0-dev
```
