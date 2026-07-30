"""PyInstaller entry point. A separate top-level script (rather than pointing
PyInstaller at app/shell.py directly) so shell.py keeps running as part of the
`app` package and its relative imports (`.settings`, `.main`) keep working."""

from app.shell import main

if __name__ == "__main__":
    main()
