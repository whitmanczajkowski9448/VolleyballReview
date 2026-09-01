from http.cookies import SimpleCookie
from urllib.parse import unquote, urlsplit, urlunsplit

import requests
import streamlit as st
from requests.cookies import RequestsCookieJar


BASE_URL = "https://filmroom.dvsport360.com"
GET_SAS_URL = f"{BASE_URL}/VideoPlayer/GetSasUrl"


def clean_text(value):
    if value is None:
        return ""
    return str(value).strip()


def standard_headers():
    return {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/152.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": BASE_URL,
        "Referer": f"{BASE_URL}/",
        "X-Requested-With": "XMLHttpRequest",
    }


def cookiejar_from_header(cookie_header):
    cookie_header = clean_text(cookie_header)
    if not cookie_header:
        raise RuntimeError("DVSPORT_COOKIE is blank.")

    jar = RequestsCookieJar()
    parsed = SimpleCookie()
    parsed.load(cookie_header)

    if not parsed:
        raise RuntimeError("DVSPORT_COOKIE could not be parsed.")

    for key, morsel in parsed.items():
        jar.set(
            key,
            morsel.value,
            domain="filmroom.dvsport360.com",
            path="/",
        )

    return jar


def make_session(cookie_header):
    session = requests.Session()
    session.headers.update(standard_headers())
    session.cookies.update(cookiejar_from_header(cookie_header))
    return session


def is_dvsport_blob_url(value):
    url = clean_text(value).lower()
    if not url.startswith(("http://", "https://")):
        return False

    return (
        "blob.core.windows.net" in url
        and ("dvsport" in url or "wvb-clips" in url)
    )


def raw_dvsport_blob_url(value):
    """
    Convert either a raw DV Sport blob URL or an existing signed SAS URL
    back to the stable raw URL FilmRoom submits to GetSasUrl.
    """
    url = clean_text(value)
    if not url:
        return ""

    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return url

    decoded_path = unquote(parts.path)

    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            decoded_path,
            "",
            "",
        )
    )


def request_sas_url(cookie_header, media_url):
    """
    Mirror FilmRoom exactly:
      POST /VideoPlayer/GetSasUrl
      form field: url=<raw blob URL>
    """
    media_url = clean_text(media_url)
    if not media_url:
        raise RuntimeError("Cannot request a SAS URL for a blank media URL.")

    if not is_dvsport_blob_url(media_url):
        return media_url

    raw_url = raw_dvsport_blob_url(media_url)
    session = make_session(cookie_header)

    response = session.post(
        GET_SAS_URL,
        data={"url": raw_url},
        timeout=60,
        allow_redirects=False,
    )

    if response.status_code in (301, 302, 303, 307, 308):
        raise RuntimeError(
            "DV Sport redirected GetSasUrl. DVSPORT_COOKIE is probably expired."
        )

    if response.status_code != 200:
        raise RuntimeError(
            f"GetSasUrl returned HTTP {response.status_code}: {response.text[:250]}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError("GetSasUrl did not return JSON.") from exc

    if not data.get("Success"):
        raise RuntimeError("DV Sport could not create a SAS URL.")

    signed_url = clean_text(data.get("Url") or data.get("url"))
    if not signed_url:
        raise RuntimeError("DV Sport reported success but returned no URL.")

    return signed_url


@st.cache_data(ttl=1800, show_spinner=False)
def _cached_sas_url(media_url):
    """
    Refresh at most every 30 minutes. The captured FilmRoom SAS URLs are
    valid for several days, so this avoids excessive signing requests.
    """
    cookie_header = clean_text(st.secrets.get("DVSPORT_COOKIE", ""))
    return request_sas_url(cookie_header, media_url)


def fresh_video_url(media_url):
    media_url = clean_text(media_url)
    if not media_url:
        return ""

    if not is_dvsport_blob_url(media_url):
        return media_url

    return _cached_sas_url(media_url)
