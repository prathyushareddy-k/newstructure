#!/usr/bin/env python3
"""
extract_structured.py
---------------------
Extract structured data from unstructured documents (HTML, Markdown, plaintext)
using the Anthropic Claude API and a user-supplied JSON schema.

Usage:
    python extract_structured.py <input_file> <schema_file> [options]

Examples:
    python extract_structured.py report.html schema.json
    python extract_structured.py notes.md schema.json --output result.json
    python extract_structured.py data.txt schema.json --pretty
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

import anthropic

# ---------------------------------------------------------------------------
# Format detection & conversion to Markdown
# ---------------------------------------------------------------------------

SUPPORTED_EXTENSIONS = {
    # HTML-like
    ".html", ".htm", ".xhtml",
    # Markdown
    ".md", ".markdown", ".mdown", ".mkd",
    # Plain text
    ".txt", ".text", ".log", ".csv", ".tsv",
    # Structured text often treated as plain
    ".rst", ".org", ".adoc", ".asciidoc",
    # Code / config that may contain docs
    ".json", ".yaml", ".yml", ".toml", ".xml",
}


def detect_format(path: Path) -> str:
    """Return a human-readable format label based on file extension."""
    ext = path.suffix.lower()
    if ext in {".html", ".htm", ".xhtml"}:
        return "html"
    if ext in {".md", ".markdown", ".mdown", ".mkd"}:
        return "markdown"
    if ext in {".rst"}:
        return "rst"
    if ext in {".org"}:
        return "org"
    if ext in {".adoc", ".asciidoc"}:
        return "asciidoc"
    if ext in {".xml"}:
        return "xml"
    if ext in {".json"}:
        return "json"
    if ext in {".yaml", ".yml"}:
        return "yaml"
    if ext in {".toml"}:
        return "toml"
    if ext in {".csv"}:
        return "csv"
    if ext in {".tsv"}:
        return "tsv"
    return "plaintext"


def html_to_markdown(html: str) -> str:
    """
    Convert HTML to Markdown, retaining as much content as possible.
    Uses the `markdownify` library if available, otherwise falls back to a
    regex-based approach that handles common elements.
    """
    try:
        import markdownify  # pip install markdownify
        return markdownify.markdownify(html, heading_style="ATX", strip=["script", "style"])
    except ImportError:
        pass

    # Fallback: basic regex conversion
    text = html

    # Remove script / style blocks
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", text, flags=re.DOTALL | re.IGNORECASE)

    # Headings
    for level in range(6, 0, -1):
        text = re.sub(
            rf"<h{level}[^>]*>(.*?)</h{level}>",
            lambda m, lv=level: "\n" + "#" * lv + " " + m.group(1).strip() + "\n",
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )

    # Bold / strong
    text = re.sub(r"<(strong|b)[^>]*>(.*?)</\1>", r"**\2**", text, flags=re.DOTALL | re.IGNORECASE)
    # Italic / em
    text = re.sub(r"<(em|i)[^>]*>(.*?)</\1>", r"*\2*", text, flags=re.DOTALL | re.IGNORECASE)
    # Links
    text = re.sub(r'<a[^>]+href=["\']([^"\']*)["\'][^>]*>(.*?)</a>', r"[\2](\1)", text, flags=re.DOTALL | re.IGNORECASE)
    # Images
    text = re.sub(r'<img[^>]+alt=["\']([^"\']*)["\'][^>]*/?>', r"![\1]", text, flags=re.IGNORECASE)
    # Line breaks
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    # Paragraphs
    text = re.sub(r"<p[^>]*>(.*?)</p>", r"\n\1\n", text, flags=re.DOTALL | re.IGNORECASE)
    # List items
    text = re.sub(r"<li[^>]*>(.*?)</li>", r"- \1\n", text, flags=re.DOTALL | re.IGNORECASE)
    # Table rows → pipe-separated
    text = re.sub(r"<tr[^>]*>(.*?)</tr>", lambda m: "| " + " | ".join(
        re.sub(r"<[^>]+>", "", cell).strip()
        for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", m.group(1), re.DOTALL | re.IGNORECASE)
    ) + " |\n", text, flags=re.DOTALL | re.IGNORECASE)
    # Code blocks
    text = re.sub(r"<pre[^>]*><code[^>]*>(.*?)</code></pre>", r"\n```\n\1\n```\n", text, flags=re.DOTALL | re.IGNORECASE)
    # Inline code
    text = re.sub(r"<code[^>]*>(.*?)</code>", r"`\1`", text, flags=re.DOTALL | re.IGNORECASE)
    # Strip remaining tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decode common HTML entities
    entities = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'", "&nbsp;": " "}
    for ent, char in entities.items():
        text = text.replace(ent, char)
    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def rst_to_markdown(text: str) -> str:
    """Basic RST → Markdown conversion."""
    # Section headings (underline style)
    lines = text.split("\n")
    output = []
    i = 0
    underline_chars = "=-~^\"'`#"
    while i < len(lines):
        if i + 1 < len(lines) and lines[i + 1] and all(c in underline_chars for c in lines[i + 1]) and len(lines[i + 1]) >= len(lines[i]):
            char = lines[i + 1][0]
            level_map = {}
            level = level_map.setdefault(char, len(level_map) + 1)
            output.append("#" * min(level, 6) + " " + lines[i])
            i += 2
            continue
        output.append(lines[i])
        i += 1
    text = "\n".join(output)
    # Bold **text**
    text = re.sub(r"\*\*(.+?)\*\*", r"**\1**", text)
    # Italic *text*
    text = re.sub(r"\*(.+?)\*", r"*\1*", text)
    # Inline code ``code``
    text = re.sub(r"``(.+?)``", r"`\1`", text)
    # Links `text <url>`_
    text = re.sub(r"`(.+?) <(.+?)>`_", r"[\1](\2)", text)
    return text.strip()


def csv_to_markdown(text: str, delimiter: str = ",") -> str:
    """Convert CSV/TSV to a Markdown table."""
    import csv, io
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = list(reader)
    if not rows:
        return text
    header = rows[0]
    md = "| " + " | ".join(header) + " |\n"
    md += "| " + " | ".join(["---"] * len(header)) + " |\n"
    for row in rows[1:]:
        # Pad short rows
        padded = row + [""] * (len(header) - len(row))
        md += "| " + " | ".join(padded[:len(header)]) + " |\n"
    return md


def to_markdown(raw: str, fmt: str) -> str:
    """Dispatch to the appropriate converter and return Markdown."""
    if fmt == "markdown":
        return raw  # Already Markdown
    if fmt == "html":
        return html_to_markdown(raw)
    if fmt == "rst":
        return rst_to_markdown(raw)
    if fmt == "csv":
        return csv_to_markdown(raw, delimiter=",")
    if fmt == "tsv":
        return csv_to_markdown(raw, delimiter="\t")
    if fmt in {"json", "yaml", "yml", "toml", "xml"}:
        # Wrap structured formats in a code block so Claude can parse them
        return f"```{fmt}\n{raw}\n```"
    # org, adoc, plaintext — return as-is; Claude handles them well natively
    return raw


# ---------------------------------------------------------------------------
# JSON schema validation helpers
# ---------------------------------------------------------------------------

def load_schema(schema_path: Path) -> dict:
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)
    if not isinstance(schema, dict):
        raise ValueError("Schema must be a JSON object (dict).")
    return schema


# ---------------------------------------------------------------------------
# Claude API extraction
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a precise data-extraction assistant.
The user will give you a document (already converted to Markdown) and a JSON schema.
Your task:
1. Read the document carefully.
2. Extract ONLY the information that matches the provided JSON schema.
3. Return ONLY a single, valid JSON object that conforms to that schema — no extra text, no markdown fences, no explanation.
4. If a field cannot be found in the document, use null for optional fields or an empty string / empty array for required ones.
5. Do not hallucinate values that are not present in the document.
"""


def extract_with_claude(markdown_content: str, schema: dict, model: str = "claude-sonnet-4-6") -> dict:
    """
    Call the Claude API to extract structured data from Markdown content
    according to the provided JSON schema.
    """
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    user_message = f"""\
## JSON Schema (target structure)
```json
{json.dumps(schema, indent=2)}
```

## Document Content (Markdown)
{markdown_content}

Extract the structured data from the document above and return it as a JSON object matching the schema.
"""

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    raw_text = response.content[0].text.strip()

    # Strip accidental markdown fences
    raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
    raw_text = re.sub(r"\s*```$", "", raw_text)

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Claude returned non-JSON output.\n"
            f"Raw response:\n{raw_text}\n\nParse error: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract structured data from unstructured documents using Claude.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("input_file", type=Path, help="Path to the input document.")
    parser.add_argument("schema_file", type=Path, help="Path to the JSON schema file.")
    parser.add_argument(
        "--output", "-o", type=Path, default=None,
        help="Write JSON output to this file (default: print to stdout).",
    )
    parser.add_argument(
        "--pretty", "-p", action="store_true",
        help="Pretty-print the JSON output with indentation.",
    )
    parser.add_argument(
        "--model", "-m", default="claude-sonnet-4-6",
        help="Claude model to use (default: claude-sonnet-4-6).",
    )
    parser.add_argument(
        "--show-markdown", action="store_true",
        help="Print the intermediate Markdown conversion to stderr for debugging.",
    )
    parser.add_argument(
        "--encoding", default="utf-8",
        help="File encoding for reading the input (default: utf-8).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # --- Validate inputs ---
    if not args.input_file.exists():
        print(f"Error: Input file not found: {args.input_file}", file=sys.stderr)
        sys.exit(1)
    if not args.schema_file.exists():
        print(f"Error: Schema file not found: {args.schema_file}", file=sys.stderr)
        sys.exit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    # --- Read input ---
    try:
        raw_content = args.input_file.read_text(encoding=args.encoding, errors="replace")
    except Exception as exc:
        print(f"Error reading input file: {exc}", file=sys.stderr)
        sys.exit(1)

    # --- Detect format & convert to Markdown ---
    fmt = detect_format(args.input_file)
    print(f"[i] Detected format: {fmt}", file=sys.stderr)

    markdown_content = to_markdown(raw_content, fmt)

    if args.show_markdown:
        print("--- Intermediate Markdown ---", file=sys.stderr)
        print(markdown_content, file=sys.stderr)
        print("----------------------------", file=sys.stderr)

    # --- Load schema ---
    try:
        schema = load_schema(args.schema_file)
    except Exception as exc:
        print(f"Error loading schema: {exc}", file=sys.stderr)
        sys.exit(1)

    # --- Extract via Claude ---
    print(f"[i] Sending to Claude ({args.model}) for extraction…", file=sys.stderr)
    try:
        result = extract_with_claude(markdown_content, schema, model=args.model)
    except Exception as exc:
        print(f"Error during extraction: {exc}", file=sys.stderr)
        sys.exit(1)

    # --- Output ---
    indent = 2 if args.pretty else None
    json_output = json.dumps(result, indent=indent, ensure_ascii=False)

    if args.output:
        args.output.write_text(json_output + "\n", encoding="utf-8")
        print(f"[✓] Output written to: {args.output}", file=sys.stderr)
    else:
        print(json_output)


if __name__ == "__main__":
    main()
