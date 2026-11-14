"""Convenience entry point for the local analysis pipeline (01, 02, 03, 05).

Add `--demo` to generate synthetic demo data (if no real data is present) and
run the core pipeline 01 -> 02 -> 03 end-to-end without the 581 MB raw dataset.
See the "1 分钟体验" section in README.md.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def _pop_demo_flag():
    demo = "--demo" in sys.argv
    if demo:
        sys.argv.remove("--demo")
    return demo


if __name__ == "__main__":
    demo = _pop_demo_flag()
    if demo:
        from scripts.make_demo_data import main as make_demo_data
        make_demo_data()  # refuses to overwrite real data
        # Demo scope: the core pipeline that produces the headline result.
        if "--steps" not in sys.argv:
            sys.argv += ["--steps", "1", "2", "3"]
        if "--engine" not in sys.argv:
            sys.argv += ["--engine", "inprocess"]
    from scripts.run_pipeline import main
    main()
