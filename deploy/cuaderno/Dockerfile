FROM node:24.21.0-bookworm-slim@sha256:0e0ff40c39bc087845bfb27465a0df4ea419520094bc35842ff83dd8cbe6f9b6 AS frontend
WORKDIR /build/vue3
COPY vue3/package.json vue3/yarn.lock ./
RUN yarn install --frozen-lockfile --non-interactive
COPY vue3/ ./
COPY cookbook/locale/ /build/cookbook/locale/
COPY scripts/cuaderno/frontend_inventory.mjs scripts/cuaderno/frontend_build_provenance.mjs /build/scripts/cuaderno/
# Capture the exact installed build/dev tree that produced this bundle.
# This is not a claim that every dependency is present in the bundled JS.
RUN yarn build && node /build/scripts/cuaderno/frontend_inventory.mjs > /build/frontend-installed.cdx.json

# Rebuild dependencies from the repository, without an opaque local pin image.
FROM python:3.13.16-alpine3.23@sha256:ddf0307d17965eaf98dc5e366bd41ba6e10e4b32164c2bfd258cd9e367b60146 AS python_dependencies
WORKDIR /opt/recipes
RUN apk add --no-cache gcc musl-dev postgresql-dev zlib-dev jpeg-dev libwebp-dev openssl-dev libffi-dev cargo openldap-dev python3-dev xmlsec-dev xmlsec build-base g++ curl rust libxml2-dev libxslt-dev
COPY requirements.txt /tmp/all-requirements.txt
COPY tooling/cuaderno/python-production.constraints.txt /tmp/production.constraints.txt
COPY scripts/cuaderno/python_lock.py /tmp/python_lock.py
COPY scripts/cuaderno/prune_node_build_tools.py /tmp/prune_node_build_tools.py
RUN sed '/# Development/,$d' /tmp/all-requirements.txt > /tmp/production-requirements.txt \
    && python -m venv venv \
    && venv/bin/pip install --no-cache-dir -c /tmp/production.constraints.txt pip setuptools wheel setuptools-rust \
    && venv/bin/pip install --no-cache-dir -c /tmp/production.constraints.txt -r /tmp/production-requirements.txt \
    && venv/bin/pip check \
    && venv/bin/python /tmp/python_lock.py --constraints /tmp/production.constraints.txt --requirements /tmp/production-requirements.txt --installed \
    && venv/bin/python /tmp/prune_node_build_tools.py
COPY scripts/cuaderno/python_sbom.py /tmp/python_sbom.py
ARG SOURCE_COMMIT
RUN venv/bin/python /tmp/python_sbom.py --constraints /tmp/production.constraints.txt --source-identity "$SOURCE_COMMIT" --output /opt/recipes/SBOM.python.cdx.json

FROM python:3.13.16-alpine3.23@sha256:ddf0307d17965eaf98dc5e366bd41ba6e10e4b32164c2bfd258cd9e367b60146 AS runtime
RUN apk add --no-cache postgresql-libs postgresql-client gettext zlib libjpeg libwebp libxml2 libxslt openldap libgcc libstdc++ nginx tini envsubst nodejs=24.18.1-r0 ada-libs=3.3.0-r0 nghttp2-libs=1.69.0-r0 pax-utils
WORKDIR /opt/recipes
# This named context is built and verified from docker/runtime-security by
# local_up.py and CI. Install the packages themselves before binding their proof.
COPY --from=runtime_security /packages /tmp/security-apks/packages
COPY --from=runtime_security /SECURITY.alpine-backports.json ./SECURITY.alpine-backports.json
RUN apk add --no-network --allow-untrusted /tmp/security-apks/packages/*/*/zlib-1.3.2-r1.apk \
    /tmp/security-apks/packages/*/*/busybox-1.37.0-r31.apk \
    /tmp/security-apks/packages/*/*/busybox-binsh-1.37.0-r31.apk \
    /tmp/security-apks/packages/*/*/ssl_client-1.37.0-r31.apk \
    && python -c "import hashlib,json; from pathlib import Path; p=json.loads(Path('SECURITY.alpine-backports.json').read_text()); assert p['verified'] is True; assert all(hashlib.sha256(Path(f).read_bytes()).hexdigest()==s for f,s in p['runtime_files'].items())" \
    && rm -r /tmp/security-apks
COPY --from=python_dependencies /opt/recipes/venv /opt/recipes/venv
COPY --from=python_dependencies /opt/recipes/SBOM.python.cdx.json ./SBOM.python.cdx.json
COPY cookbook/ ./cookbook/
COPY recipes/ ./recipes/
COPY cuaderno/ ./cuaderno/
COPY http.d/ ./http.d/
COPY manage.py boot.sh plugin.py requirements.txt LICENSE.md ./
COPY tooling/cuaderno/python-production.constraints.txt ./PYTHON-PRODUCTION.constraints.txt
COPY tooling/cuaderno/python-test.constraints.txt ./PYTHON-TEST.constraints.txt
COPY scripts/cuaderno/release_runtime_check.py scripts/cuaderno/python_lock.py scripts/cuaderno/release_manifest.py ./release-tools/
COPY scripts/cuaderno/process_supervisor.py ./release-tools/
COPY scripts/cuaderno/runtime_application.py ./release-tools/
COPY scripts/cuaderno/frontend_assets.py ./release-tools/
COPY scripts/cuaderno/patch_runtime_security.py ./release-tools/
COPY scripts/cuaderno/patch_tempfile_security.py ./release-tools/
COPY tooling/cuaderno/cpython-tempfile-security/ /tmp/cuaderno-tempfile-security/
COPY scripts/cuaderno/bind_system_node.py ./release-tools/
RUN venv/bin/python release-tools/bind_system_node.py --output /opt/recipes/SECURITY.node-runtime.json \
    && apk del pax-utils \
    && apk info -e 'nodejs=24.18.1-r0'
RUN python -c "import sys,json; from pathlib import Path; sys.path.insert(0, 'release-tools'); from patch_runtime_security import patch_poplib; Path('SECURITY.python-backports.json').write_text(json.dumps(patch_poplib(Path('/usr/local/lib/python3.13/poplib.py')), sort_keys=True)+'\n')"
RUN python -c "import sys,json; from pathlib import Path; sys.path.insert(0, 'release-tools'); from patch_tempfile_security import patch_stdlib_pair; Path('SECURITY.tempfile-backport.json').write_text(json.dumps(patch_stdlib_pair(Path('/usr/local/lib/python3.13'), source_directory=Path('/tmp/cuaderno-tempfile-security')), sort_keys=True)+'\n')" \
    && cp /tmp/cuaderno-tempfile-security/LICENSE /opt/recipes/LICENSE.cpython-tempfile-backport \
    && rm -r /tmp/cuaderno-tempfile-security
COPY --from=frontend /build/cookbook/static/vue3/ ./cookbook/static/vue3/
COPY --from=frontend /build/frontend-installed.cdx.json ./SBOM.frontend.cdx.json
ARG SOURCE_COMMIT
LABEL io.cuaderno.source-identity="${SOURCE_COMMIT}"
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DOCKER=true PATH=/opt/recipes/venv/bin:$PATH
RUN python -c "import re; assert re.fullmatch(r'[0-9a-f]{40}(?:\\+worktree\\.[0-9a-f]{64})?', '${SOURCE_COMMIT}'), 'SOURCE_COMMIT must identify exact sources'; from pathlib import Path; Path('cookbook/version_info.py').write_text('TANDOOR_VERSION = \"2.6.15-cuaderno\"\nTANDOOR_REF = \"${SOURCE_COMMIT}\"\nVERSION_INFO = []\n')" \
    && sed -i 's/\r$//' boot.sh http.d/*.template \
    && chmod 0755 boot.sh \
    && mkdir -p mediafiles staticfiles \
    && find /etc/nginx/http.d -maxdepth 1 -type f -delete \
    && ln -s /opt/recipes/http.d/Recipes.conf /etc/nginx/http.d/Recipes.conf \
    && addgroup -g 10001 cuaderno && adduser -D -u 10001 -G cuaderno cuaderno \
    && mkdir -p /var/lib/nginx /var/tmp/nginx /run/nginx \
    && chown -R cuaderno:cuaderno /opt/recipes/http.d /opt/recipes/mediafiles /opt/recipes/staticfiles /var/lib/nginx /var/tmp/nginx /run/nginx \
    && ln -sf /dev/stdout /var/log/nginx/access.log \
    && ln -sf /dev/stderr /var/log/nginx/error.log \
    && venv/bin/python release-tools/runtime_application.py --root /opt/recipes --output runtime-application-manifest.json \
    && venv/bin/python release-tools/release_manifest.py --root /opt/recipes --source-identity "$SOURCE_COMMIT" --output RELEASE-MANIFEST.json
EXPOSE 80
USER 10001:10001
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 CMD python -c "import json, urllib.request; assert json.load(urllib.request.urlopen('http://127.0.0.1/health/ready/', timeout=3))['ready'] is True"
ENTRYPOINT ["/sbin/tini", "--", "/opt/recipes/boot.sh"]
