import sys, json, datetime, os, io
from datetime import timezone, datetime
from zoneinfo import ZoneInfo

mountain_tz = ZoneInfo("America/Denver")

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("geo-sandbox")

# Pretend this is sensitive company data the agent may READ.
WELLS = {
    "NV": [{"id": "big-blind", "temp_c": 190}],
    "NM": [{"id": "lightning-dock", "temp_c": 165}],
}

def audit(action: str, args: dict, allowed: bool, reason: str = "", approved_by: dict = None ):
    # HOLE 1: emit ONE structured JSON line to stderr capturing who/what/when/allowed.
    # Why stderr and not stdout? Reason about it before you write this. (Answer below —
    # but predict first.)
    audit_trail = {
        "timestamp": datetime.now(timezone.utc).astimezone(mountain_tz).isoformat(),
        "action": action,
        "args": args,
        "allowed": allowed,
        "reason": reason,
        "approved_by": approved_by
    }
    print(json.dumps(audit_trail), file=sys.stderr, flush=True)


def get_file_stats(approval_file) -> dict:
    """Return the size and last modified time of a file, or None if it doesn't exist."""
    try:
        stats = os.stat(approval_file)
        last_modified = datetime.fromtimestamp(stats.st_mtime, tz=timezone.utc).astimezone(mountain_tz)
        access_time = datetime.fromtimestamp(stats.st_atime, tz=timezone.utc).astimezone(mountain_tz)
        file_size = stats.st_size
        return {
            "size": file_size,
            "last_modified": last_modified.isoformat(),
            "last_accessed": access_time.isoformat()
        }
    except FileNotFoundError as e:
        return f"ERROR: File not found: {approval_file}. Exception: {str(e)}"

    
@mcp.tool()
def read_wells(region: str) -> str:
    """Return known geothermal wells for a US state code (e.g. 'NV')."""
    allowed = region in WELLS
    audit("read_wells", {"region": region}, allowed)
    if not allowed:
        return f"No data for region {region!r}."
    return json.dumps(WELLS[region])

FLAGGED_SITES = {}
APPROVAL_DIR = os.environ.get("APPROVAL_DIR", "./approvals")

@mcp.tool()
def flag_site(site_id: str, note: str) -> str:
    """Flag a geothermal site for human review. This is a WRITE action."""
    is_valid_site = any(well["id"] == site_id for state, wells in WELLS.items() for well in wells)
    if not is_valid_site:
        audit("flag_site", {"site_id": site_id, "note": note}, False, "Invalid site ID.",)
        return f"Site ID {site_id!r} not found."


    approval_path = os.path.join(APPROVAL_DIR, f"{site_id}.approved")
    approved = os.path.exists(approval_path)

    if not approved:
        audit("flag_site", {"site_id": site_id, "note": note}, False,
              "Blocked: awaiting out-of-band human approval.")
        return f"Blocked: {site_id!r} requires human approval. No action taken."

    FLAGGED_SITES[site_id] = {
        "note": note,
        "flagged_at": datetime.now(timezone.utc).astimezone(mountain_tz).isoformat()
    }

    reason = "Approved out-of-band."
    audit(
        "flag_site", {"site_id": site_id, "note": note},
        True, 
        reason, 
        approved_by={
            "file_stats": get_file_stats(approval_path), 
            "consumed_date": datetime.now(timezone.utc).astimezone(mountain_tz).isoformat()
            }
        )

    return f"Site {site_id!r} flagged. (approved via {approval_path})"


if __name__ == "__main__":
    mcp.run()   # defaults to stdio transport