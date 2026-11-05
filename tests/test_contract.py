import json
from pathlib import Path

from jsonschema import Draft202012Validator
from hermes_notify.client import NotifyClient, TEST_TOKEN
from scripts.mock_notify import MockNotify


def test_http_mock_matches_pinned_public_contract():
    contract = json.loads((Path(__file__).parent / "fixtures/notify-contract.json").read_text())
    body = {"title": "Hermes test", "prompt": "Approve the harmless test?", "kind": "approval",
            "presentation": "notification", "expiresInSeconds": 120}
    Draft202012Validator(contract["request"]).validate(body)
    mock = MockNotify()
    with mock.serve() as url:
        api = NotifyClient(TEST_TOKEN, url)
        created = api.create(body, "contract-test", 2)
        schema = {"$ref": "#/components/schemas/InteractionCreated", "components": contract["components"]}
        Draft202012Validator(schema).validate(created)
        assert mock.answered.wait(2)
        result = api.wait(created["interaction"]["id"], 1, 2)
        Draft202012Validator(contract["components"]["schemas"]["Interaction"]).validate(result["interaction"])
        assert result["interaction"]["status"] == "approved"
        assert result["interaction"]["response"] == "approve"
