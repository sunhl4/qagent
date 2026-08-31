"""L1-01d fixture ProblemProvider. Handles: circuit_id / asset_id only.

# 禁止 twin_id
"""


class ProblemProvider:
    name = "eval_stub"

    def describe(self) -> str:
        return self.name
