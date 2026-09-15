"""generate_agents.py writes ADK agent stubs; the model they pin must outlive the Gemini 2.5
retirement (Vertex/Gemini API shutdown 2027-03-31 for 2.5 Flash). Static check — the script
writes files on import, so it is read, not run."""
import re
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "generate_agents.py"


def test_generated_agents_pin_a_gemini_3_model_once():
    src = SCRIPT.read_text(encoding="utf-8")
    assert "gemini-2.5" not in src, "stub template still names a retired Gemini 2.5 model"
    assert 'GEMINI_MODEL = "gemini-3.5-flash-lite"' in src, "name the model once at the top of the script"
    assert len(re.findall(r'model=\{GEMINI_MODEL!r\}', src)) == 2, "both stub templates must use GEMINI_MODEL"
