from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

TEMPLATES_DIR = PROJECT_ROOT / "templates"
OUTPUT_DIR = PROJECT_ROOT / "output" / "ready_contracts"
DATA_DIR = PROJECT_ROOT / "data"

COUNTER_FILE = DATA_DIR / "counter.json"

TEMPLATE_CONTRACT = TEMPLATES_DIR / "murabaha_template.docx"
TEMPLATE_SCHEDULE = TEMPLATES_DIR / "murabaha_schedule.docx"

ISTISNA_TEMPLATE = TEMPLATES_DIR / "istisna_template.docx"