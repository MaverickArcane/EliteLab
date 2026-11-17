"""Compatibility entry point for existing Rhino Overlay shortcuts."""
from .windows_overlay import CLASS_NAME, load_preferences, run, save_preferences
from .overlay import main


if __name__ == '__main__':
    raise SystemExit(main())
