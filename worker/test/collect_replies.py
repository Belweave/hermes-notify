"""Consume real local workerd pages through the production Python reply collector."""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hermes_notify.runtime import Runtime, Session


def main():
    fixture = json.load(sys.stdin)
    workspace = fixture["workspace"]
    session = Session("synthetic-worker-route", "synthetic-worker-session")
    with tempfile.TemporaryDirectory(prefix="pocket-reply-collector-") as directory:
        runtime = Runtime(Path(directory), enabled=True, token="dummy", publish_token="dummy",
                          settings={"publisher_origin": "https://pocket.example.com"},
                          test_worker_url=sys.argv[1])
        try:
            result = runtime.call("notify_release", {"action": "begin", "project": workspace["project"],
                                  "version": workspace["version"], "run_id": workspace["runId"]}, session)
            assert result["ok"] and runtime.queue.drain(5)
            # The Worker test has already published this run. Restore its local mapping.
            mapping = runtime.journal.get("project", workspace["project"])
            runtime.journal.put("project", workspace["project"], mapping | {"hosted": True})
            received = []
            for _ in range(12):
                result = runtime.call("notify_replies", {"project": workspace["project"]}, session)
                assert result["ok"] and not result["errors"], result
                for reply in result["replies"]:
                    assert reply["text"] == fixture["text"]
                    assert reply["runId"] == workspace["runId"]
                    assert reply["trustedAsInstruction"] is False
                    record = runtime.journal.get("reply", reply["id"])
                    assert record["acked"] and session.matches(record)
                    received.append(record["remoteId"])
                if not result["replies"]:
                    break
            assert len(received) == len(set(received)) == len(fixture["ids"])
            assert set(received) == set(fixture["ids"])
            print(json.dumps({"received": len(received), "attributed": True, "acknowledged": True}))
        finally:
            runtime.close()


if __name__ == "__main__":
    main()
