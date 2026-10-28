"""Read-only final membership evidence; never establishes a change or economic effect."""
from dataclasses import dataclass
from app.sources.direct_params import ObjectParams, ParamsUnavailable
from app.sync.parse import placement_id
from app.sync.sanitize import MASK

METHOD = "excluded_sites_membership@1"

@dataclass(frozen=True)
class Membership:
    status: str
    reason: str
    target_count: int = 0
    matched_count: int = 0
    masked_count: int = 0


def targets(action):
    ids = action.get("placement_ids") if isinstance(action, dict) and action.get("type") == "exclude_placements" else None
    if not isinstance(ids, (list, tuple)) or not ids or any(type(i) is not int or not 0 < i < 2**63 or i == placement_id(MASK) for i in ids):
        return None
    return frozenset(ids)


def verify_membership(action, after, campaign_id):
    ids = targets(action)
    if ids is None:
        return Membership("unavailable", "action_not_verifiable")
    if isinstance(after, ParamsUnavailable):
        return Membership("unavailable", after.reason, len(ids))
    if not isinstance(after, ObjectParams) or after.campaign_id != campaign_id:
        return Membership("unavailable", "object_mismatch", len(ids))
    matched = len(ids & {placement_id(site) for site in after.excluded_sites})
    if matched == len(ids):
        status, reason = "confirmed", "placements_excluded"
    elif after.excluded_sites_masked:
        status, reason = "unknown", "masked_exclusions"
    else:
        status, reason = "not_confirmed", "placements_missing"
    return Membership(status, reason, len(ids), matched, after.excluded_sites_masked)
