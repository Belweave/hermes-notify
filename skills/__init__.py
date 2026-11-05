"""Explicit native-plugin registration; Hermes does not auto-load native skills/."""
from pathlib import Path


def register(ctx):
    return ctx.register_skill(
        "notify-release-workspace",
        Path(__file__).parent / "notify-release-workspace" / "SKILL.md",
        description="Keep a release task connected to a Notify App, measured progress, native approvals and attributed replies.",
    )
