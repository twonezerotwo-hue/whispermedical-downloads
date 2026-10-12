# WhisperMedical

**Offline medical lecture transcription & study.** Record a lecture, drop the file in, get an accurate transcript with medical terms checked in context,
plus a summary, key concepts, flashcards and questions. Everything runs on your own computer.

## Download

Open the download page and click the button for your computer:

**https://twonezerotwo-hue.github.io/whispermedical-downloads/**

| | |
|---|---|
| **Windows** | Windows 10/11, 64-bit. Download `WhisperMedical-Installer-Windows.exe` and double-click it. |
| **Intel Mac** | macOS 12 or newer, **Intel** processor (2019 and similar). Not for Apple Silicon (M1/M2/M3). Download `WhisperMedical-Installer-IntelMac.zip`, open the app inside. |

The small installer downloads the program and checks every file automatically (about 3.6 GB on Windows, about 3 GB on Mac). You do not need a GitHub account,
Python, Homebrew, FFmpeg or any other tool. If your connection drops, run the installer again and it continues where it stopped.

## Offline AI

- **Whisper Large-v3** (speech recognition) is installed together with the program. Nothing is downloaded the first time you start it.
- Medical terminology correction, PDF reading and text recognition (OCR) work without internet.
- Transcription never needs a cloud service. Optional cloud AI providers for the study material exist in Settings; they are off unless you add a key.

## System requirements

- Windows 10/11 x64 (an NVIDIA GPU speeds things up; it also works on the CPU) &nbsp;·&nbsp; or macOS 12+ on an Intel Mac (works on the CPU).
- 8 GB RAM or more recommended; about 8 GB free disk space during installation.

## First launch on Mac

The Mac app is not yet notarized by Apple, so macOS asks for confirmation the first time:
**right-click the app → Open → Open.** Please do not disable Gatekeeper system-wide. Details: [Intel Mac help](downloads/install-mac-intel.html).
Windows may show a "Windows protected your PC" screen for the same reason (**More info → Run anyway**). Details: [Windows help](downloads/install-windows.html).

## Uninstall

- **Windows:** Settings → Apps → WhisperMedical (Medical Lecture Transcriber) → Uninstall. Your transcripts and downloaded models are kept.
- **Mac:** drag *Medical Lecture Transcriber.app* from Applications to the Trash.

## Privacy

Audio, video, PDFs and transcripts stay on your computer. The installer only contacts the official download location of this project to fetch the program.

## Licenses

See [licenses/THIRD_PARTY_LICENSES.txt](licenses/THIRD_PARTY_LICENSES.txt) and [licenses/MODEL_LICENSES.txt](licenses/MODEL_LICENSES.txt).
Questions or source-code requests for the open-source components: open an [issue](../../issues).
