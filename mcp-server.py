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


def consume_approval_file(approval_file: str, consumed_dir: str, site_id: str) -> None:
    """Move the approval file to the consumed directory with a timestamp."""
    try:
        os.makedirs(consumed_dir, exist_ok=True)
    except Exception as e:
        return audit("Create Consumed Directory", {"Directory": "Not available", "note": ""}, False, f"Failed: Unable to create consumed directory. Exception: {str(e)}")
    timestamp = datetime.now(timezone.utc).astimezone(mountain_tz).strftime("%Y%m%dT%H%M%S")
    new_file_name = f"{site_id}-{timestamp}.consumed"
    new_file_path = os.path.join(consumed_dir, new_file_name)
    try:
        os.rename(approval_file, new_file_path)
    except Exception as e:
        return audit("Consume Approval", {"Approval file": "Available", "note": ""}, False, f"Failed: Unable to move approval file. Exception: {str(e)}")
    if approval_file and os.path.exists(approval_file):
        audit("Consume Approval", {"Approval file": "Available", "note": ""}, False, "Failed: Approval file was not consumed.")
    elif os.path.exists(new_file_path):
        audit("Consume Approval", {"Approval file": "Consumed", "note": ""}, True, "Success: Approval files consumed.")

    
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
CONSUMED_DIR = os.environ.get("CONSUMED_DIR", f"{APPROVAL_DIR}/consumed")


@mcp.tool()
def flag_site(site_id: str, note: str) -> str:
    """Flag a geothermal site for human review. This is a WRITE action."""
    is_valid_site = any(well["id"] == site_id for state, wells in WELLS.items() for well in wells)
    if not is_valid_site:
        audit("flag_site", {"site_id": site_id, "note": note}, False, "Invalid site ID.",)
        return f"Site ID {site_id!r} not found."


    approval_path = os.path.join(APPROVAL_DIR, f"{site_id}.approved") 
    # ctime, not birth time: accidental inode changes (restore/rsync/chmod) can make
    # an old approval look fresh. Accepted: only approvers can write this volume.
    approval_creation_time = os.path.getctime(approval_path) if os.path.exists(approval_path) else None
    current_time = datetime.now(timezone.utc).timestamp()

    if approval_path and os.path.exists(approval_path):
        if (current_time - approval_creation_time) > 3600: 
            audit("flag_site", {"site_id": site_id, "note": note}, False, "Blocked: Found stale approval. Removing approval file and requiring new approval.")
            consume_approval_file(approval_path, CONSUMED_DIR, site_id)
            return f"Blocked: {site_id!r} Found stale approval. requires human approval. No action taken."
        else:
            pass  # Approval file exists and is recent, proceed to flag the site
    else:
        audit("flag_site", {"site_id": site_id, "note": note}, False, "Blocked: awaiting out-of-band human approval.")
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
    

    consume_approval_file(approval_path, CONSUMED_DIR, site_id)
    
    return f"Site {site_id!r} flagged. (approved via {approval_path})"


if __name__ == "__main__":
    mcp.run()   # defaults to stdio transport