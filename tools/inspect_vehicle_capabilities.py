"""Inspect VOGE vehicle capabilities without printing account secrets.

This local-only script asks for credentials interactively, uses fixed read-only
modern endpoints, and emits a whitelist-based structural summary. It includes
only bounded public model labels, opaque product IDs, capability flags, types,
and counts; it is not an API response dump.
"""

from __future__ import annotations

import asyncio
import getpass
import hashlib
import json
import re
import sys
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from aiohttp import ClientError, ClientSession, ClientTimeout

BASE_URL = "https://iot-api.loncinindustries.com"
LOGIN_PATH = "/api/login/loginByMobile"
MAX_BODY_BYTES = 2 * 1024 * 1024
ROUTE_MAX_BODY_BYTES = 20 * 1024 * 1024
MAX_PUBLIC_TEXT_LENGTH = 120
MAX_REQUEST_IDENTIFIER_LENGTH = 256

SENSITIVE_KEYS = frozenset(
    key.casefold()
    for key in {
        "accessKey",
        "address",
        "amapDeviceId",
        "avatarUrl",
        "beginAddr",
        "beginLatitude",
        "beginLongitude",
        "bicoseToken",
        "content",
        "deviceId",
        "deviceIdIot",
        "endAddr",
        "endLatitude",
        "endLongitude",
        "formattedAddress",
        "geoLatitude",
        "geoLongitude",
        "iccid",
        "imei",
        "latitude",
        "longitude",
        "memberId",
        "message",
        "messageId",
        "mobile",
        "nonce",
        "param",
        "password",
        "phone",
        "plateNo",
        "points",
        "refreshToken",
        "routeId",
        "signature",
        "simId",
        "tel",
        "token",
        "userId",
        "userName",
        "userNickname",
        "userNo",
        "vin",
    }
)
MODEL_LABEL_KEYS = ("deviceName", "productName")
SAFE_FIELD_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}\Z")
PRODUCT_ID = re.compile(r"[A-Za-z0-9._-]{1,64}\Z")

ENDPOINTS = {
    "M1 devices": "/api/app/favorite/device",
    "M2 diagnosis": "/api/app/favorite/synthesize-diagnosis",
    "M3 month index": "/api/app/favorite/index",
    "M4 month tracks": "/api/app/favorite/car-track-new",
    "M5 route detail": "/api/app/favorite/locus",
    "M6 behavior": "/api/app/favorite/behavior",
    "M7 riding": "/api/app/favorite/riding",
}
ALLOWED_QUERY_KEYS = {
    ENDPOINTS["M1 devices"]: frozenset(),
    ENDPOINTS["M2 diagnosis"]: frozenset(),
    ENDPOINTS["M3 month index"]: frozenset({"deviceId"}),
    ENDPOINTS["M4 month tracks"]: frozenset({"deviceId", "month"}),
    ENDPOINTS["M5 route detail"]: frozenset({"routeId"}),
    ENDPOINTS["M6 behavior"]: frozenset({"deviceId", "month"}),
    ENDPOINTS["M7 riding"]: frozenset({"deviceId", "month"}),
}


async def _read_json(response: Any, limit: int) -> dict[str, Any]:
    raw = await response.content.read(limit + 1)
    if len(raw) > limit:
        raise RuntimeError("response_too_large")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise RuntimeError("invalid_json") from err
    if not isinstance(payload, dict):
        raise RuntimeError("response_not_object")
    return payload


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return type(value).__name__


def _safe_field_name(value: Any) -> str | None:
    if not isinstance(value, str) or SAFE_FIELD_NAME.fullmatch(value) is None:
        return None
    if value.casefold() in SENSITIVE_KEYS:
        return None
    return value


def _safe_public_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    printable = "".join(char for char in value if char.isprintable()).strip()
    return printable[:MAX_PUBLIC_TEXT_LENGTH] or None


def _safe_product_id(value: Any) -> str | None:
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped if PRODUCT_ID.fullmatch(stripped) is not None else None


def _safe_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped and len(stripped) <= 10 and stripped.lstrip("-").isdigit():
            return int(stripped)
    return None


def _request_identifier(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped or len(stripped) > MAX_REQUEST_IDENTIFIER_LENGTH:
        return None
    return stripped if all(char.isprintable() for char in stripped) else None


def _field_types(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    fields = [
        (safe_key, _type_name(raw))
        for key, raw in value.items()
        if (safe_key := _safe_field_name(key)) is not None
    ]
    return dict(sorted(fields))


def _safe_menu(value: Any) -> dict[str, bool | int]:
    if not isinstance(value, dict):
        return {}
    menu: dict[str, bool | int] = {}
    for key, raw in value.items():
        safe_key = _safe_field_name(key)
        if safe_key is None:
            continue
        if isinstance(raw, bool) or (
            isinstance(raw, int) and raw in {0, 1}
        ):
            menu[safe_key] = raw
        elif isinstance(raw, float) and raw in {0.0, 1.0}:
            menu[safe_key] = int(raw)
        elif isinstance(raw, str) and raw.strip() in {"0", "1"}:
            menu[safe_key] = int(raw.strip())
    return dict(sorted(menu.items()))


def _safe_vehicle(vehicle: dict[str, Any], ordinal: int) -> dict[str, Any]:
    model_labels = {
        key: safe_value
        for key in MODEL_LABEL_KEYS
        if (safe_value := _safe_public_text(vehicle.get(key))) is not None
    }
    return {
        "ordinal": ordinal,
        "product_id": _safe_product_id(vehicle.get("productId")),
        "model_label_candidates": model_labels,
        "device_id_present": _request_identifier(vehicle.get("deviceId")) is not None,
        "vin_present": _request_identifier(vehicle.get("vin")) is not None,
        "menu": _safe_menu(vehicle.get("menu")),
        "field_types": _field_types(vehicle),
    }


def _result(payload: dict[str, Any]) -> Any:
    return payload.get("result") if _safe_int(payload.get("code")) == 200 else None


def _response_status(payload: dict[str, Any], http_status: int) -> dict[str, Any]:
    return {
        "http_status": http_status,
        "code": _safe_int(payload.get("code")),
        "success": payload.get("success") if isinstance(payload.get("success"), bool) else None,
    }


def _summarize_object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"result_type": _type_name(value)}
    summary: dict[str, Any] = {
        "result_type": "object",
        "field_types": _field_types(value),
    }
    menu = _safe_menu(value.get("menu"))
    if menu:
        summary["menu"] = menu
    can_list = value.get("canList")
    if isinstance(can_list, list):
        summary["can_group_count"] = len(can_list)
        summary["can_group_field_types"] = [
            _field_types(item) for item in can_list if isinstance(item, dict)
        ]
    return summary


def _summarize_month_tracks(value: Any) -> dict[str, Any]:
    if not isinstance(value, list):
        return {"result_type": _type_name(value), "day_count": 0, "route_count": 0}
    day_summaries: list[dict[str, Any]] = []
    route_count = 0
    first_route_id: str | None = None
    for item in value:
        if not isinstance(item, dict):
            continue
        trips = item.get("list")
        trip_count = len(trips) if isinstance(trips, list) else 0
        route_count += trip_count
        if first_route_id is None and isinstance(trips, list):
            for trip in trips:
                if not isinstance(trip, dict):
                    continue
                first_route_id = _request_identifier(trip.get("routeId"))
                if first_route_id is not None:
                    break
        day_summaries.append(
            {
                "field_types": _field_types(item),
                "trip_count": trip_count,
                "trip_field_types": (
                    _field_types(trips[0])
                    if isinstance(trips, list)
                    and trips
                    and isinstance(trips[0], dict)
                    else {}
                ),
            }
        )
    return {
        "result_type": "array",
        "day_count": len(day_summaries),
        "route_count": route_count,
        "days": day_summaries,
        "route_id_found_locally": first_route_id is not None,
        "_first_route_id": first_route_id,
    }


def _summarize_route(value: Any, expected_route_id: str | None) -> dict[str, Any]:
    summary = _summarize_object(value)
    if isinstance(value, dict):
        response_route_id = _request_identifier(value.get("routeId"))
        summary["route_id_present"] = response_route_id is not None
        summary["route_id_matches"] = (
            response_route_id == expected_route_id
            if response_route_id is not None and expected_route_id is not None
            else None
        )
        points = value.get("points")
        if isinstance(points, str):
            try:
                decoded = json.loads(points)
            except (json.JSONDecodeError, ValueError):
                summary["points"] = {"type": "json_string", "valid_json": False}
            else:
                summary["points"] = {
                    "type": "json_string",
                    "valid_json": True,
                    "item_count": len(decoded) if isinstance(decoded, list) else None,
                    "item_field_types": (
                        _field_types(decoded[0])
                        if isinstance(decoded, list)
                        and decoded
                        and isinstance(decoded[0], dict)
                        else {}
                    ),
                }
        elif points is not None:
            summary["points"] = {"type": _type_name(points)}
    return summary


def _selection_index(value: str, vehicle_count: int) -> int | None:
    stripped = value.strip()
    if vehicle_count == 1 and not stripped:
        return 0
    if not stripped.isdigit():
        return None
    ordinal = int(stripped)
    return ordinal - 1 if 1 <= ordinal <= vehicle_count else None


def _print_vehicle_choices(vehicles: list[dict[str, Any]]) -> None:
    print("Multiple vehicles found; select one by ordinal:", file=sys.stderr)
    for vehicle in vehicles:
        labels = vehicle["model_label_candidates"]
        label = next(iter(labels.values()), "unknown model")
        print(f"  [{vehicle['ordinal']}] {label}", file=sys.stderr)
    print("Selection: ", end="", file=sys.stderr, flush=True)


async def _get(
    session: ClientSession,
    path: str,
    headers: dict[str, str],
    params: dict[str, str] | None = None,
    *,
    limit: int = MAX_BODY_BYTES,
) -> tuple[int, dict[str, Any]]:
    allowed_query_keys = ALLOWED_QUERY_KEYS.get(path)
    if allowed_query_keys is None or set((params or {}).keys()) != allowed_query_keys:
        raise RuntimeError("endpoint_not_allowed")
    async with session.get(
        f"{BASE_URL}{path}",
        params=params or {},
        headers=headers,
        allow_redirects=False,
    ) as response:
        if response.status >= 300:
            return response.status, {}
        return response.status, await _read_json(response, limit)


async def _main() -> None:
    mobile = input("VOGE mobile: ").strip()
    password = getpass.getpass("VOGE password: ")
    if not mobile or not password:
        print(json.dumps({"error": "mobile_and_password_required"}))
        return

    current_month = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m")
    month = input(f"Month [default {current_month}]: ").strip() or current_month
    try:
        parsed_month = datetime.strptime(month, "%Y-%m")
    except ValueError:
        print(json.dumps({"error": "month_must_be_yyyy_mm"}))
        return
    if parsed_month.strftime("%Y-%m") != month:
        print(json.dumps({"error": "month_must_be_yyyy_mm"}))
        return

    base_headers = {
        "Content-Language": "zh_CN",
        "Platform": "ANDROID",
        "Mansuoid": "",
        "Blade-Auth": "",
        "version": "1.3.3",
        "PhoneModel": "HomeAssistant/voge-0.1.0",
        "Source": "VOGE",
    }
    login_body = {
        "mobile": mobile,
        "password": hashlib.md5(
            password.encode("utf-8"),
            usedforsecurity=False,
        ).hexdigest(),
    }

    try:
        async with ClientSession(timeout=ClientTimeout(total=60)) as session:
            async with session.post(
                f"{BASE_URL}{LOGIN_PATH}",
                json=login_body,
                headers={**base_headers, "Content-Type": "application/json"},
                allow_redirects=False,
            ) as response:
                login_status = response.status
                if login_status >= 300:
                    print(json.dumps({"login_http_status": login_status}))
                    return
                login = await _read_json(response, MAX_BODY_BYTES)

            result = _result(login)
            token = result.get("token") if isinstance(result, dict) else None
            if _safe_int(login.get("code")) != 200 or login.get("success") is False:
                print(
                    json.dumps(
                        _response_status(login, login_status),
                        ensure_ascii=False,
                    )
                )
                return
            if not isinstance(token, str) or not token.strip():
                print(json.dumps({"error": "token_missing"}))
                return

            headers = {**base_headers, "Mansuoid": token.strip()}
            output: dict[str, Any] = {"month": month, "endpoints": {}}

            m1_status, m1 = await _get(session, ENDPOINTS["M1 devices"], headers)
            m1_result = _result(m1)
            raw_vehicles = (
                [
                    vehicle
                    for vehicle in m1_result
                    if isinstance(vehicle, dict)
                    and _request_identifier(vehicle.get("deviceId")) is not None
                ]
                if isinstance(m1_result, list)
                else []
            )
            invalid_vehicle_records = (
                sum(1 for vehicle in m1_result if isinstance(vehicle, dict))
                - len(raw_vehicles)
                if isinstance(m1_result, list)
                else 0
            )
            vehicles = [
                _safe_vehicle(vehicle, index)
                for index, vehicle in enumerate(raw_vehicles, 1)
            ]
            output["endpoints"]["M1 devices"] = {
                **_response_status(m1, m1_status),
                "vehicle_count": len(vehicles),
                "invalid_vehicle_record_count": invalid_vehicle_records,
                "vehicles": vehicles,
            }

            if not vehicles:
                print(json.dumps(output, ensure_ascii=False, indent=2))
                return

            if len(vehicles) > 1:
                _print_vehicle_choices(vehicles)
                selected_index = _selection_index(input(), len(vehicles))
                if selected_index is None:
                    print(json.dumps({"error": "invalid_vehicle_selection"}))
                    return
            else:
                selected_index = 0

            selected = raw_vehicles[selected_index]
            device_id = _request_identifier(selected.get("deviceId"))
            if device_id is None:
                print(json.dumps({"error": "device_id_missing_in_m1"}))
                return
            output["selected_vehicle_ordinal"] = selected_index + 1

            m2_status, m2 = await _get(session, ENDPOINTS["M2 diagnosis"], headers)
            m2_result = _result(m2)
            output["endpoints"]["M2 diagnosis"] = {
                **_response_status(m2, m2_status),
                **_summarize_object(m2_result),
                "device_id_matches_selected": (
                    isinstance(m2_result, dict)
                    and m2_result.get("deviceId") == device_id
                ),
            }

            query = {"deviceId": device_id}
            m3_status, m3 = await _get(
                session,
                ENDPOINTS["M3 month index"],
                headers,
                query,
            )
            m3_result = _result(m3)
            output["endpoints"]["M3 month index"] = {
                **_response_status(m3, m3_status),
                **_summarize_object(m3_result),
                "device_id_matches_selected": (
                    isinstance(m3_result, dict)
                    and (
                        m3_result.get("deviceId") is None
                        or m3_result.get("deviceId") == device_id
                    )
                ),
            }

            month_query = {"deviceId": device_id, "month": month}
            m4_status, m4 = await _get(
                session,
                ENDPOINTS["M4 month tracks"],
                headers,
                month_query,
            )
            m4_result = _result(m4)
            m4_summary = _summarize_month_tracks(m4_result)
            first_route_id = m4_summary.pop("_first_route_id", None)
            output["endpoints"]["M4 month tracks"] = {
                **_response_status(m4, m4_status),
                **m4_summary,
            }

            if isinstance(first_route_id, str):
                m5_status, m5 = await _get(
                    session,
                    ENDPOINTS["M5 route detail"],
                    headers,
                    {"routeId": first_route_id},
                    limit=ROUTE_MAX_BODY_BYTES,
                )
                output["endpoints"]["M5 route detail"] = {
                    **_response_status(m5, m5_status),
                    **_summarize_route(_result(m5), first_route_id),
                }
            else:
                output["endpoints"]["M5 route detail"] = {
                    "skipped": "no_route_id_in_m4"
                }

            for name in ("M6 behavior", "M7 riding"):
                status, payload = await _get(
                    session,
                    ENDPOINTS[name],
                    headers,
                    month_query,
                )
                output["endpoints"][name] = {
                    **_response_status(payload, status),
                    **_summarize_object(_result(payload)),
                }

        print(json.dumps(output, ensure_ascii=False, indent=2))
    except (ClientError, TimeoutError) as err:
        print(json.dumps({"error": "transport_error", "type": type(err).__name__}))
    except RuntimeError as err:
        print(json.dumps({"error": str(err)}))


if __name__ == "__main__":
    asyncio.run(_main())
