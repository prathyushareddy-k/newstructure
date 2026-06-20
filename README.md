# Document Structured Data Extractor

Extract structured, schema-validated JSON from any unstructured document using the Anthropic Claude API.

## Features

- **Auto-detects format** from file extension (`.html`, `.md`, `.txt`, `.rst`, `.csv`, `.tsv`, `.json`, `.yaml`, `.xml`, and more)
- **Converts to Markdown first** to retain maximum content fidelity before sending to Claude
- **Accepts any JSON schema** — you define what data you want extracted
- **Single-file CLI** with no heavyweight dependencies beyond `anthropic`

## Supported Input Formats

| Extension | Format | Conversion |
|-----------|--------|------------|
| `.html` `.htm` `.xhtml` | HTML | → Markdown (via `markdownify` or built-in regex fallback) |
| `.md` `.markdown` `.mdown` | Markdown | No conversion needed |
| `.txt` `.text` `.log` | Plain text | Passed through as-is |
| `.rst` | reStructuredText | Basic RST → Markdown |
| `.csv` | CSV | → Markdown table |
| `.tsv` | TSV | → Markdown table |
| `.json` `.yaml` `.xml` `.toml` | Structured data | Wrapped in fenced code block |
| `.org` `.adoc` | Org / AsciiDoc | Passed through |

## Installation

```bash
pip install anthropic markdownify
```

> `markdownify` is optional but recommended for better HTML conversion. The tool falls back to a built-in regex converter if it's not installed.

## Setup

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

## Usage

```
python extract_structured.py <input_file> <schema_file> [options]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `input_file` | Path to the document to process |
| `schema_file` | Path to the JSON schema defining the output structure |
| `--output FILE` | Write JSON result to a file instead of stdout |
| `--pretty` | Pretty-print output with 2-space indentation |
| `--model MODEL` | Claude model to use (default: `claude-sonnet-4-6`) |
| `--show-markdown` | Print the intermediate Markdown to stderr for debugging |
| `--encoding ENC` | Input file encoding (default: `utf-8`) |

## Examples

### Extract job posting data from HTML

```bash
python extract_structured.py examples/job_posting.html examples/job_posting_schema.json --pretty
```

### Extract article metadata from Markdown

```bash
python extract_structured.py my_article.md examples/article_schema.json --output result.json --pretty
```

### Extract from plain text, save to file

```bash
python extract_structured.py notes.txt my_schema.json -o extracted.json -p
```

### Debug: see intermediate Markdown

```bash
python extract_structured.py report.html schema.json --show-markdown
```

## Writing a JSON Schema

The schema file is a standard [JSON Schema](https://json-schema.org/) object. Example:

```json
{
  "type": "object",
  "properties": {
    "title":   { "type": "string" },
    "authors": { "type": "array", "items": { "type": "string" } },
    "date":    { "type": ["string", "null"] },
    "summary": { "type": "string" }
  },
  "required": ["title", "summary"]
}
```

- Use `"type": ["string", "null"]` for optional fields (Claude will set them to `null` if not found).
- Add `"description"` fields to guide Claude on what to look for.
- See `examples/` for complete schemas.

## Output

The program prints (or writes) a single valid JSON object matching your schema:

```json
{
  "job_title": "Senior Python Engineer",
  "company": "Acme Corp",
  "location": "Austin, TX (Hybrid)",
  "employment_type": "full-time",
  "salary_range": {
    "min": 130000,
    "max": 160000,
    "currency": "USD",
    "period": "annual"
  },
  "required_skills": ["Python", "FastAPI", "PostgreSQL", "Redis", "Docker", "Kubernetes", "AWS"],
  ...
}
```

## Files

```
extract_structured.py          # Main CLI program
examples/
  job_posting.html             # Sample HTML document
  job_posting_schema.json      # Schema for job postings
  article_schema.json          # Generic article/report schema
README.md
```
