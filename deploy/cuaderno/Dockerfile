FROM node:24.21.0-bookworm-slim@sha256:2fe369e969550cde8e867afc3fe370b260140cab4a23d467074295b42163d553 AS frontend
WORKDIR /build/vue3
COPY vue3/package.json vue3/yarn.lock ./
RUN yarn install --frozen-lockfile --non-interactive
COPY vue3/ ./
COPY cookbook/locale/ /build/cookbook/locale/
COPY scripts/cuaderno/frontend_inventory.mjs /build/scripts/cuaderno/frontend_inventory.mjs
# Capture the exact installed build/dev tree that produced this bundle.
# This is not a claim that every dependency is present in the bundled JS.
RUN yarn build && node /build/scripts/cuaderno/frontend_inventory.mjs > /build/frontend-installed.cdx.json

# Rebuild dependencies from the repository, without an opaque local pin image.
FROM python:3.13-alpine3.23@sha256:6438599575cca0d1df94aeee0d2ae088d4d8846eab554b2ee7784a3a6df0d516 AS python_dependencies
WORKDIR /opt/recipes
RUN apk add --no-cache gcc musl-dev postgresql-dev zlib-dev jpeg-dev libwebp-dev openssl-dev libffi-dev cargo openldap-dev python3-dev xmlsec-dev xmlsec build-base g++ curl rust libxml2-dev libxslt-dev
COPY requirements.txt /tmp/all-requirements.txt
COPY scripts/cuaderno/patch_oauthlib.py /tmp/patch_oauthlib.py
COPY tooling/cuaderno/python-production.constraints.txt /tmp/production.constraints.txt
COPY scripts/cuaderno/python_lock.py /tmp/python_lock.py
RUN sed '/# Development/,$d' /tmp/all-requirements.txt > /tmp/production-requirements.txt \
    && python -m venv venv \
    && venv/bin/pip install --no-cache-dir -c /tmp/production.constraints.txt pip setuptools wheel setuptools-rust \
    && venv/bin/pip install --no-cache-dir -c /tmp/production.constraints.txt -r /tmp/production-requirements.txt \
    && venv/bin/pip check \
    && venv/bin/python /tmp/python_lock.py --constraints /tmp/production.constraints.txt --requirements /tmp/production-requirements.txt --installed \
    && venv/bin/python /tmp/patch_oauthlib.py

FROM python:3.13-alpine3.23@sha256:6438599575cca0d1df94aeee0d2ae088d4d8846eab554b2ee7784a3a6df0d516 AS runtime
RUN apk add --no-cache postgresql-libs postgresql-client gettext zlib libjpeg libwebp libxml2-dev libxslt-dev openldap libgcc libstdc++ nginx tini envsubst
WORKDIR /opt/recipes
COPY --from=python_dependencies /opt/recipes/venv /opt/recipes/venv
COPY cookbook/ ./cookbook/
COPY recipes/ ./recipes/
COPY cuaderno/ ./cuaderno/
COPY http.d/ ./http.d/
COPY manage.py boot.sh plugin.py requirements.txt LICENSE.md ./
COPY tooling/cuaderno/python-production.constraints.txt ./PYTHON-PRODUCTION.constraints.txt
COPY --from=frontend /build/cookbook/static/vue3/ ./cookbook/static/vue3/
COPY --from=frontend /build/frontend-installed.cdx.json ./SBOM.frontend.cdx.json
ARG SOURCE_COMMIT=worktree
ENV PYTHONUNBUFFERED=1 DOCKER=true PATH=/opt/recipes/venv/bin:$PATH
RUN python -c "from pathlib import Path; Path('cookbook/version_info.py').write_text('TANDOOR_VERSION = \"2.6.15-cuaderno\"\nTANDOOR_REF = \"${SOURCE_COMMIT}\"\nVERSION_INFO = []\n')" \
    && sed -i 's/\r$//' boot.sh http.d/*.template \
    && chmod +x boot.sh \
    && mkdir -p mediafiles staticfiles \
    && find /etc/nginx/http.d -maxdepth 1 -type f -delete \
    && ln -s /opt/recipes/http.d/Recipes.conf /etc/nginx/http.d/Recipes.conf \
    && chmod 1777 http.d \
    && ln -sf /dev/stdout /var/log/nginx/access.log \
    && ln -sf /dev/stderr /var/log/nginx/error.log
EXPOSE 80
ENTRYPOINT ["/sbin/tini", "--", "/opt/recipes/boot.sh"]
