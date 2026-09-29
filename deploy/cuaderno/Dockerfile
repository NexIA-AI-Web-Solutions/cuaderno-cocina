FROM node:24.21.0-bookworm-slim@sha256:2fe369e969550cde8e867afc3fe370b260140cab4a23d467074295b42163d553 AS frontend
WORKDIR /build/vue3
COPY vue3/package.json vue3/yarn.lock ./
RUN yarn install --frozen-lockfile --non-interactive
COPY vue3/ ./
COPY cookbook/locale/ /build/cookbook/locale/
RUN yarn build

# Rebuild dependencies from the repository, without an opaque local pin image.
FROM python:3.13-alpine3.23@sha256:6438599575cca0d1df94aeee0d2ae088d4d8846eab554b2ee7784a3a6df0d516 AS python_dependencies
WORKDIR /opt/recipes
RUN apk add --no-cache gcc musl-dev postgresql-dev zlib-dev jpeg-dev libwebp-dev openssl-dev libffi-dev cargo openldap-dev python3-dev xmlsec-dev xmlsec build-base g++ curl rust libxml2-dev libxslt-dev
COPY requirements.txt /tmp/all-requirements.txt
COPY scripts/cuaderno/patch_oauthlib.py /tmp/patch_oauthlib.py
RUN sed '/# Development/,$d' /tmp/all-requirements.txt > /tmp/production-requirements.txt \
    && python -m venv venv \
    && venv/bin/pip install --no-cache-dir wheel==0.46.2 setuptools_rust==1.10.2 \
    && venv/bin/pip install --no-cache-dir -r /tmp/production-requirements.txt \
    && venv/bin/pip check \
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
COPY --from=frontend /build/cookbook/static/vue3/ ./cookbook/static/vue3/
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
