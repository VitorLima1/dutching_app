from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .calculator import DutchingValidationError, calcular_dutching


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Calcula dutching para duplas combinadas.")
    parser.add_argument("payload", type=Path, help="Caminho para o payload JSON de entrada.")
    args = parser.parse_args(argv)

    try:
        payload = json.loads(args.payload.read_text(encoding="utf-8"))
        result = calcular_dutching(payload)
    except (OSError, json.JSONDecodeError, DutchingValidationError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
