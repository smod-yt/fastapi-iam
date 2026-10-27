import os
import subprocess
import sys

env_file = sys.argv[1] if len(sys.argv) > 1 else ".env.dev"

env = os.environ.copy()
env["ENV_FILE"] = env_file

subprocess.run(
    ["alembic", "upgrade", "head"],
    env=env,
    check=True,
)
