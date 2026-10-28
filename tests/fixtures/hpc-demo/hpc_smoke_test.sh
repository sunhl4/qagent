#!/bin/bash
#SBATCH --job-name=company-agent-smoke
#SBATCH --output=company-agent-smoke-%j.out
#SBATCH --error=company-agent-smoke-%j.err
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=00:02:00

set -euo pipefail

echo "status=started"
echo "host=$(hostname)"
echo "date=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
python3 - <<'PY'
import hashlib
payload = b"company-agent-hpc-smoke-test"
digest = hashlib.sha256(payload).hexdigest()
print("test=sha256")
print(f"digest={digest}")
print("status=completed")
PY
