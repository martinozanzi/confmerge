import sys

if len(sys.argv) > 1 and sys.argv[1] in ("analyze", "export", "run", "--version", "-v", "--verbose", "-h", "--help"):
    from .cli import main
else:
    from .app import main

raise SystemExit(main())
