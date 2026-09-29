import socket
import requests
import struct
from ipaddress import ip_address
from urllib.parse import urlparse, quote, urlunparse

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db.models import Func
from thefuzz import fuzz
from thefuzz import process as fuzz_process
from requests_hardened import Config, Manager


class Round(Func):
    function = 'ROUND'
    template = '%(function)s(%(expressions)s, 0)'


def str2bool(v):
    if isinstance(v, bool) or v is None:
        return v
    else:
        return v.lower() in ("yes", "true", "1")


DEFAULT_MAX_RESPONSE_BYTES = 10 * 1024 * 1024
DEFAULT_RESPONSE_CHUNK_SIZE = 64 * 1024


def safe_request(
    method,
    url,
    *,
    max_response_bytes=DEFAULT_MAX_RESPONSE_BYTES,
    response_chunk_size=DEFAULT_RESPONSE_CHUNK_SIZE,
    **kwargs,
):
    """
    Use requests-hardened to make external requests SSRF safe and keep the
    response body within a fixed in-memory limit.

    The body is buffered before the underlying stream is closed so existing
    callers can continue using ``response.content`` and ``response.json()``.
    """
    if (
        isinstance(max_response_bytes, bool)
        or not isinstance(max_response_bytes, int)
        or max_response_bytes <= 0
        or isinstance(response_chunk_size, bool)
        or not isinstance(response_chunk_size, int)
        or response_chunk_size <= 0
    ):
        raise ValueError("Response limits must be positive integers")

    http_manager = Manager(
        Config(
            default_timeout=(2, 10),
            never_redirect=False,
            # Enable SSRF IP filter
            ip_filter_enable=True,
            ip_filter_allow_loopback_ips=False,
        )
    )
    kwargs["stream"] = True
    response = http_manager.send_request(method, url, **kwargs)
    try:
        content_length = response.headers.get("Content-Length")
        if content_length is not None:
            try:
                if int(content_length) > max_response_bytes:
                    raise ValidationError("External response exceeds the allowed size")
            except ValueError:
                # An invalid or attacker-controlled header is not trusted; the
                # streamed byte counter below remains authoritative.
                pass

        chunks = []
        received = 0
        for chunk in response.iter_content(chunk_size=response_chunk_size):
            if not chunk:
                continue
            received += len(chunk)
            if received > max_response_bytes:
                raise ValidationError("External response exceeds the allowed size")
            chunks.append(chunk)

        response._content = b"".join(chunks)
        response._content_consumed = True
        return response
    finally:
        response.close()


def match_or_fuzzymatch(check_string: str, key_dict: dict) -> tuple[str, int]:
    """
    takes a string and sees if it matches exactly any of the Dictionary keys
    or any of the alternative strings listed in the value of each key.
    If there are no matches return the key of the string that returns the best fuzzy match against your check_string.

    :param check_string: A string that you want to attempt to match
    :param key_dict: key: exact terms you are searching for, value:a list of strings that are alternative terms to check.
    :return:
    """
    score = (None, 0)
    for key in key_dict:
        key_dict[key].append(key)
        if check_string.lower() in [match.lower() for match in key_dict[key]]:
            return (key, 100)
    for key in key_dict:
        key_score = fuzz_process.extract(check_string, key_dict[key], limit=1, scorer=fuzz.partial_token_sort_ratio)[0]
        if key_score[1] > score[1]:
            score = (key, key_score[1])
    return score
