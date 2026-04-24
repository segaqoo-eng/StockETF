from pathlib import Path
import pytest

FIXTURES = Path(__file__).parent / "fixtures"

@pytest.fixture
def fixture_path():
    def _resolve(name: str) -> Path:
        return FIXTURES / name
    return _resolve
