#!/bin/bash
echo "Downloading FFmpeg static build for Vercel Serverless..."
curl -L -o ffmpeg.tar.xz https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz
tar -xJvf ffmpeg.tar.xz

# Find the extracted ffmpeg folder and move the binary to the root
FFMPEG_DIR=$(find . -maxdepth 1 -type d -name "ffmpeg-*-static")
mv $FFMPEG_DIR/ffmpeg ./ffmpeg
chmod +x ./ffmpeg

# Clean up
rm -rf ffmpeg.tar.xz $FFMPEG_DIR
echo "FFmpeg installed successfully."

# Install python requirements
pip install -r requirements.txt
