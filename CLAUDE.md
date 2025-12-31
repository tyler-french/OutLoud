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

## Dependencies

- macOS: `brew install ffmpeg libsndfile`
- Linux: `apt install ffmpeg libsndfile1`

## Style

- No comments unless logic is non-obvious
- All imports at top of file (except heavy deps that should be lazy-loaded)
