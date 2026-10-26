"""Vehicle authentication and button failure regression tests."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from homeassistant.exceptions import HomeAssistantError

from tests.conftest import MockCharger, _load_file_as_module

ROOT = Path(__file__).resolve().parent.parent
BUTTON = _load_file_as_module(
    "custom_components/wattpilot/button.py", "custom_components.wattpilot.button"
)
CONFIG = yaml.safe_load(
    (ROOT / "custom_components" / "wattpilot" / "button.yaml").read_text()
)["button"]


def _button(uid, charger=None):
    charger = charger or MockCharger(extra_props={"trx": None})
    if not hasattr(charger, "send_update"):
        charger.send_update = MagicMock()
    entry = MagicMock(entry_id="test_entry")
    entry.data = {"friendly_name": "Garage"}
    cfg = next(cfg for cfg in CONFIG if cfg.get("uid", cfg["id"]) == uid)
    return BUTTON.ChargerButton(MagicMock(), entry, {**cfg, "source": "none"}, charger)


@pytest.mark.parametrize(
    ("uid", "value", "chip"),
    [("authenticate_audi", 1, "ID Chip 0"), ("authenticate_fiat", 2, "ID Chip 1")],
)
async def test_authentication_uses_existing_chip_mapping(uid, value, chip):
    entity = _button(uid)
    assert entity._init_failed is False
    assert entity._attr_unique_id == f"Garage-{uid}"
    assert entity._attr_translation_key == uid
    assert not hasattr(entity, "_attr_name")
    assert entity.entity_registry_enabled_default is True

    def report_status(identifier, reported_value):
        entity._charger.allProps[identifier] = reported_value

    entity._charger.send_update.side_effect = report_status
    await entity.async_press()

    entity._charger.send_update.assert_called_once_with("trx", value)
    assert entity._charger.allProps["trx"] == value
    sensors = yaml.safe_load(
        (ROOT / "custom_components" / "wattpilot" / "sensor.yaml").read_text(encoding="utf-8")
    )["sensor"]
    current_chip = next(cfg for cfg in sensors if cfg["id"] == "trx")
    assert current_chip["enum"][value] == chip


async def test_generic_authentication_still_uses_no_chip():
    entity = _button("trx")
    await entity.async_press()
    entity._charger.send_update.assert_called_once_with("trx", 0)
    assert entity._attr_unique_id == "Garage-trx"
    assert entity.entity_registry_enabled_default is False


@pytest.mark.parametrize(
    ("vehicle", "transaction", "chip"), [("audi", 1, "ID Chip 0"), ("fiat", 2, "ID Chip 1")]
)
async def test_authentication_wire_message_and_reported_chip(vehicle, transaction, chip):
    from tests.conftest import ChargerSensor
    from tests.test_wattpilot_lib import _load_lib

    client = _load_lib().Wattpilot(ip="192.0.2.1", password="test")
    client._connected = True
    client._allPropsInitialized = True
    client._allProps.update(MockCharger(extra_props={"trx": None}).allProps)
    button = _button(f"authenticate_{vehicle}", client)
    loop = asyncio.get_running_loop()
    sent_event = asyncio.Event()
    client._wsapp.send.side_effect = lambda message: loop.call_soon_threadsafe(sent_event.set)
    press = asyncio.create_task(button.async_press())
    await asyncio.wait_for(sent_event.wait(), timeout=1)
    sent = json.loads(client._wsapp.send.call_args.args[0])
    assert sent == {"type": "setValue", "requestId": 1, "key": "trx", "value": transaction}
    assert client.allProps["trx"] is None

    client._Wattpilot__on_message(None, json.dumps({
        "type": "response", "success": True, "requestId": 1, "status": {"trx": transaction}
    }))
    await press
    sensor_cfg = next(
        cfg for cfg in yaml.safe_load(
            (ROOT / "custom_components" / "wattpilot" / "sensor.yaml").read_text(encoding="utf-8")
        )["sensor"] if cfg["id"] == "trx"
    )
    sensor = ChargerSensor(MagicMock(), button._entry, sensor_cfg, client)
    assert sensor._init_failed is False
    await sensor.async_local_poll()
    assert sensor._attr_native_value == chip


@pytest.mark.parametrize("uid", ["authenticate_audi", "authenticate_fiat"])
@pytest.mark.parametrize("ready_attribute", ["connected", "allPropsInitialized"])
async def test_unavailable_charger_never_receives_authentication(uid, ready_attribute):
    entity = _button(uid)
    setattr(entity._charger, ready_attribute, False)
    with pytest.raises(HomeAssistantError) as error:
        await entity.async_press()
    assert error.value.translation_key == "charger_unavailable"
    entity._charger.send_update.assert_not_called()


@pytest.mark.parametrize("props", [{"trx": None, "cards": []}, {"trx": None, "cards": None}])
async def test_missing_chip_is_reported(props):
    entity = _button("authenticate_fiat", MockCharger(extra_props=props))
    with pytest.raises(HomeAssistantError) as error:
        await entity.async_press()
    assert error.value.translation_key == "authentication_chip_unavailable"
    entity._charger.send_update.assert_not_called()


async def test_missing_transaction_support_is_reported():
    entity = _button("authenticate_audi", MockCharger())
    with pytest.raises(HomeAssistantError):
        await entity.async_press()
    entity._charger.send_update.assert_not_called()


async def test_send_failure_reaches_home_assistant():
    entity = _button("authenticate_audi")
    entity._charger.send_update.side_effect = OSError("connection lost")
    with pytest.raises(HomeAssistantError) as error:
        await entity.async_press()
    assert error.value.translation_key == "charger_command_failed"


async def test_unconfirmed_authentication_does_not_change_reported_identity():
    entity = _button("authenticate_audi", MockCharger(extra_props={"trx": 0, "car": 2}))
    with patch.object(BUTTON, "AUTHENTICATION_TIMEOUT", 0.01):
        with pytest.raises(HomeAssistantError) as error:
            await entity.async_press()
    assert error.value.translation_key == "authentication_not_confirmed"
    assert error.value.translation_placeholders == {"chip": "0"}
    entity._charger.send_update.assert_called_once_with("trx", 1)
    assert entity._charger.allProps["trx"] == 0
    assert entity._charger.allProps["car"] == 2


async def test_already_selected_chip_does_not_start_another_transaction():
    entity = _button("authenticate_audi", MockCharger(extra_props={"trx": 1, "car": 2}))
    await entity.async_press()
    entity._charger.send_update.assert_not_called()
    assert entity._charger.allProps["trx"] == 1


async def test_used_transaction_rejection_is_not_reported_as_success(caplog):
    from tests.test_wattpilot_lib import _load_lib

    client = _load_lib().Wattpilot(ip="192.0.2.1", password="test")
    client._connected = True
    client._allPropsInitialized = True
    client._allProps.update(MockCharger(extra_props={"trx": 0, "car": 2}).allProps)
    entity = _button("authenticate_audi", client)
    loop = asyncio.get_running_loop()
    sent_event = asyncio.Event()
    client._wsapp.send.side_effect = lambda message: loop.call_soon_threadsafe(sent_event.set)
    with patch.object(BUTTON, "AUTHENTICATION_TIMEOUT", 0.01):
        press = asyncio.create_task(entity.async_press())
        await asyncio.wait_for(sent_event.wait(), timeout=1)
        client._Wattpilot__on_message(None, json.dumps({
            "type": "response", "requestId": 1, "success": False,
            "message": "cannot start another transaction when it has already been used to charge",
        }))
        with pytest.raises(HomeAssistantError) as error:
            await press
    assert error.value.translation_key == "authentication_not_confirmed"
    assert "cannot start another transaction" in caplog.text
    assert client.allProps["trx"] == 0
    assert client.allProps["car"] == 2
    assert client._wsapp.send.call_count == 1


async def test_disconnect_during_authentication_is_reported():
    entity = _button("authenticate_audi")
    entity._charger.send_update.side_effect = lambda key, value: setattr(entity._charger, "connected", False)
    with pytest.raises(HomeAssistantError) as error:
        await entity.async_press()
    assert error.value.translation_key == "charger_unavailable"


@pytest.mark.parametrize("language", ["en", "de"])
def test_button_names_and_errors_are_translated(language):
    translations = json.loads(
        (ROOT / "custom_components" / "wattpilot" / "translations" / f"{language}.json")
        .read_text(encoding="utf-8")
    )
    for key in ("authenticate_audi", "authenticate_fiat"):
        assert translations["entity"]["button"][key]["name"]
    for key in (
        "charger_unavailable", "authentication_chip_unavailable", "charger_command_failed",
        "authentication_not_confirmed",
    ):
        assert translations["exceptions"][key]["message"]


async def test_setup_skips_failed_button_initialization():
    charger = MockCharger(extra_props={"trx": None})
    entry = MagicMock(entry_id="test_entry")
    entry.data = {"friendly_name": "Garage"}
    hass = MagicMock()
    hass.data = {"wattpilot": {"test_entry": {"charger": charger, "push_entities": {}}}}
    added = MagicMock()
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=AsyncMock(read=AsyncMock(return_value="unused")))
    context.__aexit__ = AsyncMock(return_value=False)
    with (
        patch.object(BUTTON.aiofiles, "open", return_value=context),
        patch.object(BUTTON.yaml, "safe_load", return_value={"button": [{"id": "trx"}]}),
    ):
        await BUTTON.async_setup_entry(hass, entry, added)
    added.assert_not_called()
