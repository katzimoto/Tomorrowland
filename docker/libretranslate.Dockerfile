# LibreTranslate with pre-installed Argos Translate language packs.
#
# Build this image in a connected environment; the resulting image contains all
# required translation models so the air-gapped target host needs no internet
# access to start the translation service.
#
# Pinned base image: reproducible across connected and air-gapped builds.
FROM libretranslate/libretranslate:v1.6.3

# Switch to root so we can write into /home/libretranslate/.local during build.
USER root

# Copy and run the package-installation script.
# Packages are installed to /home/libretranslate/.local/share/argos-translate/packages
# (resolved via HOME below). The libretranslate_data named volume is mounted at
# /home/libretranslate/.local; Docker copies this directory from the image into an
# empty named volume on first container creation, making all models available
# without runtime network access.
COPY docker/install-translation-packs.py /tmp/install-translation-packs.py
# argostranslate is installed in the base image's virtual environment and is
# not importable by bare python3 running as root; install it system-wide first.
RUN pip3 install --no-cache-dir "argostranslate>=1.9.1,<2" \
    && HOME=/home/libretranslate python3 /tmp/install-translation-packs.py \
    && rm /tmp/install-translation-packs.py \
    && { chown -R libretranslate:libretranslate /home/libretranslate/.local 2>/dev/null || true; }

# Prevent automatic package updates at startup; all required models are bundled.
ENV LT_UPDATE_PACKAGES=false
