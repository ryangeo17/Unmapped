#!/usr/bin/env python3
"""Precompute the routable graph. Run once after the campus data changes.

    python3 -m planner.build_cache
"""
import os
import time

from . import graph


def main():
    start = time.time()
    data = graph.write_cache()
    size = os.path.getsize(graph.CACHE) / 1048576
    print("%d edges (%d lawn shortcuts) -> %s, %.1f MB, %.1fs"
          % (len(data["edges"]), data["shortcutCount"], graph.CACHE, size,
             time.time() - start))


if __name__ == "__main__":
    main()
