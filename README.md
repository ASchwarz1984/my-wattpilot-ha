[![GitHub Latest Release][releases_shield]][latest_release]

[latest_release]: https://github.com/ASchwarz1984/my-wattpilot-ha/releases/latest
[releases_shield]: https://img.shields.io/github/release/ASchwarz1984/my-wattpilot-ha.svg?style=popout

[community_forum_shield]: https://img.shields.io/static/v1.svg?label=%20&message=Forum&style=popout&color=41bdf5&logo=HomeAssistant&logoColor=white
[community_forum]: https://community.home-assistant.io/t/fronius-wattpilot/403118

[paypal_me_shield]: https://img.shields.io/static/v1.svg?label=%20&message=PayPal.Me&logo=paypal
[paypal_me]: https://paypal.me/KraemerMar

# What This Is:

My Wattpilot HA is an independently maintained copy of
[mk-maddin/wattpilot-HA v0.4.0](https://github.com/mk-maddin/wattpilot-HA/releases/tag/v0.4.0).
Installation, issue reporting and releases use this repository. The integration
loads only its bundled Wattpilot client; it does not install or fall back to the
external `wattpilot` package. Standard Python dependencies are still required.
Original attribution and licence files are preserved.

This is a custom component to allow control of [Fronius Wattpilot](https://www.fronius.com/en/solar-energy/installers-partners/technical-data/all-products/solutions/fronius-wattpilot/fronius-wattpilot/wattpilot-home-11-j) wallbox/electro vehicle charging devices in [Homeassistant](https://home-assistant.io) using the unofficial/reverese enginered [wattpilot python module](https://github.com/joscha82/wattpilot).

WARNING:
This is a work in progress project - it is still in early development stage, so there are still breaking changes possible.

## Disclaimer:

As written this is an unofficial implementation.
Currently there does not seem to be an official API available by fronius, so this is all based on the work of volunteers and hobby programmers.
It might stop working at any point in time.

You are using this module (and it's prerequisites/dependencies) at your own risk.
Not me neither any of contributors to this or any prerequired/dependency project are responsible for damage in any kind caused by this project or any of its prerequsites/dependencies.

# What It Does:

Allows for control of [Fronius Wattpilot](https://www.fronius.com/en/solar-energy/installers-partners/products-solutions/residential-energy-solutions/e-mobility-and-photovoltaic-residential/wattpilot-ev-charging-solution-for-homes) wallbox/electro vehicle charging devices via home assistant with the following features:

* works with wattpilot, wattpilot V2 & wattpilot flex (fw > 42.8)
* connect charger via local LAN or via Cloud
* charging mode change
* start / stop charging
* configuration for different charging behaviours
* sensors for charging box status
* manual disconnect/reconnect chargers (Helpful for Wattpilot GO version)
* next trip timing configuration via service call (& event when next trip timing value is changed) -> you can create an [input_datetime (example)](packages/wattpilot/wattpilot_input_datetime.yaml) entity & corresponding [automation (example)](packages/wattpilot/wattpilot_automation.yaml) which ensures the input_datetime is in sync with the setting wihtin your wattpilot charger
* log value changes for properties of the wallbox as warnings (enable/disable via service call)
* can enable/disable e-go cloud charging API (enable/disable via service call) -> this is at your own responsibility - is not clear if fronius/you "pay" in some way for the e-go cloud API and thus are legally allowed to use -> as it is not required at the moment for the functionality of this component, I do not recommend to enable

## Open Topics:

* create a light integration for LED color control etc.
* evaluate entity unique ID generation using WP serial number

## Known Errors:

* No explicit known errors
* See https://github.com/ASchwarz1984/my-wattpilot-ha/issues for issues.

# Screenshots

### Example Device (additional sensors + buttons can be enabled)

![screenshot of Wattpilot Device](doc/device_view1.jpg)

![screenshot of Wattpilot Device](doc/device_view2.jpg)

![screenshot of Wattpilot Device](doc/device_view3.jpg)

### Next Trip via timing via Service Call

![screenshot of Next Trip service](doc/service_view1.jpg)

# Installation and Configuration

## Installation

### Install with HACS

Do you you have [HACS](https://community.home-assistant.io/t/custom-component-hacs) installed?
You can manually add this repository to your HACS installation. [Here is the manual process](https://hacs.xyz/docs/faq/custom_repositories/).
Add `https://github.com/ASchwarz1984/my-wattpilot-ha` with category **Integration**.
Then search for "My Wattpilot HA" and install it directly from HACS.
HACS will keep track of updates and you can easily upgrade to latest version. See Configuration for how to add it in HA.

### Install manually
Download the repository and save the "wattpilot" folder into your home assistant custom_components directory.

Once the files are downloaded, you’ll need to **restart HomeAssistant** and wait some minutes (probably clear your browser cache),
for the integration to appear within the integration store.

## Configuration

### Replacing the original integration

Back up Home Assistant first. Remove the original repository's installation from
HACS without deleting the Wattpilot integration from **Settings > Devices &
services**, then install this repository and restart Home Assistant. If HACS
reports a duplicate integration domain, remove the old HACS repository before
adding this one. Never install both copies together.

The `wattpilot` domain, existing unique IDs and configuration format are
unchanged. Keeping the existing integration entry and charger name avoids
recreating entities or changing automation references.

### Audi and Fiat authentication

Two additional buttons are enabled by default:

| Button | Configured chip | Transaction value sent |
| --- | --- | --- |
| Authorize Audi (chip 0) | ID chip 0 | `trx=1` |
| Authorize Fiat (chip 1) | ID chip 1 | `trx=2` |

With German entity translations, the buttons are named **Audi freigeben (Chip 0)**
and **Fiat freigeben (Chip 1)**. Updating keeps existing entity IDs and any
user-defined names; reload or restart Home Assistant to refresh the default names.

Configure those chips on the charger first. The existing generic **Authenticate**
button remains unchanged: `trx=0` authorizes without a chip.
The vehicle buttons use the existing transaction command, not a forced-start
command; they do not change charging mode, current limits, schedules or cloud
settings. Select the correct vehicle when authorizing a new charging session.
The charger must report transaction support and the selected chip slot.

The vehicle buttons wait up to 10 seconds for the charger-reported transaction
to identify the selected chip. If it does not, Home Assistant shows an error;
the integration does not fabricate a successful chip reading.

An observed first-generation 11 kW charger on firmware 42.5 rejects changing
the identity of a transaction that has already been used to charge, reporting
`cannot start another transaction when it has already been used to charge`.
Consequently, pressing a vehicle button during such a session cannot reassign
its existing energy to a different chip. Authorize the desired chip before the
next charging transaction starts. The buttons do not stop, reset or restart a
transaction to bypass this restriction.

Enable the existing **ID Chip Current** sensor in **Settings > Devices &
services > Wattpilot > Entities** to see the chip reported by the charger.
`ID Chip 0` identifies the Audi and `ID Chip 1` the Fiat; these are assigned
identities, not automatic vehicle detection. Charging itself is reported by
the existing car/charging-state sensors. The chip energy sensors remain
available for separate consumption tracking.

The mapping is documented in the bundled client's API data and existing sensor
definitions. First-generation 11 kW firmware 42.5 is the intended installation,
but authentication and energy attribution must still be checked on a real
charger. The buttons confirm only the charger-reported chip, not successful
charging or energy attribution: verify **ID Chip Current** and the per-chip
energy counters before relying on them. Rejected commands are logged by the
client; no chip or energy reading is fabricated.

### Using MyHA:

[MyHA - Add Integration](https://my.home-assistant.io/redirect/config_flow_start?domain=wattpilot)

### Manually:

1. Browse to your Home Assistant instance.
2. In the sidebar click on Configuration.
3. From the configuration menu select: Integrations.
4. In the bottom right, click on the Add Integration button.
5. From the list, search and select "Fronius Wattpilot".
6. Follow the instruction on screen to complete the set up.
   (If connecting local/LAN you will require the local IP - for cloud connection your wattpilot serial is required)

![screenshot of Config Flow](doc/config_flow1.jpg)

# Credits:

Big thank you go to [@joscha82](https://github.com/joscha82).
Without his greate prework in the [wattpilot python module](https://github.com/joscha82/wattpilot) it would be not possible to create this.

# License

[Apache-2.0](LICENSE). By providing a contribution, you agree the contribution is licensed under Apache-2.0. This is required for Home Assistant contributions.
