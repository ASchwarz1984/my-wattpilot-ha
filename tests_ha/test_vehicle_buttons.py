"""Vehicle buttons exercised through a real Home Assistant entity platform."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import EVENT_STATE_CHANGED, Platform
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def _wait_for_reported_state(hass, entity_id, expected, action):
    reported = asyncio.Event()

    async def state_changed(event):
        state = event.data.get("new_state")
        if event.data["entity_id"] == entity_id and state and state.state == expected:
            reported.set()

    unsubscribe = hass.bus.async_listen(EVENT_STATE_CHANGED, state_changed)
    try:
        await action()
        await asyncio.wait_for(reported.wait(), timeout=5)
    finally:
        unsubscribe()


@pytest.fixture
def charger():
    return SimpleNamespace(
        connected=True, allPropsInitialized=True, serial="TEST12345",
        manufacturer="Fronius", name="Garage", hostname="wattpilot.local",
        firmware="42.5", devicetype="Wattpilot 11",
        allProps={
            "typ": "wattpilot", "var": 11, "onv": "42.5", "trx": 0,
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


@pytest.mark.parametrize(
    ("language", "labels"),
    [
        ("en", {"audi": "Authorize Audi (chip 0)", "fiat": "Authorize Fiat (chip 1)"}),
        ("de", {"audi": "Audi freigeben (Chip 0)", "fiat": "Fiat freigeben (Chip 1)"}),
    ],
)
@pytest.mark.parametrize("custom_name", [None, "My vehicle authorization"])
async def test_vehicle_buttons_setup_press_reload_and_unload(hass, charger, language, labels, custom_name):
    from custom_components.wattpilot.sensor import ChargerSensor

    hass.config.language = language
    entry = MockConfigEntry(
        domain="wattpilot",
        data={"connection": "local", "friendly_name": "Garage", "ip_address": "192.0.2.1", "password": "test"},
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    existing_entity_ids = {
        vehicle: registry.async_get_or_create(
            "button", "wattpilot", f"Garage-authenticate_{vehicle}",
            suggested_object_id=f"garage{suffix}",
        ).entity_id
        for vehicle, suffix in (("audi", ""), ("fiat", "_2"))
    }
    if custom_name:
        registry.async_update_entity(existing_entity_ids["audi"], name=custom_name)

    def make_sensor(hass, entry, entity_cfg, charger):
        if entity_cfg["id"] != "trx":
            return SimpleNamespace(_init_failed=True)
        return ChargerSensor(hass, entry, {**entity_cfg, "enabled": True}, charger)

    def report_transaction(key, value):
        charger.allProps[key] = value
        charger.register_property_callback.call_args.args[0](key, value)

    charger.send_update.side_effect = report_transaction
    with (
        patch("custom_components.wattpilot.async_ConnectCharger", AsyncMock(return_value=charger)),
        patch("custom_components.wattpilot.SUPPORTED_PLATFORMS", [Platform.BUTTON, Platform.SENSOR]),
        patch("custom_components.wattpilot.sensor.ChargerSensor", side_effect=make_sensor),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED
        entity_ids = {
            vehicle: registry.async_get_entity_id("button", "wattpilot", f"Garage-authenticate_{vehicle}")
            for vehicle in ("audi", "fiat")
        }
        assert entity_ids == existing_entity_ids
        for vehicle, entity_id in entity_ids.items():
            registered = registry.async_get(entity_id)
            assert registered.original_name == labels[vehicle]
            if vehicle == "audi" and custom_name:
                assert registered.name == custom_name
                assert custom_name in hass.states.get(entity_id).attributes["friendly_name"]
            else:
                assert hass.states.get(entity_id).attributes["friendly_name"] == f"Garage {labels[vehicle]}"
        chip_sensor = registry.async_get_entity_id("sensor", "wattpilot", "Garage-trx")
        await _wait_for_reported_state(
            hass, chip_sensor, "No Chip",
            lambda: hass.async_add_executor_job(report_transaction, "trx", charger.allProps["trx"]),
        )
        assert hass.states.get(chip_sensor).state == "No Chip"
        for vehicle, transaction in (("audi", 1), ("fiat", 2)):
            await _wait_for_reported_state(
                hass, chip_sensor, f"ID Chip {transaction - 1}",
                lambda: hass.services.async_call(
                    "button", "press", {"entity_id": entity_ids[vehicle]}, blocking=True
                ),
            )
            await hass.async_block_till_done()
            charger.send_update.assert_called_with("trx", transaction)
            assert hass.states.get(chip_sensor).state == f"ID Chip {transaction - 1}"
        assert charger.allProps["trx"] == 2

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
            assert registry.async_get(entity_id).original_name == labels[vehicle]
        if custom_name:
            assert registry.async_get(entity_ids["audi"]).name == custom_name
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.NOT_LOADED
        assert entry.entry_id not in hass.data.get("wattpilot", {})
        assert charger.disconnect.call_count == 2


async def test_unconfirmed_chip_raises_instead_of_reporting_success(hass, charger):
    entry = MockConfigEntry(
        domain="wattpilot",
        data={"connection": "local", "friendly_name": "Garage", "ip_address": "192.0.2.1", "password": "test"},
    )
    entry.add_to_hass(hass)
    charger.allProps["car"] = 2
    with (
        patch("custom_components.wattpilot.async_ConnectCharger", AsyncMock(return_value=charger)),
        patch("custom_components.wattpilot.SUPPORTED_PLATFORMS", [Platform.BUTTON]),
        patch("custom_components.wattpilot.button.AUTHENTICATION_TIMEOUT", 0.01),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        entity_id = er.async_get(hass).async_get_entity_id(
            "button", "wattpilot", "Garage-authenticate_audi"
        )
        with pytest.raises(HomeAssistantError, match="ID chip 0"):
            await hass.services.async_call("button", "press", {"entity_id": entity_id}, blocking=True)
        charger.send_update.assert_called_once_with("trx", 1)
        assert charger.allProps["trx"] == 0
        assert charger.allProps["car"] == 2
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
