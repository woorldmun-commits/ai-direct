"""Bounded offline CLI. Reports never echo input values or validation details."""
import argparse
import json
from pathlib import Path

from pydantic import ValidationError
from app.agents.supervisor import Manifest, Submission, verify

MAX_BYTES = 1_000_000


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def load(path: Path, model):
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("input too large")
    data = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
    return model.model_validate(data)


def main():
    parser = argparse.ArgumentParser(description="Offline structured evidence consistency gate")
    parser.add_argument("command", choices=["verify"])
    parser.add_argument("claims", type=Path)
    parser.add_argument("--evidence", type=Path, required=True,
                        help="Manifest supplied independently by the integration owner")
    args = parser.parse_args()
    try:
        result = verify(load(args.claims, Submission), load(args.evidence, Manifest))
    except (OSError, ValueError, ValidationError, RecursionError):
        result = {"status": "BLOCKED", "issues": [{"code": "invalid_input"}],
                  "authenticity_verified": False}
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
