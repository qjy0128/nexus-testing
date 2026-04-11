#!/usr/bin/env python3
"""Automated security scanner for Nexus Testing Framework.

Implements S1–S4 detection rules from docs/references/reference-security-scan.md.
S5 (supply chain) and S6 (permissions) require runtime context and are
left as future enhancements; the scanner reports them as SKIPPED.

Usage:
    python scripts/security-scanner.py <skill-dir> [--format json|text] [--strict]
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class Finding(NamedTuple):
    rule_id: str
    category: str          # S1 / S2 / S3 / S4
    severity: str          # CRITICAL / HIGH / MEDIUM / LOW / INFO
    confidence: str        # high / medium / low
    description: str
    file_path: str
    line_number: int | None
    matched_text: str


# ---------------------------------------------------------------------------
# Severity / confidence scoring
# ---------------------------------------------------------------------------

SEVERITY_BASE_POINTS = {
    "CRITICAL": 50,
    "HIGH": 25,
    "MEDIUM": 12,
    "LOW": 5,
    "INFO": 0,
}

CONFIDENCE_MULTIPLIERS = {
    "high": 1.0,
    "medium": 0.7,
    "low": 0.4,
}


# ---------------------------------------------------------------------------
# Chain detection
# ---------------------------------------------------------------------------

CHAIN_DEFINITIONS = {
    "CHAIN_SECRET_EXFIL": {
        "required": {"SECRET_READ", "NETWORK_POST"},
        "bonus": 25,
        "intent": "Credential / data exfiltration",
    },
    "CHAIN_DECODE_EXEC": {
        "required": {"DECODE_EXEC", "REMOTE_CODE_EXEC"},
        "bonus": 30,
        "intent": "Obfuscated payload execution",
    },
    "CHAIN_ENV_STAGE_EXFIL": {
        "required": {"ENV_ACCESS", "FILE_STAGE", "NETWORK_POST"},
        "bonus": 20,
        "intent": "Environment info staging & exfiltration",
    },
    "CHAIN_DESTRUCTIVE_EXFIL": {
        "required": {"DESTRUCTIVE_OP", "NETWORK_POST"},
        "bonus": 25,
        "intent": "Destructive operation + data exfiltration",
    },
    "CHAIN_PRIV_ESC_RCE": {
        "required": {"PRIV_ESCALATION", "REMOTE_CODE_EXEC"},
        "bonus": 35,
        "intent": "Privilege escalation → RCE",
    },
    "CHAIN_DOWNLOAD_EXEC": {
        "required": {"FILE_STAGE", "REMOTE_CODE_EXEC"},
        "bonus": 20,
        "intent": "Download and execute",
    },
}

FINDING_TYPE_MAP: dict[str, set[str]] = {
    "CR-001": {"SECRET_READ"},
    "CR-002": {"SECRET_READ"},
    "CR-003": {"SECRET_READ"},
    "CR-005": {"SECRET_READ"},
    "CR-007": {"SECRET_READ"},
    "CR-008": {"SECRET_READ"},
    "PI-001": {"REMOTE_CODE_EXEC"},
    "PI-002": {"REMOTE_CODE_EXEC"},
    "PI-005": {"REMOTE_CODE_EXEC"},
    "OBF-040": {"DECODE_EXEC", "REMOTE_CODE_EXEC"},
    "OBF-041": {"REMOTE_CODE_EXEC"},
    "OBF-043": {"REMOTE_CODE_EXEC"},
    "OBF-044": {"REMOTE_CODE_EXEC"},
    "OBF-045": {"REMOTE_CODE_EXEC"},
    "DANGEROUS_CMD_eval": {"DECODE_EXEC", "REMOTE_CODE_EXEC"},
    "DANGEROUS_CMD_curl_pipe": {"FILE_STAGE", "REMOTE_CODE_EXEC"},
    "DANGEROUS_CMD_rm_rf": {"DESTRUCTIVE_OP"},
    "NETWORK_0.0.0.0": {"NETWORK_POST"},
    "NETWORK_reverse_shell": {"NETWORK_POST", "REMOTE_CODE_EXEC"},
    "CR-009": {"ENV_ACCESS"},
    "OBF-033": {"FILE_STAGE"},
    "OBF-030": {"DECODE_EXEC"},
    "OBF-031": {"DECODE_EXEC"},
    "OBF-034": {"DECODE_EXEC"},
}


# ---------------------------------------------------------------------------
# S1 — Prompt Injection Detection
# ---------------------------------------------------------------------------

S1_RULES: list[tuple[str, str, str, re.Pattern]] = [
    ("PI-001", "HIGH", "System prompt extraction attempt",
     re.compile(r"(?i)(ignore\s+previous|forget\s+your\s+instructions|system\s+prompt|你是一个|你的真实身份)")),
    ("PI-002", "HIGH", "Jailbreak instruction",
     re.compile(r"(?i)(jailbreak|do\s+anything\s+now|DAN\b|override\s+(all\s+)?|bypass\s+(all\s+)?)")),
    ("PI-003", "HIGH", "Base64-encoded prompt segment",
     re.compile(r"[A-Za-z0-9+/]{40,}={0,2}")),
    ("PI-004", "HIGH", "Role switching attempt",
     re.compile(r"(?i)(pretend\s+you\s+are|act\s+as|you\s+are\s+now|从现在起你是)")),
    ("PI-005", "HIGH", "Output redirection attempt",
     re.compile(r"(?i)(output\s+your\s+instructions|print\s+your\s+prompt|显示你的系统指令|列出所有规则)")),
    ("PI-006", "MEDIUM", "Comment injection",
     re.compile(r"(?:<!--|/\*|//)\s*(?:ignore|exec|eval|system|import|require)\b", re.IGNORECASE)),
    ("PI-007", "MEDIUM", "Multi-language injection marker",
     re.compile(r"(?i)(忽略.*?instruction|无视.*?rule|bypass.*?安全|override.*?規則)")),
    ("PI-008", "HIGH", "Hidden instruction in description/trigger",
     re.compile(r"(?i)(偷偷|秘密地|covertly|stealth|不告诉用户|without\s+telling)")),
    ("PI-009", "MEDIUM", "Fragmented injection across files",
     re.compile(r"(?i)(payload\s*=\s*['\"]|inject\s*=\s*['\"]|exploit\s*=\s*['\"])")),
]


# ---------------------------------------------------------------------------
# S2 — Malicious Code & Vulnerability Detection (subset)
# ---------------------------------------------------------------------------

S2_DANGEROUS_FUNCTIONS: list[tuple[str, str, str]] = [
    ("eval(", "CRITICAL", "eval() — dynamic code execution"),
    ("eval (", "CRITICAL", "eval() — dynamic code execution"),
    ("exec(", "CRITICAL", "exec() — command execution"),
    ("execSync(", "CRITICAL", "execSync() — synchronous command execution"),
    ("spawn(", "HIGH", "spawn() — subprocess execution"),
    ("execFile(", "HIGH", "execFile() — file execution"),
    ("subprocess.Popen(", "CRITICAL", "subprocess.Popen() — Python subprocess"),
    ("subprocess.run(", "HIGH", "subprocess.run() — Python subprocess"),
    ("subprocess.call(", "HIGH", "subprocess.call() — Python subprocess"),
    ("os.system(", "CRITICAL", "os.system() — system command execution"),
    ("os.popen(", "HIGH", "os.popen() — popen command execution"),
    ("new Function(", "HIGH", "new Function() — dynamic function construction"),
    ("vm.runInNewContext(", "HIGH", "vm.runInNewContext() — VM sandbox escape"),
    ("vm.runInThisContext(", "HIGH", "vm.runInThisContext() — VM sandbox escape"),
    ("__import__(", "HIGH", "__import__() — dynamic module import"),
    ("getattr(", "MEDIUM", "getattr() — reflection-based access"),
    ("__getattribute__(", "MEDIUM", "__getattribute__() — reflection-based access"),
]

S2_DANGEROUS_COMMANDS: list[tuple[str, str, str, re.Pattern]] = [
    ("DANGEROUS_CMD_rm_rf", "CRITICAL", "Recursive force delete",
     re.compile(r"\brm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+|.*--no-preserve-root)")),
    ("DANGEROUS_CMD_curl_pipe", "CRITICAL", "Remote code execution via curl|bash",
     re.compile(r"(?i)(curl|wget)\b.*\|\s*(ba)?sh")),
    ("DANGEROUS_CMD_eval", "CRITICAL", "eval with variable expansion",
     re.compile(r"\beval\s+[\"'`]")),
    ("DANGEROUS_CMD_exec", "HIGH", "exec with variable expansion",
     re.compile(r"\bexec\s+[\"'`]")),
    ("DANGEROUS_CMD_chmod_777", "HIGH", "Overly permissive chmod",
     re.compile(r"\bchmod\s+(777|a\+rwx)")),
    ("DANGEROUS_CMD_etc_write", "CRITICAL", "Write to system directory",
     re.compile(r"[>]{1,2}\s*/etc/")),
    ("DANGEROUS_CMD_mkfs", "CRITICAL", "Disk operation",
     re.compile(r"\bmkfs\b|\bdd\s+if=")),
    ("DANGEROUS_CMD_fork_bomb", "CRITICAL", "Fork bomb",
     re.compile(r":\(\)\{\s*:\|:&\s*\};:")),
    ("DANGEROUS_CMD_docker_priv", "HIGH", "Docker privileged execution",
     re.compile(r"docker\s+run\s+.*--privileged")),
    ("DANGEROUS_CMD_kubectl", "HIGH", "kubectl apply/exec",
     re.compile(r"kubectl\s+(apply|exec)")),
    ("DANGEROUS_CMD_chroot", "HIGH", "chroot escape",
     re.compile(r"\bchroot\b")),
]

S2_OBFUSCATION_RULES: list[tuple[str, str, str, re.Pattern]] = [
    ("OBF-001", "HIGH", "Base64 obfuscation (long encoded string)",
     re.compile(r"[A-Za-z0-9+/]{80,}={0,2}")),
    ("OBF-005", "HIGH", "Zero-width Unicode characters (U+200B–U+200F)",
     re.compile(r"[\u200b\u200c\u200d\u200e\u200f]")),
    ("OBF-010", "HIGH", "XOR encryption pattern",
     re.compile(r"(?i)(xor|\.xor\(|\bxor_key\b)")),
    ("OBF-011", "HIGH", "AES/DES encryption module usage",
     re.compile(r"(?i)(from\s+(Crypto|cryptography)\.cipher|import\s+(aes|des|cipher)|\.encrypt\(|\.decrypt\()")),
    ("OBF-020", "HIGH", "High entropy string (potential secret/hash)",
     re.compile(r"[0-9a-fA-F]{32,}")),
    ("OBF-030", "MEDIUM", "String concatenation obfuscation",
     re.compile(r"(['\"][a-z]{1,4}['\"]\s*[+]\s*){3,}")),
    ("OBF-031", "HIGH", "CharCode / fromCharCode obfuscation",
     re.compile(r"(?i)(String\.fromCharCode|chr\(\d+)")),
    ("OBF-033", "HIGH", "Hidden code in comments",
     re.compile(r"(?m)(?:#|//|/\*)\s*(?:eval|exec|import\s+os|subprocess|require\(|__import__)")),
    ("OBF-034", "MEDIUM", "String reversal obfuscation",
     re.compile(r"(?i)(\.reverse\(\)|\.split\(['\"]['\"]\)\.reverse\(\)\.join)")),
    ("OBF-040", "CRITICAL", "eval(atob()) / exec(base64_decode())",
     re.compile(r"(?i)(eval\s*\(\s*atob|exec\s*\(\s*base64_decode)")),
    ("OBF-041", "HIGH", "new Function() constructor",
     re.compile(r"(?i)new\s+Function\s*\(")),
    ("OBF-042", "HIGH", "setTimeout/setInterval with code string",
     re.compile(r"(?i)(setTimeout|setInterval)\s*\(\s*['\"]")),
    ("OBF-043", "HIGH", "Dynamic import/require with concatenation",
     re.compile(r"(?i)(import\s*\(|require\s*\()\s*.*[+]")),
    ("OBF-044", "HIGH", "Reflection-based execution",
     re.compile(r"(?i)(getattr\s*\(|__getattribute__\s*\(|\.apply\s*\()")),
    ("OBF-045", "HIGH", "VM sandbox usage",
     re.compile(r"(?i)vm\.runIn(New|This)Context\s*\(")),
    ("OBF-050", "MEDIUM", "debugger statement",
     re.compile(r"\bdebugger\s*;")),
    ("OBF-052", "LOW", "Timing-based anti-debug",
     re.compile(r"(?i)(Date\.now\(\)\s*-\s*Date\.now\(\)|performance\.now\(\)\s*-\s*performance\.now\(\))")),
]

S2_EXECUTABLE_EXTENSIONS = {
    ".exe", ".dll", ".bat", ".cmd", ".ps1", ".psm1", ".psd1",
    ".vbs", ".scr", ".msi", ".reg", ".cpl",
}

S2_SHEBANG_PATTERN = re.compile(r"^#!\s*/", re.MULTILINE)

S2_BINARY_SIGNATURES = {
    b"\x7fELF": "ELF binary",
    b"\xfe\xfa\xed": "Mach-O ARM binary",
    b"\xfe\xee": "Mach-O x86 binary",
    b"MZ": "PE/Windows executable",
}


# ---------------------------------------------------------------------------
# S3 — Credential Leakage Detection
# ---------------------------------------------------------------------------

S3_RULES: list[tuple[str, str, str, re.Pattern]] = [
    ("CR-001", "HIGH", "Hardcoded API key",
     re.compile(r"(?i)(api_key|apikey|api-key)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]")),
    ("CR-002", "HIGH", "Hardcoded token / bearer",
     re.compile(r"(?i)(token|bearer|access_token)\s*[:=]\s*['\"][A-Za-z0-9_\-\.]{20,}['\"]")),
    ("CR-003", "HIGH", "Hardcoded password",
     re.compile(r"(?i)(password|passwd|pwd|secret)\s*[:=]\s*['\"][^'\"]{8,}['\"]")),
    ("CR-004", "HIGH", "OAuth credential",
     re.compile(r"(?i)(client_secret|consumer_secret|oauth_token)")),
    ("CR-005", "CRITICAL", "Private key content",
     re.compile(r"-----BEGIN\s+(RSA\s+|EC\s+|DSA\s+|OPENSSH\s+)?PRIVATE\s+KEY-----")),
    ("CR-006", "MEDIUM", "Base64 steganography in code files",
     re.compile(r"[A-Za-z0-9+/]{40,}={0,2}")),
    ("CR-007", "HIGH", "Cloud provider credential",
     re.compile(r"(?:AKIA[A-Z0-9]{16}|AIza[A-Za-z0-9_\-]{35}|sg_[A-Za-z0-9]{20,})")),
    ("CR-008", "HIGH", "Database connection string with credentials",
     re.compile(r"(?i)(mongodb|mysql|postgres|postgresql)://[^\s:]+:[^\s@]+@")),
    ("CR-009", "MEDIUM", "Environment variable direct output",
     re.compile(r"(?i)(process\.env|os\.environ)\b.*(?:print|console\.log|logger|logging)")),
]

S3_FALSE_POSITIVE_PATTERNS = [
    re.compile(r"(?i)(your-api-key|<API_KEY>|\$API_KEY|\$\{API_KEY\}|placeholder|example|sk_test_)"),
]


# ---------------------------------------------------------------------------
# S4 — Structure & Command Validation
# ---------------------------------------------------------------------------

S4_SKILL_MD_CHECKS = {
    "frontmatter_start": lambda text: text.strip().startswith("---"),
    "frontmatter_end": lambda text: "---" in text.strip().split("\n", 1)[1] if "\n" in text.strip() else False,
    "name_field": lambda text: bool(re.search(r"^name\s*:", text, re.MULTILINE)),
    "description_field": lambda text: bool(re.search(r"^description\s*:", text, re.MULTILINE)),
}


# ---------------------------------------------------------------------------
# Shannon entropy calculation
# ---------------------------------------------------------------------------

def shannon_entropy(data: str) -> float:
    if not data:
        return 0.0
    freq: dict[str, int] = defaultdict(int)
    for ch in data:
        freq[ch] += 1
    length = len(data)
    return -sum((count / length) * math.log2(count / length) for count in freq.values())


# ---------------------------------------------------------------------------
# Scanner engine
# ---------------------------------------------------------------------------

class SecurityScanner:
    def __init__(self, skill_dir: Path, strict: bool = False):
        self.skill_dir = skill_dir.resolve()
        self.strict = strict
        self.findings: list[Finding] = []
        self._scanned_files: list[Path] = []

    # -- file discovery --

    def _iter_target_files(self) -> list[Path]:
        extensions = {".md", ".py", ".js", ".ts", ".mjs", ".cjs", ".sh", ".json", ".yaml", ".yml", ".toml"}
        files: list[Path] = []
        for path in sorted(self.skill_dir.rglob("*")):
            if path.is_dir():
                continue
            if path.suffix in extensions:
                files.append(path)
            elif path.suffix in S2_EXECUTABLE_EXTENSIONS:
                files.append(path)
            else:
                # check for shebang in extensionless files
                try:
                    first_bytes = path.read_bytes()[:64]
                    if first_bytes.startswith(b"#!"):
                        files.append(path)
                except (OSError, PermissionError):
                    pass
        return files

    def _read_lines(self, path: Path) -> list[str]:
        try:
            return path.read_text(encoding="utf-8", errors="replace").splitlines()
        except (OSError, PermissionError):
            return []

    def _add(self, rule_id: str, category: str, severity: str,
             confidence: str, description: str, file_path: str,
             line_number: int | None, matched_text: str) -> None:
        self.findings.append(Finding(
            rule_id=rule_id, category=category, severity=severity,
            confidence=confidence, description=description,
            file_path=file_path, line_number=line_number,
            matched_text=matched_text,
        ))

    def _rel(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.skill_dir))
        except ValueError:
            return str(path)

    # -- S1 --

    def scan_s1_prompt_injection(self) -> None:
        for path in self._iter_target_files():
            if path.suffix not in {".md", ".txt"}:
                continue
            lines = self._read_lines(path)
            rel_path = self._rel(path)
            for i, line in enumerate(lines, 1):
                for rule_id, severity, desc, pattern in S1_RULES:
                    m = pattern.search(line)
                    if m:
                        matched = m.group(0)
                        if rule_id == "PI-003":
                            try:
                                decoded = base64.b64decode(matched)
                                entropy = shannon_entropy(decoded.decode("utf-8", errors="replace"))
                                if entropy < 4.0:
                                    continue
                            except Exception:
                                continue
                        self._add(rule_id, "S1", severity, "high",
                                  desc, rel_path, i, matched[:200])

    # -- S2 --

    def scan_s2_malicious_code(self) -> None:
        for path in self._iter_target_files():
            rel_path = self._rel(path)
            lines = self._read_lines(path)

            # Dangerous functions
            for i, line in enumerate(lines, 1):
                for func_name, severity, desc in S2_DANGEROUS_FUNCTIONS:
                    if func_name in line:
                        # skip if it's a comment about the function (not actual usage)
                        stripped = line.strip()
                        if stripped.startswith("#") or stripped.startswith("//"):
                            continue
                        self._add(f"S2-FUNC-{func_name.rstrip('(').strip()}",
                                  "S2", severity, "high", desc,
                                  rel_path, i, line.strip()[:200])

            # Dangerous commands
            full_text = "\n".join(lines)
            for rule_id, severity, desc, pattern in S2_DANGEROUS_COMMANDS:
                for m in pattern.finditer(full_text):
                    line_num = full_text[:m.start()].count("\n") + 1
                    self._add(rule_id, "S2", severity, "high", desc,
                              rel_path, line_num, m.group(0)[:200])

            # Obfuscation rules
            for i, line in enumerate(lines, 1):
                for rule_id, severity, desc, pattern in S2_OBFUSCATION_RULES:
                    m = pattern.search(line)
                    if m:
                        matched = m.group(0)
                        # For OBF-001, check entropy to reduce FP
                        if rule_id == "OBF-001":
                            try:
                                decoded = base64.b64decode(matched)
                                entropy = shannon_entropy(decoded.decode("utf-8", errors="replace"))
                                if entropy < 4.0:
                                    continue  # likely not suspicious
                            except Exception:
                                pass
                        # For OBF-020, require it's not just a number
                        if rule_id == "OBF-020" and matched.isdigit():
                            continue
                        self._add(rule_id, "S2", severity, "medium",
                                  desc, rel_path, i, matched[:200])

            # Executable binary detection
            if path.suffix in S2_EXECUTABLE_EXTENSIONS:
                self._add(f"S2-EXE-{path.suffix}", "S2", "HIGH", "high",
                          f"Windows executable file: {path.name}",
                          rel_path, None, path.name)

            # Binary content detection (ELF, Mach-O, PE)
            try:
                header = path.read_bytes()[:4]
                for sig, desc in S2_BINARY_SIGNATURES.items():
                    if header.startswith(sig):
                        self._add("S2-BINARY", "S2", "HIGH", "high",
                                  f"Binary file detected: {desc}",
                                  rel_path, None, desc)
                        break
            except (OSError, PermissionError):
                pass

            # Shebang detection
            if lines and S2_SHEBANG_PATTERN.search(lines[0]):
                if path.suffix not in (".sh", ".py", ".js", ".ts"):
                    self._add("S2-SHEBANG", "S2", "MEDIUM", "medium",
                              f"Shebang in non-script file: {lines[0].strip()}",
                              rel_path, 1, lines[0].strip()[:200])

    # -- S3 --

    def scan_s3_credential_leak(self) -> None:
        code_extensions = {".py", ".js", ".ts", ".mjs", ".cjs", ".sh", ".json", ".yaml", ".yml"}
        for path in self._iter_target_files():
            rel_path = self._rel(path)
            lines = self._read_lines(path)

            target_rules = S3_RULES
            # Only scan code files for CR-006 (Base64 in code)
            for i, line in enumerate(lines, 1):
                for rule_id, severity, desc, pattern in target_rules:
                    if rule_id == "CR-006" and path.suffix not in code_extensions:
                        continue
                    m = pattern.search(line)
                    if not m:
                        continue
                    matched = m.group(0)
                    # False positive check
                    is_fp = any(fp.search(matched) for fp in S3_FALSE_POSITIVE_PATTERNS)
                    if is_fp:
                        continue
                    self._add(rule_id, "S3", severity, "medium",
                              desc, rel_path, i, matched[:200])

    # -- S4 --

    def scan_s4_structure(self) -> None:
        skill_md = self.skill_dir / "SKILL.md"
        rel_path = self._rel(skill_md)

        if not skill_md.exists():
            self._add("S4-MISSING", "S4", "CRITICAL", "high",
                      "SKILL.md is missing", str(self.skill_dir.name) + "/SKILL.md",
                      None, "file not found")
            return

        text = skill_md.read_text(encoding="utf-8", errors="replace")

        for check_name, check_fn in S4_SKILL_MD_CHECKS.items():
            if not check_fn(text):
                severity = "HIGH" if check_name in ("name_field", "description_field") else "CRITICAL"
                self._add(f"S4-{check_name.upper()}", "S4", severity, "high",
                          f"SKILL.md check failed: {check_name}",
                          rel_path, None, f"check: {check_name}")

        # Check description length
        desc_match = re.search(r"^description\s*:\s*(.+)$", text, re.MULTILINE)
        if desc_match and len(desc_match.group(1).strip().strip("'\"")) < 10:
            self._add("S4-DESC_SHORT", "S4", "MEDIUM", "high",
                      "SKILL.md description is too short (< 10 chars)",
                      rel_path, None, desc_match.group(0)[:200])

        # Check referenced files exist
        link_pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
        for m in link_pattern.finditer(text):
            target = m.group(1).split("#")[0].strip()
            if not target or target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            resolved = (skill_md.parent / target).resolve()
            if not resolved.exists():
                self._add("S4-BROKEN_REF", "S4", "HIGH", "high",
                          f"SKILL.md references missing file: {target}",
                          rel_path, None, target)

    # -- scoring --

    def calculate_risk_score(self) -> tuple[float, list[tuple[str, int, str]]]:
        raw_score = 0.0
        chain_bonuses: list[tuple[str, int, str]] = []

        for finding in self.findings:
            base = SEVERITY_BASE_POINTS.get(finding.severity, 0)
            multiplier = CONFIDENCE_MULTIPLIERS.get(finding.confidence, 0.4)
            raw_score += base * multiplier

        # Chain detection
        present_types: set[str] = set()
        for finding in self.findings:
            types = FINDING_TYPE_MAP.get(finding.rule_id, set())
            present_types.update(types)

        for chain_id, chain_def in CHAIN_DEFINITIONS.items():
            if chain_def["required"].issubset(present_types):
                chain_bonuses.append((chain_id, chain_def["bonus"], chain_def["intent"]))
                raw_score += chain_def["bonus"]

        # Trust credits
        has_high_critical = any(f.severity in ("HIGH", "CRITICAL") for f in self.findings)
        trust = 0 if has_high_critical else min(len([f for f in self.findings if f.severity == "INFO"]) * 5, 20)

        final = max(0.0, min(100.0, raw_score - trust))
        return final, chain_bonuses

    def get_verdict(self, score: float, strict: bool = False) -> str:
        if strict:
            if score <= 19:
                return "SAFE"
            elif score <= 49:
                return "WARNING"
            elif score <= 69:
                return "UNSAFE"
            else:
                return "CRITICAL"
        else:
            if score <= 29:
                return "SAFE"
            elif score <= 59:
                return "WARNING"
            elif score <= 79:
                return "UNSAFE"
            else:
                return "CRITICAL"

    # -- main scan --

    def scan(self) -> None:
        self.scan_s1_prompt_injection()
        self.scan_s2_malicious_code()
        self.scan_s3_credential_leak()
        self.scan_s4_structure()

    # -- output --

    def to_json(self) -> str:
        score, chains = self.calculate_risk_score()
        verdict = self.get_verdict(score, self.strict)

        by_category: dict[str, list[dict]] = defaultdict(list)
        for f in self.findings:
            by_category[f.category].append({
                "rule_id": f.rule_id,
                "severity": f.severity,
                "confidence": f.confidence,
                "description": f.description,
                "file": f.file_path,
                "line": f.line_number,
                "matched": f.matched_text,
            })

        result = {
            "skill_dir": str(self.skill_dir),
            "total_findings": len(self.findings),
            "risk_score": round(score, 1),
            "verdict": verdict,
            "strict_mode": self.strict,
            "chain_detections": [
                {"chain_id": cid, "bonus": bonus, "intent": intent}
                for cid, bonus, intent in chains
            ],
            "findings_by_stage": dict(by_category),
            "skipped_stages": {
                "S5": "Supply chain verification requires runtime context",
                "S6": "Permission/audit requires runtime context",
            },
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    def to_text(self) -> str:
        score, chains = self.calculate_risk_score()
        verdict = self.get_verdict(score, self.strict)

        lines: list[str] = []
        lines.append("=" * 60)
        lines.append(f"SECURITY SCAN — {self.skill_dir.name}")
        lines.append(f"Path: {self.skill_dir}")
        lines.append("Scanner: nexus-security-scanner (S1-S4 automated)")
        lines.append("=" * 60)

        # Per-stage summary
        for stage in ("S1", "S2", "S3", "S4"):
            stage_findings = [f for f in self.findings if f.category == stage]
            high_count = sum(1 for f in stage_findings if f.severity in ("CRITICAL", "HIGH"))
            med_count = sum(1 for f in stage_findings if f.severity == "MEDIUM")
            if not stage_findings:
                status = "PASS"
            elif high_count:
                status = f"FAIL ({high_count} high+)"
            else:
                status = f"WARN ({med_count} medium)"

            stage_names = {"S1": "Prompt Injection", "S2": "Malicious Code",
                           "S3": "Credential Leak", "S4": "Structure & Cmd"}
            lines.append(f"[{stage}] {stage_names[stage]:.<25s} {status}")

        lines.append("")
        lines.append(f"[S5] {'Supply Chain':.<25s} SKIPPED (runtime)")
        lines.append(f"[S6] {'Permissions':.<25s} SKIPPED (runtime)")

        lines.append("")
        lines.append("=" * 60)
        lines.append(f"RISK SCORE: {score:.1f} ({verdict})")
        if chains:
            chain_total = sum(b for _, b, _ in chains)
            lines.append(f"Chain Bonuses: +{chain_total}")
            for cid, bonus, intent in chains:
                lines.append(f"  {cid}: +{bonus} — {intent}")
        lines.append("=" * 60)

        # Verdict
        verdict_emoji = {"SAFE": "✅", "WARNING": "⚠️", "UNSAFE": "🔴", "CRITICAL": "🚫"}
        lines.append(f"VERDICT: {verdict_emoji.get(verdict, '?')} {verdict}")

        high_count = sum(1 for f in self.findings if f.severity in ("CRITICAL", "HIGH"))
        med_count = sum(1 for f in self.findings if f.severity == "MEDIUM")
        lines.append(f"Reasons: {high_count} HIGH+, {med_count} MEDIUM, {len(self.findings)} total")
        lines.append("=" * 60)

        # Detailed findings
        if self.findings:
            lines.append("")
            lines.append("Detailed findings:")
            for f in self.findings:
                loc = f"{f.file_path}:{f.line_number}" if f.line_number else f.file_path
                lines.append(f"  [{f.category}] {f.rule_id}: {f.description}")
                lines.append(f"    Location: {loc}")
                lines.append(f"    Severity: {f.severity} | Confidence: {f.confidence}")
                if f.matched_text:
                    lines.append(f"    Matched: {f.matched_text[:120]}")
                lines.append("")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Nexus Security Scanner — automated S1-S4 checks"
    )
    parser.add_argument("skill_dir", type=Path, help="Path to the Skill directory to scan")
    parser.add_argument("--format", choices=("json", "text"), default="text",
                        help="Output format (default: text)")
    parser.add_argument("--strict", action="store_true",
                        help="Use stricter scoring thresholds")
    args = parser.parse_args(argv)

    skill_dir: Path = args.skill_dir
    if not skill_dir.is_dir():
        print(f"ERROR: {skill_dir} is not a directory", file=sys.stderr)
        return 1

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    scanner = SecurityScanner(skill_dir, strict=args.strict)
    scanner.scan()

    if args.format == "json":
        print(scanner.to_json())
    else:
        print(scanner.to_text())

    # Exit code based on verdict
    score, _ = scanner.calculate_risk_score()
    verdict = scanner.get_verdict(score, args.strict)
    if verdict in ("UNSAFE", "CRITICAL"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

