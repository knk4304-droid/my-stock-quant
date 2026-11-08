"""v4.1 offline smoke and regression tests; no market API calls."""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent

class TestSourceIntegrity(unittest.TestCase):
    def test_python_syntax(self):
        for path in ROOT.glob("*.py"):
            with self.subTest(file=path.name):
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    def test_required_modules_present(self):
        for name in ("app.py", "quant.py", "universe.py", "batch_update.py", "backtest.py"):
            self.assertTrue((ROOT / name).is_file(), name)

    def test_no_obsolete_module_imports(self):
        text = (ROOT / "test_modules.py").read_text(encoding="utf-8")
        for name in ("quant_engine", "signal_generator", "macro_analyzer", "ui_components"):
            self.assertNotIn("import " + name, text)

    def test_app_return_periods(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("c.iloc[-6]", source)
        self.assertIn("c.iloc[-21]", source)
        self.assertIn("c.iloc[-61]", source)

if __name__ == "__main__":
    unittest.main()
