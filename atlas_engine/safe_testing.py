import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


class SafeTester:
    @staticmethod
    def run_isolated_pytest(test_body: str, working_directory: str | None = None) -> Dict[str, Any]:
        temp_dir = Path(tempfile.mkdtemp(prefix="atlas-safe-test-", dir=working_directory))
        test_file = temp_dir / "test_proposal.py"
        test_file.write_text(test_body, encoding="utf-8")
        result = subprocess.run(
            ["python", "-m", "pytest", str(test_file), "-q"],
            capture_output=True,
            text=True,
            cwd=str(temp_dir),
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "workspace": str(temp_dir),
            "passed": result.returncode == 0,
        }

    @staticmethod
    def validate_proposal(proposal: Dict[str, Any]) -> Dict[str, Any]:
        test_body = f'''
import pytest

def test_proposal_is_safe_and_reviewable():
    assert {proposal.get("status") == "approved"!r}
    assert {proposal.get("proposed_change")!r} is not None
    assert {proposal.get("test_plan")!r} != ""
'''
        return SafeTester.run_isolated_pytest(test_body)
