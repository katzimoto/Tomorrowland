# Preview worker image: the backend runtime plus LibreOffice headless, used to
# convert Office documents (DOCX/PPTX/…) to PDF preview artifacts (#539).
#
# Built FROM the already-built backend image so it shares the Python runtime
# and application code; only the soffice + font layer is extra. Keeping
# LibreOffice out of the base image means only this one worker carries the
# ~400 MB cost.
ARG TOMORROWLAND_BACKEND_IMAGE=tomorrowland/backend:airgap
FROM ${TOMORROWLAND_BACKEND_IMAGE} AS preview-worker

USER root

# libreoffice-core + the writer/impress/calc filters cover DOCX/PPTX/XLSX/ODF
# conversion. Liberation + DejaVu fonts give sane substitutions for common
# Office fonts so air-gapped conversion never reaches for a network font.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libreoffice-writer-nogui \
        libreoffice-impress-nogui \
        libreoffice-calc-nogui \
        fonts-liberation \
        fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*

USER appuser

CMD ["tomorrowland-preview-worker"]
