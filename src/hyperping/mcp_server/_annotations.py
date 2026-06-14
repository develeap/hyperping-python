"""Reusable ToolAnnotations constants for MCP tool risk classification.

Four tiers:
- READ_ONLY: safe reads, no side effects
- MUTATING: creates or updates resources, reversible
- DESTRUCTIVE: deletes or irreversibly changes state
- ACTION: state-transition operations (pause/resume/acknowledge), idempotent
"""

from mcp.types import ToolAnnotations

READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)

MUTATING = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)

DESTRUCTIVE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=False,
    openWorldHint=True,
)

ACTION = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=True,
    openWorldHint=True,
)
