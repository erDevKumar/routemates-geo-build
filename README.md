# routemates-geo-build

Monthly Valhalla routing tiles for India, built from the Geofabrik OSM extract (ODbL, © OpenStreetMap contributors).
Public on purpose: free 16 GB arm64 runners. No app code, no secrets. Consumed by the Routemates VM `geo-refresh` Job (infra D05.05).

Also builds India state/UT polygons + a ghat list (`scripts/build-regions.sh`, same ODbL extract) for routemates-backend `pkg/region`; on refresh, diff the `regions` artifact into that package.
