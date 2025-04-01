#!/bin/bash

# Script to run Prover9 GUI with better Wayland compatibility

# Set environment variables for better GTK/Wayland compatibility
export GDK_BACKEND=x11
export GTK_CSD=0
export GTK_THEME=Adwaita:light
export GTK_ENABLE_ANIMATIONS=0
export QT_QPA_PLATFORM=xcb
export WLR_NO_HARDWARE_CURSORS=1

# Run the Prover9 GUI
echo "Starting Prover9 GUI with Wayland compatibility settings..."
python3 prover9-mace4.py
