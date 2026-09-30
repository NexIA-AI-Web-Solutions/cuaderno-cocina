#!/usr/bin/env python3
"""Release smoke against the isolated Cuaderno demo over its real HTTP API."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPCookieProcessor, Request, build_opener


BASE_URL = "http://127.0.0.1:18081"
ACCOUNT_PREFIX = "demo-"
EDITIONS = {
    "esencial": "Esencial",
    "profesional": "Profesional",
    "integral": "Integral",
}
DEMO_ACCOUNTS = frozenset(f"{ACCOUNT_PREFIX}{edition}" for edition in EDITIONS)
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
SERVICE_TITLE = "Release HTTP smoke DEMO"


class SmokeFailure(RuntimeError):
    pass


class NoRedirectHandler(HTTPRedirectHandler):
    """Return redirect responses to the caller; never forward cookies or bodies."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class _CsrfParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.token: str | None = None

    def handle_starttag(self, tag, attrs):
        if tag != "input":
            return
        values = dict(attrs)
        if values.get("name") == "csrfmiddlewaretoken" and values.get("value"):
            self.token = values["value"]


def _csrf_from_html(html: str) -> str:
    parser = _CsrfParser()
    parser.feed(html)
    if not parser.token:
        raise SmokeFailure("El formulario de login no contiene un CSRF utilizable.")
    return parser.token


def _guard_base_url(base_url: str = BASE_URL) -> None:
    parsed = urlsplit(base_url)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.port != 18081:
        raise SmokeFailure("El smoke solo admite http://127.0.0.1:18081.")
    if parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise SmokeFailure("La URL del smoke no puede contener ruta, credenciales ni parámetros.")


def _safe_url(path: str) -> str:
    _guard_base_url()
    parsed = urlsplit(path)
    if not path.startswith("/") or path.startswith("//") or parsed.scheme or parsed.netloc or parsed.fragment:
        raise SmokeFailure("Ruta HTTP fuera del origen local permitido.")
    return f"{BASE_URL}{path}"


def _validated_redirect(location: str) -> str:
    if not isinstance(location, str) or not location or location.startswith("//"):
        raise SmokeFailure("La redirección HTTP no tiene un destino local válido.")
    supplied = urlsplit(location)
    if not supplied.scheme and not location.startswith("/"):
        raise SmokeFailure("La redirección HTTP debe usar una ruta absoluta local.")
    target = urljoin(f"{BASE_URL}/", location)
    parsed = urlsplit(target)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.port != 18081
        or parsed.username is not None
        or parsed.password is not None
        or not parsed.path.startswith("/")
    ):
        raise SmokeFailure("La redirección HTTP intentó salir del origen local permitido.")
    return target


def _guard_environment() -> str:
    if os.environ.get("CUADERNO_ENV") not in {"local", "test"}:
        raise SmokeFailure("CUADERNO_ENV debe ser local o test.")
    password = os.environ.get("CUADERNO_DEMO_PASSWORD")
    if not password or len(password) < 12:
        raise SmokeFailure("CUADERNO_DEMO_PASSWORD es obligatorio y debe tener al menos 12 caracteres.")
    return password


def _decimal(value, label: str) -> Decimal:
    if not isinstance(value, str):
        raise SmokeFailure(f"{label} no llegó como decimal textual.")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise SmokeFailure(f"{label} no es un decimal válido.") from exc
    if not parsed.is_finite():
        raise SmokeFailure(f"{label} no es finito.")
    return parsed


def _expect_decimal(payload: dict, key: str, expected: str) -> None:
    actual = _decimal(payload.get(key), key)
    if actual != Decimal(expected):
        raise SmokeFailure(f"{key} no coincide con el contrato DEMO.")


class HttpSession:
    def __init__(self):
        self.cookies = CookieJar()
        self.opener = build_opener(NoRedirectHandler(), HTTPCookieProcessor(self.cookies))

    def _csrf_cookie(self) -> str:
        for cookie in self.cookies:
            if cookie.name == "csrftoken" and cookie.value:
                return cookie.value
        raise SmokeFailure("La sesión autenticada no contiene cookie CSRF.")

    def request(self, method: str, path: str, *, payload=None, form=False, csrf=True, expected=(200,), accept="application/json"):
        headers = {"Accept": accept, "User-Agent": "Cuaderno-Release-Smoke/1"}
        body = None
        if payload is not None:
            if form:
                body = urlencode(payload).encode("utf-8")
                headers["Content-Type"] = "application/x-www-form-urlencoded"
            else:
                body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
                headers["Content-Type"] = "application/json"
        if csrf:
            headers["X-CSRFToken"] = self._csrf_cookie()
            headers["Referer"] = f"{BASE_URL}/"
        request = Request(_safe_url(path), data=body, headers=headers, method=method)
        try:
            response = self.opener.open(request, timeout=10)
        except HTTPError as exc:
            response = exc
        except (URLError, TimeoutError, OSError) as exc:
            raise SmokeFailure(f"No se pudo completar {method} {urlsplit(path).path}.") from exc
        try:
            data = response.read(MAX_RESPONSE_BYTES + 1)
            status = response.status
            content_type = response.headers.get_content_type()
            redirect_location = response.headers.get("Location")
        finally:
            response.close()
        if len(data) > MAX_RESPONSE_BYTES:
            raise SmokeFailure(f"Respuesta demasiado grande en {method} {urlsplit(path).path}.")
        if 300 <= status < 400:
            if status != 302 or status not in expected:
                raise SmokeFailure(f"Redirección HTTP {status} no permitida en {method} {urlsplit(path).path}.")
            _validated_redirect(redirect_location)
        if status not in expected:
            raise SmokeFailure(f"Estado HTTP {status} inesperado en {method} {urlsplit(path).path}.")
        return status, content_type, data

    def text(self, method: str, path: str, **kwargs) -> str:
        _, _, body = self.request(method, path, **kwargs)
        return body.decode("utf-8", errors="strict")

    def json(self, method: str, path: str, **kwargs):
        _, content_type, body = self.request(method, path, **kwargs)
        if content_type != "application/json":
            raise SmokeFailure(f"{method} {urlsplit(path).path} no devolvió JSON.")
        try:
            return json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SmokeFailure(f"JSON inválido en {method} {urlsplit(path).path}.") from exc

    def login(self, username: str, password: str) -> None:
        if username not in DEMO_ACCOUNTS:
            raise SmokeFailure("El smoke solo admite las tres cuentas DEMO fijadas.")
        html = self.text("GET", "/accounts/login/", csrf=False, accept="text/html")
        token = _csrf_from_html(html)
        self.request(
            "POST",
            "/accounts/login/",
            payload={"csrfmiddlewaretoken": token, "login": username, "password": password},
            form=True,
            csrf=False,
            accept="text/html",
            expected=(302,),
        )

    def logout(self) -> None:
        self.request("GET", "/accounts/logout/", csrf=False, accept="text/html", expected=(302,))
        self.request("GET", "/api/cuaderno/edition/", csrf=False, expected=(401, 403))


def _items(payload) -> list:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        return payload["results"]
    raise SmokeFailure("La API de lista no devolvió una colección reconocible.")


def _check_account(session: HttpSession, edition: str, title: str, password: str, confirm_service: bool) -> dict:
    session.login(f"{ACCOUNT_PREFIX}{edition}", password)

    edition_payload = session.json("GET", "/api/cuaderno/edition/", csrf=False)
    if not isinstance(edition_payload, dict) or edition_payload.get("edition") != edition:
        raise SmokeFailure(f"La cuenta DEMO no está en la edición {edition}.")

    memberships = _items(session.json("GET", "/api/user-space/all_personal/", csrf=False))
    active = [row for row in memberships if isinstance(row, dict) and row.get("active") is True]
    if len(active) != 1 or not isinstance(active[0].get("space"), int):
        raise SmokeFailure("La cuenta DEMO debe tener exactamente un Space activo.")
    space = session.json("GET", f"/api/space/{active[0]['space']}/", csrf=False)
    if not isinstance(space, dict) or space.get("name") != f"Cuaderno {title} DEMO":
        raise SmokeFailure("El Space activo no es el sintético esperado.")

    query = urlencode({"query": "Salsa DEMO", "page_size": "50"})
    recipes = [
        row for row in _items(session.json("GET", f"/api/recipe/?{query}", csrf=False))
        if isinstance(row, dict) and row.get("name") == "Salsa DEMO"
    ]
    if len(recipes) != 1 or not isinstance(recipes[0].get("id"), int):
        raise SmokeFailure("Salsa DEMO no es visible de forma unívoca para su cuenta.")
    recipe_id = recipes[0]["id"]

    cost = session.json("GET", f"/api/cuaderno/recipes/{recipe_id}/cost/?servings=4", csrf=False)
    if not isinstance(cost, dict) or cost.get("status") != "complete":
        raise SmokeFailure("El coste DEMO no está completo.")
    _expect_decimal(cost, "total", "2.56")
    _expect_decimal(cost, "per_serving", "0.64")

    result = {"recipes": len(recipes), "cost": "ok", "finance": "not_applicable", "service": "not_requested"}
    if edition != "esencial":
        finance_path = f"/api/cuaderno/recipes/{recipe_id}/finance/?servings=4"
        requested = {"selling_price_per_serving": "1.25", "budget_per_person": "1"}
        saved = session.json("PUT", finance_path, payload=requested)
        if not isinstance(saved, dict) or not isinstance(saved.get("finance"), dict):
            raise SmokeFailure("La escritura financiera no devolvió su contrato.")
        finance = saved["finance"]
        _expect_decimal(finance, "ingredient_cost_per_serving", "0.64")
        _expect_decimal(finance, "difference_per_serving", "0.61")
        _expect_decimal(finance, "food_cost_ratio", "0.512")

        persisted = session.json("GET", finance_path, csrf=False)
        if persisted.get("finance") != finance:
            raise SmokeFailure("Los datos financieros no persistieron sin cambios.")

        session.request("PUT", finance_path, payload={"selling_price_per_serving": "9", "budget_per_person": "9"}, csrf=False, expected=(403,))
        after_rejected = session.json("GET", finance_path, csrf=False)
        if after_rejected.get("finance") != finance:
            raise SmokeFailure("Una escritura sin CSRF alteró los datos financieros.")
        result["finance"] = "persisted_csrf_protected"

        if confirm_service:
            service = _confirmed_service(session, recipe_id, finance)
            if service.get("snapshot", {}).get("finance") != finance:
                raise SmokeFailure("El servicio no congeló el contrato financiero vigente.")
            result["service"] = "confirmed_snapshot_frozen"

    session.logout()
    return result


def _confirmed_service(session: HttpSession, recipe_id: int, finance: dict) -> dict:
    services = [
        row for row in _items(session.json("GET", "/api/cuaderno/services/", csrf=False))
        if isinstance(row, dict) and row.get("title") == SERVICE_TITLE
    ]
    if len(services) > 1:
        raise SmokeFailure("Hay más de un servicio de smoke con el nombre reservado.")
    if services:
        service = services[0]
    else:
        service = session.json(
            "POST",
            "/api/cuaderno/services/",
            payload={
                "recipe": recipe_id,
                "covers": "4",
                "service_date": (date.today() + timedelta(days=1)).isoformat(),
                "title": SERVICE_TITLE,
            },
            expected=(201,),
        )
    service_id = service.get("id")
    if not isinstance(service_id, int):
        raise SmokeFailure("El servicio de smoke no devolvió identificador.")
    detail_path = f"/api/cuaderno/services/{service_id}/"
    detail = session.json("GET", detail_path, csrf=False)
    if detail.get("state") == "draft":
        detail = session.json("POST", detail_path, payload={"action": "confirm"})
    if detail.get("state") != "confirmed":
        raise SmokeFailure("El servicio de smoke no está confirmado.")
    if detail.get("snapshot", {}).get("finance") != finance:
        raise SmokeFailure("El snapshot financiero confirmado no coincide.")
    reread = session.json("GET", detail_path, csrf=False)
    if reread.get("snapshot", {}).get("finance") != finance:
        raise SmokeFailure("El snapshot financiero cambió al releerlo.")
    return reread


def run(*, confirm_service: bool = False) -> dict:
    _guard_base_url()
    password = _guard_environment()
    ready = HttpSession().json("GET", "/health/ready/", csrf=False)
    if not isinstance(ready, dict) or ready.get("ready") is not True:
        raise SmokeFailure("Readiness no confirma aplicación y BD disponibles.")

    editions = {}
    for edition, title in EDITIONS.items():
        editions[edition] = _check_account(HttpSession(), edition, title, password, confirm_service)
    return {
        "ready": True,
        "accounts_checked": len(editions),
        "finance_writes": sum(row["finance"] == "persisted_csrf_protected" for row in editions.values()),
        "services_confirmed": sum(row["service"] == "confirmed_snapshot_frozen" for row in editions.values()),
        "editions": editions,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-service", action="store_true", help="Crea/reutiliza y confirma un servicio DEMO por edición compatible.")
    args = parser.parse_args(argv)
    try:
        result = run(confirm_service=args.confirm_service)
    except SmokeFailure as exc:
        print(f"CUADERNO_RELEASE_HTTP_SMOKE ERROR: {exc}", file=sys.stderr)
        return 1
    print("CUADERNO_RELEASE_HTTP_SMOKE " + json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
