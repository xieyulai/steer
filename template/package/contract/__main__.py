"""``python -m contract`` — evaluate（默认）、``finalize-round``、``write-keeper``、``sanity``。"""
import sys

from experiment import (
    _cli_evaluation_main,
    _cli_finalize_round_main,
    _cli_sanity_main,
    _cli_write_keeper_main,
)

if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "finalize-round":
        sys.argv.pop(1)
        _cli_finalize_round_main()
    elif len(sys.argv) >= 2 and sys.argv[1] == "write-keeper":
        sys.argv.pop(1)
        _cli_write_keeper_main()
    elif len(sys.argv) >= 2 and sys.argv[1] == "sanity":
        sys.argv.pop(1)
        _cli_sanity_main()
    else:
        _cli_evaluation_main()
