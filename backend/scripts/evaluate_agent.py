#!/usr/bin/env python3
"""Run the deterministic purchase-agent evaluation suite.

Usage (from the repository root):

    python backend/scripts/evaluate_agent.py
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from evals.runner import format_report, run_evaluation  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Avaliação funcional determinística do agente de compras."
    )
    parser.parse_args()
    report = asyncio.run(run_evaluation())
    print(format_report(report))
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
