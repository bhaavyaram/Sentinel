import os

# Set before any test imports app.config, so the settings object sees it.
os.environ["BACKGROUND_WORKERS"] = "false"