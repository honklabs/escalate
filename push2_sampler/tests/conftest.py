import sys
from pathlib import Path

# Allow "pytest" to be run from anywhere without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
