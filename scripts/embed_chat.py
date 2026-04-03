#!/usr/bin/env python
"""
Chat Embedding Pipeline — vectorizes WhatsApp messages using nomic-embed-text
via Ollama for semantic search during column writing.

Embeds all non-system messages from parsed_messages.json and stores vectors
locally as a searchable index. Optionally upserts to Pinecone.

Usage:
    python scripts/embed_chat.py                          # embed all messages
    python scripts/embed_chat.py --query "trade veto"     # search embedded messages
    python scripts/embed_chat.py --query "trade veto" -n 10
    python scripts/embed_chat.py --rebuild                # force re-embed everything
    python scripts/embed_chat.py --stats                  # show index stats
"""

import argparse
import json
import math
import sys
import time
import urllib.request
import urllib.error

from shared import (
    CHAT_DIR,
    OLLAMA_BASE,
    EMBED_MODEL,
    EMBEDDING_BATCH_SIZE as BATCH_SIZE,
)

PARSED_MESSAGES = CHAT_DIR / "parsed_messages.json"
EMBEDDINGS_PATH = CHAT_DIR / "embeddings.json"


# ---------------------------------------------------------------------------
# Ollama embedding API
# ---------------------------------------------------------------------------


def embed_batch(texts, model=EMBED_MODEL):
    """Embed a batch of texts via Ollama /api/embed."""
    payload = {"model": model, "input": texts}
    url = f"{OLLAMA_BASE}/api/embed"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result.get("embeddings", [])
    except urllib.error.URLError as e:
        print(f"Error: Ollama unreachable at {OLLAMA_BASE}: {e}", file=sys.stderr)
        return []


def embed_single(text, model=EMBED_MODEL):
    """Embed a single text string."""
    result = embed_batch([text], model)
    return result[0] if result else None


# ---------------------------------------------------------------------------
# Vector math (no numpy needed)
# ---------------------------------------------------------------------------


def cosine_similarity(a, b):
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ---------------------------------------------------------------------------
# Index management
# ---------------------------------------------------------------------------


def load_messages():
    """Load parsed messages, filtering out system messages and empties."""
    if not PARSED_MESSAGES.exists():
        print(f"Error: {PARSED_MESSAGES} not found.", file=sys.stderr)
        print("Run: python scripts/parse_whatsapp.py first", file=sys.stderr)
        sys.exit(1)

    data = json.load(open(PARSED_MESSAGES, "r", encoding="utf-8"))
    messages = data.get("messages", [])

    # Filter: non-system, has text, has sender
    filtered = [
        m
        for m in messages
        if not m.get("is_system")
        and m.get("text")
        and m.get("sender")
        and len(m["text"].strip()) > 5  # skip very short messages
    ]
    return filtered


def load_index():
    """Load existing embeddings index."""
    if EMBEDDINGS_PATH.exists():
        return json.load(open(EMBEDDINGS_PATH, "r", encoding="utf-8"))
    return {"version": 1, "model": EMBED_MODEL, "entries": []}


def save_index(index):
    """Save embeddings index."""
    EMBEDDINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(EMBEDDINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, separators=(",", ":"))  # compact for size
    size_mb = EMBEDDINGS_PATH.stat().st_size / (1024 * 1024)
    print(f"Saved index: {len(index['entries'])} entries, {size_mb:.1f} MB")


def build_index(messages, existing_index=None, rebuild=False):
    """Embed messages and build/update the index."""
    if existing_index and not rebuild:
        existing_ids = {e["id"] for e in existing_index.get("entries", [])}
        to_embed = [m for m in messages if m["id"] not in existing_ids]
        entries = list(existing_index.get("entries", []))
    else:
        to_embed = messages
        entries = []

    if not to_embed:
        print("All messages already embedded. Use --rebuild to re-embed.")
        return existing_index or {
            "version": 1,
            "model": EMBED_MODEL,
            "entries": entries,
        }

    total = len(to_embed)
    print(f"Embedding {total} messages in batches of {BATCH_SIZE}...")

    start = time.time()
    for i in range(0, total, BATCH_SIZE):
        batch = to_embed[i : i + BATCH_SIZE]
        texts = [
            f"[{m['sender']} {m['timestamp_local'][:10]}] {m['text'][:500]}"
            for m in batch
        ]

        embeddings = embed_batch(texts)
        if not embeddings:
            print(f"  Batch {i // BATCH_SIZE + 1} failed, skipping...", file=sys.stderr)
            continue

        for m, vec in zip(batch, embeddings):
            entries.append(
                {
                    "id": m["id"],
                    "sender": m["sender"],
                    "date": m["timestamp_local"][:10],
                    "text": m["text"][:300],  # truncate for index size
                    "vec": vec,
                }
            )

        done = min(i + BATCH_SIZE, total)
        elapsed = time.time() - start
        rate = done / elapsed if elapsed > 0 else 0
        eta = (total - done) / rate if rate > 0 else 0
        print(
            f"  {done}/{total} ({done*100//total}%) — {rate:.0f} msg/s, ETA {eta:.0f}s"
        )

    elapsed = time.time() - start
    print(f"Embedded {len(entries)} messages in {elapsed:.1f}s")

    return {"version": 1, "model": EMBED_MODEL, "entries": entries}


def search_index(index, query, top_n=5):
    """Search the index for messages similar to query."""
    query_vec = embed_single(query)
    if not query_vec:
        print("Error: Failed to embed query", file=sys.stderr)
        return []

    scored = []
    for entry in index.get("entries", []):
        sim = cosine_similarity(query_vec, entry["vec"])
        scored.append((sim, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:top_n]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Embed and search WhatsApp chat messages"
    )
    parser.add_argument(
        "--rebuild", action="store_true", help="Re-embed all messages from scratch"
    )
    parser.add_argument(
        "--query", "-q", type=str, help="Search query to find relevant messages"
    )
    parser.add_argument(
        "-n", type=int, default=5, help="Number of results to return (default: 5)"
    )
    parser.add_argument("--stats", action="store_true", help="Show index statistics")
    parser.add_argument(
        "--model", default=EMBED_MODEL, help=f"Embedding model (default: {EMBED_MODEL})"
    )
    args = parser.parse_args()

    if args.stats:
        index = load_index()
        entries = index.get("entries", [])
        if not entries:
            print("No embeddings index found. Run without --stats to build it.")
            return
        senders = {}
        dates = set()
        for e in entries:
            senders[e["sender"]] = senders.get(e["sender"], 0) + 1
            dates.add(e["date"])
        print(
            f"Index: {len(entries)} messages, {len(senders)} senders, {len(dates)} days"
        )
        print(f"Date range: {min(dates)} to {max(dates)}")
        print(f"Model: {index.get('model', 'unknown')}")
        size_mb = (
            EMBEDDINGS_PATH.stat().st_size / (1024 * 1024)
            if EMBEDDINGS_PATH.exists()
            else 0
        )
        print(f"Size: {size_mb:.1f} MB")
        print("\nMessages per sender:")
        for sender, count in sorted(senders.items(), key=lambda x: -x[1]):
            print(f"  {sender}: {count}")
        return

    if args.query:
        index = load_index()
        if not index.get("entries"):
            print("No embeddings index found. Run without --query first to build it.")
            return
        print(f"Searching for: '{args.query}'\n")
        results = search_index(index, args.query, top_n=args.n)
        for i, (score, entry) in enumerate(results, 1):
            print(f"  {i}. [{score:.3f}] {entry['sender']} ({entry['date']})")
            print(f"     {entry['text'][:120]}")
            print()
        return

    # Build/update index
    messages = load_messages()
    print(f"Loaded {len(messages)} embeddable messages")

    existing = load_index() if not args.rebuild else None
    index = build_index(messages, existing, rebuild=args.rebuild)
    save_index(index)


if __name__ == "__main__":
    main()
