# OddsManager – Quick command reference

**Do this → to get that**

| To do this | Run this command |
|------------|------------------|
| Start the desktop app (development) | `cd desktop` then `cargo tauri dev` |
| Build the desktop app (release) | `cd desktop` then `cargo tauri build` |
| Run the built app | `cd desktop/src-tauri` then `cargo run --release` |
| Run Rust tests for the desktop app | `cd desktop/src-tauri` then `cargo test` |
| Check Rust compiles (no build) | `cd desktop/src-tauri` then `cargo check` |

Install Tauri CLI once (needed for `tauri dev` and `tauri build`):

```bash
cargo install tauri-cli --version "^2.0.0" --locked
```

More detail: see [DESKTOP_APP.md](DESKTOP_APP.md).
