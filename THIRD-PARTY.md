# Third-party components

This repository contains only the interpreter source code. It does not bundle
model weights, engine binaries, or audio samples.

| Component | Role | License | Distribution |
|---|---|---|---|
| [piper-tts](https://github.com/OHF-Voice/piper1-gpl) | Spanish TTS | GPL-3.0-or-later | Installed by `scripts/install-piper.sh`; not bundled |
| [Piper voice `es_ES-davefx-medium`](https://huggingface.co/rhasspy/piper-voices) | Spanish voice | CC0 (per upstream voice card) | Downloaded by the install script; not bundled |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | Speech-to-text runtime | MIT | Python dependency |
| [Whisper large-v3-turbo](https://huggingface.co/mobiuslabsgmbh/faster-whisper-large-v3-turbo) | STT model | MIT (model card) | Downloaded/cached by the user; not bundled |
| [Silero VAD](https://github.com/snakers4/silero-vad) | Voice activity detection | MIT | ONNX model used locally; not bundled |
| [VOICEVOX Engine](https://github.com/VOICEVOX/voicevox_engine) | Japanese TTS | LGPL-3.0 | Installed separately; not bundled |
| VOICEVOX voice styles | Japanese voices | Per voice/model terms | Downloaded with the engine; not bundled |
| [GTK 4](https://www.gtk.org/) / [libadwaita](https://gnome.pages.gitlab.gnome.org/libadwaita/) | Desktop UI | LGPL-2.1-or-later | System libraries |
| [FFmpeg](https://ffmpeg.org/) | Audio conversion | LGPL/GPL depending on build | External binary in `PATH`; not bundled |
| Python dependencies | Runtime | See each package metadata | Installed from PyPI |

## GPL note

`piper-tts` is licensed under GPL-3.0-or-later and is imported directly by
`src/interprete/tts/piper.py`. For that reason this repository is distributed
under GPL-3.0-or-later, not MIT. If you replace Piper with a permissively
licensed TTS, the project license can be revisited.

## Not legal advice

This file is an engineering inventory, not a legal opinion. Review the upstream
licenses and voice-model terms before redistributing binaries, models, or
synthesized audio.
