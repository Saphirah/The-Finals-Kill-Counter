# Screenshot Monitor with OCR

A Python program that continuously monitors your screen by comparing screenshots with a reference image. When a match is detected (similarity above threshold), it performs OCR text extraction and logs the results.

## Features

- 📸 Takes screenshots every second
- 🔍 Compares screenshots with a predefined reference image
- 📊 Uses Structural Similarity Index (SSIM) for accurate comparison
- 🔤 Performs OCR text detection using Tesseract when match is found
- ⏸️ Automatic 5-minute timeout after detection
- 📝 Saves detection logs with timestamps

## Prerequisites

### 1. Install Tesseract OCR

**Windows:**

1. Download from: https://github.com/UB-Mannheim/tesseract/wiki
2. Run the installer (tesseract-ocr-w64-setup-v5.3.3.exe or later)
3. During installation, note the installation path (default: `C:\Program Files\Tesseract-OCR`)
4. Add Tesseract to your PATH, or update the path in the script:
   ```python
   pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
   ```

**Linux:**

```bash
sudo apt-get install tesseract-ocr
```

**macOS:**

```bash
brew install tesseract
```

### 2. Python Dependencies

Activate your virtual environment and install requirements:

```powershell
.venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

### Step 1: Prepare Your Reference Image

Take a screenshot of the screen state you want to detect and save it (e.g., `reference.png`).

### Step 2: Run the Monitor

```powershell
python screenshot_monitor.py <reference_image_path> [similarity_threshold]
```

**Arguments:**

- `reference_image_path`: Path to your reference screenshot (required)
- `similarity_threshold`: Number between 0-1 (optional, default: 0.95)
  - 1.0 = exact match only
  - 0.95 = very similar (recommended)
  - 0.8 = moderately similar

**Examples:**

```powershell
# Using default threshold (0.95)
python screenshot_monitor.py reference.png

# Custom threshold
python screenshot_monitor.py reference.png 0.9

# With full path
python screenshot_monitor.py "C:\Images\target_screen.png" 0.95
```

### Step 3: Monitor Output

The program will display:

- Current time and similarity score every second
- "MATCH DETECTED!" when threshold is exceeded
- Extracted text from the screen
- Log file location

### Step 4: Stop Monitoring

Press `Ctrl+C` to stop the program.

## Output

### Console Output

```
[14:30:15] Similarity: 0.7234
[14:30:16] Similarity: 0.8891
[14:30:17] Similarity: 0.9521 ✓ MATCH DETECTED!
Performing OCR text detection...

--- Extracted Text (245 characters) ---
[Detected text appears here]
```

### Log Files

Detection logs are saved in the `detection_logs/` folder:

```
detection_logs/
├── detection_2026-03-11_14-30-17.txt
├── detection_2026-03-11_15-45-23.txt
└── ...
```

Each log contains:

- Detection timestamp
- Similarity score
- Full extracted text

## Configuration

### Adjust Similarity Threshold

Lower threshold = more sensitive (may trigger false positives)
Higher threshold = less sensitive (may miss variations)

```powershell
# Very strict matching
python screenshot_monitor.py reference.png 0.98

# More lenient matching
python screenshot_monitor.py reference.png 0.85
```

### Modify Tesseract Path

If Tesseract is not in your PATH, edit `screenshot_monitor.py`:

```python
# Uncomment and update this line (around line 28)
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
```

### Change Timeout Duration

Edit line 119 in `screenshot_monitor.py`:

```python
time.sleep(300)  # Change 300 to desired seconds
```

## Troubleshooting

### "Tesseract not found"

- Verify Tesseract is installed: Run `tesseract --version` in terminal
- Add Tesseract to PATH or set path in script

### "Reference image not found"

- Check file path is correct
- Use absolute path or ensure file is in same directory

### OCR not detecting text

- Ensure text is clear and readable in screenshot
- Try preprocessing images for better OCR results
- Install additional Tesseract language packs if needed

### High CPU usage

- Normal behavior due to continuous screenshot capture
- Increase sleep interval if needed (edit line 155)

## Technical Details

- **Image Comparison**: Uses Structural Similarity Index (SSIM)
- **OCR Engine**: Tesseract OCR 5.x
- **Screenshot**: PIL ImageGrab (cross-platform)
- **Image Processing**: OpenCV and scikit-image

## License

Free to use and modify for your projects.
