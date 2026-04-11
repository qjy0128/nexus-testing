#!/usr/bin/env python3
"""Core validation logic for the Nexus skill structure validator."""

from _bootstrap import bootstrap_paths

bootstrap_paths()

import ast
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from nexus_testing.frontmatter_utils import parse_frontmatter

# Version
VERSION = "1.1.0"

SUPPORTED_SCRIPT_SUFFIXES = (".py", ".js", ".ts", ".mjs", ".cjs")

PYTHON_STDLIB_MODULES = set(getattr(sys, "stdlib_module_names", set()))
PYTHON_STDLIB_MODULES.update({"__future__", "typing_extensions"})

NODE_BUILTINS = {
    "assert", "assert/strict", "buffer", "child_process", "cluster", "console",
    "constants", "crypto", "dgram", "diagnostics_channel", "dns", "dns/promises",
    "domain", "events", "fs", "fs/promises", "http", "http2", "https", "inspector",
    "module", "net", "node:assert", "node:assert/strict", "node:buffer",
    "node:child_process", "node:cluster", "node:console", "node:constants",
    "node:crypto", "node:dgram", "node:diagnostics_channel", "node:dns",
    "node:dns/promises", "node:domain", "node:events", "node:fs",
    "node:fs/promises", "node:http", "node:http2", "node:https",
    "node:inspector", "node:module", "node:net", "node:os", "node:path",
    "node:path/posix", "node:path/win32", "node:perf_hooks", "node:process",
    "node:punycode", "node:querystring", "node:readline",
    "node:readline/promises", "node:repl", "node:stream", "node:stream/consumers",
    "node:stream/promises", "node:stream/web", "node:string_decoder",
    "node:sys", "node:timers", "node:timers/promises", "node:tls",
    "node:trace_events", "node:tty", "node:url", "node:util", "node:v8",
    "node:vm", "node:wasi", "node:worker_threads", "node:zlib", "os", "path",
    "path/posix", "path/win32", "perf_hooks", "process", "punycode",
    "querystring", "readline", "readline/promises", "repl", "stream",
    "stream/consumers", "stream/promises", "stream/web", "string_decoder",
    "sys", "timers", "timers/promises", "tls", "trace_events", "tty",
    "url", "util", "v8", "vm", "wasi", "worker_threads", "zlib",
}

REQUIRED_SECTIONS = {
    "Description": ("Description", "描述"),
    "Usage": ("Usage", "用法", "使用", "快速开始"),
    "Examples": ("Examples", "示例", "例子"),
}

# Tier requirements
TIER_REQUIREMENTS = {
    "BASIC": {
        "min_skill_md_lines": 100,
        "min_scripts": 1,
        "min_script_loc": 50,
        "max_script_loc": 300,
        "required_dirs": ["scripts"],
        "optional_dirs": ["assets", "references", "expected_outputs", "tests"],
        "features_required": ["cli_parser", "entrypoint"],
        "features_optional": ["machine_output", "error_handling", "help_text"]
    },
    "STANDARD": {
        "min_skill_md_lines": 200,
        "min_scripts": 1,
        "min_script_loc": 150,
        "max_script_loc": 500,
        "required_dirs": ["scripts", "assets", "references"],
        "optional_dirs": ["expected_outputs", "tests", "docs"],
        "features_required": ["cli_parser", "entrypoint", "machine_output", "error_handling"],
        "features_optional": ["help_text", "logging"]
    },
    "POWERFUL": {
        "min_skill_md_lines": 300,
        "min_scripts": 2,
        "min_script_loc": 300,
        "max_script_loc": 800,
        "required_dirs": ["scripts", "assets", "references", "expected_outputs"],
        "optional_dirs": ["tests", "docs", "examples", "config"],
        "features_required": ["cli_parser", "entrypoint", "machine_output", "error_handling", "help_text"],
        "features_optional": ["logging", "config_file", "multiple_output_formats"]
    }
}

# Frontmatter required fields
FRONTMATTER_REQUIRED = ["name", "description"]


class ValidationReport:
    def __init__(self, skill_path: str):
        self.skill_path = Path(skill_path).resolve()
        self.timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self.checks: Dict[str, Dict] = {}
        self.warnings: List[str] = []
        self.errors: List[str] = []
        self.suggestions: List[str] = []
        self.overall_score = 0.0
        self.compliance_level = "FAIL"
        self.detected_tier: Optional[str] = None
        self.external_imports: Dict[str, List[str]] = {}

    def add_check(self, check_name: str, passed: bool, message: str = "", score: float = 0.0):
        self.checks[check_name] = {
            "passed": passed,
            "message": message,
            "score": score
        }

    def add_warning(self, message: str):
        self.warnings.append(message)

    def add_error(self, message: str):
        self.errors.append(message)

    def add_suggestion(self, message: str):
        self.suggestions.append(message)

    def calculate_overall_score(self):
        if not self.checks:
            self.overall_score = 0.0
            return

        total_score = sum(check["score"] for check in self.checks.values())
        max_score = len(self.checks) * 1.0
        self.overall_score = (total_score / max_score) * 100 if max_score > 0 else 0.0

        if self.overall_score >= 90:
            self.compliance_level = "EXCELLENT"
        elif self.overall_score >= 75:
            self.compliance_level = "GOOD"
        elif self.overall_score >= 60:
            self.compliance_level = "ACCEPTABLE"
        elif self.overall_score >= 40:
            self.compliance_level = "NEEDS_IMPROVEMENT"
        else:
            self.compliance_level = "POOR"

    def to_dict(self) -> Dict:
        return {
            "skill_path": str(self.skill_path),
            "timestamp": self.timestamp,
            "overall_score": round(self.overall_score, 1),
            "compliance_level": self.compliance_level,
            "detected_tier": self.detected_tier,
            "checks": self.checks,
            "warnings": self.warnings,
            "errors": self.errors,
            "suggestions": self.suggestions,
            "external_imports": self.external_imports
        }


class SkillStructureValidator:
    def __init__(self, skill_path: str, target_tier: Optional[str] = None, verbose: bool = False):
        self.skill_path = Path(skill_path).resolve()
        self.target_tier = target_tier
        self.verbose = verbose
        self.report = ValidationReport(str(self.skill_path))
        self.skill_md_line_count = 0
        self.script_facts: List[Dict[str, object]] = []
        scripts_dir = self.skill_path / "scripts"
        self.local_python_modules = {
            path.stem for path in scripts_dir.glob("*.py")
        } if scripts_dir.exists() else set()

    def log(self, message: str):
        if self.verbose:
            print(f"[VERBOSE] {message}", file=sys.stderr)

    def validate_all(self) -> ValidationReport:
        """Main validation entry point"""
        self.log(f"Starting validation of {self.skill_path}")

        if not self.skill_path.exists():
            self.report.add_error(f"Skill path does not exist: {self.skill_path}")
            return self.report

        if not self.skill_path.is_dir():
            self.report.add_error(f"Skill path is not a directory: {self.skill_path}")
            return self.report

        self._validate_skill_md()
        self._validate_readme()
        self._validate_directory_structure()
        self.script_facts = self._validate_scripts()
        self._validate_imports()
        self._detect_tier()
        self._validate_tier_compliance()

        self.report.calculate_overall_score()
        return self.report

    def _validate_skill_md(self):
        """Validate SKILL.md presence and content"""
        self.log("Validating SKILL.md...")

        skill_md_path = self.skill_path / "SKILL.md"
        if not skill_md_path.exists():
            self.report.add_check("skill_md_exists", False, "SKILL.md missing", 0.0)
            self.report.add_error("SKILL.md is required but missing")
            return

        self.report.add_check("skill_md_exists", True, "SKILL.md found", 1.0)

        try:
            content = skill_md_path.read_text(encoding='utf-8-sig')
            lines = [line for line in content.split('\n') if line.strip()]
            line_count = len(lines)
            self.skill_md_line_count = line_count

            if line_count >= 100:
                self.report.add_check("skill_md_length", True,
                                     f"SKILL.md has {line_count} lines (>=100)", 1.0)
            elif line_count >= 50:
                self.report.add_check("skill_md_length", True,
                                     f"SKILL.md has {line_count} lines (>=50)", 0.7)
                self.report.add_warning(f"SKILL.md is brief ({line_count} lines), consider expanding")
            else:
                self.report.add_check("skill_md_length", False,
                                     f"SKILL.md too short: {line_count} lines", 0.0)
                self.report.add_error(f"SKILL.md too short: {line_count} lines")

            self._validate_frontmatter(content)
            self._validate_required_sections(content)

        except Exception as e:
            self.report.add_check("skill_md_readable", False, f"Error reading SKILL.md: {e}", 0.0)
            self.report.add_error(f"Cannot read SKILL.md: {e}")

    def _validate_frontmatter(self, content: str):
        """Validate YAML frontmatter"""
        self.log("Validating frontmatter...")

        if not content.startswith('---'):
            self.report.add_check("frontmatter_exists", False, "No frontmatter found", 0.0)
            self.report.add_error("SKILL.md must start with YAML frontmatter (---)")
            return

        try:
            end_marker = content.find('---', 3)
            if end_marker == -1:
                self.report.add_check("frontmatter_format", False, "No closing ---", 0.0)
                self.report.add_error("Frontmatter closing marker not found")
                return

            frontmatter_text = content[3:end_marker].strip()
            frontmatter = self._parse_frontmatter(frontmatter_text)

            if not isinstance(frontmatter, dict):
                self.report.add_check("frontmatter_format", False, "Invalid frontmatter", 0.0)
                return

            missing = [f for f in FRONTMATTER_REQUIRED if f not in frontmatter]
            if not missing:
                self.report.add_check("frontmatter_complete", True,
                                     "Required frontmatter fields present", 1.0)
            else:
                self.report.add_check("frontmatter_complete", False,
                                     f"Missing: {', '.join(missing)}", 0.0)
                self.report.add_error(f"Missing frontmatter fields: {', '.join(missing)}")

        except Exception as e:
            self.report.add_check("frontmatter_format", False, f"YAML error: {e}", 0.0)
            self.report.add_error(f"Invalid YAML frontmatter: {e}")

    def _parse_frontmatter(self, text: str) -> Optional[Dict]:
        """Parse YAML frontmatter using the shared repository helper."""
        wrapped = f"---\n{text.strip()}\n---\n"
        return parse_frontmatter(wrapped)

    def _validate_required_sections(self, content: str):
        """Validate required markdown sections"""
        self.log("Checking required sections...")

        missing = []
        for section, aliases in REQUIRED_SECTIONS.items():
            matched = any(
                re.search(rf'^#+\s*{re.escape(alias)}\b', content, re.MULTILINE | re.IGNORECASE)
                for alias in aliases
            )
            if not matched:
                missing.append(section)

        if not missing:
            self.report.add_check("required_sections", True,
                                 "All required sections present", 1.0)
        else:
            self.report.add_check("required_sections", False,
                                 f"Missing: {', '.join(missing)}", 0.0)
            self.report.add_suggestion(f"Add missing sections: {', '.join(missing)}")

    def _validate_readme(self):
        """Validate README.md if present"""
        self.log("Validating README.md...")

        readme_path = self.skill_path / "README.md"
        if not readme_path.exists():
            self.report.add_check("readme_exists", False, "README.md missing (optional)", 0.5)
            self.report.add_suggestion("Add README.md with usage instructions")
            return

        self.report.add_check("readme_exists", True, "README.md found", 0.5)

        try:
            content = readme_path.read_text(encoding='utf-8')
            if len(content.strip()) >= 200:
                self.report.add_check("readme_substantial", True,
                                     "README.md has substantial content", 0.5)
            else:
                self.report.add_check("readme_substantial", False,
                                     "README.md content is brief", 0.25)
                self.report.add_suggestion("Expand README.md with more details")
        except Exception as e:
            self.report.add_check("readme_readable", False, f"Cannot read README.md: {e}", 0.0)

    def _validate_directory_structure(self):
        """Validate directory structure"""
        self.log("Validating directory structure...")

        required_dirs = ["scripts"]
        for dir_name in required_dirs:
            dir_path = self.skill_path / dir_name
            if dir_path.exists() and dir_path.is_dir():
                self.report.add_check(f"dir_{dir_name}", True,
                                     f"{dir_name}/ found", 1.0)
            else:
                self.report.add_check(f"dir_{dir_name}", False,
                                     f"{dir_name}/ missing", 0.0)
                self.report.add_error(f"Missing required directory: {dir_name}/")

        # Check optional directories
        optional_dirs = ["assets", "references", "expected_outputs", "tests", "docs"]
        found_optional = []
        for dir_name in optional_dirs:
            dir_path = self.skill_path / dir_name
            if dir_path.exists() and dir_path.is_dir():
                found_optional.append(dir_name)

        if found_optional:
            self.report.add_suggestion(f"Optional directories found: {', '.join(found_optional)}")

    def _validate_scripts(self):
        """Validate supported scripts under scripts/."""
        self.log("Validating supported scripts...")

        scripts_dir = self.skill_path / "scripts"
        if not scripts_dir.exists():
            self.report.add_check("scripts_dir_exists", False, "scripts/ directory missing", 0.0)
            return []

        script_files = sorted(
            path for path in scripts_dir.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_SCRIPT_SUFFIXES
        )
        if not script_files:
            self.report.add_check(
                "supported_scripts_exist",
                False,
                "No supported scripts found (.py/.js/.ts/.mjs/.cjs)",
                0.0,
            )
            self.report.add_error("No supported scripts in scripts/ directory")
            return []

        self.report.add_check(
            "supported_scripts_exist",
            True,
            f"Found {len(script_files)} supported script(s)",
            1.0,
        )

        script_facts: List[Dict[str, object]] = []
        for script_path in script_files:
            script_name = script_path.name
            self.log(f"Validating script: {script_name}")
            try:
                content = script_path.read_text(encoding='utf-8-sig')
            except Exception as e:
                self.report.add_check(f"script_readable_{script_name}", False, f"Cannot read {script_name}: {e}", 0.0)
                self.report.add_error(f"Cannot read {script_name}: {e}")
                continue

            language = self._detect_language(script_path)
            loc = len([
                line for line in content.split('\n')
                if line.strip() and not line.strip().startswith(('#', '//'))
            ])

            syntax_checked, syntax_valid, syntax_message = self._check_script_syntax(script_path, content, language)
            syntax_score = 1.0 if syntax_valid else 0.0
            if not syntax_checked:
                syntax_score = 0.5
                self.report.add_warning(f"{script_name}: {syntax_message}")
            elif not syntax_valid:
                self.report.add_error(f"Syntax error in {script_name}: {syntax_message}")

            self.report.add_check(f"script_loc_{script_name}", True, f"{script_name}: {loc} LOC ({language})", 1.0)
            self.report.add_check(
                f"script_syntax_{script_name}",
                syntax_valid if syntax_checked else True,
                f"{script_name}: {syntax_message}",
                syntax_score,
            )

            has_cli_parser = self._detect_cli_parser(content, language)
            has_entrypoint = self._detect_entrypoint(content, language)
            has_machine_output = self._contains_any(content, ("json.dumps", "JSON.stringify", "--json", "application/json", "to_json"))
            has_error_handling = self._detect_error_handling(content, language)
            has_help_text = self._contains_any(content, ("--help", "-h", "help=", "help:", ".help(", "showHelp"))
            has_logging = self._contains_any(content, ("logging.", "logger.", "print(", "console.", "debug("))
            has_config_file = self._contains_any(content, ("config", ".env", "load_dotenv", "dotenv", "yaml", "toml", "json.load"))
            has_multiple_output_formats = sum(1 for marker in ("--format", "output_type", "markdown", "table", "json", "text") if marker in content) >= 3

            self._record_feature_check(
                f"script_cli_parser_{script_name}",
                has_cli_parser,
                script_name,
                "uses a CLI parser",
                "should expose argument parsing",
            )
            self._record_feature_check(
                f"script_entrypoint_{script_name}",
                has_entrypoint,
                script_name,
                "has an entrypoint",
                "should declare an executable entrypoint",
            )
            self._record_feature_check(
                f"script_machine_output_{script_name}",
                has_machine_output,
                script_name,
                "supports machine-readable output",
                "should expose JSON or another machine-readable output mode",
                required=False,
            )
            self._record_feature_check(
                f"script_error_handling_{script_name}",
                has_error_handling,
                script_name,
                "contains error handling",
                "should handle runtime errors explicitly",
                required=False,
            )
            self._record_feature_check(
                f"script_help_text_{script_name}",
                has_help_text,
                script_name,
                "contains CLI help text",
                "should expose --help or equivalent help text",
                required=False,
            )

            script_facts.append({
                "path": script_path,
                "name": script_name,
                "language": language,
                "loc": loc,
                "has_cli_parser": has_cli_parser,
                "has_entrypoint": has_entrypoint,
                "has_machine_output": has_machine_output,
                "has_error_handling": has_error_handling,
                "has_help_text": has_help_text,
                "has_logging": has_logging,
                "has_config_file": has_config_file,
                "has_multiple_output_formats": has_multiple_output_formats,
            })

        return script_facts

    def _record_feature_check(
        self,
        check_name: str,
        present: bool,
        script_name: str,
        success_message: str,
        warning_message: str,
        required: bool = True,
    ):
        if present:
            self.report.add_check(check_name, True, f"{script_name}: {success_message}", 1.0)
            return

        self.report.add_check(check_name, False, f"{script_name}: missing {success_message}", 0.0 if required else 0.5)
        self.report.add_warning(f"{script_name} {warning_message}")

    def _contains_any(self, content: str, markers) -> bool:
        return any(marker in content for marker in markers)

    def _detect_language(self, script_path: Path) -> str:
        suffix = script_path.suffix.lower()
        if suffix == ".py":
            return "python"
        if suffix in {".js", ".mjs", ".cjs"}:
            return "javascript"
        return "typescript"

    def _check_script_syntax(self, script_path: Path, content: str, language: str):
        if language == "python":
            try:
                ast.parse(content)
                return True, True, "valid Python syntax"
            except SyntaxError as exc:
                return True, False, f"syntax error at line {exc.lineno}"

        if language == "javascript":
            return self._check_node_syntax(script_path)

        return self._check_typescript_syntax(script_path)

    def _check_node_syntax(self, script_path: Path):
        node = self._which("node")
        if not node:
            return False, True, "JavaScript syntax check skipped (node unavailable)"

        result = subprocess.run(
            [node, "--check", str(script_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode == 0:
            return True, True, "valid JavaScript syntax"
        return True, False, (result.stderr or result.stdout or "syntax check failed").strip()

    def _check_typescript_syntax(self, script_path: Path):
        tsc = self._which("tsc")
        if not tsc:
            return False, True, "TypeScript syntax check skipped (tsc unavailable)"

        result = subprocess.run(
            [tsc, "--noEmit", "--pretty", "false", str(script_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode == 0:
            return True, True, "valid TypeScript syntax"
        return True, False, (result.stderr or result.stdout or "syntax check failed").strip()

    def _which(self, name: str) -> Optional[str]:
        from shutil import which

        return which(name)

    def _detect_cli_parser(self, content: str, language: str) -> bool:
        if language == "python":
            markers = ("argparse", "sys.argv", "click", "typer")
        else:
            markers = ("process.argv", "Deno.args", "commander", "yargs", "cac", "meow")
        return self._contains_any(content, markers)

    def _detect_entrypoint(self, content: str, language: str) -> bool:
        if language == "python":
            return "__name__" in content and "__main__" in content
        return self._contains_any(content, ("#!/usr/bin/env node", "require.main === module", "import.meta.url", "process.argv[1]"))

    def _detect_error_handling(self, content: str, language: str) -> bool:
        if language == "python":
            markers = ("try:", "except ", "raise ")
        else:
            markers = ("try {", ".catch(", "throw new ", "throw ")
        return self._contains_any(content, markers)

    def _validate_imports(self):
        """Validate imports for supported script languages."""
        self.log("Validating imports...")

        if not self.script_facts:
            return

        all_external = {}

        for script in self.script_facts:
            script_path = script["path"]
            try:
                content = script_path.read_text(encoding='utf-8-sig')
                if script["language"] == "python":
                    external = self._find_external_python_imports(content)
                else:
                    external = self._find_external_node_imports(content)
                if external:
                    all_external[script_path.name] = external
            except Exception:
                pass

        if not all_external:
            self.report.add_check("stdlib_only", True,
                                  "All scripts use built-in modules only", 1.0)
        else:
            self.report.add_check("stdlib_only", False,
                                  f"External imports found: {all_external}", 0.0)
            self.report.add_error(f"Scripts use external imports: {all_external}")
            self.report.external_imports = all_external

    def _find_external_python_imports(self, content: str) -> List[str]:
        """Find external (non-stdlib) Python imports."""
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return []

        external = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod = alias.name.split('.')[0]
                    if (
                        mod not in PYTHON_STDLIB_MODULES
                        and mod not in self.local_python_modules
                        and not mod.startswith('_')
                    ):
                        external.append(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                mod = node.module.split('.')[0]
                if (
                    mod not in PYTHON_STDLIB_MODULES
                    and mod not in self.local_python_modules
                    and not mod.startswith('_')
                ):
                    external.append(node.module)
        return list(set(external))

    def _find_external_node_imports(self, content: str) -> List[str]:
        """Find external npm-style imports."""
        modules = set()
        pattern = r"""(?:import\s+.+?\s+from\s+|import\s*\(|require\s*\()\s*['"]([^'"]+)['"]"""
        for match in re.finditer(pattern, content, re.MULTILINE):
            modules.add(match.group(1))

        external = set()
        for module in modules:
            if module.startswith((".", "/", "@/")):
                continue
            if module in NODE_BUILTINS:
                continue
            external.add(module)
        return sorted(external)

    def _detect_tier(self):
        """Auto-detect tier based on structure"""
        self.log("Detecting tier...")

        if not self.skill_md_line_count:
            self.report.detected_tier = "UNKNOWN"
            return

        for tier_name in ("POWERFUL", "STANDARD", "BASIC"):
            if self._meets_tier(tier_name):
                self.report.detected_tier = tier_name
                break
        else:
            self.report.detected_tier = "BASIC"

        self.report.add_check("tier_detection", True, f"Detected tier: {self.report.detected_tier}", 1.0)

    def _validate_tier_compliance(self):
        """Validate against target tier requirements"""
        if not self.target_tier:
            return

        self.log(f"Validating {self.target_tier} tier compliance...")

        if self.target_tier not in TIER_REQUIREMENTS:
            self.report.add_error(f"Unknown tier: {self.target_tier}")
            return

        reqs = TIER_REQUIREMENTS[self.target_tier]
        passed = True

        if self.skill_md_line_count >= reqs["min_skill_md_lines"]:
            self.report.add_check("tier_skill_md_lines", True, f"SKILL.md {self.skill_md_line_count} lines (>={reqs['min_skill_md_lines']})", 1.0)
        else:
            self.report.add_check("tier_skill_md_lines", False, f"SKILL.md {self.skill_md_line_count} lines (<{reqs['min_skill_md_lines']})", 0.0)
            passed = False

        if len(self.script_facts) >= reqs["min_scripts"]:
            self.report.add_check("tier_script_count", True, f"{len(self.script_facts)} scripts (>={reqs['min_scripts']})", 1.0)
        else:
            self.report.add_check("tier_script_count", False, f"{len(self.script_facts)} scripts (<{reqs['min_scripts']})", 0.0)
            passed = False

        # Check directory structure
        missing_dirs = []
        for dir_name in reqs["required_dirs"]:
            if not (self.skill_path / dir_name).exists():
                missing_dirs.append(dir_name)

        if not missing_dirs:
            self.report.add_check("tier_dirs", True,
                                 "All required directories present", 1.0)
        else:
            self.report.add_check("tier_dirs", False,
                                 f"Missing directories: {', '.join(missing_dirs)}", 0.0)
            passed = False

        top_scripts = sorted(self.script_facts, key=lambda item: item["loc"], reverse=True)[: reqs["min_scripts"]]
        if len(top_scripts) == reqs["min_scripts"] and all(reqs["min_script_loc"] <= item["loc"] <= reqs["max_script_loc"] for item in top_scripts):
            self.report.add_check("tier_script_loc", True, f"Top {reqs['min_scripts']} script(s) meet LOC range {reqs['min_script_loc']}-{reqs['max_script_loc']}", 1.0)
        else:
            details = ", ".join(f"{item['name']}:{item['loc']}" for item in top_scripts) or "none"
            self.report.add_check("tier_script_loc", False, f"Scripts outside LOC range {reqs['min_script_loc']}-{reqs['max_script_loc']}: {details}", 0.0)
            passed = False

        for feature_name in reqs["features_required"]:
            if self._has_required_feature(feature_name):
                self.report.add_check(f"tier_feature_{feature_name}", True, f"Required feature present: {feature_name}", 1.0)
            else:
                self.report.add_check(f"tier_feature_{feature_name}", False, f"Missing required feature: {feature_name}", 0.0)
                passed = False

        if passed:
            self.report.add_check("tier_compliance", True, f"Meets {self.target_tier} requirements", 1.0)
        else:
            self.report.add_check("tier_compliance", False, f"Does not meet {self.target_tier} requirements", 0.0)

    def _meets_tier(self, tier_name: str) -> bool:
        reqs = TIER_REQUIREMENTS[tier_name]
        if self.skill_md_line_count < reqs["min_skill_md_lines"]:
            return False
        if len(self.script_facts) < reqs["min_scripts"]:
            return False
        if any(not (self.skill_path / dir_name).is_dir() for dir_name in reqs["required_dirs"]):
            return False

        top_scripts = sorted(self.script_facts, key=lambda item: item["loc"], reverse=True)[: reqs["min_scripts"]]
        return len(top_scripts) == reqs["min_scripts"] and all(
            reqs["min_script_loc"] <= item["loc"] <= reqs["max_script_loc"]
            for item in top_scripts
        )

    def _has_required_feature(self, feature_name: str) -> bool:
        feature_map = {
            "cli_parser": "has_cli_parser",
            "entrypoint": "has_entrypoint",
            "machine_output": "has_machine_output",
            "error_handling": "has_error_handling",
            "help_text": "has_help_text",
            "logging": "has_logging",
            "config_file": "has_config_file",
            "multiple_output_formats": "has_multiple_output_formats",
        }
        attribute = feature_map[feature_name]
        return any(bool(item.get(attribute)) for item in self.script_facts)
