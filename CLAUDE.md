# OutLoud

Text-to-speech web app using Kokoro TTS.

## Commands

```bash
bazel run //:app                  # Run server (localhost:5001)
bazel test //:e2e_test            # Run tests
bazel run //:requirements.update  # Update lock file
bazel run //:ruff -- check .      # Lint
bazel run //:ruff -- format .     # Format
```

- Do not wrap commands in `timeout`. Let me cancel if needed.
- Do not prefix commands with environment variables. If you need to set env vars, use `export` in a separate command or tell me to set them.
- Run bazel commands directly, e.g. `bazel test //:app` not `timeout 60 bazel test //:app`

## Dependencies

- macOS: `brew install ffmpeg libsndfile`
- Linux: `apt install ffmpeg libsndfile1`

## Style

- No comments unless logic is non-obvious
- All imports at top of file (except heavy deps that should be lazy-loaded)
