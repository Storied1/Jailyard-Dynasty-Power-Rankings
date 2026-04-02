#!/usr/bin/env python
"""
Ollama MCP Server — exposes local Ollama models as Claude Code tools.

Implements the Model Context Protocol (MCP) over stdio using JSON-RPC 2.0
with Content-Length framing. Zero external dependencies beyond stdlib.

Provides three tools:
  - ollama_generate: text generation (completion)
  - ollama_chat: multi-turn chat completion
  - ollama_embed: generate embeddings via nomic-embed-text

Usage (registered in .mcp.json):
    { "command": "python", "args": ["scripts/ollama_mcp_server.py"] }
"""

import json
import sys
import urllib.request
import urllib.error

OLLAMA_BASE = "http://localhost:11434"
DEFAULT_MODEL = "qwen3:30b-a3b"
EMBED_MODEL = "nomic-embed-text"

# ---------------------------------------------------------------------------
# Ollama API helpers
# ---------------------------------------------------------------------------


def ollama_generate(
    model, prompt, system=None, temperature=0.7, max_tokens=4096, think=True
):
    """Call Ollama /api/generate (streaming off).

    Args:
        think: If True (default), Qwen 3 uses thinking mode and we double
               num_predict to compensate. If False, appends /no_think to
               skip reasoning — faster and no token waste.
    """
    if not think:
        prompt = prompt.rstrip() + " /no_think"
        token_budget = max_tokens
    else:
        token_budget = max_tokens * 2

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": token_budget},
    }
    if system:
        payload["system"] = system
    return _post("/api/generate", payload)


def ollama_chat(model, messages, temperature=0.7, max_tokens=4096, think=True):
    """Call Ollama /api/chat (streaming off).

    Args:
        think: If True, doubles num_predict for thinking overhead.
               If False, appends /no_think to last user message.
    """
    if not think:
        token_budget = max_tokens
        # Append /no_think to the last user message
        messages = [m.copy() for m in messages]
        for m in reversed(messages):
            if m.get("role") == "user":
                m["content"] = m["content"].rstrip() + " /no_think"
                break
    else:
        token_budget = max_tokens * 2

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": token_budget},
    }
    return _post("/api/chat", payload)


def ollama_embed(text, model=EMBED_MODEL):
    """Call Ollama /api/embed."""
    payload = {"model": model, "input": text}
    return _post("/api/embed", payload)


def _post(path, payload):
    """HTTP POST to Ollama, return parsed JSON."""
    url = OLLAMA_BASE + path
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        return {"error": f"Ollama unreachable at {OLLAMA_BASE}: {e}"}
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# MCP Protocol — stdio JSON-RPC with Content-Length framing
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "ollama_generate",
        "description": (
            "Generate text using a local Ollama model (Qwen 3 30B MoE by default). "
            "Good for drafts, creative writing, summaries, and bulk text generation. "
            "Use the 'system' parameter to set persona/instructions."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The prompt to generate from",
                },
                "system": {
                    "type": "string",
                    "description": "Optional system prompt for persona/instructions",
                },
                "model": {
                    "type": "string",
                    "description": f"Model name (default: {DEFAULT_MODEL})",
                    "default": DEFAULT_MODEL,
                },
                "temperature": {
                    "type": "number",
                    "description": "Sampling temperature 0-2 (default: 0.7)",
                    "default": 0.7,
                },
                "max_tokens": {
                    "type": "integer",
                    "description": "Max tokens to generate (default: 4096)",
                    "default": 4096,
                },
                "think": {
                    "type": "boolean",
                    "description": "Enable thinking mode (default: true). Set false for faster responses on simple tasks.",
                    "default": True,
                },
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "ollama_chat",
        "description": (
            "Multi-turn chat with a local Ollama model. Send a conversation as a list of "
            "{role, content} messages. Good for iterative refinement, Q&A, and review tasks."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "messages": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "role": {
                                "type": "string",
                                "enum": ["system", "user", "assistant"],
                            },
                            "content": {"type": "string"},
                        },
                        "required": ["role", "content"],
                    },
                    "description": "Conversation messages [{role, content}, ...]",
                },
                "model": {
                    "type": "string",
                    "description": f"Model name (default: {DEFAULT_MODEL})",
                    "default": DEFAULT_MODEL,
                },
                "temperature": {"type": "number", "default": 0.7},
                "max_tokens": {"type": "integer", "default": 4096},
                "think": {
                    "type": "boolean",
                    "description": "Enable thinking mode (default: true). Set false for faster responses.",
                    "default": True,
                },
            },
            "required": ["messages"],
        },
    },
    {
        "name": "ollama_embed",
        "description": (
            "Generate embeddings using the local nomic-embed-text model. "
            "Pass a string or list of strings. Returns float vectors for semantic search."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {
                    "description": "Text string or list of strings to embed",
                },
                "model": {
                    "type": "string",
                    "description": f"Embedding model (default: {EMBED_MODEL})",
                    "default": EMBED_MODEL,
                },
            },
            "required": ["text"],
        },
    },
]


def read_message():
    """Read a JSON-RPC message from stdin (Content-Length framing)."""
    headers = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None  # EOF
        line = line.decode("utf-8").rstrip("\r\n")
        if not line:
            break  # empty line = end of headers
        if ": " in line:
            key, value = line.split(": ", 1)
            headers[key] = value

    content_length = int(headers.get("Content-Length", 0))
    if content_length == 0:
        return None
    body = sys.stdin.buffer.read(content_length)
    return json.loads(body.decode("utf-8"))


def write_message(msg):
    """Write a JSON-RPC message to stdout with Content-Length framing."""
    body = json.dumps(msg)
    encoded = body.encode("utf-8")
    header = f"Content-Length: {len(encoded)}\r\n\r\n"
    sys.stdout.buffer.write(header.encode("utf-8"))
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


def make_response(id, result):
    return {"jsonrpc": "2.0", "id": id, "result": result}


def make_error(id, code, message):
    return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}


def handle_tool_call(name, arguments):
    """Dispatch a tool call to the appropriate Ollama API."""
    if name == "ollama_generate":
        result = ollama_generate(
            model=arguments.get("model", DEFAULT_MODEL),
            prompt=arguments["prompt"],
            system=arguments.get("system"),
            temperature=arguments.get("temperature", 0.7),
            max_tokens=arguments.get("max_tokens", 4096),
            think=arguments.get("think", True),
        )
        if "error" in result:
            return [{"type": "text", "text": f"Error: {result['error']}"}]
        return [{"type": "text", "text": result.get("response", "")}]

    elif name == "ollama_chat":
        result = ollama_chat(
            model=arguments.get("model", DEFAULT_MODEL),
            messages=arguments["messages"],
            temperature=arguments.get("temperature", 0.7),
            max_tokens=arguments.get("max_tokens", 4096),
            think=arguments.get("think", True),
        )
        if "error" in result:
            return [{"type": "text", "text": f"Error: {result['error']}"}]
        msg = result.get("message", {})
        return [{"type": "text", "text": msg.get("content", "")}]

    elif name == "ollama_embed":
        text = arguments["text"]
        result = ollama_embed(text, model=arguments.get("model", EMBED_MODEL))
        if "error" in result:
            return [{"type": "text", "text": f"Error: {result['error']}"}]
        embeddings = result.get("embeddings", [])
        return [{"type": "text", "text": json.dumps(embeddings)}]

    else:
        return [{"type": "text", "text": f"Unknown tool: {name}"}]


def main():
    """Main MCP server loop."""
    while True:
        msg = read_message()
        if msg is None:
            break

        method = msg.get("method", "")
        id = msg.get("id")
        params = msg.get("params", {})

        if method == "initialize":
            write_message(
                make_response(
                    id,
                    {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "ollama-local", "version": "1.0.0"},
                    },
                )
            )

        elif method == "notifications/initialized":
            pass  # no response needed for notifications

        elif method == "tools/list":
            write_message(make_response(id, {"tools": TOOLS}))

        elif method == "tools/call":
            name = params.get("name", "")
            arguments = params.get("arguments", {})
            try:
                content = handle_tool_call(name, arguments)
                write_message(make_response(id, {"content": content}))
            except Exception as e:
                write_message(
                    make_response(
                        id,
                        {
                            "content": [{"type": "text", "text": f"Error: {e}"}],
                            "isError": True,
                        },
                    )
                )

        elif method == "ping":
            write_message(make_response(id, {}))

        elif id is not None:
            write_message(make_error(id, -32601, f"Method not found: {method}"))


if __name__ == "__main__":
    main()
