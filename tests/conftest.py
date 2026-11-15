import json
from pathlib import Path

import pytest

from enviropermit.contracts import CaseSnapshot
from enviropermit.inference import load_release

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def case():
    def load(name="A", **updates):
        data = json.loads((ROOT / "cases/regression/water_spike" / f"{name}.json").read_text())
        data.update(updates)
        return CaseSnapshot.model_validate(data)
    return load


@pytest.fixture
def release():
    return load_release()

