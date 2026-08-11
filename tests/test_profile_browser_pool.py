from app.browser.profile_pool import normalize_cookies


def test_normalize_cookies_uses_platform_domain_and_playwright_types():
    cookies = normalize_cookies([
        {
            "name": "li_at",
            "value": "secret",
            "expires": "1999999999",
            "sameSite": "lax",
            "secure": 1,
        },
        {"value": "missing-name"},
    ], "linkedin")

    assert cookies == [{
        "name": "li_at",
        "value": "secret",
        "domain": ".linkedin.com",
        "path": "/",
        "secure": True,
        "expires": 1999999999.0,
        "sameSite": "Lax",
    }]
