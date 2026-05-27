from __future__ import annotations

"""Pre-install Argos Translate language packages into the LibreTranslate image.

Run during Docker build (connected environment) to bundle required translation
models. The packages are stored in $HOME/.local/share/argos-translate/packages
so they are pre-populated into the libretranslate_data named volume on first
container creation — no internet access required at runtime.

Required pairs: all supported non-English languages must translate to and from
English. Direct non-English-to-non-English pairs use LibreTranslate's English
pivot at runtime.

RC supported languages: en, he, zh, ko, th, ar, fr, ru, es.
Chinese support means Chinese Simplified (zh) only.
"""

import sys

import argostranslate.package

REQUIRED_PAIRS: list[tuple[str, str]] = [
    ("ar", "en"),
    ("en", "ar"),
    ("fr", "en"),
    ("en", "fr"),
    ("ru", "en"),
    ("en", "ru"),
    ("es", "en"),
    ("en", "es"),
    ("zh", "en"),
    ("en", "zh"),
    ("ko", "en"),
    ("en", "ko"),
    ("th", "en"),
    ("en", "th"),
    ("he", "en"),
    ("en", "he"),
]


def main() -> None:
    print("Updating Argos Translate package index (requires internet at build time)...")
    try:
        argostranslate.package.update_package_index()
    except Exception as exc:  # pragma: no cover
        print(f"ERROR: could not update Argos package index: {exc}", file=sys.stderr)
        sys.exit(1)

    available: dict[tuple[str, str], argostranslate.package.AvailablePackage] = {
        (p.from_code, p.to_code): p
        for p in argostranslate.package.get_available_packages()
    }

    missing_required: list[tuple[str, str]] = []

    for pair in REQUIRED_PAIRS:
        pkg = available.get(pair)
        if pkg is None:
            print(
                f"ERROR: required package {pair[0]}->{pair[1]} not found in Argos index",
                file=sys.stderr,
            )
            missing_required.append(pair)
        else:
            print(f"Installing {pair[0]}->{pair[1]} ...")
            try:
                pkg.install()
            except Exception as exc:  # pragma: no cover
                print(
                    f"ERROR: failed to install {pair[0]}->{pair[1]}: {exc}",
                    file=sys.stderr,
                )
                missing_required.append(pair)

    if missing_required:
        print(
            f"Build failed: required language packages not available: {missing_required}",
            file=sys.stderr,
        )
        sys.exit(1)

    print("Translation language pack installation complete.")


if __name__ == "__main__":
    main()
