from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "pilot_annotated_counts.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("pilot_annotated_counts", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PilotAnnotatedBackendTests(unittest.TestCase):
    def test_auto_backend_prefers_project_local_native_frog(self):
        script = load_script_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            frog = root / "local" / "frog" / "bin" / "frog"
            frog.parent.mkdir(parents=True)
            frog.write_text("#!/bin/sh\n", encoding="utf-8")

            self.assertEqual(script.select_backend("auto", root), "native")

    def test_default_native_prefix_prefers_llvm_openmp_frog(self):
        script = load_script_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            default_frog = root / "local" / "frog" / "bin" / "frog"
            llvm_frog = root / "local" / "frog-llvm-omp" / "bin" / "frog"
            default_frog.parent.mkdir(parents=True)
            llvm_frog.parent.mkdir(parents=True)
            default_frog.write_text("#!/bin/sh\n", encoding="utf-8")
            llvm_frog.write_text("#!/bin/sh\n", encoding="utf-8")

            self.assertEqual(script.resolve_native_prefix(root), root / "local" / "frog-llvm-omp")

    def test_native_invocation_uses_local_frog_and_runtime_env(self):
        script = load_script_module()
        root = Path("/project")
        invocation = script.build_frog_invocation(
            "native",
            Path("/project/run"),
            Path("/project/run/input.txt"),
            Path("/project/run/output.tsv"),
            root=root,
            base_env={"PATH": "/usr/bin", "DYLD_LIBRARY_PATH": "/existing/lib"},
        )

        self.assertEqual(invocation["backend"], "native")
        self.assertEqual(invocation["command"][0], "/project/local/frog/bin/frog")
        self.assertIn("--skip=mpcn", invocation["command"])
        self.assertIn("/project/run/input.txt", invocation["command"])
        self.assertIn("/project/run/output.tsv", invocation["command"])
        self.assertTrue(invocation["env"]["PATH"].startswith("/project/local/frog/bin:"))
        self.assertTrue(invocation["env"]["DYLD_LIBRARY_PATH"].startswith("/project/local/frog/lib:"))

    def test_native_invocation_accepts_prefix_and_threads(self):
        script = load_script_module()
        invocation = script.build_frog_invocation(
            "native",
            Path("/project/run"),
            Path("/project/run/input.txt"),
            Path("/project/run/output.tsv"),
            root=Path("/project"),
            native_prefix=Path("/project/local/frog-llvm-omp"),
            frog_threads=8,
            base_env={"PATH": "/usr/bin", "DYLD_LIBRARY_PATH": ""},
        )

        self.assertEqual(invocation["command"][0], "/project/local/frog-llvm-omp/bin/frog")
        self.assertIn("--threads=8", invocation["command"])
        self.assertTrue(invocation["env"]["PATH"].startswith("/project/local/frog-llvm-omp/bin:"))
        self.assertTrue(invocation["env"]["DYLD_LIBRARY_PATH"].startswith("/project/local/frog-llvm-omp/lib:"))

    def test_docker_invocation_preserves_lamachine_command(self):
        script = load_script_module()
        invocation = script.build_frog_invocation(
            "docker",
            Path("/project/run"),
            Path("/project/run/input.txt"),
            Path("/project/run/output.tsv"),
            root=Path("/project"),
        )

        self.assertEqual(invocation["backend"], "docker")
        self.assertEqual(invocation["command"][:5], ["docker", "run", "--rm", "--platform", "linux/amd64"])
        self.assertIn("proycon/lamachine:latest", invocation["command"])
        self.assertIsNone(invocation["env"])


if __name__ == "__main__":
    unittest.main()
