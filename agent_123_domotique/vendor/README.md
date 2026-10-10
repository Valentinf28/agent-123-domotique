# SolarMAN connector bundle

Upstream: https://github.com/davidrapan/ha-solarman
Release: https://github.com/davidrapan/ha-solarman/releases/tag/v25.08.16
Asset: https://github.com/davidrapan/ha-solarman/releases/download/v25.08.16/solarman.zip
SHA-256: `04fd37da1ba1cd3a590146a48602162ad5c7e0c319c80ca326369cd5a26da977`

The archive is the unchanged official release asset. Its digest was checked against
GitHub's release asset metadata. SOLARMAN-LICENSE is copied from the release tag's
root `license` file; nested dependency licenses remain in the archive. Installation
also copies this root license into the installed integration.

Bundling permits offline placement of the integration without HACS. Home Assistant
may still need Internet to install Python requirements when first loading it.
No compatibility claim with a new HA version is implied by packaging. Validate
loading, configuration and real readings on the Showroom before releasing.

Installation applies two documented 1.2.3 Home adaptations to the extracted copy
(the archived upstream asset remains unchanged): config_flow accepts an explicit
`logger_serial`, and the endpoint uses that serial without UDP discovery or the
upstream automatic HTTP logger configuration. The original discovery behavior is
retained for connections without an explicit serial. A separate, attributed Deye
measurement-only profile is installed under `inverter_definitions/custom`.
The setup action always selects that profile and supplies the explicit serial.
