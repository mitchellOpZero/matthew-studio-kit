#!/usr/bin/env python3
"""A passive hook. Any failure leaves the original tool untouched."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))

try:
    import support
    if '--flush' in sys.argv:
        support.start_worker()
        support.flush()
    else:
        raw = sys.stdin.buffer.read(2000001)
        if len(raw) <= 2000000:
            support.observe(json.loads(raw))
        elif support.config().get('enabled'):
            support.append('gap', {'reason': 'hook payload exceeded 2 MB; metadata not recovered'})
except Exception:
    pass
# Deliberately no stdout, permission decisions, input rewriting or context injection.
