import pytest

from planner.modules.analytics.catalog import CATALOG, EventProps, ScreenViewed, analytics_event, spec_for


def test_preauth_events_are_client_events() -> None:
    preauth = {name for name, spec in CATALOG.items() if spec.preauth_allowed}
    assert preauth == {"screen_viewed", "register_clicked", "a2hs_prompted", "a2hs_accepted", "a2hs_instructions_shown"}
    assert all(CATALOG[n].source == "client" for n in preauth)


def test_spec_for_registered_model() -> None:
    spec = spec_for(ScreenViewed(screen="welcome"))
    assert spec.name == "screen_viewed"
    assert spec.version == 1


def test_duplicate_registration_rejected() -> None:
    with pytest.raises(ValueError, match="registered twice"):

        @analytics_event("screen_viewed", source="client")
        class Dup(EventProps):
            pass


def test_server_events_cannot_be_preauth() -> None:
    with pytest.raises(ValueError, match="only client events"):

        @analytics_event("bogus_server_event", preauth_allowed=True)
        class Bogus(EventProps):
            pass


def test_properties_are_strict() -> None:
    with pytest.raises(ValueError):
        ScreenViewed.model_validate({"screen": "welcome", "email": "x@y.z"})
