from unittest.mock import MagicMock

import pytest

from docketpilot import audit


@pytest.mark.parametrize("key", ["password", "email", "full_name", "raw_text", "token"])
def test_personal_data_keys_rejected(key):
    with pytest.raises(ValueError, match="personal data"):
        audit.record(MagicMock(), "x", details={key: "secret"})


def test_event_added_to_session():
    session = MagicMock()
    event = audit.record(session, "matter.view", target_type="matter", target_id="m1", details={"page": 2})
    session.add.assert_called_once_with(event)
    assert event.action == "matter.view"
    assert event.details == {"page": 2}
