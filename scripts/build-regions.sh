#!/usr/bin/env bash
# India states + ghats for routemates-backend pkg/region from a Geofabrik India extract.
# usage: scripts/build-regions.sh india-latest.osm.pbf outdir
set -euo pipefail
pbf=$1 out=$2 tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
osmium tags-filter "$pbf" r/admin_level=4 -o "$tmp/a4.pbf"
osmium tags-filter "$tmp/a4.pbf" r/boundary=administrative -o "$tmp/states.pbf"
# A state cut by the extract boundary (Arunachal: claimed_by=CN) misses member ways and won't assemble;
# take those few relations whole from the OSM API instead (same ODbL data, one request each).
fix=("$tmp/states.pbf")
for r in $(osmium cat "$tmp/states.pbf" -t relation -f opl | grep 'ISO3166-2=IN-' | grep 'admin_level=4' | cut -d' ' -f1); do
  osmium getid -r "$tmp/states.pbf" "$r" -o "$tmp/$r.pbf"
  if ! osmium check-refs -r "$tmp/$r.pbf" >/dev/null 2>&1; then
    curl -fsSL -A routemates-geo-build "https://api.openstreetmap.org/api/0.6/relation/${r#r}/full" -o "$tmp/$r.osm"
    osmium sort "$tmp/$r.osm" -o "$tmp/$r.full.pbf"
    fix+=("$tmp/$r.full.pbf")
  fi
done
osmium merge "${fix[@]}" -o "$tmp/states-full.pbf"
osmium export "$tmp/states-full.pbf" -f geojsonseq --geometry-types=polygon -o "$tmp/states.geojsonseq"
osmium tags-filter "$pbf" 'w/name=*Ghat' 'w/name=*ghat' 'w/name=*GHAT' 'w/name:en=*Ghat' 'w/name=*घाट' -o "$tmp/ghat.pbf"
osmium tags-filter "$tmp/ghat.pbf" w/highway -o "$tmp/ghatroads.pbf"
osmium export "$tmp/ghatroads.pbf" -f geojsonseq --geometry-types=linestring --add-unique-id=type_id -o "$tmp/ghats.geojsonseq"
osmium tags-filter "$pbf" n/mountain_pass=yes n/natural=mountain_pass -o "$tmp/pass.pbf"
osmium export "$tmp/pass.pbf" -f geojsonseq --geometry-types=point --add-unique-id=type_id -o "$tmp/passes.geojsonseq"
osmium tags-filter "$pbf" w/highway=trunk,primary,secondary,tertiary,unclassified,trunk_link,primary_link,secondary_link,tertiary_link -o "$tmp/roads.pbf"
echo '{"include_tags":["highway"]}' > "$tmp/exp.json"
osmium export "$tmp/roads.pbf" -c "$tmp/exp.json" -f geojsonseq --geometry-types=linestring -o "$tmp/roads.geojsonseq"
python3 -I "$(dirname "$0")/build_regions.py" "$tmp/states.geojsonseq" "$tmp/ghats.geojsonseq" "$tmp/passes.geojsonseq" "$tmp/roads.geojsonseq" "$out"
