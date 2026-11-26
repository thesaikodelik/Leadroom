from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from app import market
from app.filters import domain_key

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # The app remains usable before the optional local engine is installed.
    psycopg = None
    dict_row = None


DEFAULT_OSM_DATABASE_URL = "postgresql://leadroom:leadroom-local@127.0.0.1:5432/leadroom_osm"
NICHE_ALIASES = {
    "beauty": ("beauty", "hairdresser", "salon"),
    "hair": ("hairdresser", "beauty", "salon"),
    "salon": ("salon", "hairdresser", "beauty"),
    "cafe": ("cafe", "coffee shop"),
    "cafes": ("cafe", "coffee shop"),
    "dental": ("dentist", "dental"),
    "dentist": ("dentist", "dental"),
    "hvac": ("hvac", "air conditioning", "heating", "ventilation"),
    "air conditioning": ("air conditioning", "hvac", "ventilation"),
}
NICHE_QUALIFIERS = {
    "business",
    "businesses",
    "contractor",
    "contractors",
    "independent",
    "local",
    "provider",
    "providers",
    "service",
    "services",
    "shop",
    "shops",
    "store",
    "stores",
}


class LocalDataService:
    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or os.getenv("OSM_DATABASE_URL", DEFAULT_OSM_DATABASE_URL)

    def status(self) -> dict[str, Any]:
        result = self._status()
        if LOCAL_DATA_SYNC.running:
            result["update_status"] = "running"
            result["update_message"] = "Downloading and applying OpenStreetMap changes."
        elif result.get("update_status") == "running" and self._use_wsl_bridge:
            # The update script records "running" when it starts; if WSL was shut down
            # part-way through, nothing records the end. Trust only a live service.
            try:
                still_running = self.update_service_active()
            except (OSError, subprocess.SubprocessError):
                still_running = False
            if not still_running:
                result["update_status"] = "idle"
                result["update_message"] = "The last update was interrupted; it will run again."
        if LOCAL_DATA_SYNC.last_error and result.get("update_status") != "running":
            result["update_status"] = "failed"
            result["update_message"] = LOCAL_DATA_SYNC.last_error
        return result

    def _status(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "engine": "PostgreSQL + PostGIS",
            "dataset": "OpenStreetMap Great Britain",
            "ready": False,
            "database": "offline",
            "businesses": 0,
            "with_website": 0,
            "with_phone": 0,
            "with_email": 0,
            "last_imported_at": None,
            "last_updated_at": None,
            "update_status": "not_configured",
            "update_message": "Automatic updates are not configured.",
            "update_schedule": "Daily while Leadroom is open",
            "data_timestamp": None,
            "message": "The local data engine is not connected.",
        }
        if psycopg is None:
            result["message"] = "Install psycopg to connect to the local data engine."
            return result
        if self._use_wsl_bridge:
            return self._wsl_status(result)
        started = time.perf_counter()
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute("SELECT PostGIS_Version() AS version")
                postgis = cursor.fetchone()["version"]
                cursor.execute("SELECT to_regclass('public.leadroom_osm_businesses') AS table_name")
                if not cursor.fetchone()["table_name"]:
                    result.update(
                        database="online",
                        postgis_version=postgis,
                        latency_ms=round((time.perf_counter() - started) * 1000),
                        message="Engine ready. Import an OSM dataset to begin local discovery.",
                    )
                    return result
                cursor.execute(
                    """
                    SELECT count(*) AS businesses,
                           count(*) FILTER (WHERE website <> '') AS with_website,
                           count(*) FILTER (WHERE phone <> '') AS with_phone,
                           count(*) FILTER (WHERE email <> '') AS with_email
                    FROM leadroom_osm_businesses
                    """
                )
                counts = cursor.fetchone()
                cursor.execute(
                    """
                    SELECT json_build_object(
                        'last_imported_at', max(value) FILTER (WHERE key = 'last_imported_at'),
                        'last_updated_at', max(value) FILTER (WHERE key = 'last_updated_at'),
                        'update_status', coalesce(
                            max(value) FILTER (WHERE key = 'update_status'), 'not_configured'
                        ),
                        'update_message', coalesce(
                            max(value) FILTER (WHERE key = 'update_message'),
                            'Automatic updates are not configured.'
                        )
                    ) AS metadata
                    FROM leadroom_osm_metadata
                    """
                )
                imported = cursor.fetchone()
                cursor.execute(
                    """
                    SELECT to_regclass('public.osm2pgsql_properties') IS NOT NULL
                       AND has_table_privilege('public.osm2pgsql_properties', 'SELECT') AS readable
                    """
                )
                if cursor.fetchone()["readable"]:
                    cursor.execute(
                        "SELECT property, value FROM osm2pgsql_properties "
                        "WHERE property IN ('replication_timestamp', 'current_timestamp', 'import_timestamp')"
                    )
                    result["data_timestamp"] = _data_timestamp(
                        {row["property"]: row["value"] for row in cursor.fetchall()}
                    )
                result.update(
                    ready=counts["businesses"] > 0,
                    database="online",
                    postgis_version=postgis,
                    latency_ms=round((time.perf_counter() - started) * 1000),
                    **(imported["metadata"] if imported else {}),
                    message=(
                        "Local discovery is ready."
                        if counts["businesses"] > 0
                        else "Engine ready. Import an OSM dataset to begin local discovery."
                    ),
                    **counts,
                )
                return result
        except Exception as exc:
            result["message"] = str(exc).splitlines()[0][:240]
            return result

    def search(self, niche: str, location: str, limit: int, offset: int = 0) -> list[dict[str, str]]:
        if psycopg is None:
            raise RuntimeError("The local data engine requires psycopg")
        niche_terms = _expand_niche(niche)
        location_term = _location_term(location)
        if self._use_wsl_bridge:
            return self._wsl_search(niche, niche_terms, location_term, limit, offset)
        niche_parameters = {f"niche_{index}": term for index, term in enumerate(niche_terms)}
        niche_rank = ", ".join(
            part
            for index in range(len(niche_terms))
            for part in (
                f"similarity(business.search_text, %(niche_{index})s)",
                f"word_similarity(%(niche_{index})s, business.search_text)",
            )
        )
        niche_match, word_parameters = _niche_match_sql(niche, lambda name: f"%({name})s", "%%")
        niche_parameters.update(word_parameters)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                WITH matching_places AS MATERIALIZED (
                    SELECT place.geom,
                           greatest(similarity(place.search_text, %(location)s),
                                    word_similarity(%(location)s, place.search_text)) AS rank
                    FROM leadroom_osm_places AS place
                    WHERE %(location)s <> ''
                      AND ST_Dimension(place.geom) >= 2
                      AND (%(location)s <%% place.search_text
                           OR place.search_text ILIKE '%%' || %(location)s || '%%')
                    ORDER BY rank DESC
                    LIMIT 24
                ), raw_location_candidates AS MATERIALIZED (
                    SELECT business.osm_type, business.osm_id, place.rank
                    FROM matching_places AS place
                    JOIN leadroom_osm_businesses AS business
                      ON ST_Covers(place.geom, business.geom)
                    UNION ALL
                    SELECT business.osm_type, business.osm_id,
                           greatest(similarity(business.location_text, %(location)s),
                                    word_similarity(%(location)s, business.location_text)) AS rank
                    FROM leadroom_osm_businesses AS business
                    WHERE %(location)s <> ''
                      AND NOT EXISTS (SELECT 1 FROM matching_places)
                      AND (%(location)s <%% business.location_text
                           OR business.location_text ILIKE '%%' || %(location)s || '%%')
                    UNION ALL
                    SELECT business.osm_type, business.osm_id, 0::real AS rank
                    FROM leadroom_osm_businesses AS business
                    WHERE %(location)s = ''
                ), location_candidates AS MATERIALIZED (
                    SELECT osm_type, osm_id, max(rank) AS rank
                    FROM raw_location_candidates
                    GROUP BY osm_type, osm_id
                )
                SELECT business.osm_type, business.osm_id, business.name, business.category,
                       business.category_value, business.website, business.phone, business.email,
                       business.address, business.city, business.postcode,
                       ST_Y(business.geom) AS latitude, ST_X(business.geom) AS longitude,
                       greatest({niche_rank}) AS niche_rank,
                       location_match.rank AS location_rank
                FROM leadroom_osm_businesses AS business
                JOIN location_candidates AS location_match
                  ON location_match.osm_type = business.osm_type
                 AND location_match.osm_id = business.osm_id
                WHERE ({niche_match})
                ORDER BY location_rank DESC, niche_rank DESC,
                         (website <> '') DESC, (email <> '') DESC, (phone <> '') DESC, name
                LIMIT %(limit)s OFFSET %(offset)s
                """,
                {
                    **niche_parameters,
                    "location": location_term,
                    "limit": limit,
                    "offset": offset,
                },
            )
            rows = cursor.fetchall()
        return [self._candidate(row) for row in rows]

    def areas(self, location: str, limit: int = 40) -> list[str]:
        """The districts inside a location, largest first (London gives its 32 boroughs).

        Searching each district finds businesses that a search for the whole city
        ranks too low to show.
        """
        location_term = _location_term(location)
        if not location_term:
            return []
        rows = self._json_rows(
            f"""
            WITH area AS ({_area_sql(location_term)})
            SELECT place.name
            FROM leadroom_osm_places AS place, area
            WHERE place.osm_id <> area.osm_id
              AND place.admin_level ~ '^[0-9]+$'
              AND place.admin_level::int > area.level
              AND place.geom && area.geom
              AND ST_Covers(area.geom, ST_PointOnSurface(place.geom))
            ORDER BY place.admin_level::int, ST_Area(place.geom) DESC
            LIMIT {int(limit)}
            """
        )
        names = [_district_name(str(row.get("name") or "")) for row in rows]
        return [name for name in dict.fromkeys(names) if name and name.casefold() != location_term]

    def find_names(self, names: list[str], location: str, limit: int = 60) -> list[dict[str, str]]:
        """Businesses in a location whose names match names found elsewhere, such as a list
        article; this adds their address and phone even when the name says nothing
        about the market."""
        location_term = _location_term(location)
        wanted = [" ".join(name.casefold().split()) for name in names]
        wanted = [name for name in dict.fromkeys(wanted) if 4 <= len(name) <= 60][:60]
        if not location_term or not wanted:
            return []
        array = "ARRAY[" + ", ".join(_sql_literal(name) for name in wanted) + "]::text[]"
        rows = self._json_rows(
            f"""
            WITH area AS ({_area_sql(location_term)}),
            wanted(name) AS (SELECT unnest({array})),
            -- Only the businesses inside the location are compared with the names; the
            -- spatial index finds them first, so the comparison stays small.
            nearby AS MATERIALIZED (
                SELECT business.*
                FROM leadroom_osm_businesses AS business, area
                WHERE business.geom && area.geom AND ST_Covers(area.geom, business.geom)
            )
            SELECT DISTINCT ON (business.osm_type, business.osm_id)
                   business.osm_type, business.osm_id, business.name, business.category,
                   business.category_value, business.website, business.phone, business.email,
                   business.address, business.city, business.postcode,
                   ST_Y(business.geom) AS latitude, ST_X(business.geom) AS longitude,
                   wanted.name AS wanted
            FROM wanted
            JOIN nearby AS business ON similarity(lower(business.name), wanted.name) >= 0.75
            LIMIT {int(limit)}
            """,
            # Comparing every business in a city with each name takes a few seconds,
            # more while a market search runs beside it.
            timeout=45,
        )
        return [
            self._candidate(row)
            for row in rows
            if _same_business(str(row.get("name") or ""), str(row.get("wanted") or ""), wanted)
        ]

    def _json_rows(self, query: str, timeout: int = 20) -> list[dict[str, Any]]:
        wrapped = f"SELECT coalesce(json_agg(row_to_json(result)), '[]'::json) FROM ({query}) AS result"
        if self._use_wsl_bridge:
            rows = self._wsl_json(wrapped, timeout)
        else:
            if psycopg is None:
                raise RuntimeError("The local data engine requires psycopg")
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(wrapped)
                row = cursor.fetchone()
                rows = next(iter(row.values())) if row else []
        return rows if isinstance(rows, list) else []

    def preview(self, niche: str, location: str, limit: int = 8) -> dict[str, Any]:
        started = time.perf_counter()
        results = self.search(niche, location, limit)
        return {
            "count": len(results),
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
            "results": results,
        }

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row, connect_timeout=3)

    @property
    def _use_wsl_bridge(self) -> bool:
        return sys.platform == "win32" and "OSM_DATABASE_URL" not in os.environ

    def _wsl_status(self, result: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            engine = self._wsl_json(
                "SELECT json_build_object('version', PostGIS_Version(), "
                "'table_ready', to_regclass('public.leadroom_osm_businesses') IS NOT NULL, "
                "'properties_ready', to_regclass('public.osm2pgsql_properties') IS NOT NULL)"
            )
            if not engine["table_ready"]:
                result.update(
                    database="online",
                    postgis_version=engine["version"],
                    latency_ms=round((time.perf_counter() - started) * 1000),
                    message="Engine ready. Import an OSM dataset to begin local discovery.",
                )
                return result
            counts = self._wsl_json(
                "SELECT json_build_object("
                "'businesses', count(*), "
                "'with_website', count(*) FILTER (WHERE website <> ''), "
                "'with_phone', count(*) FILTER (WHERE phone <> ''), "
                "'with_email', count(*) FILTER (WHERE email <> '')) "
                "FROM leadroom_osm_businesses"
            )
            imported = self._wsl_json(
                "SELECT json_build_object("
                "'last_imported_at', max(value) FILTER (WHERE key = 'last_imported_at'), "
                "'last_updated_at', max(value) FILTER (WHERE key = 'last_updated_at'), "
                "'update_status', coalesce(max(value) FILTER (WHERE key = 'update_status'), "
                "'not_configured'), "
                "'update_message', coalesce(max(value) FILTER (WHERE key = 'update_message'), "
                "'Automatic updates are not configured.')) "
                "FROM leadroom_osm_metadata"
            )
            if engine.get("properties_ready"):
                properties = self._wsl_json(
                    "SELECT coalesce(json_object_agg(property, value), '{}'::json) "
                    "FROM osm2pgsql_properties WHERE property IN "
                    "('replication_timestamp', 'current_timestamp', 'import_timestamp')"
                )
                result["data_timestamp"] = _data_timestamp(properties or {})
            result.update(
                ready=counts["businesses"] > 0,
                database="online",
                postgis_version=engine["version"],
                latency_ms=round((time.perf_counter() - started) * 1000),
                **imported,
                message="Local discovery is ready." if counts["businesses"] else "Dataset is empty.",
                **counts,
            )
            return result
        except Exception as exc:
            result["message"] = str(exc).splitlines()[0][:240]
            return result

    def _wsl_search(
        self, niche: str, niche_terms: list[str], location: str, limit: int, offset: int
    ) -> list[dict[str, str]]:
        niche_sql = [_sql_literal(term) for term in niche_terms]
        location_sql = _sql_literal(location)
        niche_rank = ", ".join(
            part
            for term in niche_sql
            for part in (
                f"similarity(business.search_text, {term})",
                f"word_similarity({term}, business.search_text)",
            )
        )
        niche_match, word_parameters = _niche_match_sql(niche, lambda name: "{" + name + "}", "%")
        niche_match = niche_match.format(
            **{name: _sql_literal(value) for name, value in word_parameters.items()}
        )
        query = f"""
            WITH matching_places AS MATERIALIZED (
                SELECT place.geom,
                       greatest(similarity(place.search_text, {location_sql}),
                                word_similarity({location_sql}, place.search_text)) AS rank
                FROM leadroom_osm_places AS place
                WHERE {location_sql} <> ''
                  AND ST_Dimension(place.geom) >= 2
                  AND ({location_sql} <% place.search_text
                       OR place.search_text ILIKE '%' || {location_sql} || '%')
                ORDER BY rank DESC
                LIMIT 24
            ), raw_location_candidates AS MATERIALIZED (
                SELECT business.osm_type, business.osm_id, place.rank
                FROM matching_places AS place
                JOIN leadroom_osm_businesses AS business
                  ON ST_Covers(place.geom, business.geom)
                UNION ALL
                SELECT business.osm_type, business.osm_id,
                       greatest(similarity(business.location_text, {location_sql}),
                                word_similarity({location_sql}, business.location_text)) AS rank
                FROM leadroom_osm_businesses AS business
                WHERE {location_sql} <> ''
                  AND NOT EXISTS (SELECT 1 FROM matching_places)
                  AND ({location_sql} <% business.location_text
                       OR business.location_text ILIKE '%' || {location_sql} || '%')
                UNION ALL
                SELECT business.osm_type, business.osm_id, 0::real AS rank
                FROM leadroom_osm_businesses AS business
                WHERE {location_sql} = ''
            ), location_candidates AS MATERIALIZED (
                SELECT osm_type, osm_id, max(rank) AS rank
                FROM raw_location_candidates
                GROUP BY osm_type, osm_id
            )
            SELECT coalesce(json_agg(row_to_json(candidate)), '[]'::json)
            FROM (
                SELECT business.osm_type, business.osm_id, business.name, business.category,
                       business.category_value, business.website, business.phone, business.email,
                       business.address, business.city, business.postcode,
                       ST_Y(business.geom) AS latitude, ST_X(business.geom) AS longitude,
                       greatest({niche_rank}) AS niche_rank,
                       location_match.rank AS location_rank
                FROM leadroom_osm_businesses AS business
                JOIN location_candidates AS location_match
                  ON location_match.osm_type = business.osm_type
                 AND location_match.osm_id = business.osm_id
                WHERE ({niche_match})
                ORDER BY location_rank DESC, niche_rank DESC,
                         (website <> '') DESC, (email <> '') DESC, (phone <> '') DESC, name
                LIMIT {int(limit)} OFFSET {int(offset)}
            ) AS candidate
        """
        return [self._candidate(row) for row in self._wsl_json(query)]

    @staticmethod
    def _wsl_json(query: str, timeout: int = 20) -> Any:
        completed = _run_hidden(
            [
                "wsl",
                "-d",
                "Ubuntu",
                "-u",
                "postgres",
                "--",
                "psql",
                "-d",
                "leadroom_osm",
                "-Atq",
                "-c",
                query,
            ],
            timeout=timeout,
        )
        if completed.returncode:
            raise RuntimeError(completed.stderr.strip() or "WSL PostgreSQL query failed")
        return json.loads(completed.stdout.strip() or "null")

    def request_update(self) -> dict[str, str]:
        if not self._use_wsl_bridge:
            raise RuntimeError("Manual sync is only available from the Windows local engine")
        return LOCAL_DATA_SYNC.start()

    def update_service_active(self) -> bool:
        """Whether the update service is running in WSL now, not just recorded as running."""
        completed = _run_hidden(
            ["wsl", "-d", "Ubuntu", "-u", "root", "--", "systemctl", "is-active", UPDATE_SERVICE],
            timeout=15,
        )
        return completed.stdout.strip() in {"active", "activating"}

    @staticmethod
    def _candidate(row: dict[str, Any]) -> dict[str, str]:
        website = str(row.get("website") or "").strip()
        osm_type = str(row["osm_type"])
        osm_path_type = {"N": "node", "W": "way", "R": "relation"}.get(osm_type, osm_type)
        osm_id = str(row["osm_id"])
        identity = f"osm-{osm_type}-{osm_id}"
        category = " ".join(
            part.replace("_", " ")
            for part in [str(row.get("category") or ""), str(row.get("category_value") or "")]
            if part
        )
        area = ", ".join(
            part for part in [str(row.get("city") or ""), str(row.get("postcode") or "")] if part
        )
        return {
            "source": "osm_local",
            "sources": ["local"],
            "source_id": identity,
            "title": str(row.get("name") or identity),
            "url": website,
            "homepage": website,
            "snippet": " | ".join(part for part in [category, str(row.get("address") or ""), area] if part),
            "domain": domain_key(website) or identity,
            "business_name": str(row.get("name") or ""),
            "business_type": category,
            "city_or_area": area,
            "address": str(row.get("address") or ""),
            "phone": str(row.get("phone") or ""),
            "email": str(row.get("email") or ""),
            "latitude": str(row.get("latitude") or ""),
            "longitude": str(row.get("longitude") or ""),
            "osm_url": f"https://www.openstreetmap.org/{osm_path_type}/{osm_id}",
        }


def _location_term(location: str) -> str:
    return " ".join(
        re.sub(r"\b(?:uk|united kingdom)\b", " ", location.casefold())
        .translate(str.maketrans({",": " ", ".": " ", "-": " "}))
        .split()
    )


def _area_sql(location_term: str) -> str:
    """The one place polygon that best matches a location, with its administrative level."""
    literal = _sql_literal(location_term)
    return f"""
        SELECT place.osm_id, place.geom,
               CASE WHEN place.admin_level ~ '^[0-9]+$' THEN place.admin_level::int ELSE 0 END AS level
        FROM leadroom_osm_places AS place
        WHERE ST_Dimension(place.geom) >= 2
          AND ({literal} <% place.search_text OR place.search_text ILIKE '%' || {literal} || '%')
        ORDER BY greatest(similarity(place.search_text, {literal}),
                          word_similarity({literal}, place.search_text)) DESC,
                 ST_Area(place.geom) DESC
        LIMIT 1
    """


_DISTRICT_PREFIXES = re.compile(
    r"^(?:(?:london|royal|metropolitan)\s+)?(?:borough|district|city|county|municipality)\s+of\s+",
    re.IGNORECASE,
)


def _district_name(name: str) -> str:
    """ "London Borough of Ealing" -> "Ealing"; "City of Westminster" -> "Westminster"."""
    return " ".join(_DISTRICT_PREFIXES.sub("", " ".join(name.split())).split())


def _same_business(found: str, wanted: str, all_wanted: list[str]) -> bool:
    """Whether a map name is the wanted business and not a namesake with the same common words.

    Words several wanted names share ("supermarket", "super") say little; a rarer
    word of this name ("Aran", "Zaman") must be in the map's name, so "Afran
    Supermarket" is not taken for "Aran Supermarket". Spaces are ignored, so
    "Zam Zam" is "Zamzam".
    """
    squashed = "".join(re.findall(r"[^\W_]+", found.casefold()))
    counts: dict[str, int] = {}
    for name in all_wanted:
        for word in set(re.findall(r"[^\W_]+", name)):
            counts[word] = counts.get(word, 0) + 1
    words = [word for word in re.findall(r"[^\W_]+", wanted) if len(word) >= 3]
    rare = [word for word in words if counts.get(word, 0) <= 2] or words
    return any(word in squashed for word in rare)


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _run_hidden(command: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    options: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": timeout,
        "check": False,
    }
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        options.update(
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            startupinfo=startupinfo,
        )
    return subprocess.run(command, **options)


def _expand_niche(value: str) -> list[str]:
    normalized = " ".join(value.casefold().split())
    meaningful = " ".join(token for token in normalized.split() if token not in NICHE_QUALIFIERS)
    terms = [meaningful or normalized]
    for trigger, aliases in NICHE_ALIASES.items():
        if trigger in normalized:
            terms.extend(aliases)
    return list(dict.fromkeys(term for term in terms if term))


def _niche_alternatives(value: str) -> list[list[tuple[str, ...]]]:
    """Ways a business can match the market: each is a list of concepts that must all appear.

    "Iranian supermarket" needs both an Iranian word and a supermarket word, so a
    chain supermarket does not match on "supermarket" alone. The concepts and their
    synonyms come from app.market, so this works for any market without word lists.
    """
    normalized = " ".join(value.casefold().split())
    alternatives: list[list[tuple[str, ...]]] = []
    groups = market.concepts(value)
    if groups:
        alternatives.append(groups)
    for trigger, aliases in NICHE_ALIASES.items():
        if trigger in normalized:
            alternatives.extend([[(alias,)] for alias in aliases])
    unique: list[list[tuple[str, ...]]] = []
    for alternative in alternatives:
        if alternative not in unique:
            unique.append(alternative)
    return unique


def _niche_match_sql(
    niche: str, placeholder: Callable[[str], str], percent: str
) -> tuple[str, dict[str, str]]:
    """SQL that keeps businesses whose name or category contains every word of the market."""
    parameters: dict[str, str] = {}
    clauses: list[str] = []
    for alt_index, groups in enumerate(_niche_alternatives(niche)):
        parts: list[str] = []
        for group_index, group in enumerate(groups):
            name = f"niche_word_{alt_index}_{group_index}"
            # Each form must start a word, so "iran" finds "Iranian" but not "Miranda".
            parameters[name] = market.concept_pattern(group)
            parts.append(f"business.search_text ~ {placeholder(name)}")
        if len(groups) == 1 and len(groups[0]) == 1:
            # A single word keeps fuzzy matching for small spelling differences.
            fuzzy = f"fuzzy_{alt_index}"
            parameters[fuzzy] = groups[0][0]
            parts = [f"({parts[0]} OR {placeholder(fuzzy)} <{percent} business.search_text)"]
        clauses.append("(" + " AND ".join(parts) + ")")
    return " OR ".join(clauses) or "TRUE", parameters


UPDATE_SERVICE = "leadroom-osm-update.service"


def _data_timestamp(properties: dict[str, Any]) -> str | None:
    """The date the local OpenStreetMap data is current to, from osm2pgsql's own record."""
    for key in ("replication_timestamp", "current_timestamp", "import_timestamp"):
        value = str(properties.get(key) or "").strip()
        if value:
            return value
    return None


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


class LocalDataSync:
    """Runs the WSL update service from the app and keeps WSL alive while it works.

    WSL shuts its distribution down seconds after the last Windows-side command ends, so a
    nightly timer inside it fires only on the rare nights WSL happens to be running, and an
    update started with --no-block can be cut off part-way. Running ``systemctl start`` and
    waiting for it holds WSL open until the update has finished.
    """

    # Geofabrik publishes daily diffs, so data a little over a day old is as fresh as it gets.
    STALE_AFTER = timedelta(hours=30)
    CHECK_EVERY = timedelta(hours=1)
    RETRY_AFTER_FAILURE = timedelta(hours=6)
    UPDATE_TIMEOUT_SECONDS = 6 * 60 * 60

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._auto: threading.Thread | None = None
        self._stop = threading.Event()
        self.last_error = ""
        self.last_attempt: datetime | None = None

    @property
    def running(self) -> bool:
        worker = self._worker
        return bool(worker and worker.is_alive())

    def start(self) -> dict[str, str]:
        with self._lock:
            if self.running:
                return {"status": "running", "message": "Local data sync is already running."}
            self.last_error = ""
            self.last_attempt = datetime.now(UTC)
            self._worker = threading.Thread(target=self._run, name="local-data-sync", daemon=True)
            self._worker.start()
        return {"status": "started", "message": "Local data sync started in the background."}

    def _run(self) -> None:
        try:
            completed = _run_hidden(
                ["wsl", "-d", "Ubuntu", "-u", "root", "--", "systemctl", "start", UPDATE_SERVICE],
                timeout=self.UPDATE_TIMEOUT_SECONDS,
            )
            if completed.returncode:
                self.last_error = (
                    "The local data update failed. Review: wsl -d Ubuntu -u root -- "
                    "journalctl -u leadroom-osm-update.service"
                )
        except (OSError, subprocess.SubprocessError) as exc:
            self.last_error = f"The local data update could not run: {exc}"[:240]

    def due(self, status: dict[str, Any], now: datetime | None = None) -> bool:
        """Whether an automatic update should start now, given a LocalDataService status."""
        now = now or datetime.now(UTC)
        if not status.get("ready") or status.get("update_status") in {"running", "not_configured"}:
            return False
        if self.running:
            return False
        if self.last_attempt and now - self.last_attempt < (
            self.RETRY_AFTER_FAILURE if self.last_error else self.CHECK_EVERY
        ):
            return False
        current_to = _parse_timestamp(status.get("data_timestamp"))
        return current_to is None or now - current_to > self.STALE_AFTER

    def start_automatic(self, first_delay: float = 90) -> None:
        """Check a little after start-up and then hourly; only on the Windows WSL engine."""
        if sys.platform != "win32" or "OSM_DATABASE_URL" in os.environ:
            return
        if self._auto and self._auto.is_alive():
            return

        def loop() -> None:
            delay = first_delay
            while not self._stop.wait(delay):
                delay = self.CHECK_EVERY.total_seconds()
                try:
                    service = LocalDataService()
                    if self.due(service.status()):
                        service.request_update()
                except Exception:  # noqa: BLE001 - a background check must never stop the app
                    continue

        self._auto = threading.Thread(target=loop, name="local-data-auto-sync", daemon=True)
        self._auto.start()

    def stop_automatic(self) -> None:
        self._stop.set()


LOCAL_DATA_SYNC = LocalDataSync()
