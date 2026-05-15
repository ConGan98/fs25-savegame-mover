"""Single entry point for the packaged .exe.

When the .exe runs with no args, it launches the GUI wizard.
When run with a subcommand (summary/migrate/etc.), it acts as a CLI.
"""
from fs25_mover.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
