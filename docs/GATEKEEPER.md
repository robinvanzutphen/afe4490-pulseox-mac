# The macOS "unidentified developer" warning (Gatekeeper)

This is the macOS equivalent of the Windows SmartScreen warning. It appears because
the app is not signed and notarized with a paid Apple Developer ID - not because
anything is wrong with it.

## What students see

On the first launch of a downloaded app, macOS shows one of:

- "AFE4490_PulseOx.app can't be opened because Apple cannot check it for malicious
  software", or
- "AFE4490_PulseOx.app cannot be opened because the developer cannot be verified."

## The one-time fix (simplest for students)

1. In Finder, **Control-click (or right-click) `AFE4490_PulseOx.app`**.
2. Choose **Open**.
3. In the dialog, click **Open** again.

Opening it this way records the student's consent, so every later launch is a normal
double-click. This is the method in `READ ME FIRST.txt`.

### Alternative: System Settings

Apple menu -> **System Settings** -> **Privacy & Security** -> scroll to the message
about the blocked app -> **Open Anyway**. (On macOS 15 Sequoia the Control-click
method is required first; the "Open Anyway" button appears afterwards.)

### Alternative: Terminal (for the instructor or a lab image)

Remove the download quarantine flag from the app, after which it opens normally:

```bash
xattr -dr com.apple.quarantine "/path/to/AFE4490_PulseOx.app"
```

This is handy when pre-loading lab Macs, so students never see the prompt.

## Why not just remove the warning?

The only way to stop the prompt entirely is Apple Developer ID **signing +
notarization**, which requires a paid Apple Developer account. If Amsterdam UMC can
provide one, sign during the build (see [BUILD_THE_APP.md](BUILD_THE_APP.md)) and
notarize the ZIP; a notarized app launches with no warning even when downloaded.

## Not the same as "wrong architecture"

If the app **bounces or reports it cannot run at all** (rather than showing the
security prompt above), the build probably does not match the Mac's processor -
Apple Silicon vs Intel. Use the matching build, or see
[BUILD_THE_APP.md](BUILD_THE_APP.md).
