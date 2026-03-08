# Use Cases

PlanOpticon is built for anyone who needs to turn unstructured content — recordings, documents, notes, web pages — into structured, searchable, actionable knowledge. Here are the most common ways people use it.

---

## Meeting notes and follow-ups

**Problem:** You have hours of meeting recordings but no time to rewatch them. Action items get lost, decisions are forgotten, and new team members have no way to catch up.

**Solution:** Point PlanOpticon at your recordings and get structured transcripts, action items with assignees and deadlines, key decisions, and a knowledge graph linking people to topics.

```bash
# Analyze a single meeting recording
planopticon analyze -i standup-2026-03-07.mp4 -o ./meetings/march-7

# Process a month of recordings at once
planopticon batch -i ./recordings/march -o ./meetings --title "March 2026 Meetings"

# Query what was decided
planopticon query "What decisions were made about the API redesign?"

# Find all action items assigned to Alice
planopticon query "relationships --source Alice"
```

**What you get:**

- Full transcript with timestamps and speaker segments
- Action items extracted with assignees, deadlines, and context
- Key points and decisions highlighted
- Knowledge graph connecting people, topics, technologies, and decisions
- Markdown report you can share with the team

**Next steps:** Export to your team's wiki or note system:

```bash
# Push to GitHub wiki
planopticon wiki generate --input ./meetings --output ./wiki
planopticon wiki push --input ./wiki --target "github://your-org/your-repo"

# Export to Obsidian for personal knowledge management
planopticon export obsidian --input ./meetings --output ~/Obsidian/Meetings
```

---

## Research processing

**Problem:** You're researching a topic across YouTube talks, arXiv papers, blog posts, and podcasts. Information is scattered and hard to cross-reference.

**Solution:** Ingest everything into a single knowledge graph, then query across all sources.

```bash
# Ingest a YouTube conference talk
planopticon ingest "https://youtube.com/watch?v=..." --output ./research

# Ingest arXiv papers
planopticon ingest "https://arxiv.org/abs/2401.12345" --output ./research

# Ingest blog posts and documentation
planopticon ingest "https://example.com/blog/post" --output ./research

# Ingest local PDF papers
planopticon ingest ./papers/ --output ./research --recursive

# Now query across everything
planopticon query "What approaches to vector search were discussed?"
planopticon query "entities --type technology"
planopticon query "neighbors TransformerArchitecture"
```

**What you get:**

- A unified knowledge graph merging entities across all sources
- Cross-references showing where the same concept appears in different sources
- Searchable entity index by type (people, technologies, concepts, papers)
- Relationship maps showing how ideas connect

**Go deeper with the companion:**

```bash
planopticon companion --kb ./research
```

```
planopticon> What are the main approaches to retrieval-augmented generation?
planopticon> /entities --type technology
planopticon> /neighbors RAG
planopticon> /export obsidian
```

---

## Knowledge gathering across platforms

**Problem:** Your team's knowledge is spread across Google Docs, Notion, Obsidian, GitHub wikis, and Apple Notes. There's no single place to search everything.

**Solution:** Pull from all sources into one knowledge graph.

```bash
# Authenticate with your platforms
planopticon auth google
planopticon auth notion
planopticon auth github

# Ingest from Google Workspace
planopticon gws ingest --folder-id abc123 --output ./kb --recursive

# Ingest from Notion
planopticon ingest --source notion --output ./kb

# Ingest from an Obsidian vault
planopticon ingest ~/Obsidian/WorkVault --output ./kb --recursive

# Ingest from GitHub wikis and READMEs
planopticon ingest "github://your-org/project-a" --output ./kb
planopticon ingest "github://your-org/project-b" --output ./kb

# Query the unified knowledge base
planopticon query stats
planopticon query "entities --type person"
planopticon query "What do we know about the authentication system?"
```

**What you get:**

- Merged knowledge graph with provenance tracking (you can see which source each entity came from)
- Deduplicated entities across platforms (same concept mentioned in Notion and Google Docs gets merged)
- Full-text search across all ingested content
- Relationship maps showing how concepts connect across your organization's documents

---

## Team onboarding

**Problem:** New team members spend weeks reading docs, watching recorded meetings, and asking questions to get up to speed.

**Solution:** Build a knowledge base from existing content and let new people explore it conversationally.

```bash
# Build the knowledge base from everything
planopticon batch -i ./recordings/onboarding -o ./kb --title "Team Onboarding"
planopticon ingest ./docs/ --output ./kb --recursive
planopticon ingest ./architecture-decisions/ --output ./kb --recursive

# New team member launches the companion
planopticon companion --kb ./kb
```

```
planopticon> What is the overall architecture of the system?
planopticon> Who are the key people on the team?
planopticon> /entities --type technology
planopticon> What was the rationale for choosing PostgreSQL over MongoDB?
planopticon> /neighbors AuthenticationService
planopticon> What are the main open issues or risks?
```

**What you get:**

- Interactive Q&A over the entire team knowledge base
- Entity exploration — browse people, technologies, services, decisions
- Relationship navigation — "show me everything connected to the payment system"
- No need to rewatch hours of recordings

---

## Data collection and synthesis

**Problem:** You need to collect and synthesize information from many sources — customer interviews, competitor analysis, market research — into a coherent picture.

**Solution:** Batch process recordings and documents, then use the planning agent to generate synthesis artifacts.

```bash
# Process customer interview recordings
planopticon batch -i ./interviews -o ./research --title "Customer Interviews Q1"

# Ingest competitor documentation
planopticon ingest ./competitor-analysis/ --output ./research --recursive

# Ingest market research PDFs
planopticon ingest ./market-reports/ --output ./research --recursive

# Use the planning agent to synthesize
planopticon agent --kb ./research --interactive
```

```
planopticon> Generate a summary of common customer pain points
planopticon> /plan
planopticon> /tasks
planopticon> /export markdown
```

**What you get:**

- Merged knowledge graph across all interviews and documents
- Cross-referenced entities showing which customers mentioned which features
- Agent-generated project plans, PRDs, and task breakdowns based on the data
- Exportable artifacts for sharing with stakeholders

---

## Content creation from video

**Problem:** You have video content (lectures, tutorials, webinars) that you want to turn into written documentation, blog posts, or course materials.

**Solution:** Extract structured knowledge and export it in your preferred format.

```bash
# Analyze the video
planopticon analyze -i webinar-recording.mp4 -o ./content

# Generate multiple document types (no LLM needed for these)
planopticon export markdown --input ./content --output ./docs

# Export to Obsidian for further editing
planopticon export obsidian --input ./content --output ~/Obsidian/Content
```

**What you get for each video:**

- Full transcript (JSON, plain text, SRT subtitles)
- Extracted diagrams reproduced as Mermaid/SVG/PNG
- Charts reproduced with data tables
- Knowledge graph of concepts and relationships
- 7 types of markdown documents: summary, meeting notes, glossary, relationship map, status report, entity index, CSV data

---

## Decision tracking over time

**Problem:** Important decisions are made in meetings but never formally recorded. Months later, nobody remembers why a choice was made.

**Solution:** Process meeting recordings continuously and query the growing knowledge graph for decisions and their context.

```bash
# Process each week's recordings
planopticon batch -i ./recordings/week-12 -o ./decisions --title "Week 12"

# The knowledge graph grows over time — entities merge across weeks
planopticon query "entities --type goal"
planopticon query "entities --type risk"
planopticon query "entities --type milestone"

# Find decisions about a specific topic
planopticon query "What was decided about the database migration?"

# Track risks over time
planopticon query "relationships --type risk"
```

The planning taxonomy automatically classifies entities as goals, requirements, risks, tasks, and milestones — giving you a structured view of project evolution over time.

---

## Zoom / Teams / Meet integration

**Problem:** Meeting recordings are sitting in Zoom/Teams/Meet cloud storage. You want to process them without manually downloading each one.

**Solution:** Authenticate once, list recordings, and process them directly.

```bash
# Authenticate with your meeting platform
planopticon auth zoom
# or: planopticon auth microsoft
# or: planopticon auth google

# List recent recordings
planopticon recordings zoom-list
planopticon recordings teams-list --from 2026-01-01
planopticon recordings meet-list --limit 20

# Process recordings (download + analyze)
planopticon analyze -i "zoom://recording-id" -o ./output
```

**Setup requirements:**

| Platform | What you need |
|----------|--------------|
| Zoom | `ZOOM_CLIENT_ID` + `ZOOM_CLIENT_SECRET` (create an OAuth app at marketplace.zoom.us) |
| Teams | `MICROSOFT_CLIENT_ID` + `MICROSOFT_CLIENT_SECRET` (register an Azure AD app) |
| Meet | `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET` (create OAuth credentials in Google Cloud Console) |

See the [Authentication guide](guide/authentication.md) for detailed setup instructions.

---

## Fully offline processing

**Problem:** You're working with sensitive content that can't leave your network, or you simply don't want to pay for API calls.

**Solution:** Use Ollama for local AI processing with no external API calls.

```bash
# Install Ollama and pull models
ollama pull llama3.2       # Chat/analysis
ollama pull llava          # Vision (diagram detection)

# Install local Whisper for transcription
pip install planopticon[gpu]

# Process entirely offline
planopticon analyze -i sensitive-meeting.mp4 -o ./output --provider ollama
```

PlanOpticon auto-detects Ollama when it's running. If no cloud API keys are configured, it uses Ollama automatically. Pair with local Whisper transcription for a fully air-gapped pipeline.

---

## Competitive research

**Problem:** You want to systematically analyze competitor content — conference talks, documentation, blog posts — and identify patterns.

**Solution:** Ingest competitor content from multiple sources and query for patterns.

```bash
# Ingest competitor conference talks from YouTube
planopticon ingest "https://youtube.com/watch?v=competitor-talk-1" --output ./competitive
planopticon ingest "https://youtube.com/watch?v=competitor-talk-2" --output ./competitive

# Ingest their documentation
planopticon ingest "https://competitor.com/docs" --output ./competitive

# Ingest their GitHub repos
planopticon auth github
planopticon ingest "github://competitor/main-product" --output ./competitive

# Analyze patterns
planopticon query "entities --type technology"
planopticon query "What technologies are competitors investing in?"
planopticon companion --kb ./competitive
```

```
planopticon> What are the common architectural patterns across competitors?
planopticon> /entities --type technology
planopticon> Which technologies appear most frequently?
planopticon> /export markdown
```
