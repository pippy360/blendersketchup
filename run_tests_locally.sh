#!/bin/bash
set -e

# Try to find Blender on Mac or fall back to BLENDER_BIN env variable
if [ -z "$BLENDER_BIN" ]; then
    if [ -f "/Applications/Blender.app/Contents/MacOS/Blender" ]; then
        BLENDER_BIN="/Applications/Blender.app/Contents/MacOS/Blender"
    else
        echo "Error: Could not find Blender automatically."
        echo "Please set the BLENDER_BIN environment variable to your Blender executable."
        echo "Example: export BLENDER_BIN=/Applications/Blender.app/Contents/MacOS/Blender"
        exit 1
    fi
fi

echo "Using Blender at: $BLENDER_BIN"

# Create a temporary directory for the zip build
BUILD_DIR=$(mktemp -d)
echo "Building addon zip in temporary directory..."

mkdir -p "$BUILD_DIR/blendersketchup"

# Copy all python files (the addon source) into the temporary folder
cp *.py "$BUILD_DIR/blendersketchup/" 2>/dev/null || true

# Zip the folder
cd "$BUILD_DIR"
zip -r blendersketchup.zip blendersketchup > /dev/null
cd - > /dev/null

# Set the environment variable that test_addon.py expects
export ADDON_ZIP_PATH="$BUILD_DIR/blendersketchup.zip"

echo ""
echo "=============================="
echo "      RUNNING TESTS           "
echo "=============================="
echo ""

# Run the test inside Headless Blender
"$BLENDER_BIN" --background --python tests/test_addon.py

# Clean up the temporary zip file
rm -rf "$BUILD_DIR"

echo ""
echo "=============================="
echo "    TESTS COMPLETED!          "
echo "=============================="
