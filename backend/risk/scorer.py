import re
from typing import Any
from dataclasses import dataclass, field

INJECTION_PATTERNS = [
    (r"ignore (previous|all|prior|above) instructions", 30),
    (r"you are now", 20),
    (r"disregard (your|all|any) (previous|prior|system|instructions)", 30),
    (r"act as (a|an|the|if you were)", 20),
    (r"do not follow", 25),
    (r"forget (your|all|previous) (instructions|rules|training)", 30),
    (r"jailbreak", 35),
    (r"bypass (security|safety|restrictions|filters)", 35),
    (r"sudo|root access|admin (mode|access|override)", 25),
    (r"override (safety|security|policy|restrictions)", 30),
    (r"you must (now|immediately|always)", 15),
    (r"new (system prompt|instructions|directives)", 25),
    (r"pretend (you are|to be|that you)", 20),
    (r"(reveal|show|print|output) (your|the) (system prompt|instructions|config)", 30),
]

DANGEROUS_ACTIONS = {
    "delete": 40,
    "drop": 50,
    "truncate": 45,
    "format": 40,
    "destroy": 50,
    "remove": 25,
    "rm": 35,
    "unlink": 30,
    "purge": 40,
    "wipe": 45,
    "exec": 30,
    "execute": 25,
    "eval": 35,
    "run": 15,
    "shell": 40,
    "cmd": 35,
    "bash": 40,
    "powershell": 40,
    "send_email": 20,
    "send_message": 15,
    "post": 10,
    "publish": 10,
}

SENSITIVE_DATA_PATTERNS = [
    (r"\b\d{16}\b", "credit_card", 35),
    (r"\b\d{3}-\d{2}-\d{4}\b", "ssn", 50),
    (r"password\s*[=:]\s*\S+", "password", 40),
    (r"api[_-]?key\s*[=:]\s*\S+", "api_key", 35),
    (r"secret\s*[=:]\s*\S+", "secret", 35),
    (r"token\s*[=:]\s*\S+", "token", 30),
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "email", 10),
]


@dataclass
class RiskResult:
    score: float = 0.0
    flags: list[str] = field(default_factory=list)

    @property
    def level(self) -> str:
        if self.score >= 81:
            return "critical"
        elif self.score >= 61:
            return "high"
        elif self.score >= 31:
            return "medium"
        return "low"


class RiskScorer:
    def score(self, prompt: str | None, tool: str, action: str, tool_input: Any) -> RiskResult:
        result = RiskResult()

        # Score dangerous action
        action_lower = action.lower()
        for danger_action, base_score in DANGEROUS_ACTIONS.items():
            if danger_action in action_lower:
                result.score += base_score
                result.flags.append(f"dangerous_action:{danger_action}")

        # Check prompt for injection
        if prompt:
            prompt_lower = prompt.lower()
            for pattern, score in INJECTION_PATTERNS:
                if re.search(pattern, prompt_lower, re.IGNORECASE):
                    result.score += score
                    result.flags.append(f"injection_pattern:{pattern[:30]}")

        # Check tool_input for sensitive data
        input_str = str(tool_input) if tool_input else ""
        for pattern, label, score in SENSITIVE_DATA_PATTERNS:
            if re.search(pattern, input_str, re.IGNORECASE):
                result.score += score
                result.flags.append(f"sensitive_data:{label}")

        # Cap at 100
        result.score = min(100.0, result.score)
        return result


risk_scorer = RiskScorer()
