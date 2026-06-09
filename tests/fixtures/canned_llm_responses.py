"""Canned LLM responses for the offline demo and tests.

The script format is `SCRIPT: dict[role_value -> list[Turn]]` where each Turn
is a list of chunks. A chunk is either:
  - a str: emitted as a text Delta
  - ("tool_call", id, name, args): emitted as a Delta with ToolCallSpec
  - ("done", finish_reason): emitted as the final Delta for the turn
"""

# Planner: decomposes the refactor task into 3 spawn_agent calls
PLANNER_TURN_0 = [
    "Analyzing the request...\n",
    "Plan:\n",
    "  1. Explorer: survey the target file\n",
    "  2. Implementer: apply the dataclass refactor\n",
    "  3. Reviewer: run tests to verify\n",
    ("tool_call", "p1", "spawn_agent", {
        "role": "explorer",
        "task": "Survey tests/fixtures/sample_repo and report file structure",
        "context": {"files": ["tests/fixtures/sample_repo/example.py"]},
    }),
    ("tool_call", "p2", "spawn_agent", {
        "role": "implementer",
        "task": "Refactor tests/fixtures/sample_repo/example.py to use @dataclass and add type hints",
        "context": {"target": "tests/fixtures/sample_repo/example.py"},
    }),
    ("tool_call", "p3", "spawn_agent", {
        "role": "reviewer",
        "task": "Run pytest on tests/fixtures/sample_repo and report pass/fail",
        "context": {"cwd": "tests/fixtures/sample_repo"},
    }),
    ("done", "tool_use"),
]

# Planner turn 1 (after sub-agents return): synthesize the final answer
PLANNER_TURN_1 = [
    "All three sub-agents reported success.\n",
    "Summary:\n",
    "- Explorer: located 1 Python file (example.py)\n",
    "- Implementer: refactored to @dataclass with type hints\n",
    "- Reviewer: 3/3 tests pass\n",
    "Done.\n",
    ("done", "end_turn"),
]

# Explorer: uses read_file / glob / grep
EXPLORER_TURN_0 = [
    "Surveying the repo...\n",
    ("tool_call", "e1", "glob_files", {"pattern": "**/*.py", "root": "tests/fixtures/sample_repo"}),
    ("done", "tool_use"),
]
EXPLORER_TURN_1 = [
    "Found 1 Python file: tests/fixtures/sample_repo/example.py (412 bytes).\n",
    ("tool_call", "e2", "read_file", {"path": "tests/fixtures/sample_repo/example.py"}),
    ("done", "tool_use"),
]
EXPLORER_TURN_2 = [
    "File uses an old-style class with __init__ and no type hints. Refactor target confirmed.\n",
    ("done", "end_turn"),
]

# Implementer: uses edit_file to apply the refactor
IMPLEMENTER_TURN_0 = [
    "Reading the target file...\n",
    ("tool_call", "i1", "read_file", {"path": "tests/fixtures/sample_repo/example.py"}),
    ("done", "tool_use"),
]
IMPLEMENTER_TURN_1 = [
    "Applying dataclass conversion...\n",
    ("tool_call", "i2", "edit_file", {
        "path": "tests/fixtures/sample_repo/example.py",
        "old": "class Point:\n    def __init__(self, x, y):\n        self.x = x\n        self.y = y\n",
        "new": "from dataclasses import dataclass\n\n@dataclass\nclass Point:\n    x: float\n    y: float\n",
        "replace_all": False,
    }),
    ("done", "tool_use"),
]
IMPLEMENTER_TURN_2 = [
    "Refactor applied successfully.\n",
    ("done", "end_turn"),
]

# Reviewer: runs pytest via shell
REVIEWER_TURN_0 = [
    "Running tests...\n",
    ("tool_call", "r1", "run_shell", {"cmd": "cd tests/fixtures/sample_repo && python -m pytest -q", "timeout": 30}),
    ("done", "tool_use"),
]
REVIEWER_TURN_1 = [
    "3 passed in 0.05s\n",
    ("done", "end_turn"),
]


SCRIPT = {
    "planner": [PLANNER_TURN_0, PLANNER_TURN_1],
    "explorer": [EXPLORER_TURN_0, EXPLORER_TURN_1, EXPLORER_TURN_2],
    "implementer": [IMPLEMENTER_TURN_0, IMPLEMENTER_TURN_1, IMPLEMENTER_TURN_2],
    "reviewer": [REVIEWER_TURN_0, REVIEWER_TURN_1],
}
