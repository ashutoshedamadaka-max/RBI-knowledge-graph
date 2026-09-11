import argparse
import json
from pathlib import Path

from app.config.settings import get_settings
from app.evaluation.harness import EvaluationHarness


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate vector-only retrieval against routed Graph RAG.")
    parser.add_argument("--dataset", type=Path, default=Path("data/evaluation/questions.json"))
    parser.add_argument("--output", type=Path, default=Path("data/evaluation/latest-results.json"))
    args = parser.parse_args()

    harness = EvaluationHarness(get_settings())
    report = harness.run(harness.load_cases(args.dataset))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report.model_dump(), indent=2))
    print(json.dumps(report.model_dump(exclude={"results"}), indent=2))


if __name__ == "__main__":
    main()

