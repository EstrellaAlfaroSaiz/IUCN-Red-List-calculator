# -*- coding: utf-8 -*-
"""Small GBIF client using Python standard library only.

The plugin intentionally avoids external Python dependencies because many QGIS
installations do not ship with additional packages such as requests.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request

GBIF_API = "https://api.gbif.org/v1"


class GbifError(RuntimeError):
    """Raised when GBIF cannot be queried or returns an error."""


def _get_json(path: str, params=None, timeout: int = 45) -> dict:
    query = urllib.parse.urlencode(params or {}, doseq=True)
    url = f"{GBIF_API}{path}"
    if query:
        url = f"{url}?{query}"

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "QGIS-AOO-EOO-GBIF-Pro/0.2.5",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310 - public GBIF API
            payload = response.read().decode("utf-8")
            return json.loads(payload)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise GbifError(f"GBIF HTTP {exc.code}: {body[:500]}") from exc
    except urllib.error.URLError as exc:
        raise GbifError(f"No se pudo conectar con GBIF: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise GbifError("GBIF returned a non-JSON response") from exc


def _post_json_basic_auth(path: str, payload: dict, username: str, password: str, timeout: int = 60) -> dict:
    url = f"{GBIF_API}{path}"
    body = json.dumps(payload).encode("utf-8")
    credentials = f"{username}:{password}".encode("utf-8")
    auth = base64.b64encode(credentials).decode("ascii")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "User-Agent": "QGIS-AOO-EOO-GBIF-Pro/0.2.5",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Basic {auth}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310 - public GBIF API
            payload_text = response.read().decode("utf-8")
            return json.loads(payload_text)
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise GbifError(f"GBIF HTTP {exc.code}: {body_text[:1000]}") from exc
    except urllib.error.URLError as exc:
        raise GbifError(f"No se pudo conectar con GBIF: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise GbifError("GBIF returned a non-JSON response") from exc


def match_species(scientific_name: str) -> dict:
    """Resolve a name against the GBIF backbone.

    Returns the raw match response. The dialog uses usageKey when available.
    """
    name = (scientific_name or "").strip()
    if not name:
        raise GbifError("Enter a scientific name or a taxonKey.")
    return _get_json("/species/match", {"name": name})


def occurrence_facets(params: dict, facets=None) -> dict:
    """Get total count and facet counts for selected GBIF filters."""
    facets = facets or ["basisOfRecord", "establishmentMeans", "occurrenceStatus", "country"]
    query = dict(params)
    query["limit"] = 0
    query["facetLimit"] = 50
    query["facet"] = facets
    return _get_json("/occurrence/search", query)


def search_occurrences(params: dict, max_records=None, progress_callback=None):
    """Search occurrences with pagination.

    GBIF's occurrence search endpoint uses limit/offset pagination. By default
    the plugin retrieves records until GBIF reports the end of the result set.
    The optional max_records argument is kept only for backward compatibility
    with older calls.
    """
    records: list[dict] = []
    offset = 0
    page_size = 300

    while True:
        query = dict(params)
        if max_records is None:
            query["limit"] = page_size
        else:
            remaining = max_records - len(records)
            if remaining <= 0:
                break
            query["limit"] = min(page_size, remaining)
        query["offset"] = offset

        data = _get_json("/occurrence/search", query)
        batch = data.get("results", [])
        if not batch:
            break

        records.extend(batch)
        if progress_callback:
            progress_callback(len(records), data.get("count"))

        if data.get("endOfRecords"):
            break
        if max_records is not None and len(records) >= max_records:
            break

        offset += len(batch)
        if len(batch) < query["limit"]:
            break

    return records


def slim_record(record: dict) -> dict:
    """Return the GBIF fields used by this plugin."""
    return {
        "gbifID": str(record.get("gbifID", "")),
        "scientificName": record.get("scientificName") or record.get("species") or "",
        "taxonKey": record.get("taxonKey") or record.get("speciesKey") or "",
        "decimalLatitude": record.get("decimalLatitude"),
        "decimalLongitude": record.get("decimalLongitude"),
        "basisOfRecord": record.get("basisOfRecord") or "",
        "occurrenceStatus": record.get("occurrenceStatus") or "",
        "establishmentMeans": record.get("establishmentMeans") or "",
        "eventDate": record.get("eventDate") or "",
        "year": record.get("year"),
        "countryCode": record.get("countryCode") or "",
        "datasetKey": record.get("datasetKey") or "",
        "institutionCode": record.get("institutionCode") or "",
        "collectionCode": record.get("collectionCode") or "",
        "recordedBy": record.get("recordedBy") or "",
        "identifiedBy": record.get("identifiedBy") or "",
        "coordinateUncertaintyInMeters": record.get("coordinateUncertaintyInMeters"),
        "issues": ";".join(record.get("issues") or []),
        "data_origin": "GBIF",
        "review_status": "accepted",
        "include_for_aoo_eoo": True,
    }


def create_derived_dataset(
    dataset_counts: dict,
    title: str,
    description: str,
    source_url: str,
    username: str,
    password: str,
    gbif_download_doi: str | None = None,
) -> dict:
    """Create a GBIF Derived Dataset and return the registry response.

    GBIF expects a JSON payload with title, description, sourceUrl and
    relatedDatasets, where relatedDatasets maps datasetKey -> record count.
    Authentication uses the GBIF.org username and password supplied by the user.
    """
    clean_counts = {}
    for key, count in (dataset_counts or {}).items():
        key_text = str(key).strip()
        try:
            count_int = int(count)
        except (TypeError, ValueError):
            continue
        if key_text and count_int > 0:
            clean_counts[key_text] = count_int

    if not clean_counts:
        raise GbifError("There are no valid datasetKey/count values to create the Derived Dataset.")
    if not title:
        raise GbifError("The Derived Dataset title is required.")
    if not description:
        raise GbifError("The Derived Dataset description is required.")
    if not source_url:
        raise GbifError("The public dataset URL is required.")
    if not username or not password:
        raise GbifError("GBIF username and password are required.")

    payload = {
        "title": title,
        "description": description,
        "sourceUrl": source_url,
        "relatedDatasets": clean_counts,
    }
    if gbif_download_doi:
        payload["originalDownloadDOI"] = gbif_download_doi

    return _post_json_basic_auth("/derivedDataset", payload, username, password)



def _post_json_basic_auth_text(path: str, payload: dict, username: str, password: str, timeout: int = 60) -> str:
    """POST JSON with GBIF basic auth and return the raw response text."""
    url = f"{GBIF_API}{path}"
    body = json.dumps(payload).encode("utf-8")
    credentials = f"{username}:{password}".encode("utf-8")
    auth = base64.b64encode(credentials).decode("ascii")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "User-Agent": "QGIS-AOO-EOO-GBIF-Pro/0.2.5",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Authorization": f"Basic {auth}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310 - public GBIF API
            return response.read().decode("utf-8").strip().strip('"')
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise GbifError(f"GBIF HTTP {exc.code}: {body_text[:1000]}") from exc
    except urllib.error.URLError as exc:
        raise GbifError(f"No se pudo conectar con GBIF: {exc}") from exc


def request_occurrence_download_by_gbif_ids(
    gbif_ids: list[str],
    username: str,
    password: str,
    notification_email: str | None = None,
    download_format: str = "SIMPLE_CSV",
) -> str:
    """Request an official GBIF occurrence download for the exact GBIF IDs used.

    The returned value is the GBIF download key. The DOI is available later,
    once GBIF finishes the asynchronous download.
    """
    clean_ids = []
    seen = set()
    for value in gbif_ids or []:
        text_value = str(value).strip()
        if text_value and text_value not in seen:
            clean_ids.append(text_value)
            seen.add(text_value)

    if not clean_ids:
        raise GbifError("There are no valid gbifIDs to request an official download.")
    if not username or not password:
        raise GbifError("GBIF username and password are required.")

    # GBIF authenticates the requester with the Basic Auth username.
    # Do not send a separate "creator" value here: if it differs from the
    # authenticated GBIF username, GBIF rejects the request with HTTP 401
    # (e.g. "not allowed to create download with creator ...").
    payload = {
        "sendNotification": bool(notification_email),
        "format": download_format or "SIMPLE_CSV",
        "predicate": {
            "type": "in",
            "key": "GBIF_ID",
            "values": clean_ids,
        },
    }
    if notification_email:
        payload["notificationAddresses"] = [notification_email]

    return _post_json_basic_auth_text("/occurrence/download/request", payload, username, password, timeout=90)


def get_occurrence_download(download_key: str) -> dict:
    """Return GBIF occurrence download metadata for a download key."""
    key = (download_key or "").strip()
    if not key:
        raise GbifError("Introduce una clave de descarga GBIF.")
    return _get_json(f"/occurrence/download/{urllib.parse.quote(key)}")
