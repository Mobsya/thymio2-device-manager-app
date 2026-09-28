#!/bin/bash
# Only called by tagged CI builds. Never enable shell tracing in this script.
set -euo pipefail

: "${RUNNER_TEMP:?Run this on a GitHub Actions runner}"
: "${MACOS_CERTIFICATE_P12:?Set the base64 Developer ID Application certificate secret}"
: "${MACOS_CERTIFICATE_PASSWORD:?Set the certificate password secret}"
: "${MACOS_SIGN_IDENTITY:?Set the Developer ID Application identity repository variable}"
: "${APPLE_API_KEY_P8:?Set the App Store Connect private key secret}"
: "${APPLE_API_KEY_ID:?Set the App Store Connect key ID secret}"

signing_dir="$RUNNER_TEMP/tdm-signing"
umask 077
mkdir -p "$signing_dir"
printf '%s' "$MACOS_CERTIFICATE_P12" | base64 --decode > "$signing_dir/certificate.p12"
printf '%s' "$APPLE_API_KEY_P8" > "$signing_dir/notary.p8"
keychain="$signing_dir/signing.keychain-db"
keychain_password=$(openssl rand -hex 24)
echo "::add-mask::$keychain_password"
security create-keychain -p "$keychain_password" "$keychain"
security set-keychain-settings -lut 21600 "$keychain"
security unlock-keychain -p "$keychain_password" "$keychain"
security import "$signing_dir/certificate.p12" -k "$keychain" -P "$MACOS_CERTIFICATE_PASSWORD" -T /usr/bin/codesign -T /usr/bin/security > /dev/null
security set-key-partition-list -S apple-tool:,apple:,codesign: -k "$keychain_password" "$keychain" > /dev/null
security list-keychains -d user -s "$keychain" "$HOME/Library/Keychains/login.keychain-db"
notary_args=(--key "$signing_dir/notary.p8" --key-id "$APPLE_API_KEY_ID")
# Team keys require an issuer; individual keys must omit it.
if [[ -n "${APPLE_API_ISSUER_ID:-}" ]]; then
    notary_args+=(--issuer "$APPLE_API_ISSUER_ID")
fi
xcrun notarytool store-credentials tdm-ci --keychain "$keychain" "${notary_args[@]}"
