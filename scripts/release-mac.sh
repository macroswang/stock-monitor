#!/bin/sh
# Run after package_core.py and tauri build --bundles app.
set -eu
cd "$(dirname "$0")/.."
version=$(node -p "require('./package.json').version")
output="$PWD/releases/production-$version-mac-arm64"
stage="$PWD/build/production-dmg"
mkdir -p "$output"
rm -rf "$stage"
mkdir -p "$stage"
ditto src-tauri/target/release/bundle/macos/观量.app "$stage/观量.app"
# Local distribution signature only; never select an unrelated account certificate.
codesign --force --sign - "$stage/观量.app/Contents/MacOS/monitor-core"
codesign --force --sign - "$stage/观量.app"
codesign --verify --deep --strict --verbose=2 "$stage/观量.app"
ln -s /Applications "$stage/Applications"
sed "s/0.4.0/$version/g" docs/production-0.4.0/安装说明.txt > "$stage/安装说明.txt"
cp "$stage/安装说明.txt" "$output/安装说明.txt"
cp scripts/install-upgrade-mac.command "$stage/安装或升级观量.command"
chmod +x "$stage/安装或升级观量.command"
hdiutil create -volname "观量 $version" -srcfolder "$stage" -ov -format UDZO "$output/StockMonitor-$version-mac-arm64.dmg"
ditto -c -k --sequesterRsrc --keepParent "$stage/观量.app" "$output/StockMonitor-$version-mac-arm64.zip"
(cd "$output" && shasum -a 256 ./*.dmg ./*.zip > SHA256SUMS.txt)
echo "$output"
