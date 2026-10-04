#!/bin/sh
set -eu

export PACKAGER="Cuaderno Cocina reproducible security build <security@invalid.local>"
export REPODEST=/out/packages
export SRCDEST=/var/cache/distfiles
export JOBS="${JOBS:-$(getconf _NPROCESSORS_ONLN)}"
export SOURCE_DATE_EPOCH=1790981383
export PACKAGER_PRIVKEY=/home/builder/.abuild/cuaderno-reproducible.rsa

install -d -o builder -g builder "$REPODEST" "$SRCDEST" /out/corresponding-source
cp -a /runtime-security/aports /home/builder/aports
install -d -m 700 -o builder -g builder /home/builder/.abuild
install -m 600 -o builder -g builder /runtime-security/keys/cuaderno-reproducible.rsa "$PACKAGER_PRIVKEY"
install -m 644 -o builder -g builder /runtime-security/keys/cuaderno-reproducible.rsa.pub "$PACKAGER_PRIVKEY.pub"
install -m 644 /runtime-security/keys/cuaderno-reproducible.rsa.pub /etc/apk/keys/cuaderno-reproducible.rsa.pub
chown -R builder:builder /home/builder/aports "$REPODEST" "$SRCDEST"
su builder -c 'cd /home/builder/aports/main/zlib && abuild -r'
sh /runtime-security/tests/test-zlib-cve.sh
su builder -c 'cd /home/builder/aports/main/busybox && abuild -r'

cp -a /home/builder/aports /out/corresponding-source/
cp -a "$SRCDEST" /out/corresponding-source/distfiles
cp /runtime-security/Dockerfile /runtime-security/build.sh /runtime-security/verify.sh \
  /runtime-security/PROVENANCE.md /runtime-security/source-inputs.json /out/corresponding-source/
cp -a /runtime-security/tests /runtime-security/keys /out/corresponding-source/
one_apk_sha() {
  spec="$1"
  set -- $(find "$REPODEST" -type f -name "$spec.apk")
  [ "$#" -eq 1 ] || { echo "expected one $spec.apk" >&2; exit 1; }
  sha256sum "$1" | cut -d' ' -f1
}
busybox_apk_sha=$(one_apk_sha busybox-1.37.0-r31)
busybox_binsh_apk_sha=$(one_apk_sha busybox-binsh-1.37.0-r31)
ssl_client_apk_sha=$(one_apk_sha ssl_client-1.37.0-r31)
zlib_apk_sha=$(one_apk_sha zlib-1.3.2-r1)
source_inputs_sha=$(sha256sum /runtime-security/source-inputs.json | cut -d' ' -f1)
cat >/out/SECURITY.alpine-backports.json <<EOF
{"schema_version":1,"alpine_aports_commit":"e63efda2ffc3f7389eda3adbf5f569961d9b0d7a","alpine_image":"sha256:85fe1e81d6758c208f3e1eed4338a1997e19d4be002d4dd32d3100c9a8c010a0","architecture":"x86_64","source_date_epoch":1790981383,"source_inputs_sha256":"$source_inputs_sha","packages":{"busybox":{"version":"1.37.0-r31","apk_sha256":"$busybox_apk_sha"},"busybox-binsh":{"version":"1.37.0-r31","apk_sha256":"$busybox_binsh_apk_sha"},"ssl_client":{"version":"1.37.0-r31","apk_sha256":"$ssl_client_apk_sha"},"zlib":{"version":"1.3.2-r1","apk_sha256":"$zlib_apk_sha"}},"patches":{"CVE-2025-60876":["3c8c5b48f53ceb2641bb60c5c43b2a623e72246f2b7c0a87c1367136f455a936"],"CVE-2026-85091":["110ff14375733173d8aa54574473424fbd7dfe4b81f1ca34a759c6fe14b15b14","96040ee84d0d187905283912dbd3f7b66ac2033976a2ceefe9b8cca63143d9c2","6475806cdb6383788a03e7af5617188ef2692803889cded1fcb014825923d16c","a786b2b08412686008c7fe1247e90701cebde564037806bd9935f84907737cc4"]},"verified":true}
EOF
find /out -type f ! -name SHA256SUMS -exec sha256sum '{}' + | sort -k2 > /out/SHA256SUMS
(cd /out && sha256sum -c SHA256SUMS)
