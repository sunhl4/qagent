cd /home/sunhl/qagent-copy
/home/sunhl/.venvs/company-agent/bin/python -m pytest -q -p no:cacheprovider --tb=no tests/ 2>&1 | tail -8
