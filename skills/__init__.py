"""Explicit native-plugin registration; Hermes does not auto-load native skills/."""
from pathlib import Path


def register(ctx):
    return ctx.register_skill(
        "notify-release-workspace",
        Path(__file__).parent / "notify-release-workspace" / "SKILL.md",
        description="Manage releases, phone approvals, and replies with Notify.",
    )
