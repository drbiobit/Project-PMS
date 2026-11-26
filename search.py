"""search.py — command-line semantic search.

Embeds a free-text query via the running llama-server, ranks it against the
stored vectors in SQLite, and prints the top matches with scores and paths.

    ./venv/bin/python search.py --query "a red sports car in the rain" --top 10
"""

from __future__ import annotations

import argparse
import os
import sys

from common import (
    EmbeddingClient,
    MediaDB,
    cosine_rank,
    load_config,
    server_url,
)


def search(cfg: dict, query: str, top_n: int):
    emb = cfg["embedding"]
    client = EmbeddingClient(
        base_url=server_url(cfg),
        dim=emb["dim"],
        query_prefix=emb["query_prefix"],
        query_prefix_text=emb["query_prefix_text"],
    )
    qvec = client.embed_text(query)

    db_path = os.path.abspath(cfg["db_path"])
    with MediaDB(db_path) as db:
        paths, filenames, kinds, matrix = db.load_all()

    if matrix.size == 0:
        print("No media indexed yet. Run ./run.sh (or build_index.py) first.")
        return

    ranked = cosine_rank(matrix, qvec, top_n)
    for rank, (idx, score) in enumerate(ranked, start=1):
        print(f"{rank:>2}. {score:.4f}  [{kinds[idx]:>5}]  {filenames[idx]}  "
              f"({paths[idx]})")


def main():
    ap = argparse.ArgumentParser(description="Semantic search over indexed media.")
    ap.add_argument("--query", required=True, help="free-text query")
    ap.add_argument("--top", type=int, default=None, help="number of results")
    ap.add_argument("--config", default="config.json", help="path to config.json")
    ap.add_argument("--db", default=None, help="override db path")
    args = ap.parse_args()

    cfg = load_config(args.config)
    if args.db:
        cfg["db_path"] = args.db
    top_n = args.top or cfg["web"]["top_n"]

    search(cfg, args.query, top_n)


if __name__ == "__main__":
    main()
