@echo off
REM VEGA AI — Local Video/Image Generation Dependencies
REM For RTX 4060 8GB (CUDA 12.1)

cd /d "%~dp0.."

echo.
echo ============================================================
echo   VEGA AI — Local Video/Image Deps (GPU)
echo ============================================================
echo.
echo This installs torch (CUDA 12.1), diffusers, transformers,
echo accelerate, imageio, opencv, sentencepiece.
echo.
echo Download size: ~5 GB
echo.
pause

python -m pip install --upgrade pip
python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
python -m pip install diffusers>=0.31.0 transformers>=4.44.0 accelerate>=0.30.0 sentencepiece
python -m pip install imageio[ffmpeg] opencv-python

echo.
echo [OK] Local video/image stack installed.
echo You can now use Wan2, CogVideoX, LTX, AnimateDiff, Flux, SDXL Turbo.
echo.
pause
