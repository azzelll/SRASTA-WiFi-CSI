"""Hash-bound, separate decisions about existing captures; never repair raw data."""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re
import uuid


def participant_identity(session, config=None):
    """Resolve confirmed person corrections without changing stored identity or split."""
    from .capture_archive import digest

    session = Path(session)
    config = config or json.loads((session / "capture_config.json").read_text())
    result = {"subject_id": config["subject_id"], "original_subject_id": config["subject_id"],
              "split": config["split"], "participant_group": None, "correction_files": []}
    groups = set()
    for path in sorted((session.parent.parent / "corrections").glob("*participants*.json")):
        correction = json.loads(path.read_text())
        if correction.get("schema_version") != "srasta.local.participant-correction.v1":
            continue
        for row in correction.get("sessions", []):
            if row.get("session_id") != session.name:
                continue
            group = row.get("participant_group", "")
            if (correction.get("split_override") is not False
                    or correction.get("raw_or_archive_modified") is not False
                    or row.get("original_recorded_subject_id") != config["subject_id"]
                    or row.get("original_split") != config["split"]
                    or row.get("checksums_manifest_sha256") != digest(session / "checksums.json")
                    or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,31}", group)):
                raise ValueError("participant correction does not match original archive/split")
            groups.add(group)
            result["correction_files"].append(path.name)
    if len(groups) > 1:
        raise ValueError("conflicting participant corrections")
    if groups:
        result["participant_group"] = next(iter(groups))
        result["subject_id"] = "LOC_" + result["participant_group"]
    elif config.get("guided_protocol") == "empty":
        # A room-only recording has a session group, never an invented person.
        result["subject_id"] = "EMPTY_" + session.name
    return result


def data_use_approval(session):
    """Return the latest applicable decision, independently of capture-time permission."""
    from .capture_archive import digest

    session = Path(session)
    decisions = []
    for path in sorted((session.parent.parent / "data_use_approvals").glob("*.json")):
        record = json.loads(path.read_text())
        entries = [r for r in record.get("sessions", []) if r.get("session_id") == session.name]
        if not entries:
            continue
        if (len(entries) != 1 or record.get("schema_version") != "srasta.capture.data-use.v1"
                or record.get("scope") != "local_model_development"
                or record.get("source") != "owner_team_attestation"
                or not record.get("approval_id") or not record.get("statement", "").strip()
                or record.get("decision") not in {"approved", "revoked"}):
            raise ValueError("invalid data-use approval record")
        stamp = datetime.fromisoformat(record["recorded_at_utc"].replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError("data-use approval requires an explicit timezone")
        decisions.append((stamp, path.name, record, entries[0]))
    if not decisions:
        return None
    _, _, record, entry = max(decisions, key=lambda row: (row[0], row[1]))
    for field, filename in (("capture_config_sha256", "capture_config.json"),
                            ("events_sha256", "events.jsonl"),
                            ("checksums_sha256", "checksums.json")):
        if entry.get(field) != digest(session / filename):
            raise ValueError("data-use approval does not match archive hashes")
    config = json.loads((session / "capture_config.json").read_text())
    if config["split"] not in {"train", "validation"}:
        raise ValueError("development approval cannot admit test or pilot data")
    created = config.get("created_at_utc")
    if created and datetime.fromisoformat(record["recorded_at_utc"].replace("Z", "+00:00")) < datetime.fromisoformat(created.replace("Z", "+00:00")):
        raise ValueError("data-use decision predates capture")
    if record["decision"] == "revoked":
        return None
    return {key: record[key] for key in ("approval_id", "recorded_at_utc", "scope", "source")}


def record_data_use_approval(root, session_ids, statement, source_reference):
    """Record an explicitly supplied team decision now, bound to existing archives."""
    from .capture_archive import digest, private_write, utc_now

    root = Path(root)
    if not statement.strip() or not source_reference.strip() or not session_ids:
        raise ValueError("actual team statement, source and sessions are required")
    sessions = []
    for session_id in sorted(set(session_ids)):
        if Path(session_id).name != session_id or not session_id.startswith("SES_"):
            raise ValueError("invalid session ID")
        path = root / "sessions" / session_id
        config = json.loads((path / "capture_config.json").read_text())
        if config["split"] not in {"train", "validation"}:
            raise ValueError("development approval cannot admit test or pilot data")
        sessions.append({"session_id": session_id,
                         "capture_config_sha256": digest(path / "capture_config.json"),
                         "events_sha256": digest(path / "events.jsonl"),
                         "checksums_sha256": digest(path / "checksums.json")})
    stamp = utc_now()
    reference = "DUA_" + stamp[:10].replace("-", "") + "_" + uuid.uuid4().hex[:8].upper()
    record = {"schema_version": "srasta.capture.data-use.v1", "approval_id": reference,
              "decision": "approved", "scope": "local_model_development",
              "recorded_at_utc": stamp, "source": "owner_team_attestation",
              "source_reference": source_reference, "statement": statement,
              "capture_time_authorization_claimed": False, "sessions": sessions}
    folder = root / "data_use_approvals"
    folder.mkdir(exist_ok=True, mode=0o700)
    target = folder / (reference + ".json")
    private_write(target, record)
    return target
