"""
CaseReady Surgery Briefing Agent

Gives a surgeon the complete readiness picture for their case
before they walk into the OR.

Usage:
    python agent/case_agent.py --case CR-2026-0841
    python agent/case_agent.py --case CR-2026-0842
"""

import json
import os
import argparse
from datetime import datetime, timezone

import anthropic

from agent.prompts import SYSTEM_PROMPT
from agent.tools import TOOL_DEFINITIONS, TOOL_FUNCTIONS
from agent.models import SurgeryBrief, DimensionStatus, ReadinessLevel


def _run_tool(tool_name: str, tool_input: dict) -> str:
    fn = TOOL_FUNCTIONS.get(tool_name)
    if not fn:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    result = fn(**tool_input)
    return json.dumps(result, indent=2)


def _parse_brief(raw: str, case_id: str) -> SurgeryBrief:
    """Parse Claude's JSON output into a SurgeryBrief. Falls back gracefully."""
    try:
        text = raw.strip()
        # Strip markdown code fences
        if "```" in text:
            import re
            match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
            if match:
                text = match.group(1).strip()
        # Find the outermost JSON object if there's surrounding prose
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            text = text[start:end]
        data = json.loads(text)
        return SurgeryBrief(**data)
    except Exception:
        return SurgeryBrief(
            case_id=case_id,
            patient_name="Unknown",
            procedure="Unknown",
            surgeon="Unknown",
            or_time="Unknown",
            or_room="Unknown",
            overall_status=ReadinessLevel.AT_RISK,
            vendor=DimensionStatus(status=ReadinessLevel.AT_RISK, summary="Could not parse agent output"),
            spd=DimensionStatus(status=ReadinessLevel.AT_RISK, summary="Could not parse agent output"),
            inventory=DimensionStatus(status=ReadinessLevel.AT_RISK, summary="Could not parse agent output"),
            preference_card=DimensionStatus(status=ReadinessLevel.AT_RISK, summary="Could not parse agent output"),
            patient_prep=DimensionStatus(status=ReadinessLevel.AT_RISK, summary="Could not parse agent output"),
            critical_actions=["Review raw agent output"],
            surgeon_notes=raw[:500],
            generated_at=datetime.now(timezone.utc).isoformat(),
        )


def brief_surgeon(case_id: str, api_key: str = None) -> SurgeryBrief:
    """
    Run the CaseReady agent for a given case ID.
    Returns a structured SurgeryBrief with full readiness status.
    """
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY must be set")

    client = anthropic.Anthropic(api_key=api_key)
    messages = [
        {
            "role": "user",
            "content": (
                f"Generate a complete surgery brief for case {case_id}. "
                f"Check all five readiness dimensions — vendor, SPD/sterilization, "
                f"implant inventory, preference card, and patient prep — then produce "
                f"a structured JSON SurgeryBrief.\n\n"
                f"Required JSON schema:\n"
                f'{{"case_id": str, "patient_name": str, "procedure": str, "surgeon": str, '
                f'"or_time": str, "or_room": str, "overall_status": "READY|AT_RISK|BLOCKED", '
                f'"vendor": {{"status": str, "summary": str, "flags": [], "action_required": str|null}}, '
                f'"spd": {{...same...}}, "inventory": {{...same...}}, '
                f'"preference_card": {{...same...}}, "patient_prep": {{...same...}}, '
                f'"critical_actions": [str], "surgeon_notes": str, "generated_at": str}}'
            )
        }
    ]

    # Agentic loop — runs until Claude stops calling tools
    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )

        # Collect any tool calls from this turn
        tool_calls = [b for b in response.content if b.type == "tool_use"]

        if not tool_calls:
            # No more tool calls — extract the text response
            text_blocks = [b for b in response.content if b.type == "text"]
            raw = text_blocks[0].text if text_blocks else "{}"
            return _parse_brief(raw, case_id)

        # Add assistant's response to history
        messages.append({"role": "assistant", "content": response.content})

        # Execute all tool calls and add results
        tool_results = []
        for tc in tool_calls:
            result = _run_tool(tc.name, tc.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tc.id,
                "content": result,
            })

        messages.append({"role": "user", "content": tool_results})


def print_brief(brief: SurgeryBrief) -> None:
    """Print a formatted surgery brief to the terminal."""
    STATUS_COLOR = {
        ReadinessLevel.READY: "\033[92m",      # green
        ReadinessLevel.AT_RISK: "\033[93m",    # yellow
        ReadinessLevel.BLOCKED: "\033[91m",    # red
    }
    RESET = "\033[0m"
    BOLD = "\033[1m"

    def badge(level: ReadinessLevel) -> str:
        return f"{STATUS_COLOR[level]}{level.value}{RESET}"

    SEP = "=" * 64
    DIV = "-" * 64
    print(f"\n{SEP}")
    print(f"{BOLD}  CASEREADY SURGERY BRIEF{RESET}")
    print(SEP)
    print(f"  Case:      {brief.case_id}")
    print(f"  Patient:   {brief.patient_name}")
    print(f"  Procedure: {brief.procedure}")
    print(f"  Surgeon:   {brief.surgeon}")
    print(f"  OR Time:   {brief.or_time}  |  Room: {brief.or_room}")
    print(f"  Status:    {badge(brief.overall_status)}")
    print(DIV)

    dimensions = [
        ("Vendor / Rep",       brief.vendor),
        ("SPD / Sterilization", brief.spd),
        ("Implant Inventory",  brief.inventory),
        ("Preference Card",    brief.preference_card),
        ("Patient Prep",       brief.patient_prep),
    ]

    for name, dim in dimensions:
        print(f"\n  {BOLD}{name}{RESET}  [{badge(dim.status)}]")
        print(f"    {dim.summary}")
        for flag in dim.flags:
            print(f"    {STATUS_COLOR[ReadinessLevel.BLOCKED]}⚠ {flag}{RESET}")
        if dim.action_required:
            print(f"    → {dim.action_required}")

    if brief.critical_actions:
        print(f"\n{DIV}")
        print(f"  {BOLD}CRITICAL ACTIONS{RESET}")
        for i, action in enumerate(brief.critical_actions, 1):
            print(f"  {i}. {action}")

    if brief.surgeon_notes:
        print(f"\n  {BOLD}SURGEON NOTES{RESET}")
        print(f"  {brief.surgeon_notes}")

    print(f"\n{DIV}")
    print(f"  Generated: {brief.generated_at}")
    print(f"{SEP}\n")


def main():
    parser = argparse.ArgumentParser(description="CaseReady Surgery Briefing Agent")
    parser.add_argument("--case", required=True, help="Case ID (e.g. CR-2026-0841)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON instead of formatted brief")
    args = parser.parse_args()

    print(f"Running CaseReady briefing for {args.case}...")
    brief = brief_surgeon(args.case)

    if args.json:
        print(brief.model_dump_json(indent=2))
    else:
        print_brief(brief)


if __name__ == "__main__":
    main()
