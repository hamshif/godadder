# generate_env.py

import os
from pathlib import Path

home = os.environ["HOME"]
project_root = Path(__file__).resolve()

env_contents = f"""\
PYTHONPATH={project_root}/src
"""

with open(project_root / ".env", "w") as f:
    f.write(env_contents)

print(".env file generated.")
