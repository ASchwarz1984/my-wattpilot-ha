"""Vehicle buttons exercised through a real Home Assistant entity platform."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import Platform
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.fixture
def charger():
    return SimpleNamespace(
        connected=True, allPropsInitialized=True, serial="TEST12345",
        manufacturer="Fronius", name="Garage", hostname="wattpilot.local",
        firmware="42.5", devicetype="Wattpilot 11",
        allProps={
            "typ": "wattpilot", "var": 11, "onv": "42.5", "trx": None,
            "cards": [
                SimpleNamespace(name="Audi", energy=0),
                SimpleNamespace(name="Fiat", energy=0),
            ],
        },
        send_update=MagicMock(),
        register_property_callback=MagicMock(),
        unregister_property_callback=MagicMock(),
        disconnect=MagicMock(),
    )


async def test_vehicle_buttons_setup_press_reload_and_unload(hass, charger):
    entry = MockConfigEntry(
        domain="wattpilot",
        data={"connection": "local", "friendly_name": "Garage", "ip_address": "192.0.2.1", "password": "test"},
    )
    entry.add_to_hass(hass)
    with (
        patch("custom_components.wattpilot.async_ConnectCharger", AsyncMock(return_value=charger)),
        patch("custom_components.wattpilot.SUPPORTED_PLATFORMS", [Platform.BUTTON]),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED
        registry = er.async_get(hass)
        entity_ids = {
            vehicle: registry.async_get_entity_id("button", "wattpilot", f"Garage-authenticate_{vehicle}")
            for vehicle in ("audi", "fiat")
        }
        assert all(entity_ids.values())
        for vehicle, transaction in (("audi", 1), ("fiat", 2)):
            await hass.services.async_call(
                "button", "press", {"entity_id": entity_ids[vehicle]}, blocking=True
            )
            charger.send_update.assert_called_with("trx", transaction)
        assert charger.allProps["trx"] is None

        charger.send_update.side_effect = OSError("connection lost")
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                "button", "press", {"entity_id": entity_ids["audi"]}, blocking=True
            )
        charger.send_update.side_effect = None

        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED
        for vehicle, entity_id in entity_ids.items():
            assert registry.async_get_entity_id(
                "button", "wattpilot", f"Garage-authenticate_{vehicle}"
            ) == entity_id
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.NOT_LOADED
        assert entry.entry_id not in hass.data.get("wattpilot", {})
        assert charger.disconnect.call_count == 2
