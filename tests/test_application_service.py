from services.application_service import (
    is_supported_application_url,
)


def test_supported_host():
    assert is_supported_application_url(
        "https://boards.greenhouse.io/example/jobs/123"
    )


def test_unsupported_host():
    assert not is_supported_application_url(
        "https://example.com/jobs/123"
    )
