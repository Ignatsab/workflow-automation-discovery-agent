"""Command line interface for evaluation and artifact generation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .artifacts import generate_mermaid, generate_product_card
from .engine import create_case, evaluate_case


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate an automation intake case")
    sub = parser.add_subparsers(dest="command", required=True)
    new = sub.add_parser("new")
    new.add_argument("case_id")
    new.add_argument("--output", required=True)
    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("case")
    generate = sub.add_parser("generate")
    generate.add_argument("case")
    generate.add_argument("--output-dir", default="output")
    args = parser.parse_args()

    if args.command == "new":
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(create_case(args.case_id), indent=2) + "\n", encoding="utf-8")
        print(str(target))
        return

    record = json.loads(Path(args.case).read_text(encoding="utf-8"))
    if args.command == "evaluate":
        print(json.dumps(evaluate_case(record), indent=2))
        return
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    docx = generate_product_card(record, out / "workflow_automation_product_card.docx")
    diagrams = generate_mermaid(record, out)
    print(json.dumps({"product_card": str(docx), "diagrams": [str(path) for path in diagrams]}, indent=2))


if __name__ == "__main__":
    main()
