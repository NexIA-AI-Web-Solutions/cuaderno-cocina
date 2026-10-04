#!/bin/sh
set -eu

# The vulnerable stock wget opens a connection for a CRLF-bearing URL.
rm -f /tmp/stock-connected
(printf 'HTTP/1.0 400 Bad Request\r\nContent-Length: 0\r\n\r\n' | busybox nc -l -p 18081; touch /tmp/stock-connected) & stock_nc=$!
busybox wget -T 2 -O /dev/null "http://127.0.0.1:18081/$(printf '\r\nX-Injected: yes')" 2>/tmp/stock-wget || true
for i in 1 2 3 4 5; do [ -e /tmp/stock-connected ] && break; sleep 1; done
kill "$stock_nc" 2>/dev/null || true
test -e /tmp/stock-connected

apk add --no-network --allow-untrusted /security-apks/packages/*/*/zlib-1.3.2-r1.apk
apk add --no-network --allow-untrusted /security-apks/packages/*/*/busybox-1.37.0-r31.apk \
  /security-apks/packages/*/*/busybox-binsh-1.37.0-r31.apk \
  /security-apks/packages/*/*/ssl_client-1.37.0-r31.apk
apk info -e 'zlib=1.3.2-r1'
apk info -e 'busybox=1.37.0-r31'
apk info -e 'busybox-binsh=1.37.0-r31'
apk info -e 'ssl_client=1.37.0-r31'

# The package retains precisely the Alpine applet selection.
busybox --list | LC_ALL=C sort > /tmp/patched-applets
diff -u /reference-applets /tmp/patched-applets

# Each prohibited URL dies during parsing, before DNS or socket handling.
rm -f /tmp/patched-connected
(printf 'HTTP/1.0 400 Bad Request\r\nContent-Length: 0\r\n\r\n' | busybox nc -l -p 18082; touch /tmp/patched-connected) & reject_nc=$!
for suffix in ' bad' "$(printf '\tbad')" "$(printf '\rbad')" "$(printf '\nbad')"; do
  if busybox wget -T 1 -O /dev/null "http://127.0.0.1:18082/$suffix" 2>/tmp/reject; then exit 1; fi
  grep -q 'Unencoded control character' /tmp/reject
done
sleep 1
kill "$reject_nc" 2>/dev/null || true
test ! -e /tmp/patched-connected

# Ordinary loopback HTTP remains functional.
(printf 'HTTP/1.0 200 OK\r\nContent-Length: 2\r\n\r\nok' | busybox nc -l -p 18080) & pid=$!
trap 'kill "$pid" 2>/dev/null || true' EXIT
for i in 1 2 3 4 5; do busybox wget -q -O /tmp/got http://127.0.0.1:18080/ && break; sleep 1; done
test "$(cat /tmp/got)" = ok

# Bind the installed runtime bytes, rather than relying on local version labels.
for path in /bin/busybox /usr/bin/ssl_client /usr/lib/libz.so.1.3.2; do
  [ -f "$path" ] && [ ! -L "$path" ]
done
busybox_runtime_sha=$(sha256sum /bin/busybox | cut -d' ' -f1)
ssl_client_runtime_sha=$(sha256sum /usr/bin/ssl_client | cut -d' ' -f1)
zlib_runtime_sha=$(sha256sum /usr/lib/libz.so.1.3.2 | cut -d' ' -f1)
record=/security-apks/SECURITY.alpine-backports.json
sed '$ s/}$/,"runtime_files":{"\/bin\/busybox":"'"$busybox_runtime_sha"'","\/usr\/bin\/ssl_client":"'"$ssl_client_runtime_sha"'","\/usr\/lib\/libz.so.1.3.2":"'"$zlib_runtime_sha"'"}}/' "$record" >"$record.tmp"
mv "$record.tmp" "$record"
(cd /security-apks && find . -type f ! -name SHA256SUMS -exec sha256sum '{}' + | sort -k2) >/tmp/SHA256SUMS
mv /tmp/SHA256SUMS /security-apks/SHA256SUMS
(cd /security-apks && sha256sum -c SHA256SUMS)
